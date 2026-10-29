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


def test_reset_vergisst_alles_bisherige():
    s = _store()
    s.reset_history()
    assert s.recent_numbers() == []
    assert s.recent_solutions() == []
    assert s.region_history() == []


def test_env_grenze(monkeypatch):
    monkeypatch.setenv("HISTORY_FROM", "2026-10-29T11:00:00+01:00")
    assert RoundStore("a").history_from == 1793268000
    monkeypatch.setenv("HISTORY_FROM", "kaputt")
    assert RoundStore("a").history_from == 0
