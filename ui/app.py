"""
Interface Streamlit Simplifiée — Garden AI Premium.
Visualisation et Génération à partir d'un fichier RAG JSON externe.

Usage: streamlit run garden_ai/ui/app.py
"""
from __future__ import annotations

import os
import sys
import json
import time
from pathlib import Path
from datetime import datetime

import streamlit as st
from PIL import Image

# Ajouter le projet au path pour les imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT.parent))

from image_generation.full_garden_generator import generate_full_garden
from image_generation.bfl_provider import has_bfl_key

# Configuration des dossiers
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
DATA_DIR = PROJECT_ROOT / "data"
UI_INPUTS_DIR = OUTPUTS_DIR / "_ui_inputs"
UI_INPUTS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

SAMPLE_IMAGE = DATA_DIR / "garden.jpg"

def inject_custom_css():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
    
    html, body, [class*="st-"] {
        font-family: 'Inter', sans-serif;
    }

    .stApp {
        background: linear-gradient(180deg, #0f172a 0%, #020617 100%);
        color: #f8fafc;
    }

    .main-title {
        font-size: 3rem;
        font-weight: 800;
        background: linear-gradient(90deg, #4ade80, #2dd4bf);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        margin-bottom: 0.2rem;
    }
    .sub-title {
        font-size: 1.2rem;
        color: #94a3b8;
        text-align: center;
        margin-bottom: 3rem;
    }

    .glass-card {
        background: rgba(30, 41, 59, 0.5);
        backdrop-filter: blur(12px);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 16px;
        padding: 2rem;
        margin-bottom: 2rem;
    }

    [data-testid="stSidebar"] {
        background-color: #0f172a;
        border-right: 1px solid rgba(255, 255, 255, 0.1);
    }

    .stButton > button {
        width: 100%;
        border-radius: 12px;
        padding: 0.75rem 1.5rem;
        font-weight: 600;
        transition: all 0.3s ease;
    }
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #22c55e 0%, #10b981 100%);
        border: none;
        box-shadow: 0 4px 12px rgba(34, 197, 94, 0.3);
    }

    .img-container {
        border-radius: 20px;
        overflow: hidden;
        border: 2px solid rgba(255, 255, 255, 0.1);
        box-shadow: 0 20px 50px rgba(0,0,0,0.5);
    }

    .plant-badge {
        display: inline-block;
        background: rgba(34, 197, 94, 0.1);
        color: #4ade80;
        border: 1px solid rgba(34, 197, 94, 0.3);
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.85rem;
        margin: 4px;
    }
    
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    </style>
    """, unsafe_allow_html=True)

def main():
    st.set_page_config(page_title="Garden AI | Design Paysager", layout="wide")
    if "rag_ready" not in st.session_state:
        st.session_state["rag_ready"] = False
    if "rag_path" not in st.session_state:
        st.session_state["rag_path"] = None
    inject_custom_css()

    # --- HEADER ---
    st.markdown('<h1 class="main-title">Garden AI</h1>', unsafe_allow_html=True)
    st.markdown('<p class="sub-title">Visualisez votre jardin idéal à partir des recommandations RAG</p>', unsafe_allow_html=True)

    # --- SIDEBAR : CONFIGURATION ---
    with st.sidebar:
        st.image("https://cdn-icons-png.flaticon.com/512/1518/1518965.png", width=80)
        st.title("Configuration")
        
        st.subheader("📸 Image Source")
        img_source = st.radio("Source", ["Image par défaut", "Télécharger une photo"], label_visibility="collapsed")
        
        if img_source == "Image par défaut":
            image_path = SAMPLE_IMAGE if SAMPLE_IMAGE.exists() else None
            if image_path:
                st.image(str(image_path), caption="Jardin actuel", use_container_width=True)
        else:
            uploaded_file = st.file_uploader("Choisir une photo...", type=["jpg", "jpeg", "png"])
            if uploaded_file:
                image_path = UI_INPUTS_DIR / "uploaded_garden.jpg"
                with open(image_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                st.image(str(image_path), caption="Photo chargée", use_container_width=True)
            else:
                image_path = None

        st.divider()
        
        st.subheader("🌱 Add plants only")
        exclude_lawn = st.checkbox("Exclure la pelouse du masque (bordures seules)", value=True)
        use_mask = st.checkbox("Utiliser le masque plantable (recommandé)", value=True)
        plant_density = st.select_slider(
            "Densité des plantations",
            options=["low", "medium", "high"],
            value="medium",
            format_func=lambda x: {"low": "Faible", "medium": "Moyenne", "high": "Forte"}[x],
        )
        
        st.divider()
        
        st.subheader("⚙️ Paramètres de Rendu")
        time_of_day = st.select_slider("Moment de la journée", options=["Jour", "Nuit"])
        night_intensity = st.slider("Intensité lumineuse (Nuit)", 0.0, 1.0, 0.5) if time_of_day == "Nuit" else 0.5
        
        st.subheader("🔧 Debug (optionnel)")
        use_seed_debug = st.checkbox("Seed fixe (debug A/B)", value=False, help="Reproductibilité : même image + même seed + autre RAG pour comparer l'influence du RAG.")
        seed_debug = None
        if use_seed_debug:
            seed_debug = st.number_input("Seed (debug)", min_value=0, max_value=2**31 - 1, value=42, step=1, format="%d")
        else:
            seed_debug = None
        
        st.divider()
        
        if not has_bfl_key():
            st.error("🔑 Clé API BFL manquante (BFL_API_KEY)")
        else:
            st.success("🔑 API BFL Connectée")

    # --- MAIN CONTENT : GÉNÉRATION ---
    col_left, col_right = st.columns([1, 1.2], gap="large")

    with col_left:
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        st.subheader("🚀 Générer le jardin")
        st.write("Choisissez une image (sidebar), puis lancez la génération. Un fichier RAG est optionnel pour personnaliser les plantes.")
        
        # RAG optionnel (masqué par défaut pour ne pas bloquer)
        with st.expander("📄 Fichier RAG (optionnel)", expanded=False):
            json_files = [f.name for f in DATA_DIR.glob("*.json")] if DATA_DIR.exists() else []
            selected_json = st.selectbox(
                "Fichier RAG",
                options=json_files if json_files else ["(Aucun)"],
                index=0,
            )
            if selected_json == "(Aucun)":
                selected_json = None
            uploaded_rag = st.file_uploader("Ou télécharger un JSON RAG", type=["json"])
            
            if uploaded_rag:
                rag_path = UI_INPUTS_DIR / "uploaded_rag.json"
                with open(rag_path, "wb") as f:
                    f.write(uploaded_rag.getbuffer())
                st.success("✓ RAG chargé")
            elif selected_json:
                rag_path = DATA_DIR / selected_json
            else:
                rag_path = None

            if rag_path and rag_path.exists():
                try:
                    with open(rag_path, "r", encoding="utf-8") as f:
                        rag_data = json.load(f)
                    plants = rag_data.get("garden", []) or rag_data.get("plants", [])
                    if plants:
                        st.write(f"**{len(plants)} plantes**")
                        st.session_state["rag_path"] = rag_path
                    else:
                        st.session_state["rag_path"] = None
                except Exception:
                    st.session_state["rag_path"] = None
            else:
                st.session_state["rag_path"] = None
        
        st.markdown('</div>', unsafe_allow_html=True)

        # BOUTON GÉNÉRER : actif dès qu'une image est disponible (RAG optionnel)
        if st.button("🚀 GÉNÉRER MON JARDIN IDÉAL", type="primary", use_container_width=True, 
                     disabled=not image_path):
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            try:
                status_text.text("Pipeline stable (add plants only) — masque + prompt RAG...")
                progress_bar.progress(20)
                
                rag_path = st.session_state.get("rag_path")  # optionnel : None = prompt par défaut
                return_debug = use_seed_debug
                out = generate_full_garden(
                    image_path=image_path,
                    outputs_dir=OUTPUTS_DIR,
                    exclude_lawn=exclude_lawn,
                    plant_density=plant_density,
                    use_mask=use_mask,
                    rag_path=rag_path if (rag_path and Path(rag_path).exists()) else None,
                    time_of_day="night" if time_of_day == "Nuit" else "day",
                    night_light_intensity=night_intensity,
                    return_debug=return_debug,
                    seed=seed_debug,
                )
                if return_debug and isinstance(out, tuple):
                    st.session_state["last_debug"] = {"path": str(out[0]), "info": out[1]}
                else:
                    st.session_state.pop("last_debug", None)
                
                progress_bar.progress(100)
                status_text.text("Génération terminée avec succès !")
                time.sleep(1)
                st.rerun()
                
            except Exception as e:
                st.error(f"Erreur lors de la génération : {e}")
                st.exception(e)

    with col_right:
        st.subheader("🖼️ Visualisation")
        
        tab1, tab2 = st.tabs(["✨ Résultat Final", "🔍 Comparaison"])
        
        final_img_path = OUTPUTS_DIR / ("final_garden_night.png" if time_of_day == "Nuit" else "final_garden.png")
        
        with tab1:
            if final_img_path.exists():
                st.markdown('<div class="img-container">', unsafe_allow_html=True)
                st.image(str(final_img_path), use_container_width=True)
                st.markdown('</div>', unsafe_allow_html=True)
                
                with open(final_img_path, "rb") as file:
                    st.download_button(
                        label="📥 Télécharger mon jardin",
                        data=file,
                        file_name=f"mon_jardin_ideal_{datetime.now().strftime('%Y%m%d_%H%M')}.png",
                        mime="image/png",
                    )
            else:
                st.info("Votre jardin idéal apparaîtra ici après la génération.")
                if image_path and image_path.exists():
                    st.image(str(image_path), caption="Aperçu de votre jardin actuel", use_container_width=True)

        with tab2:
            if final_img_path.exists() and image_path and image_path.exists():
                c1, c2 = st.columns(2)
                with c1:
                    st.write("**Avant**")
                    st.image(str(image_path), use_container_width=True)
                with c2:
                    st.write("**Après**")
                    st.image(str(final_img_path), use_container_width=True)
            else:
                st.info("Générez d'abord une image pour comparer.")

        # Debug : afficher seed, white_pct, mask_mode, strength_final, guidance, steps, plantes
        if st.session_state.get("last_debug"):
            db = st.session_state["last_debug"]
            info = db.get("info") or {}
            with st.expander("🔧 Dernière génération (debug)"):
                st.write("**Seed:**", info.get("seed", "—"))
                st.write("**white_pct:**", info.get("white_pct_bin") or info.get("white_pct"), "**mask_mode:**", info.get("mask_mode", "—"))
                st.write("**strength_final:**", info.get("strength", "—"), "**guidance:**", info.get("guidance", "—"), "**steps:**", info.get("steps", "—"))
                st.write("**Plantes RAG:**", info.get("rag_plants_used", []) or "—")
                st.write("**Output:**", db.get("path", "—"))

    # --- FOOTER ---
    st.divider()
    st.caption("Garden AI v2.0 - Propulsé par FLUX.1 Fill & RAG Technology")

if __name__ == "__main__":
    main()
