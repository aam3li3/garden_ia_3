"""
Génération legacy (en un seul pass) - utile pour tests ou comparaison.

Usage:
    python run_legacy.py
"""
import sys
from pathlib import Path

from segmentation.sam_segmentation import GardenSegmenter
from depth import get_depth_estimator
from generation.garden_generation import GardenGenerator

# Chemins possibles pour l'image
IMAGE_PATHS = [
    Path("data ") / "garden.jpg",
    Path("data") / "garden.jpg",
]


def find_image_path():
    for p in IMAGE_PATHS:
        if p.exists():
            return p
    raise FileNotFoundError(
        f"Aucune image trouvée. Placez garden.jpg dans data/ ou data /"
    )


def main():
    try:
        image_path = find_image_path()
    except FileNotFoundError as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)

    try:
        segmenter = GardenSegmenter()
        depth_estimator = get_depth_estimator()
        generator = GardenGenerator()
    except FileNotFoundError as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)

    image, masks = segmenter.segment(str(image_path))
    plantable_mask = segmenter.extract_plantable_mask(image, masks)
    depth_map = depth_estimator.predict(image)

    prompt = (
        "modern landscaped garden, natural plants, "
        "olive trees, lavender, realistic, daylight"
    )

    result = generator.generate(
        image=image,
        depth_map=depth_map,
        plantable_mask=plantable_mask,
        prompt=prompt,
    )

    Path("output").mkdir(exist_ok=True)
    out_path = Path("output/generated_garden_legacy.png")
    result.save(str(out_path))
    print(f"✅ Image sauvegardée : {out_path}")


if __name__ == "__main__":
    main()
