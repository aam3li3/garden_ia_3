"""
Script de test des étapes du pipeline (sans génération SD).

Permet de vérifier que segmentation, profondeur et découpage fonctionnent
avant de lancer le pipeline complet (qui nécessite GPU et modèles SD).

Usage:
    python test_steps.py [chemin_image]
"""
import sys
from pathlib import Path

import numpy as np

# Chemins par défaut
DEFAULT_PATHS = [
    Path("data ") / "garden.jpg",
    Path("data") / "garden.jpg",
]


def find_image(argv):
    if len(argv) > 1:
        p = Path(argv[1])
        if p.exists():
            return p
        print(f"❌ Fichier non trouvé : {p}", file=sys.stderr)
        sys.exit(1)
    for p in DEFAULT_PATHS:
        if p.exists():
            return p
    print("❌ Aucune image trouvée. Usage: python test_steps.py [chemin_image]", file=sys.stderr)
    sys.exit(1)


def main():
    image_path = find_image(sys.argv)
    print(f"📷 Image : {image_path}\n")

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    # 1. Segmentation
    print("1. Segmentation SAM...")
    try:
        from segmentation.sam_segmentation import GardenSegmenter
        segmenter = GardenSegmenter()
        image, masks = segmenter.segment(str(image_path))
        plantable = segmenter.extract_plantable_mask(image, masks)
        print(f"   OK : {len(masks)} masques, plantable {plantable.shape}")
        from PIL import Image
        Image.fromarray(plantable).save(output_dir / "test_plantable_mask.png")
        print(f"   Sauvegardé : output/test_plantable_mask.png")
    except FileNotFoundError as e:
        print(f"   ❌ {e}")
        sys.exit(1)
    except Exception as e:
        print(f"   ❌ {e}")
        sys.exit(1)

    # 2. Profondeur (Depth-Anything si USE_DEPTH_ANYTHING=1, sinon MiDaS)
    print("\n2. Estimation profondeur...")
    try:
        from depth import get_depth_estimator
        depth_est = get_depth_estimator()
        depth_map = depth_est.predict(image)
        print(f"   OK : {depth_map.shape}")
        Image.fromarray(depth_map).save(output_dir / "test_depth.png")
        print(f"   Sauvegardé : output/test_depth.png")
    except Exception as e:
        print(f"   ❌ {e}")
        sys.exit(1)

    # 3. Découpage en régions
    print("\n3. Découpage en régions (k-means)...")
    n_plants = 3
    from utils.region_splitter import split_plantable_mask
    region_masks = split_plantable_mask(plantable, depth_map, n_plants)
    print(f"   OK : {len(region_masks)} régions")

    # Visualisation des régions (couleurs différentes)
    vis = np.zeros((*plantable.shape, 3), dtype=np.uint8)
    colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
    for i, mask in enumerate(region_masks):
        c = colors[i % len(colors)]
        vis[mask > 0] = c
    Image.fromarray(vis).save(output_dir / "test_regions.png")
    print(f"   Sauvegardé : output/test_regions.png")

    print("\n✅ Toutes les étapes OK. Vous pouvez lancer python main.py")


if __name__ == "__main__":
    main()
