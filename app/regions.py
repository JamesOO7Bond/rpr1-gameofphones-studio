"""Regionen von Rheinland-Pfalz für die Fragen-Rotation.

Die Gewichte steuern, wie oft eine Region vorgeschlagen wird. „Land allgemein“
darf laut Redaktion häufiger kommen. Die Gewichte lassen sich über die
Umgebungsvariable REGION_WEIGHTS (JSON, z. B. {"Nahe": 1.5}) überschreiben.
"""

from __future__ import annotations

import json
import os

DEFAULT_REGIONS: list[dict] = [
    {"name": "Land allgemein", "weight": 3.0},
    {"name": "Pfalz", "weight": 2.0},
    {"name": "Rheinhessen", "weight": 2.0},
    {"name": "Eifel", "weight": 2.0},
    {"name": "Mosel", "weight": 2.0},
    {"name": "Rhein", "weight": 2.0},
    {"name": "Hunsrück", "weight": 1.5},
    {"name": "Westerwald", "weight": 1.5},
    {"name": "Nahe", "weight": 1.0},
    {"name": "Hochwald", "weight": 0.7},
]

# Schreibweisen, die die KI in der Datenerfassung liefern könnte → Regionsname
ALIASES = {
    "land": "Land allgemein",
    "allgemein": "Land allgemein",
    "land allgemein": "Land allgemein",
    "rheinland-pfalz": "Land allgemein",
    "rlp": "Land allgemein",
    "pfalz": "Pfalz",
    "pfälzerwald": "Pfalz",
    "weinstraße": "Pfalz",
    "rheinhessen": "Rheinhessen",
    "mainz": "Rheinhessen",
    "worms": "Rheinhessen",
    "eifel": "Eifel",
    "vulkaneifel": "Eifel",
    "mosel": "Mosel",
    "trier": "Mosel",
    "rhein": "Rhein",
    "mittelrhein": "Rhein",
    "koblenz": "Rhein",
    "hunsrück": "Hunsrück",
    "hunsrueck": "Hunsrück",
    "westerwald": "Westerwald",
    "nahe": "Nahe",
    "hochwald": "Hochwald",
}


def load_regions() -> list[dict]:
    regions = [dict(r) for r in DEFAULT_REGIONS]
    raw = os.environ.get("REGION_WEIGHTS", "").strip()
    if raw:
        try:
            overrides = json.loads(raw)
        except json.JSONDecodeError:
            overrides = {}
        for r in regions:
            if r["name"] in overrides:
                try:
                    r["weight"] = max(0.0, float(overrides[r["name"]]))
                except (TypeError, ValueError):
                    pass
    return regions


def normalize_region(value: str | None) -> str | None:
    """Macht aus einer freien Angabe der KI einen bekannten Regionsnamen."""
    if not value:
        return None
    key = value.strip().lower()
    if key in ALIASES:
        return ALIASES[key]
    for alias, name in ALIASES.items():
        if alias in key:
            return name
    return None


REGION_NAMES = [r["name"] for r in DEFAULT_REGIONS]
