import time

from app.store import Round, RoundStore


def _store() -> RoundStore:
    s = RoundStore("agent_test")
    now = int(time.time())
    s.rounds["alt"] = Round("alt", now - 7200, status="fertig", frage_nr="92", loesung="Rammstein", region="Pfalz")
    s.rounds["neu"] = Round("neu", now - 60, status="fertig", frage_nr="110", loesung="Nature One", region="Hunsrück")
    return s


def test_ohne_grenze_zaehlen_alle_runden():
    s = _store()
    s.history_from = 0
    assert sorted(s.recent_numbers()) == [92, 110]


def test_grenze_blendet_proberunden_aus():
    s = _store()
    s.history_from = int(time.time()) - 600
    assert s.recent_numbers() == [110]
    assert s.recent_solutions() == ["Nature One"]
    assert s.region_history() == ["Hunsrück"]


def test_standardgrenze_vergisst_proberunden(monkeypatch):
    monkeypatch.delenv("HISTORY_FROM", raising=False)
    s = RoundStore("a")
    assert s.history_from == 1793273400
    s.rounds["probe"] = Round("probe", 1793269087, status="fertig", frage_nr="92")
    s.rounds["echt"] = Round("echt", 1793273500, status="fertig", frage_nr="110")
    assert s.recent_numbers() == [110]


def test_null_schaltet_grenze_ab(monkeypatch):
    monkeypatch.setenv("HISTORY_FROM", "0")
    assert RoundStore("a").history_from == 0


def test_env_grenze(monkeypatch):
    monkeypatch.setenv("HISTORY_FROM", "2026-10-29T11:00:00+01:00")
    assert RoundStore("a").history_from == 1793268000
    monkeypatch.setenv("HISTORY_FROM", "kaputt")
    assert RoundStore("a").history_from == 0
