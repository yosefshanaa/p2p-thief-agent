"""Two-repo sync script (scripts/sync_repos.py) - book §9.4 / PLAN ADR-2.

The script lives outside the package (meta-tooling, not agent runtime), so
the tests import it straight from scripts/.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import sync_repos  # noqa: E402

README = (
    "# p2p-pursuit — title\n"
    "\n"
    "Intro paragraph.\n"
    "**Sister repositories** (submission split, book rule #49): police repo "
    "https://example.com/p2p-police-agent · thief repo "
    "https://example.com/p2p-thief-agent — both built from this codebase.\n"
)
URLS = {
    "police": "https://example.com/p2p-police-agent",
    "thief": "https://example.com/p2p-thief-agent",
    "workspace_name": "final_Project",
    "workspace": "https://example.com/final_Project",
}


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, text=True,
                          capture_output=True).stdout


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    _git(ws, "init", "-q")
    _git(ws, "config", "user.email", "t@t")
    _git(ws, "config", "user.name", "t")
    (ws / "README.md").write_text(README, encoding="utf-8")
    (ws / "src").mkdir()
    (ws / "src" / "a.py").write_text("A = 1\n", encoding="utf-8")
    (ws / ".gitignore").write_text("token.json\n", encoding="utf-8")
    (ws / "token.json").write_text("SECRET", encoding="utf-8")  # ignored
    _git(ws, "add", "README.md", "src/a.py", ".gitignore")
    _git(ws, "commit", "-qm", "init")
    (ws / "untracked.tmp").write_text("scratch", encoding="utf-8")
    return ws


def test_tracked_files_excludes_secrets_and_untracked(workspace: Path) -> None:
    files = sync_repos.tracked_files(workspace)
    assert "src/a.py" in files and "README.md" in files
    assert "token.json" not in files and "untracked.tmp" not in files


def test_transform_readme_inserts_role_banner_idempotently() -> None:
    once = sync_repos.transform_readme(README, "police", URLS)
    assert "POLICE" in once.splitlines()[2]  # banner right under the H1
    assert URLS["thief"] in once  # sister cross-link (mandatory README item #6)
    twice = sync_repos.transform_readme(once, "police", URLS)
    assert twice == once


def test_banner_names_the_development_repo_it_was_published_from() -> None:
    """A reader landing on a role repo has to be able to find the codebase it
    came from: the split repos carry no history of their own worth reading,
    only one `sync:` commit per workspace commit."""
    banner = sync_repos.transform_readme(README, "thief", URLS)
    assert URLS["workspace"] in banner
    assert "final_Project" in banner
    # and it survives a re-sync, since sync_one always re-transforms a pristine
    # workspace README rather than the published one
    assert sync_repos.transform_readme(README, "police", URLS).count(
        URLS["workspace"]) == 1


def test_sync_one_copies_tree_writes_role_and_prunes_stale(workspace: Path) -> None:
    target = workspace.parent / "p2p-thief-agent"
    target.mkdir()
    _git(target, "init", "-q")
    (target / "stale.py").write_text("OLD", encoding="utf-8")
    sync_repos.sync_one(workspace, target, "thief", URLS)
    assert (target / "src" / "a.py").read_text(encoding="utf-8") == "A = 1\n"
    assert (target / "ROLE").read_text(encoding="utf-8").strip() == "thief"
    assert "THIEF" in (target / "README.md").read_text(encoding="utf-8")
    assert not (target / "stale.py").exists()  # pruned
    assert not (target / "token.json").exists()  # secrets never copied
    assert (target / ".git").is_dir()  # target history preserved


def test_secrets_history_check_passes_on_clean_repo(workspace: Path) -> None:
    assert sync_repos.secrets_history_clean(workspace)


def test_repo_default_role_reads_marker(tmp_path: Path) -> None:
    from p2p_pursuit.shared.role_marker import repo_default_role

    assert repo_default_role(tmp_path) is None
    (tmp_path / "ROLE").write_text("police\n", encoding="utf-8")
    assert repo_default_role(tmp_path) == "police"
    (tmp_path / "ROLE").write_text("junk\n", encoding="utf-8")
    assert repo_default_role(tmp_path) is None


def test_ollama_base_url_is_configurable_not_hardcoded(tmp_path: Path) -> None:
    """The Ollama endpoint must come from config: under WSL a Windows-side
    Ollama is not on localhost (guardrail: tunables in config/)."""
    from p2p_pursuit.shared.config import load_peer
    from p2p_pursuit.strategy.talk_llm import make_talk_provider

    toml = tmp_path / "game.toml"
    toml.write_text('[llm]\nbase_url = "http://10.255.255.254:11434"\n', encoding="utf-8")
    assert load_peer(toml).llm_base_url == "http://10.255.255.254:11434"

    provider = make_talk_provider("ollama", "llama3.2", 30, "http://host:11434")
    assert provider.url == "http://host:11434/api/generate"
    assert make_talk_provider("ollama", "", 30, "").url.startswith("http://localhost:11434")
