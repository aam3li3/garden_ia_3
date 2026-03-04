"""
Retrieval + filtres + scoring.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .schemas import Plant, Query

# Ordre eau : faible < moyen < fort
WATER_ORDER = {"faible": 0, "moyen": 1, "fort": 2}


def _water_compatible(plant_water: str, constraint: str) -> bool:
    """
    water_constraint = max accepté.
    Si constraint "faible" -> seulement "faible"
    Si "moyen" -> "faible" ou "moyen"
    Si "fort" -> tous
    """
    if not constraint:
        return True
    constraint = constraint.lower().strip()
    plant_water = (plant_water or "").lower().strip()
    if not plant_water:
        return True
    c_level = WATER_ORDER.get(constraint, 1)
    p_level = WATER_ORDER.get(plant_water, 1)
    return p_level <= c_level


def _climate_match(plant_climate: str, query_climat: str) -> bool:
    if not query_climat:
        return True
    p = (plant_climate or "").lower().strip()
    q = (query_climat or "").lower().strip()
    return p == q


def _sun_match(plant_sun: str, query_sun: str) -> bool:
    if not query_sun:
        return True
    p = (plant_sun or "").lower().strip()
    q = (query_sun or "").lower().strip()
    return p == q


def _season_match(plant_season: str, query_season: str) -> bool:
    if not query_season:
        return True
    p = (plant_season or "").lower().strip()
    q = (query_season or "").lower().strip()
    if p == "toutes_saisons":
        return True
    return p == q


def apply_filters(
    plants: list["Plant"],
    query: "Query",
) -> list["Plant"]:
    """Applique les filtres climat, sun_exposure, season, water_constraint."""
    result = []
    for p in plants:
        if not _water_compatible(p.water_needs, query.water_constraint):
            continue
        if not _climate_match(p.climate, query.climat):
            continue
        if not _sun_match(p.sun_exposure, query.sun_exposure):
            continue
        if not _season_match(p.season, query.season):
            continue
        result.append(p)
    return result


def compute_score(
    plant: "Plant",
    query: "Query",
    embedding_distance: float,
) -> float:
    """
    score_total = -embedding_distance (plus proche = mieux)
                  + bonus style_tag match
                  + bonus saison match
                  - pénalité eau incompatible (déjà filtré)
    """
    # Convertir distance cosine en score (0-1, 1=meilleur)
    score = 1.0 - min(embedding_distance, 1.0)

    # Bonus style_tag
    q_style = (query.style or "").lower()
    if q_style and q_style in [t.lower() for t in plant.style_tags]:
        score += 0.2
    for tag in plant.style_tags:
        if tag.lower() in (query.description or "").lower():
            score += 0.1

    # Bonus saison
    if _season_match(plant.season, query.season):
        score += 0.15

    return score
