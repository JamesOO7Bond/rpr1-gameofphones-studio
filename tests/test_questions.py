import random
from pathlib import Path

from app.questions import QuestionPool, parse_pool

FIX = Path(__file__).parent / "fixtures"


def _pool():
    texts = [(FIX / n).read_text(encoding="utf-8") for n in ("grundpool.txt", "kategorien.txt", "regionen.txt")]
    p = QuestionPool()
    p.questions = parse_pool(texts)
    return p


def test_parse_categories_and_regions():
    p = _pool()
    q = p.questions
    assert 16 in q and "sport" in q[16].categories and "Pfalz" in q[16].regions
    assert 109 in q and "musik" in q[109].categories and "Eifel" in q[109].regions
    assert q[154].antwort == "Allemol" and "heimat" in q[154].categories and q[154].regions == {"Westerwald"}
    assert "Nahe" in q[145].regions and "Land allgemein" in q[145].regions
    assert q[47].blocked and q[123].blocked and q[178].blocked
    assert "Tabu: Fritz, Walter" in q[16].as_line()


def test_pick_round_gives_one_per_category_and_avoids_recent():
    p = _pool()
    picks = p.pick_round([115, 109], ["Luchs"], ["Pfalz"], rng=random.Random(1))
    assert set(picks) == {"musik", "heimat", "natur", "promis", "essen", "sport"}
    assert all(not q.blocked for q in picks.values())
    assert picks["natur"].nr != 115 and picks["musik"].nr != 109
    assert len({q.nr for q in picks.values()}) == 6


def test_rotation_spreads_regions():
    p = _pool()
    nums, sols, regs = [], [], []
    seen_regions = set()
    rng = random.Random(7)
    for _ in range(15):
        picks = p.pick_round(nums, sols, regs, rng=rng)
        cat = rng.choice(list(picks))
        q = picks[cat]
        nums.insert(0, q.nr)
        sols.insert(0, q.antwort)
        reg = sorted(q.regions)[0]
        regs.insert(0, reg)
        seen_regions |= q.regions
    assert len(set(nums)) == len(nums)  # keine Wiederholung in 15 Runden (Testpool ist klein)
    assert len(seen_regions) >= 6


def test_heimat_and_natur_lists_with_parentheses_are_parsed():
    p = _pool()
    q = p.questions
    # Zeile „HEIMAT (Städte, …): 8, 10, …“ und „NATUR (…): 3, …, 115“
    assert "natur" in q[115].categories
    assert "heimat" in q[154].categories


def test_level_filter(monkeypatch):
    p = _pool()
    monkeypatch.setenv("FRAGEN_STUFE", "1")
    picks = p.pick_round([], [], [], rng=random.Random(3))
    from app.questions import LEVELS
    assert all(LEVELS.get(q.nr) == "1" for q in picks.values())
    from app.questions import Question
    x = Question(nr=24, frage="f", antwort="a", categories={"heimat"})
    assert x.blocked  # X
    monkeypatch.setenv("FRAGEN_STUFE", "3")
    assert x.blocked  # X bleibt raus
    assert not Question(nr=154, frage="f", antwort="a").blocked
