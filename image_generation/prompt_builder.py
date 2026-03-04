"""
Construction des prompts pour la génération de plantes.

Mode "additive inpainting" : préserver l'image, ajouter uniquement des plantes.
"""
from __future__ import annotations

from typing import Any


# A) Verrouillage base
ADDITIVE_BASE = (
    "Use the input photo as the base. Keep camera angle, perspective, lighting, shadows, "
    "and all existing elements exactly the same. "
    "Preserve the original photo completely. Same composition and color grading. "
)

ADDITIVE_VISIBLE = (
    "Add clearly noticeable plants ONLY in the masked areas. "
    "The added plants must be clearly visible and recognizable (not subtle). "
    "Keep image sharp, no blur, no haze. "
    "Do not change lawn, do not change trees, do not change sky. "
    "Photorealistic, seamless blend. No text, no labels, no overlays. "
)

# B) Interdits forts (anti-objets parasites)
ADDITIVE_NEGATIVE = (
    "DO NOT add any new objects or landscaping elements. Only add the requested plants. "
    "DO NOT create new flower beds or change terrain. No new soil beds, no edging, no mulch, no rocks, no gravel. "
    "No paths, no benches, no ponds, no lights, no fences, no walls, no decorations, no statues. "
    "DO NOT add pathways, gravel, stones, lamps, buildings, or structures. DO NOT add people or animals. "
    "DO NOT change season or time of day. DO NOT change camera position or focal length. "
    "DO NOT repaint the whole image. DO NOT redesign the garden."
)

# C) Contrainte masque
MASK_CONSTRAINT = (
    "ONLY paint inside the masked area. Outside the mask must remain pixel-identical to the original."
)

# D) Placement réaliste
PLACEMENT_REALISTIC = (
    "Place plants only along existing borders and existing planting areas; do not invent new structures. "
    "Plants must be grounded in soil, with realistic scale and consistent shadows."
)

# RAG : les plantes doivent être clairement visibles et identifiables (E)
RAG_MUST_BE_VISIBLE = (
    "RAG MUST BE VISIBLE AND IDENTIFIABLE: The following plants must appear clearly "
    "in the image, recognizable and well visible. Do not hide them or make them tiny or blurry. "
    "The added plants must be clearly visible and recognizable (not subtle)."
)

# Règles de placement add-only (historique, complément)
PLACEMENT_RULES = (
    "Only inside masked area. Do not add paths, benches, ponds, or new structures. "
    "Keep lighting and shadows consistent with the original photo."
)

REDESIGN_BASE = (
    "Transform this garden into a well-designed landscaped garden. "
    "Multiple flowerbeds and planting borders. Photorealistic. "
    "No text, no labels, no overlays. "
)


def build_full_garden_prompt(
    plant_density: str = "medium",
    preserve_base: bool = True,
    force_full_redesign: bool = False,
    plant_list: list[str] | None = None,
) -> str:
    """
    Prompt FLUX Fill — mode additive par défaut (ajouter plantes uniquement).

    Si preserve_base=True : impose conservation de l'image + ajout plantes visibles.
    Si plant_list fourni : force l'usage de ces plantes.
    """
    if force_full_redesign or not preserve_base:
        density_spec = {
            "low": "Sparse planting along borders.",
            "medium": "Several flowerbeds along borders.",
            "high": "Dense flowerbeds, numerous plants.",
        }.get(plant_density.lower(), "Dense flowerbeds.")
        return f"{REDESIGN_BASE} {density_spec}"

    # Mode ADDITIVE : préservation + ajout visible
    density_spec = {
        "low": "Sparse but visible accents.",
        "medium": "Several clearly visible plants, shrubs, flowers.",
        "high": "Dense, colorful planting. Lavender, roses, grasses, shrubs.",
    }.get(plant_density.lower(), "Clearly visible plants in masked areas. Moderate density.")

    plant_block = ""
    if plant_list:
        plants_str = ", ".join(plant_list[:15])
        plant_block = f" Use these plants (as many as possible): {plants_str}."

    return (
        f"{ADDITIVE_BASE} {ADDITIVE_VISIBLE} {density_spec}.{plant_block} "
        f"{MASK_CONSTRAINT} {PLACEMENT_REALISTIC} {ADDITIVE_NEGATIVE}"
    )


