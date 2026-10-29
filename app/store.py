"""Rundenspeicher.

Die Wahrheit liegt bei ElevenLabs: Jedes Gespräch trägt nach dem Ende die
Datenerfassung (Region, Lösung, Ergebnis …). Der Server hält davon nur einen
Zwischenspeicher im Arbeitsspeicher und baut ihn beim Start aus der
Gesprächsliste wieder auf. So braucht der Dienst keinen Datenträger und
übersteht jeden Neustart.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from . import elevenlabs
from .regions import normalize_region

log = logging.getLogger("gop.store")

DATA_FIELDS = ("kandidat_name", "kandidat_ort", "kategorie", "region", "loesung", "ergebnis", "frage_nr")


@dataclass
class Round:
    conversation_id: str
    start_time: int  # Unix-Sekunden
    status: str = "offen"  # offen | fertig | ohne_analyse
    duration: int = 0
    planned_region: str | None = None
    kandidat_name: str | None = None
    kandidat_ort: str | None = None
    kategorie: str | None = None
    region: str | None = None
    loesung: str | None = None
    ergebnis: str | None = None
    frage_nr: str | None = None
    planned_numbers: list = field(default_factory=list)
    summary: str | None = None
    extra: dict = field(default_factory=dict)

    def to_public(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("extra", None)
        d["start_iso"] = datetime.fromtimestamp(self.start_time, tz=timezone.utc).isoformat()
        return d


# Proberunden bis 29.10.2026 12:30 Uhr zählen nicht als „schon gespielt“ (Wunsch Holger/Armin).
DEFAULT_HISTORY_FROM = "2026-10-29T12:30:00+01:00"


def _env_history_from() -> int:
    """Rundenhistorie erst ab diesem Zeitpunkt zählen (HISTORY_FROM, ISO-Datum oder Unix-Sekunden).
    Ohne Angabe gilt DEFAULT_HISTORY_FROM; „0“ schaltet die Grenze ab."""
    raw = os.environ.get("HISTORY_FROM", "").strip() or DEFAULT_HISTORY_FROM
    if raw.isdigit():
        return int(raw)
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        log.warning("HISTORY_FROM nicht lesbar: %r", raw)
        return 0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _field(results: dict, name: str) -> str | None:
    item = results.get(name)
    if isinstance(item, dict):
        value = item.get("value")
    else:
        value = item
    if value is None:
        return None
    value = str(value).strip()
    if not value or value.lower() in {"unbekannt", "none", "null", "n/a", "-"}:
        return None
    return value


class RoundStore:
    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id
        self.rounds: dict[str, Round] = {}
        self.last_refresh = 0.0
        self.history_from = _env_history_from()
        self._lock = asyncio.Lock()

    # ----- Lesen -------------------------------------------------------
    def ordered(self) -> list[Round]:
        return sorted(self.rounds.values(), key=lambda r: r.start_time, reverse=True)

    def history(self) -> list[Round]:
        """Runden, die für die Auswahl zählen (neueste zuerst). Ältere Proberunden bleiben außen vor."""
        return [r for r in self.ordered() if r.start_time >= self.history_from]

    def region_history(self) -> list[str]:
        """Gespielte Regionen, neueste zuerst. Geplante Region als Rückfall."""
        out: list[str] = []
        for r in self.history():
            if r.status == "ohne_analyse" and not r.region:
                continue
            name = r.region or r.planned_region
            if name:
                out.append(name)
        return out

    def recent_numbers(self) -> list[int]:
        """Gespielte Fragennummern, neueste zuerst; ohne Auswertung zählen alle sechs vorgeschlagenen."""
        out: list[int] = []
        for r in self.history():
            if r.frage_nr and str(r.frage_nr).strip().isdigit():
                out.append(int(str(r.frage_nr).strip()))
            elif r.status != "fertig":
                out.extend(r.planned_numbers)
        return out

    def recent_solutions(self, limit: int = 40) -> list[str]:
        out: list[str] = []
        for r in self.history():
            if r.loesung and r.loesung not in out:
                out.append(r.loesung)
            if len(out) >= limit:
                break
        return out

    # ----- Schreiben ---------------------------------------------------
    def register(self, conversation_id: str, planned_numbers: list[int], name: str, ort: str) -> Round:
        rnd = Round(
            conversation_id=conversation_id,
            start_time=int(time.time()),
            planned_numbers=list(planned_numbers),
            kandidat_name=name or None,
            kandidat_ort=ort or None,
        )
        self.rounds[conversation_id] = rnd
        return rnd

    def _apply_details(self, rnd: Round, data: dict[str, Any]) -> bool:
        """Überträgt Gesprächsdetails. Gibt True zurück, wenn die Analyse da war."""
        meta = data.get("metadata") or {}
        rnd.start_time = int(meta.get("start_time_unix_secs") or rnd.start_time)
        rnd.duration = int(meta.get("call_duration_secs") or 0)
        analysis = data.get("analysis") or {}
        results = analysis.get("data_collection_results") or {}
        status = data.get("status")
        if status not in ("done", "failed") and not results:
            rnd.status = "offen"
            return False
        if not results and not analysis.get("transcript_summary"):
            rnd.status = "ohne_analyse"
            return False
        for name in DATA_FIELDS:
            value = _field(results, name)
            if value:
                setattr(rnd, name, value)
        rnd.region = normalize_region(rnd.region) or rnd.region
        rnd.summary = analysis.get("transcript_summary")
        rnd.status = "fertig"
        return True

    async def sync(self, conversation_id: str, attempts: int = 8, delay: float = 5.0) -> Round:
        """Holt die Details einer Runde; wartet, bis die Analyse da ist."""
        rnd = self.rounds.get(conversation_id) or Round(conversation_id=conversation_id, start_time=int(time.time()))
        self.rounds[conversation_id] = rnd
        for i in range(attempts):
            try:
                data = await elevenlabs.get_conversation(conversation_id)
            except elevenlabs.ElevenLabsError as exc:
                log.warning("Details %s: %s", conversation_id, exc)
                data = {}
            if data and self._apply_details(rnd, data):
                return rnd
            if i < attempts - 1:
                await asyncio.sleep(delay)
        return rnd

    async def refresh(self, force: bool = False, max_age: float = 300.0) -> None:
        """Baut den Speicher aus der ElevenLabs-Gesprächsliste auf."""
        if not force and time.time() - self.last_refresh < max_age:
            return
        async with self._lock:
            if not force and time.time() - self.last_refresh < max_age:
                return
            try:
                convs = await elevenlabs.list_conversations(self.agent_id, page_size=30)
            except elevenlabs.ElevenLabsError as exc:
                log.warning("Gesprächsliste: %s", exc)
                return
            for c in convs:
                cid = c.get("conversation_id")
                if not cid:
                    continue
                rnd = self.rounds.get(cid)
                if rnd and rnd.status == "fertig":
                    continue
                if (c.get("message_count") or 0) == 0:
                    continue
                if rnd is None:
                    rnd = Round(conversation_id=cid, start_time=int(c.get("start_time_unix_secs") or 0))
                    self.rounds[cid] = rnd
                try:
                    data = await elevenlabs.get_conversation(cid)
                except elevenlabs.ElevenLabsError as exc:
                    log.warning("Details %s: %s", cid, exc)
                    continue
                self._apply_details(rnd, data)
            self.last_refresh = time.time()
