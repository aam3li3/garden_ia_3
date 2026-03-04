# Garden AI - Génération de jardin avec IA

Projet de génération de jardin : RAG + génération d'image plante par plante.

## Modules

- **`rag/`** : Mini-RAG local (ChromaDB + sentence-transformers)
- **`image_generation/`** : Génération d'image (BFL FLUX Fill PRO ou MOCK)
- **`ui/`** : Interface Streamlit

## Installation

```bash
pip install -r requirements.txt
pip install -r requirements_rag.txt  # Si utilisation du RAG
```

## Usage

### Mode MOCK (sans API)

```bash
export MOCK_BFL=true
python -m image_generation.demo
```

### Interface Streamlit

**Avec API BFL (recommandé)** :
```bash
export BFL_API_KEY='votre_clé'
unset MOCK_BFL
streamlit run ui/app.py
```

**Mode MOCK** (sans API) :
```bash
export MOCK_BFL=true
streamlit run ui/app.py
```

## Structure des données

- **`data/garden.jpg`** : photo du jardin
- **`data/rag_output.json`** : plantes recommandées (format : voir `data/rag_output.schema.json`)
- **`outputs/`** : images générées, masques, scene.json

## Contrat RAG → image_generation

Voir `data/rag_output.schema.json` pour le format exact.

Format minimal :
```json
{
  "metadata": {
    "style": "potager",
    "season": "printemps",
    "climate": "tempere"
  },
  "garden": [
    {
      "plant_id": "plant_01",
      "name": "Lavande",
      "type": "fleur",
      "height_cm": 60,
      "zone_hint": "foreground_left"
    }
  ]
}
```

## Outputs

- `outputs/final_garden.png` : jardin généré (mode jour)
- `outputs/final_garden_night.png` : version nuit (si mode night)
- `outputs/masks/plantable_mask.png` : masque plantable global (blanc = zone à modifier)
