"""Fragenpool aus der ElevenLabs-Wissensbasis und Auswahl pro Runde.

Der Dienst liest die vier Pool-Dokumente direkt aus der Wissensbasis des
Agenten (eine Quelle der Wahrheit) und zieht vor jeder Runde pro Kategorie
genau eine Frage. Die Auswahl verteilt sich über die Regionen von
Rheinland-Pfalz, bevorzugt „Land allgemein“ und lässt Fragen aus den letzten
Runden weg. Die KI bekommt nur diese sechs Fragen und muss nicht selbst suchen.
"""

from __future__ import annotations

import logging
import os
import random
import re
from dataclasses import dataclass, field

from . import elevenlabs
from .regions import load_regions

log = logging.getLogger("gop.questions")

DEFAULT_DOC_IDS = {
    "grundpool": "9nn8PGCdgCU6l6Rpg4Nt",
    "stufe2": "DRNRjXRd4pOlLQ2JlsmZ",
    "kategorien": "goCpSUophjJwoOi3Z6KH",
    "regionen": "aNA5eOKsz6NkhI85edQ4",
}

CATEGORIES = {
    "musik": "Musik",
    "heimat": "Heimat",
    "natur": "Natur",
    "promis": "Promis Film und Fernsehen",
    "essen": "Essen und Trinken",
    "sport": "Sport",
}

NEVER = {9, 47}

# Schwierigkeit laut Redaktion (Liste vom 23.10.2026): 1 leicht, 2 mittel, 3 schwer, X raus.
# FRAGEN_STUFE legt die höchste erlaubte Stufe fest (Standard 1). Fragen ohne Einstufung
# gelten als 2, bis die Redaktion sie bewertet hat.
import json as _json
from pathlib import Path as _Path

try:
    LEVELS: dict[int, str] = {
        int(k): str(v).strip().upper()
        for k, v in _json.loads((_Path(__file__).parent / "data" / "stufen.json").read_text(encoding="utf-8")).items()
    }
except (OSError, ValueError):
    LEVELS = {}


def max_level() -> int:
    try:
        return max(1, min(3, int(os.environ.get("FRAGEN_STUFE", "1"))))
    except ValueError:
        return 1
LINE_RE = re.compile(r"^\s*(\d{1,3})\s*\|\s*(.+)$")
FIELD_KEYS = ("Region", "Kategorie", "Frage", "Antwort", "Gilt auch", "Tabu", "Bonus", "Hinweis")


@dataclass
class Question:
    nr: int
    frage: str
    antwort: str
    gilt_auch: str = ""
    tabu: str = ""
    bonus: str = ""
    hinweis: str = ""
    categories: set[str] = field(default_factory=set)  # Schlüssel aus CATEGORIES
    regions: set[str] = field(default_factory=set)

    @property
    def level(self) -> str:
        return LEVELS.get(self.nr, "2")

    @property
    def blocked(self) -> bool:
        if self.nr in NEVER or "NICHT VERWENDEN" in self.hinweis.upper():
            return True
        lv = self.level
        if lv == "X" or not lv.isdigit():
            return True
        return int(lv) > max_level()

    def as_line(self) -> str:
        parts = [f"Nr {self.nr}", f"Frage: {self.frage}", f"Antwort: {self.antwort}"]
        if self.gilt_auch:
            parts.append(f"Gilt auch: {self.gilt_auch}")
        tabu = self.tabu
        parts.append(f"Tabu: {tabu}" if tabu else "Tabu: –")
        if self.bonus:
            parts.append(f"Bonus: {self.bonus}")
        return " | ".join(parts)


def _category_key(label: str) -> str | None:
    l = label.lower()
    if l.startswith("musik"):
        return "musik"
    if l.startswith("heimat"):
        return "heimat"
    if l.startswith("natur"):
        return "natur"
    if l.startswith("promis"):
        return "promis"
    if l.startswith("essen"):
        return "essen"
    if l.startswith("sport"):
        return "sport"
    return None


