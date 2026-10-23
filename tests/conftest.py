import pytest


@pytest.fixture(autouse=True)
def _alle_stufen(monkeypatch):
    # Die Basis-Tests prüfen Auswahl und Rotation über den ganzen (kleinen) Testpool.
    monkeypatch.setenv("FRAGEN_STUFE", "3")
