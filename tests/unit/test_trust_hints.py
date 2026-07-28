"""Trust dynamics + hint parsing, including the book's canonical lie scenario."""

from p2p_pursuit.domain.hints import clip_words, parse_hint, region_cells, region_of
from p2p_pursuit.domain.scent import ScentField
from p2p_pursuit.domain.trust import CONTRADICTED, CORROBORATED, NEUTRAL, TrustModel


def test_trust_transitions():
    t = TrustModel()
    assert t.judge(region_scent_mass=0.05, max_tau=0.81) == CONTRADICTED
    assert t.value == 0.25
    assert t.judge(region_scent_mass=0.9, max_tau=0.81) == CORROBORATED
    assert t.value == 0.35
    assert t.judge(region_scent_mass=0.3, max_tau=0.81) == NEUTRAL
    assert t.judge(region_scent_mass=0.0, max_tau=0.1) == NEUTRAL  # faint trail: no verdict


def test_trust_floor():
    t = TrustModel(value=0.06)
    t.judge(0.0, 0.9)
    assert t.value == 0.05


def test_book_lie_scenario_moved_north_scent_southeast():
    """Ch. 4.4: thief claims 'moved north' while all scent mass sits south-east."""
    field = ScentField(7)
    field.emit((5, 5))
    field.decay()  # fresh SE trail (0.81), zero in the north
    scent = field.snapshot()
    region = parse_hint("I moved north, you will never catch me", 7, "")
    assert region == region_cells("north", 7)
    mass = sum(scent[r][c] for r, c in region) / max(sum(map(sum, scent)), 1e-9)
    t = TrustModel()
    assert t.judge(mass, 0.81) == CONTRADICTED
    assert t.value < 0.5  # the liar burned its credibility


def test_region_cells_and_region_of():
    cells = region_cells("northwest", 9)
    assert (0, 0) in cells and (8, 8) not in cells
    assert region_of((0, 0), 9) == "northwest"
    assert region_of((4, 4), 9) == "center"
    assert region_of((8, 4), 9) == "south"


def test_parse_landmarks_and_garbage():
    assert parse_hint("hiding near Times Square tonight", 7, "New York") == \
        region_cells("center", 7)
    assert parse_hint("slipping past the north gate", 7, "") == region_cells("north", 7)
    assert parse_hint("blorp glorp nonsense 12345", 7, "New York") is None


def test_clip_words_enforces_cap():
    text = " ".join(str(i) for i in range(30))
    assert len(clip_words(text, 15).split()) == 15