def build_full_garden_prompt_from_rag(
    metadata: dict[str, Any],
    plants: list[dict[str, Any]],
    plant_density: str = "medium",
    preserve_base: bool = True,
    plant_list: list[str] | None = None,
    debug: bool = False,
) -> str:
    """
    Prompt FLUX à partir du RAG — mode additive par défaut.
    plant_list : noms extraits pour "Use these plants (as many as possible)".
    Si debug=True, les infos debug (plantes, etc.) sont à logger par l'appelant (seed dans generator).
    """
    if not preserve_base:
        base = REDESIGN_BASE
    else:
        base = f"{ADDITIVE_BASE} {ADDITIVE_VISIBLE}"

    constraints = (
        f" {MASK_CONSTRAINT} "
        + (f" {PLACEMENT_REALISTIC} " + ADDITIVE_NEGATIVE if preserve_base else "")
    )
    placement = f" {PLACEMENT_RULES}" if preserve_base else ""

    parts = []
    style = metadata.get("style") or metadata.get("climat") or ""
    if style:
        parts.append(f"Style: {style}.")
    desc = metadata.get("description", "")
    if desc:
        parts.append(f"Ambiance: {desc}.")
    region = metadata.get("region", "")
    if region:
        parts.append(f"Region: {region}.")
    climate = metadata.get("climate") or metadata.get("climat", "")
    if climate:
        parts.append(f"Climate: {climate}.")
    exposure = metadata.get("sun_exposure") or metadata.get("exposition", "")
    if exposure:
        parts.append(f"Sun exposure: {exposure.replace('_', ' ')}.")
    season = metadata.get("season", "")
    if season and str(season).lower() not in ("", "toutes_saisons"):
        parts.append(f"Season: {season}.")

    colors = set()
    sizes = set()
    plant_descriptors = []  # (name, type, form) for RAG visible block
    for p in plants:
        c = p.get("color") or p.get("colors")
        if isinstance(c, str):
            colors.add(c)
        elif isinstance(c, dict):
            colors.update(str(v) for v in c.values() if v)
        sz = p.get("size") or p.get("height") or p.get("mature_size")
        if sz and isinstance(sz, str):
            sizes.add(sz)
    if colors:
        parts.append(f"Color palette: {', '.join(colors)}.")
    if sizes:
        parts.append(f"Plant sizes / habit: {', '.join(sizes)}.")

    names = plant_list if plant_list else [p.get("name") or p.get("species") for p in plants if p.get("name") or p.get("species")]
    names = [n for n in names if n and n != "plant"][:15]
    # Descripteurs par plante : type (shrub/perennial/grass/succulent) + forme (tall/low) si dispo
    for p in plants[:15]:
        name = p.get("name") or p.get("species")
        if not name or name == "plant":
            continue
        ptype = (p.get("type") or p.get("plant_type") or "").lower()
        form = (p.get("height") or p.get("mature_size") or p.get("form") or "")
        if isinstance(form, str):
            form = "tall" if any(x in form.lower() for x in ("high", "grand", "tall", "large")) else ("low" if any(x in form.lower() for x in ("low", "petit", "small", "nain")) else "")
        else:
            form = ""
        if ptype in ("shrub", "perennial", "grass", "succulent", "tree", "annual"):
            if form:
                plant_descriptors.append(f"{name} ({ptype}, {form})")
            else:
                plant_descriptors.append(f"{name} ({ptype})")
        else:
            plant_descriptors.append(name)
    visible_list = ", ".join(plant_descriptors[:15]) if plant_descriptors else ", ".join(names) if names else ""
    visible_block = f"{RAG_MUST_BE_VISIBLE} Plants to add (clearly visible): {visible_list}." if (visible_list or names) else ""
    if names:
        parts.append(f"Use these plants (as many as possible): {', '.join(names)}. Add them clearly in the masked areas.")
    else:
        parts.append("Plants to add: lavender, roses, grasses, shrubs, perennials.")

    rag_block = " ".join(parts)
    mid = f" {visible_block}" if visible_block else ""
    prompt = f"{base} {constraints}{placement}{mid} RAG: {rag_block}"
    if debug:
        import logging
        log = logging.getLogger(__name__)
        log.info("DEBUG prompt_builder: plants_used=%s", names)
        log.info("DEBUG prompt_builder: prompt_preview=%s", prompt[:300] + "..." if len(prompt) > 300 else prompt)
    return prompt


RELIGHT_NIGHT_PROMPT = (
    "Nighttime garden scene, realistic landscape lighting, "
    "warm ground spotlights illuminating plants, deep blue night sky, "
    "subtle ambient moonlight, keep composition identical, "
    "no new objects like cars or people, photorealistic, no text."
)


def build_inpaint_prompt(plant_name: str) -> str:
    """Prompt placement précis dans la zone masquée."""
    return (
        f"Add a highly visible and realistic {plant_name} planted in the ground inside the masked area. "
        "The plant must have vibrant colors and clear details to stand out from the background. "
        "Photorealistic. Match lighting and perspective. "
        "PRESERVE THE ORIGINAL PHOTO COMPLETELY. DO NOT REPAINT THE WHOLE IMAGE. "
        "ONLY modify the masked area. Keep the rest of the garden exactly as it is. "
        "No text, no labels, no overlays."
    )


def build_global_context(metadata: dict[str, Any]) -> str:
    """Contexte global depuis metadata RAG."""
    parts = []
    style = metadata.get("style", "")
    if style:
        parts.append(f"{style} garden")
    season = metadata.get("season", "")
    if season and season != "toutes_saisons":
        parts.append(f"{season} season")
    climate = metadata.get("climate", "")
    if climate:
        parts.append(f"{climate} climate")
    sun = metadata.get("sun_exposure", "")
    if sun:
        parts.append(sun.replace("_", " "))
    return ", ".join(parts) if parts else ""


def build_plant_prompt(
    plant: dict[str, Any],
    metadata: dict[str, Any] | None = None,
) -> str:
    """Construit le prompt pour une plante (legacy RAG)."""
    parts = []
    name = plant.get("name") or "garden plant"
    parts.append(f"realistic {name}")
    plant_type = plant.get("type", "")
    if plant_type:
        parts.append(plant_type)
    parts.append("photorealistic, match lighting. No text, no labels.")
    if metadata:
        ctx = build_global_context(metadata)
        if ctx:
            parts.insert(1, ctx)
    return ", ".join(parts)


def build_prompt(plant: dict[str, Any], global_style: str | None = None) -> str:
    """Alias legacy."""
    metadata = {"style": global_style} if global_style else None
    return build_plant_prompt(plant, metadata)


def build_negative_prompt() -> str:
    """Prompt négatif standard."""
    return (
        "cartoon, CGI, 3d render, text, watermark, logo, "
        "distorted, blurry, low quality, oversaturated, "
        "artificial, fake plant, plastic, deformed"
    )
