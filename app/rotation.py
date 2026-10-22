"""Auswahl der nächsten Region.

Regel: Gewicht geteilt durch (1 + 2 × Anzahl der Einsätze in den letzten zehn
Runden). Regionen aus den letzten zwei Runden sind gesperrt, solange noch
andere übrig sind. Bei Gleichstand gewinnt die Region, die am längsten nicht
dran war. Das ist bewusst deterministisch, damit das Studio vorher sieht,
welche Region als Nächstes kommt.
"""

from __future__ import annotations

RECENT_WINDOW = 10
BLOCK_LAST = 2


def next_region(regions: list[dict], history: list[str]) -> str:
    """`history`: gespielte Regionen, neueste zuerst."""
    if not regions:
        return "Land allgemein"
    recent = [h for h in history[:RECENT_WINDOW] if h]
    blocked = set(recent[:BLOCK_LAST])

    def last_index(name: str) -> int:
        # Je größer, desto länger nicht gespielt
        for i, h in enumerate(history):
            if h == name:
                return i
        return len(history) + 1

    candidates = [r for r in regions if r["weight"] > 0 and r["name"] not in blocked]
    if not candidates:
        candidates = [r for r in regions if r["weight"] > 0] or regions

    def score(r: dict) -> tuple[float, int]:
        count = sum(1 for h in recent if h == r["name"])
        return (r["weight"] / (1 + 2 * count), last_index(r["name"]))

    best = max(candidates, key=score)
    return best["name"]
