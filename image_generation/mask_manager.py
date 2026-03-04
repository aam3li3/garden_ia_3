"""
Gestion des masques individuels par plante.

Modes: "random" (bbox aléatoire) ou "fixed" (zone_hint prédéfini).
Noir = ne pas modifier, Blanc = modifier (zone à inpaint).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Union

import numpy as np
from PIL import Image

from .config import PLACEMENT_MODE

# Mapping zone_hint -> (y_min, y_max, x_min, x_max) en ratio 0-1 (mode "fixed")
# y=0 haut, y=1 bas
ZONE_HINT_REGIONS: dict[str, tuple[float, float, float, float]] = {
    "foreground_left": (0.70, 0.90, 0.05, 0.30),
    "foreground_right": (0.70, 0.90, 0.70, 0.95),
    "foreground_center": (0.75, 0.95, 0.35, 0.65),
    "midground_left": (0.50, 0.70, 0.05, 0.30),
    "midground_right": (0.50, 0.70, 0.70, 0.95),
    "midground_center": (0.55, 0.75, 0.35, 0.65),
    "middle_left": (0.50, 0.70, 0.05, 0.30),
    "middle_right": (0.50, 0.70, 0.70, 0.95),
    "middle_center": (0.55, 0.75, 0.35, 0.65),
    "background_left": (0.35, 0.50, 0.10, 0.35),
    "background_right": (0.35, 0.50, 0.65, 0.90),
    "background_center": (0.35, 0.50, 0.35, 0.65),
}
DEFAULT_ZONE = (0.60, 0.80, 0.40, 0.60)


def create_manual_test_mask(
    image_path: Union[str, Path],
    output_path: Union[str, Path],
    cx: int = 160,
    cy: int = 320,
    radius: int = 40,
) -> Path:
    """
    Crée un masque circulaire pour test manuel.
    Blanc = zone à inpaint, Noir = conserver.
    """
    img = Image.open(image_path).convert("RGB")
    w, h = img.size
    mask = np.zeros((h, w), dtype=np.uint8)
    yy, xx = np.ogrid[:h, :w]
    inside = (xx - cx) ** 2 + (yy - cy) ** 2 <= radius ** 2
    mask[inside] = 255
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(mask).convert("L").save(out)
    return out


@dataclass
class MaskResult:
    """Résultat : chemin du masque + bbox."""

    mask_path: str
    bbox: list[int]  # [x1, y1, x2, y2]


def _create_random_bbox(w: int, h: int, plant_id: str, plant_index: int) -> tuple[int, int, int, int]:
    """
    Génère une bbox aléatoire dans la zone jardin (évite le ciel).

    - margin = 20px
    - bbox_w = int(w * 0.18), bbox_h = int(h * 0.18)
    - y_min >= 45% de la hauteur (évite le ciel)
    """
    margin = 20
    bbox_w = max(32, int(w * 0.18))
    bbox_h = max(32, int(h * 0.18))

    y_min_allowed = int(h * 0.45)
    x_min_allowed = margin
    x_max_allowed = max(x_min_allowed, w - bbox_w - margin)
    y_max_allowed = max(y_min_allowed, h - bbox_h - margin)

    rng = np.random.default_rng(seed=hash(plant_id) % (2**32) + plant_index * 1000)
    x1 = int(rng.integers(x_min_allowed, x_max_allowed + 1))
    y1 = int(rng.integers(y_min_allowed, y_max_allowed + 1))
    x2 = min(x1 + bbox_w, w)
    y2 = min(y1 + bbox_h, h)

    return x1, y1, x2, y2


class MaskManager:
    """
    Crée et sauvegarde les masques par plante.
    Blanc = zone à inpaint, Noir = conserver.
    """

    def __init__(self, masks_dir: Union[str, Path], use_ellipse: bool = False):
        self.masks_dir = Path(masks_dir)
        self.masks_dir.mkdir(parents=True, exist_ok=True)
        self.use_ellipse = use_ellipse
        self._plant_counter = 0

    def create_mask(
        self,
        image_path: Union[str, Path],
        plant_id: str,
        zone_hint: str = "midground_center",
    ) -> MaskResult:
        """
        Crée un masque pour une plante et le sauvegarde.
        """
        img = Image.open(image_path).convert("RGB")
        w, h = img.size

        if PLACEMENT_MODE == "random":
            x1, y1, x2, y2 = _create_random_bbox(w, h, plant_id, self._plant_counter)
            self._plant_counter += 1
        else:
            ratios = ZONE_HINT_REGIONS.get(
                (zone_hint or "").lower().strip(),
                DEFAULT_ZONE,
            )
            y_min_r, y_max_r, x_min_r, x_max_r = ratios
            y1, y2 = int(y_min_r * h), int(y_max_r * h)
            x1, x2 = int(x_min_r * w), int(x_max_r * w)
            y2, x2 = max(y2, y1 + 32), max(x2, x1 + 32)

        mask = np.zeros((h, w), dtype=np.uint8)
        mask[y1:y2, x1:x2] = 255
        mask_pil = Image.fromarray(mask).convert("L")
        mask_path = self.masks_dir / f"{plant_id}.png"
        mask_pil.save(mask_path)

        return MaskResult(mask_path=str(mask_path), bbox=[x1, y1, x2, y2])

    def create_combined_mask(
        self,
        image_path: Union[str, Path],
        plants: list[dict],
        output_path: Union[str, Path],
    ) -> list[dict]:
        """
        Crée un masque unique combinant toutes les zones de plantation.
        Retourne la liste des plantes avec leurs bboxes calculées.
        """
        img = Image.open(image_path).convert("RGB")
        w, h = img.size
        combined_mask = np.zeros((h, w), dtype=np.uint8)
        updated_plants = []

        for i, plant in enumerate(plants):
            zone_hint = plant.get("zone_hint", "midground_center")
            ratios = ZONE_HINT_REGIONS.get(zone_hint.lower().strip(), DEFAULT_ZONE)
            y1, y2 = int(ratios[0] * h), int(ratios[1] * h)
            x1, x2 = int(ratios[2] * w), int(ratios[3] * w)
            y2, x2 = max(y2, y1 + 32), max(x2, x1 + 32)
            
            combined_mask[y1:y2, x1:x2] = 255
            
            plant_copy = plant.copy()
            plant_copy["bbox"] = [x1, y1, x2, y2]
            updated_plants.append(plant_copy)

        Image.fromarray(combined_mask).convert("L").save(output_path)
        return updated_plants
