# Vendored conformance vectors — `copthief-league-protocol`

Test **data** only, no third-party code. Copied verbatim from
<https://github.com/Imreec/copthief-league-protocol> at commit
`ad6557626587e09146af4283a5e808e7001343c5`, MIT licensed (see `LICENSE`) —
Team ImreEyal (Imree Cohen, Eyal Shtinmetz) with Team anrbj666 (Alon Engel,
Renat Karimov).

`tests/unit/test_kit_conformance.py` runs **our** implementation against these
files. That direction is the point: a kit that only verifies itself proves
nothing about us, and the failure mode the kit exists to catch — two honest
peers whose serializers disagree, each concluding the other cheated, both
scored 0 — is invisible until a real match.

Refreshing them is deliberate, not automatic. Re-copy from a named upstream
commit, record it above, and let the test say what moved: a vector that
changes under us is either an upstream correction we must adopt or a
divergence we must negotiate, and either way a human decides which.

| file | kit status | what it pins |
|---|---|---|
| `canonical_json.json` | CORE | the one canonical form every hash uses, including non-ASCII and float round-trip |
| `commit_reveal.json` | CORE | `sha256(canonical(payload)\|nonce)` — the per-step seal the opponent re-hashes |
| `game_uid.json` | CORE | deterministic `game_id` / `game_uid`, both sorted so peer order cannot matter |
| `terms_signature.json` | CORE | the pre-game agreement gate over the 14 negotiated terms |
| `report_consensus.json` | CORE | the settlement digest — the *second*, spaced-separator encoding |
| `pheromone.json` | CORE | `subtractive_chebyshev_v1`, the reference implementation's scent physics |
| `scent_book_v3.json` | PROMOTED | `multiplicative_book_v1` — the book's ch. 4 model, which is ours |
