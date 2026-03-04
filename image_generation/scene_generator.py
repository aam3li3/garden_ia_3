"""
Génération de scène jardin : boucle plante par plante, inpainting BFL.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Union

import os
from PIL import Image

from .mask_manager import MaskManager
from .prompt_builder import build_prompt
from .utils_rag import ALLOWED_INPAINT_KWARGS, load_rag


def inpaint(
    image_path: Union[str, Path],
    mask_path: Union[str, Path],
    prompt: str,
    out_path: Union[str, Path],
    **kwargs,
) -> None:
    """
    Switch provider : MOCK si BFL_API_KEY absent ou MOCK_BFL=true ou 402.
    Ne passe que seed, steps, guidance à l'API BFL. Jamais plant_name, bbox, zone_hint, etc.
    """
    allowed = {k: kwargs[k] for k in ALLOWED_INPAINT_KWARGS if k in kwargs}

    use_mock = (
        os.environ.get("MOCK_BFL", "").lower() == "true"
        or not os.environ.get("BFL_API_KEY", "").strip()
    )

    if use_mock:
        print("   [MOCK MODE: skipping image generation API]")
        from .mock_provider import inpaint_mock
        inpaint_mock(image_path, mask_path, prompt, out_path, seed=allowed.get("seed"))
        return

    try:
        from .bfl_provider import inpaint as bfl_inpaint
        bfl_inpaint(image_path, mask_path, prompt, out_path, **allowed)
    except Exception as e:
        if "402" in str(e) or "Insufficient credits" in str(e):
            print("   [BFL 402 Insufficient credits → fallback MOCK]")
            from .mock_provider import inpaint_mock
            inpaint_mock(image_path, mask_path, prompt, out_path, **kwargs)
        else:
            raise




def generate_scene(
    image_path: Union[str, Path],
    rag_json_path: Union[str, Path],
    outputs_dir: Union[str, Path] = "outputs",
    global_style: str | None = None,
    time_of_day: str = "day",
    night_light_intensity: float = 0.5,
) -> dict:
    """
    Génère le jardin idéal en un seul appel API (Inpainting Global).
    """
    outputs_dir = Path(outputs_dir)
    outputs_dir.mkdir(parents=True, exist_ok=True)
    masks_dir = outputs_dir / "masks"
    masks_dir.mkdir(exist_ok=True)

    mask_manager = MaskManager(masks_dir=masks_dir)
    metadata, plants_data = load_rag(rag_json_path)
    # Limiter à 8 plantes pour garder une densité cohérente en un seul appel
    plants_data = plants_data[:8]
    print(f"🌱 {len(plants_data)} plantes sélectionnées pour l'inpainting global")

    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"Image non trouvée : {image_path}")

    from .prompt_builder import build_full_garden_prompt_from_rag, build_global_context
    from .config import BFL_STEPS, BFL_GUIDANCE, BFL_STRENGTH

    # 1. Création du masque combiné
    combined_mask_path = masks_dir / "combined_plantable_mask.png"
    plants_with_bboxes = mask_manager.create_combined_mask(
        image_path=image_path,
        plants=plants_data,
        output_path=combined_mask_path
    )

    # 2. Construction du prompt consolidé
    global_context = build_global_context(metadata) if metadata else (global_style or "")
    prompt = build_full_garden_prompt_from_rag(
        metadata=metadata,
        plants=plants_with_bboxes,
        preserve_base=True
    )

    # 3. Appel API unique
    final_path = outputs_dir / "final_garden.png"
    print(f"🚀 Appel API BFL (Inpainting Global)...")
    inpaint(
        image_path=image_path,
        mask_path=combined_mask_path,
        prompt=prompt,
        out_path=final_path,
        seed=42,
        steps=BFL_STEPS,
        guidance=BFL_GUIDANCE,
        strength=BFL_STRENGTH
    )

    # 4. Préparation des données de sortie
    plants_out = []
    for i, p in enumerate(plants_with_bboxes):
        bbox = p["bbox"]
        plants_out.append({
            "plant_id": p.get("plant_id", f"plant_{i:02d}"),
            "name": p.get("name", "plant"),
            "type": p.get("type", ""),
            "bbox": bbox,
            "centroid": [(bbox[0] + bbox[2]) // 2, (bbox[1] + bbox[3]) // 2],
            "mask_path": str(combined_mask_path),
            "zone_hint": p.get("zone_hint", "midground_center"),
            "prompt_used": prompt,
            "editable": True,
            "layer_order": i,
            "status": "placed",
        })

    # Post-process: relight jour -> nuit si demandé
    if time_of_day == "night" and final_path.exists():
        try:
            from ..utils.relight import relight_to_night
            relight_to_night(
                final_path,
                outputs_dir / "final_garden_night.png",
                light_intensity=night_light_intensity,
                plants=plants_out,
            )
        except Exception as e:
            print(f"[RELIGHT] Erreur : {e}")

    scene_dict = {
        "input_image": str(image_path),
        "final_image": str(final_path),
        "metadata": metadata,
        "global_context": global_context,
        "plants": plants_out,
    }
    with open(outputs_dir / "scene.json", "w", encoding="utf-8") as f:
        json.dump(scene_dict, f, indent=2, ensure_ascii=False)

    # Preview boxes (debug uniquement)
    from .mock_provider import create_preview_boxes
    create_preview_boxes(final_path, plants_out, outputs_dir / "preview_boxes.png")

    print(f"   Scène sauvegardée : {final_path}")
    return scene_dict