def _parse_fields(rest: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in rest.split(" | "):
        part = part.strip()
        for key in FIELD_KEYS:
            prefix = key + ":"
            if part.startswith(prefix):
                out[key] = part[len(prefix):].strip()
                break
    return out


def _parse_numbers(text: str) -> list[int]:
    nums: list[int] = []
    for token in re.findall(r"\d{1,3}(?:\s*-\s*\d{1,3})?", text):
        if "-" in token:
            a, b = (int(x) for x in token.split("-"))
            nums.extend(range(a, b + 1))
        else:
            nums.append(int(token))
    return nums


def parse_pool(texts: list[str]) -> dict[int, Question]:
    """Liest alle Pool-Zeilen, Kategorienlisten und Regionenlisten."""
    questions: dict[int, Question] = {}
    category_lists: dict[str, set[int]] = {k: set() for k in CATEGORIES}
    region_names = [r["name"] for r in load_regions()]
    region_lists: dict[str, set[int]] = {r: set() for r in region_names}

    for text in texts:
        for raw in text.splitlines():
            line = raw.strip()
            m = LINE_RE.match(line)
            if m and "Frage:" in line:
                nr = int(m.group(1))
                f = _parse_fields(m.group(2))
                if not f.get("Frage") or not f.get("Antwort"):
                    continue
                q = Question(
                    nr=nr,
                    frage=f["Frage"],
                    antwort=f["Antwort"],
                    gilt_auch=f.get("Gilt auch", ""),
                    tabu=f.get("Tabu", ""),
                    bonus=f.get("Bonus", ""),
                    hinweis=f.get("Hinweis", ""),
                )
                if f.get("Kategorie"):
                    key = _category_key(f["Kategorie"])
                    if key:
                        q.categories.add(key)
                if f.get("Region"):
                    reg = f["Region"].strip()
                    if reg in region_lists:
                        q.regions.add(reg)
                questions[nr] = q
                continue
            # Listen wie „MUSIK: 45, 92, …“ oder „PFALZ: 5, 6, …“
            # Kombizeile „MOSEL: 122-128 · EIFEL: 129-134 · …“
            if "·" in line and ":" in line:
                for chunk in line.split("·"):
                    if ":" not in chunk:
                        continue
                    h, t = chunk.split(":", 1)
                    for reg in region_names:
                        if h.strip().upper() == reg.upper():
                            region_lists[reg].update(_parse_numbers(t))
                continue
            if ":" in line and not line.startswith(("Frage", "So nutzt")):
                head, tail = line.split(":", 1)
                head_clean = head.strip()
                if not re.search(r"\d", tail):
                    continue
                key = _category_key(head_clean)
                if key and head_clean.split("(")[0].strip().isupper():
                    category_lists[key].update(_parse_numbers(tail))
                    continue
                for reg in region_names:
                    if head_clean.upper() == reg.upper():
                        region_lists[reg].update(_parse_numbers(tail))
                        break

    for key, nums in category_lists.items():
        for n in nums:
            if n in questions:
                questions[n].categories.add(key)
    for reg, nums in region_lists.items():
        for n in nums:
            if n in questions:
                questions[n].regions.add(reg)
    for q in questions.values():
        if not q.regions:
            q.regions.add("Land allgemein")
    return questions


class QuestionPool:
    def __init__(self) -> None:
        self.questions: dict[int, Question] = {}
        self.error: str | None = None

    @property
    def ready(self) -> bool:
        return bool(self.questions)

    async def load(self) -> None:
        ids = dict(DEFAULT_DOC_IDS)
        raw = os.environ.get("KB_DOC_IDS", "").strip()
        if raw:
            ids = {f"doc{i}": d.strip() for i, d in enumerate(raw.split(",")) if d.strip()}
        texts: list[str] = []
        errors: list[str] = []
        for name, doc_id in ids.items():
            try:
                texts.append(await elevenlabs.get_kb_text(doc_id))
            except elevenlabs.ElevenLabsError as exc:
                errors.append(f"{name}: {exc}")
        if texts:
            self.questions = parse_pool(texts)
        self.error = "; ".join(errors) or None
        log.info("Fragenpool: %d Fragen, Fehler: %s", len(self.questions), self.error)

    def summary(self) -> dict:
        per_cat = {k: 0 for k in CATEGORIES}
        per_reg: dict[str, int] = {}
        for q in self.questions.values():
            if q.blocked:
                continue
            for c in q.categories:
                per_cat[c] += 1
            for r in q.regions:
                per_reg[r] = per_reg.get(r, 0) + 1
        return {
            "fragen": len(self.questions),
            "aktiv": sum(1 for q in self.questions.values() if not q.blocked and q.categories),
            "stufe": max_level(),
            "kategorien": per_cat,
            "regionen": per_reg,
            "fehler": self.error,
        }

    def pick_round(
        self,
        recent_numbers: list[int],
        recent_solutions: list[str],
        recent_regions: list[str],
        rng: random.Random | None = None,
    ) -> dict[str, Question]:
        """Eine Frage pro Kategorie. recent_* jeweils neueste zuerst."""
        rng = rng or random.Random()
        regions = {r["name"]: r["weight"] for r in load_regions()}
        recent_set = set(recent_numbers[:60])
        solutions = {s.strip().lower() for s in recent_solutions[:40] if s}
        region_recent = recent_regions[:10]
        used_regions: list[str] = []
        picks: dict[str, Question] = {}

        order = list(CATEGORIES)
        rng.shuffle(order)
        for cat in order:
            cands = [q for q in self.questions.values() if cat in q.categories and not q.blocked]
            fresh = [
                q for q in cands
                if q.nr not in recent_set and q.antwort.strip().lower() not in solutions
                and q.nr not in {p.nr for p in picks.values()}
            ]
            if not cands:
                continue
            if not fresh:
                # Alle Fragen der Kategorie waren kürzlich dran: die am längsten nicht gespielte nehmen
                pool_left = [q for q in cands if q.nr not in {p.nr for p in picks.values()}] or cands
                def age(q: Question) -> int:
                    return recent_numbers.index(q.nr) if q.nr in recent_numbers else 10_000
                oldest = max(age(q) for q in pool_left)
                fresh = [q for q in pool_left if age(q) == oldest]
            if not fresh:
                continue

            def weight(q: Question) -> float:
                best = 0.0
                for reg in q.regions:
                    w = regions.get(reg, 1.0)
                    w /= 1 + 2 * region_recent.count(reg)
                    w /= 1 + 1.5 * used_regions.count(reg)
                    best = max(best, w)
                if q.nr >= 51:
                    best *= 1.3
                return max(best, 0.01)

            weights = [weight(q) for q in fresh]
            choice = rng.choices(fresh, weights=weights, k=1)[0]
            picks[cat] = choice
            used_regions.extend(choice.regions)
        return picks
