"""
Garden AI — Interface Streamlit v3 (sans QCM).
jardin_complet.json est chargé automatiquement au démarrage.
"""
from __future__ import annotations

import base64
import json
import shutil
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from image_generation.scene_generator import generate_scene
from image_generation.scene_generator_v2 import dispatch_generation
from image_generation.bfl_provider import has_bfl_key
from image_generation.utils_rag import load_rag
from ui.mask_editor import EDITOR_BBOX_PARAM, render_mask_editor

OUTPUTS_DIR = PROJECT_ROOT / "outputs"
DATA_DIR    = PROJECT_ROOT / "data"
UI_INPUTS   = OUTPUTS_DIR / "_ui_inputs"
for d in [OUTPUTS_DIR, UI_INPUTS]:
    d.mkdir(parents=True, exist_ok=True)

SAMPLE_IMAGE   = DATA_DIR / "garden.jpg"
JARDIN_COMPLET = DATA_DIR / "jardin_complet.json"
RAG_PATH       = OUTPUTS_DIR / "current_rag_selection.json"
SCENE_SEQ_JSON = OUTPUTS_DIR / "scene_sequential.json"


def inject_css():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
    html,body,[class*="st-"]{font-family:'Inter',sans-serif;}
    .stApp{background:linear-gradient(180deg,#0f172a 0%,#020617 100%);color:#f8fafc;}
    .main-title{font-size:2.8rem;font-weight:800;
        background:linear-gradient(90deg,#4ade80,#2dd4bf);
        -webkit-background-clip:text;-webkit-text-fill-color:transparent;
        text-align:center;margin-bottom:.2rem;}
    .sub-title{font-size:1.1rem;color:#94a3b8;text-align:center;margin-bottom:2rem;}
    .glass{background:rgba(30,41,59,.5);backdrop-filter:blur(12px);
        border:1px solid rgba(255,255,255,.1);border-radius:16px;
        padding:1.5rem;margin-bottom:1.5rem;}
    [data-testid="stSidebar"]{background-color:#0f172a;
        border-right:1px solid rgba(255,255,255,.1);}
    .stButton>button{border-radius:12px;font-weight:600;transition:all .3s;}
    .stButton>button[kind="primary"]{
        background:linear-gradient(135deg,#22c55e,#10b981);
        border:none;box-shadow:0 4px 12px rgba(34,197,94,.3);}
    .badge{display:inline-block;background:rgba(34,197,94,.1);color:#4ade80;
        border:1px solid rgba(34,197,94,.3);padding:3px 10px;
        border-radius:20px;font-size:.82rem;margin:3px;}
    .img-box{border-radius:16px;overflow:hidden;
        border:2px solid rgba(255,255,255,.1);
        box-shadow:0 20px 50px rgba(0,0,0,.5);}
    #MainMenu{visibility:hidden;}footer{visibility:hidden;}
    </style>""", unsafe_allow_html=True)


def _get_steps_list() -> list[dict[str, Any]]:
    """Étapes en session ou rechargées depuis le JSON séquentiel sur disque."""
    steps = list(st.session_state.get("steps", []))
    if steps:
        return steps
    if SCENE_SEQ_JSON.exists():
        with open(SCENE_SEQ_JSON, encoding="utf-8") as fh:
            return json.load(fh).get("steps", [])
    return []


def _sorted_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(steps, key=lambda s: int(s.get("index", 0)))


def _shared_generation_kwargs(
    image_path: Path | str,
    *,
    time_of_day: str,
    night_int: float,
    max_plants: int,
) -> dict[str, Any]:
    """Paramètres communs à dispatch_generation / generate_scene."""
    return {
        "image_path": image_path,
        "rag_json_path": st.session_state["rag_path"],
        "outputs_dir": OUTPUTS_DIR,
        "time_of_day": "night" if time_of_day == "Nuit" else "day",
        "night_light_intensity": night_int,
        "max_plants": max_plants,
        "debug": True,
    }


def _decode_editor_bbox_updates(raw_b64: str) -> list | None:
    try:
        decoded = base64.b64decode(str(raw_b64).encode("ascii")).decode("utf-8")
        data = json.loads(decoded)
        return data if isinstance(data, list) else None
    except (ValueError, json.JSONDecodeError, TypeError):
        return None


def _merge_editor_updates_into_steps(updates: list) -> bool:
    by_pid = {
        str(u["plant_id"]): u["bbox"]
        for u in updates
        if isinstance(u, dict) and "plant_id" in u and "bbox" in u
    }
    if not by_pid:
        return False
    steps = _get_steps_list()
    if not steps:
        return False
    changed = False
    for s in steps:
        pid = str(s.get("plant_id", ""))
        if pid in by_pid:
            s["bbox"] = by_pid[pid]
            changed = True
    if changed:
        st.session_state["steps"] = steps
    return changed


def _apply_editor_b64_to_steps(b64_str: str) -> bool:
    updates = _decode_editor_bbox_updates(b64_str.strip())
    if updates is None:
        return False
    return _merge_editor_updates_into_steps(updates)


def _apply_editor_bbox_from_url():
    """Reçoit les bboxes repositionnées depuis l’éditeur (query param après rechargement)."""
    if EDITOR_BBOX_PARAM not in st.query_params:
        return
    raw = st.query_params[EDITOR_BBOX_PARAM]
    if isinstance(raw, list):
        raw = raw[0]
    updates = _decode_editor_bbox_updates(str(raw))
    if updates is None:
        st.error("Paramètre d’éditeur invalide (editor_bbox).")
        st.query_params.pop(EDITOR_BBOX_PARAM, None)
        st.rerun()
        return
    _merge_editor_updates_into_steps(updates)
    st.query_params.pop(EDITOR_BBOX_PARAM, None)
    st.rerun()


def _auto_load_jardin():
    """Charge jardin_complet.json automatiquement au premier chargement."""
    if st.session_state.get("rag_ready"):
        return
    if not JARDIN_COMPLET.exists():
        st.error(f"❌ Fichier introuvable : {JARDIN_COMPLET}")
        return
    try:
        _, plants = load_rag(JARDIN_COMPLET)
        shutil.copy2(JARDIN_COMPLET, RAG_PATH)
        st.session_state["rag_ready"]       = True
        st.session_state["rag_path"]        = str(RAG_PATH)
        st.session_state["selected_plants"] = [p["name"] for p in plants]
    except Exception as e:
        st.error(f"Erreur chargement jardin_complet.json : {e}")


def main():
    st.set_page_config(page_title="Garden AI", layout="wide")
    inject_css()

    st.markdown('<h1 class="main-title">Garden AI</h1>', unsafe_allow_html=True)
    st.markdown(
        '<p class="sub-title">Génération de jardin plante par plante — Flux Fill</p>',
        unsafe_allow_html=True)

    # Chargement auto jardin_complet.json dès le démarrage
    _auto_load_jardin()
    _apply_editor_bbox_from_url()

    # ── SIDEBAR ─────────────────────────────────────────────
    with st.sidebar:
        st.title("⚙️ Configuration")

        st.subheader("📸 Photo du jardin")
        img_src = st.radio("", ["Image par défaut", "Uploader une photo"],
                           label_visibility="collapsed")
        if img_src == "Image par défaut":
            image_path = SAMPLE_IMAGE
            if image_path.exists():
                st.image(str(image_path), use_container_width=True)
        else:
            f = st.file_uploader("Choisir...", type=["jpg","jpeg","png"])
            if f:
                image_path = UI_INPUTS / "uploaded_garden.jpg"
                image_path.write_bytes(f.read())
                st.image(str(image_path), use_container_width=True)
            else:
                image_path = None

        st.divider()

        mode_label = st.selectbox("Mode de génération", [
            "🌱 Séquentiel (plante par plante)",
            "⚡ Global (un seul appel BFL)",
        ])
        st.session_state["mode"] = (
            "sequential" if "Séquentiel" in mode_label else "global"
        )
        rag_count = len(st.session_state.get("selected_plants", [])) or 15
        max_plants  = st.slider("Nb max de plantes", 1, rag_count, rag_count)
        time_of_day = st.select_slider("Heure", options=["Jour","Nuit"])
        night_int   = (
            st.slider("Intensité nuit", 0.0, 1.0, 0.5)
            if time_of_day == "Nuit" else 0.5
        )

        st.divider()
        st.subheader("📂 Changer les plantes")
        st.caption("jardin_complet.json chargé auto. Upload un autre JSON si besoin.")
        up_rag = st.file_uploader("Autre JSON RAG", type=["json"])
        if up_rag:
            try:
                with tempfile.NamedTemporaryFile(
                    suffix=".json", delete=False
                ) as tmp:
                    tmp.write(up_rag.read())
                    tmp_path = Path(tmp.name)
                try:
                    _, plants = load_rag(tmp_path)
                    shutil.copy2(tmp_path, RAG_PATH)
                    st.session_state["rag_ready"] = True
                    st.session_state["rag_path"] = str(RAG_PATH)
                    st.session_state["selected_plants"] = [p["name"] for p in plants]
                    st.success(f"✅ {len(plants)} plantes depuis {up_rag.name}")
                finally:
                    tmp_path.unlink(missing_ok=True)
            except Exception as e:
                st.error(f"Erreur : {e}")

        st.divider()
        if not has_bfl_key():
            st.warning("⚠️ BFL_API_KEY manquante → mode MOCK actif")
        else:
            st.success("🔑 API BFL connectée")

    # ── MAIN ────────────────────────────────────────────────
    col_left, col_right = st.columns([1, 1.3], gap="large")

    with col_left:
        st.markdown('<div class="glass">', unsafe_allow_html=True)
        st.subheader("🌿 Plantes chargées")

        plants_list = st.session_state.get("selected_plants", [])
        if plants_list:
            st.markdown(
                "".join(f'<span class="badge">{p}</span>' for p in plants_list),
                unsafe_allow_html=True)
            st.caption(f"{len(plants_list)} plantes — jardin_complet.json")
        else:
            st.info("Chargement...")

        st.markdown('</div>', unsafe_allow_html=True)

        # Bouton Générer
        can_go = bool(
            image_path
            and st.session_state.get("rag_ready")
            and plants_list
        )
        if not image_path:
            st.warning("Sélectionne une image dans la sidebar.")

        if st.button("🚀 GÉNÉRER MON JARDIN", type="primary",
                     use_container_width=True, disabled=not can_go):
            prog  = st.progress(0)
            msg   = st.empty()
            mode  = st.session_state.get("mode", "sequential")
            msg.text(f"⏳ Génération {'séquentielle' if mode=='sequential' else 'globale'}...")
            prog.progress(10)
            try:
                gkw = _shared_generation_kwargs(
                    image_path,
                    time_of_day=time_of_day,
                    night_int=night_int,
                    max_plants=max_plants,
                )
                scene = dispatch_generation(**gkw, mode=mode)
                st.session_state["steps"] = scene.get("steps", [])
                prog.progress(100)
                msg.text("✅ Génération terminée !")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"❌ Erreur : {e}")
                st.exception(e)

    with col_right:
        final = OUTPUTS_DIR / (
            "final_garden_night.png" if time_of_day=="Nuit" else "final_garden.png"
        )
        tab_r, tab_ab, tab_steps, tab_mask, tab_editor = st.tabs(
            ["✨ Résultat", "🔍 Avant/Après", "🌿 Étapes", "🗺️ Masque", "✏️ Éditeur"])

        with tab_r:
            if final.exists():
                st.markdown('<div class="img-box">', unsafe_allow_html=True)
                st.image(str(final), use_container_width=True)
                st.markdown('</div>', unsafe_allow_html=True)
                with open(final,"rb") as fh:
                    st.download_button("📥 Télécharger", fh,
                        f"jardin_{datetime.now().strftime('%Y%m%d_%H%M')}.png",
                        "image/png")
            else:
                st.info("Le résultat apparaîtra ici après la génération.")
                if image_path and Path(str(image_path)).exists():
                    st.image(str(image_path), caption="Jardin actuel",
                             use_container_width=True)

        with tab_ab:
            if final.exists() and image_path and Path(str(image_path)).exists():
                c1,c2 = st.columns(2)
                c1.write("**Avant**"); c1.image(str(image_path), use_container_width=True)
                c2.write("**Après**"); c2.image(str(final), use_container_width=True)
            else:
                st.info("Générez d'abord une image.")

        with tab_steps:
            steps = _get_steps_list()
            if steps:
                st.write(f"**{len(steps)} plantes générées :**")
                for s in steps:
                    with st.expander(
                        f"🌱 {s['index']+1}. {s['name']} ({s.get('zone_hint','?')})"
                    ):
                        c1,c2 = st.columns(2)
                        mp,cp = s.get("mask_path",""), s.get("composite_path","")
                        if mp and Path(mp).exists():
                            c1.write("Masque"); c1.image(mp, use_container_width=True)
                        if cp and Path(cp).exists():
                            c2.write("Résultat"); c2.image(cp, use_container_width=True)
                        m1,m2,m3 = st.columns(3)
                        m1.metric("Zone",     s.get("zone_hint","—"))
                        m2.metric("Couleur",  s.get("color","—") or "—")
                        m3.metric("Strength", f"{s.get("strength",0):.2f}")
                        st.caption(f"Prompt : {s.get("prompt","")[:250]}...")
            else:
                st.info("Les étapes apparaîtront après une génération séquentielle.")

        with tab_mask:
            dbg = OUTPUTS_DIR / "mask_debug.png"
            if dbg.exists():
                st.image(str(dbg), use_container_width=True)
            else:
                st.info("Le masque apparaîtra après la génération.")

        with tab_editor:
            steps = _get_steps_list()
            if steps and image_path and Path(str(image_path)).exists():
                st.write(
                    "**Glisse les rectangles colorés** sur le canevas (souris ou doigt), puis **Appliquer** ; "
                    "ensuite **Regénérer**. Dans l’aperçu intégré (Cursor, etc.), ouvre l’app dans **Safari/Chrome** "
                    "sur `localhost` si le rechargement est bloqué — ou utilise le **secours** sous le canevas."
                )
                if st.session_state.get("mode") != "sequential":
                    st.warning(
                        "Le repositionnement s’applique au **mode séquentiel**. "
                        "Repasse en séquentiel dans la barre latérale pour regénérer avec des bboxes."
                    )
                render_mask_editor(
                    base_image_path=final if final.exists() else image_path,
                    steps=_sorted_steps(steps),
                )
                with st.expander("📌 Secours : appliquer sans recharger la page", expanded=False):
                    st.caption(
                        "Si le bouton vert *Appliquer* ne fait rien : après avoir cliqué dessus, "
                        "un code est souvent copié automatiquement — sinon refais *Appliquer* puis colle ici (Ctrl+V)."
                    )
                    manual_b64 = st.text_input(
                        "Code positions (base64)",
                        key="editor_bbox_manual_fallback",
                        placeholder="Colle le code ici…",
                        label_visibility="collapsed",
                    )
                    if st.button("Enregistrer les positions collées", key="editor_bbox_manual_apply"):
                        if _apply_editor_b64_to_steps(manual_b64):
                            st.success("Positions enregistrées — clique **Regénérer**.")
                            st.rerun()
                        elif manual_b64.strip():
                            st.error("Code illisible ou vide.")
                regen = st.button(
                    "🔄 Regénérer le jardin (positions actuelles des étapes)",
                    key="regen_bbox_steps",
                    disabled=(
                        st.session_state.get("mode") != "sequential"
                        or not st.session_state.get("rag_ready")
                        or not can_go
                    ),
                )
                if regen:
                    bbox_overrides = [s.get("bbox") for s in _sorted_steps(_get_steps_list())]
                    prog = st.progress(0)
                    msg = st.empty()
                    msg.text("⏳ Regénération avec les bboxes ajustées…")
                    prog.progress(15)
                    try:
                        gkw = _shared_generation_kwargs(
                            image_path,
                            time_of_day=time_of_day,
                            night_int=night_int,
                            max_plants=max_plants,
                        )
                        scene = generate_scene(
                            **gkw,
                            mode="sequential",
                            bbox_overrides=bbox_overrides,
                        )
                        st.session_state["steps"] = scene.get("steps", [])
                        prog.progress(100)
                        msg.text("✅ Regénération terminée.")
                        time.sleep(0.8)
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ {e}")
                        st.exception(e)
            else:
                st.info("Génère d'abord un jardin pour accéder à l'éditeur.")

    st.divider()
    st.caption("Garden AI v3 — Flux.1 Fill | génération plante par plante")


if __name__ == "__main__":
    main()
