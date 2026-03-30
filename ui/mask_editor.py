"""
Éditeur de masques interactif — permet de repositionner les plantes après génération.
Utilise Streamlit + HTML/JS canvas pour le drag & drop des zones de masque.
"""
from __future__ import annotations

import base64
import io
import json
from pathlib import Path
from typing import Any

import streamlit as st
import streamlit.components.v1 as components
from PIL import Image

MAX_DISPLAY_W = 700
JPEG_QUALITY = 85
# Même clé que st.query_params / secours (ne pas renommer sans mettre à jour app.py)
EDITOR_BBOX_PARAM = "editor_bbox"


def _rgb_image_to_jpeg_data_url(img: Image.Image) -> tuple[str, int, int]:
    """Encode une image RVB en JPEG base64 (data URL payload) + dimensions."""
    rgb = img if img.mode == "RGB" else img.convert("RGB")
    w, h = rgb.size
    buf = io.BytesIO()
    rgb.save(buf, format="JPEG", quality=JPEG_QUALITY)
    return base64.b64encode(buf.getvalue()).decode(), w, h


def _streamlit_page_url() -> str:
    try:
        url = getattr(getattr(st, "context", None), "url", None)
        return str(url).strip() if url else ""
    except Exception:
        return ""


def render_mask_editor(
    base_image_path: str | Path,
    steps: list[dict[str, Any]],
) -> None:
    """Affiche l’éditeur interactif (glisser-déposer des bboxes)."""
    if not steps:
        st.info("Lancez d'abord une génération pour utiliser l'éditeur.")
        return

    with Image.open(Path(base_image_path)) as pil_img:
        img_b64, img_w, img_h = _rgb_image_to_jpeg_data_url(pil_img)

    # Prépare les données des plantes pour le JS
    plants_data = []
    for s in steps:
        bbox = s.get("bbox", [0, 0, 100, 100])
        plants_data.append({
            "plant_id": s["plant_id"],
            "name": s["name"],
            "index": s["index"],
            "x1": bbox[0], "y1": bbox[1],
            "x2": bbox[2], "y2": bbox[3],
            "color": _zone_color(s["index"]),
        })

    plants_json = json.dumps(plants_data)
    streamlit_page_url_js = json.dumps(_streamlit_page_url())
    editor_param_js = json.dumps(EDITOR_BBOX_PARAM)

    html = f"""
    <style>
        #editor-container {{
            position: relative;
            display: inline-block;
            cursor: default;
            user-select: none;
            -webkit-user-select: none;
            touch-action: none;
        }}
        #garden-canvas {{
            border: 2px solid #4ade80;
            border-radius: 8px;
            display: block;
            touch-action: none;
            -webkit-tap-highlight-color: transparent;
            max-width: 100%;
            height: auto;
        }}
        #info-panel {{
            margin-top: 10px;
            color: #94a3b8;
            font-family: Inter, sans-serif;
            font-size: 13px;
        }}
        .plant-label {{
            position: absolute;
            background: rgba(0,0,0,0.7);
            color: white;
            font-size: 11px;
            padding: 2px 6px;
            border-radius: 4px;
            pointer-events: none;
            font-family: Inter, sans-serif;
        }}
        #save-btn {{
            margin-top: 12px;
            background: linear-gradient(135deg, #22c55e, #10b981);
            color: white;
            border: none;
            padding: 10px 24px;
            border-radius: 10px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            width: 100%;
        }}
        #save-btn:hover {{ opacity: 0.9; }}
        #legend {{
            margin-top: 8px;
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            gap: 4px;
            font-family: Inter, sans-serif;
            font-size: 11px;
            color: #cbd5e1;
        }}
        .legend-dot {{
            width: 12px;
            height: 12px;
            border-radius: 3px;
        }}
    </style>

    <div id="editor-container">
        <canvas id="garden-canvas"></canvas>
        <div id="info-panel">🖱️ / 👆 Glisse une zone colorée pour déplacer la plante</div>
        <div id="legend"></div>
        <button id="save-btn" onclick="savePositions()">💾 Appliquer les nouveaux emplacements</button>
    </div>

    <script>
    const IMG_W = {img_w};
    const IMG_H = {img_h};
    const PLANTS = {plants_json};
    const STREAMLIT_PAGE_URL = {streamlit_page_url_js};
    const EDITOR_Q = {editor_param_js};

    const canvas = document.getElementById('garden-canvas');
    const ctx = canvas.getContext('2d');

    const MAX_W = {MAX_DISPLAY_W};
    const scale = Math.min(1.0, MAX_W / IMG_W);
    canvas.width  = Math.round(IMG_W * scale);
    canvas.height = Math.round(IMG_H * scale);

    // Charger l'image
    const img = new Image();
    img.src = 'data:image/jpeg;base64,{img_b64}';

    // État des rectangles (coordonnées écran)
    let rects = PLANTS.map(p => ({{
        ...p,
        sx: p.x1 * scale,
        sy: p.y1 * scale,
        sw: (p.x2 - p.x1) * scale,
        sh: (p.y2 - p.y1) * scale,
        dragging: false,
        dragOffX: 0,
        dragOffY: 0,
    }}));

    // Légende
    const legend = document.getElementById('legend');
    rects.forEach(r => {{
        const item = document.createElement('div');
        item.className = 'legend-item';
        item.innerHTML = `<div class="legend-dot" style="background:${{r.color}}"></div>${{r.name.substring(0,20)}}`;
        legend.appendChild(item);
    }});

    function draw() {{
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        if (img.complete) ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

        rects.forEach(r => {{
            // Rectangle semi-transparent
            ctx.fillStyle = r.color + '44';
            ctx.fillRect(r.sx, r.sy, r.sw, r.sh);
            // Bordure
            ctx.strokeStyle = r.color;
            ctx.lineWidth = r.dragging ? 3 : 2;
            ctx.setLineDash(r.dragging ? [] : [5, 3]);
            ctx.strokeRect(r.sx, r.sy, r.sw, r.sh);
            ctx.setLineDash([]);
            // Numéro
            ctx.fillStyle = r.color;
            ctx.font = 'bold 13px Inter';
            ctx.fillText(`${{r.index + 1}}`, r.sx + 5, r.sy + 16);
        }});
    }}

    if (img.complete) draw();
    else img.onload = draw;

    // Marge invisible pour faciliter la saisie au doigt (petites bboxes)
    const HIT_PAD = 28;

    function getRect(x, y) {{
        for (let i = rects.length - 1; i >= 0; i--) {{
            const r = rects[i];
            if (x >= r.sx - HIT_PAD && x <= r.sx + r.sw + HIT_PAD
                && y >= r.sy - HIT_PAD && y <= r.sy + r.sh + HIT_PAD) {{
                return r;
            }}
        }}
        return null;
    }}

    function clientToCanvas(e) {{
        const rect = canvas.getBoundingClientRect();
        const sx = e.clientX - rect.left;
        const sy = e.clientY - rect.top;
        const scaleX = canvas.width / rect.width;
        const scaleY = canvas.height / rect.height;
        return {{ x: sx * scaleX, y: sy * scaleY }};
    }}

    let activePointerId = null;

    function startDrag(x, y, pointerId) {{
        const r = getRect(x, y);
        if (r) {{
            r.dragging = true;
            r.dragOffX = x - r.sx;
            r.dragOffY = y - r.sy;
            activePointerId = pointerId;
            canvas.style.cursor = 'grabbing';
            try {{ canvas.setPointerCapture(pointerId); }} catch (err) {{}}
            return true;
        }}
        return false;
    }}

    function moveDrag(x, y) {{
        const dragging = rects.find(r => r.dragging);
        if (dragging) {{
            dragging.sx = Math.max(0, Math.min(canvas.width - dragging.sw, x - dragging.dragOffX));
            dragging.sy = Math.max(0, Math.min(canvas.height - dragging.sh, y - dragging.dragOffY));
            draw();
        }}
    }}

    function endDrag(pointerId) {{
        if (activePointerId !== null && pointerId !== undefined && pointerId !== activePointerId) return;
        rects.forEach(r => r.dragging = false);
        activePointerId = null;
        canvas.style.cursor = 'default';
        try {{
            if (pointerId !== undefined) canvas.releasePointerCapture(pointerId);
        }} catch (err) {{}}
    }}

    // Pointer Events = souris + doigt + stylet (évite les conflits scroll / iframe)
    canvas.addEventListener('pointerdown', e => {{
        if (e.pointerType === 'mouse' && e.button !== 0) return;
        e.preventDefault();
        try {{ canvas.focus({{ preventScroll: true }}); }} catch (err) {{ canvas.focus(); }}
        const {{ x, y }} = clientToCanvas(e);
        startDrag(x, y, e.pointerId);
    }});

    canvas.addEventListener('pointermove', e => {{
        const {{ x, y }} = clientToCanvas(e);
        moveDrag(x, y);
        if (!rects.some(r => r.dragging)) {{
            canvas.style.cursor = getRect(x, y) ? 'grab' : 'default';
        }}
    }});

    canvas.addEventListener('pointerup', e => {{
        e.preventDefault();
        endDrag(e.pointerId);
    }});

    canvas.addEventListener('pointercancel', e => {{
        endDrag(e.pointerId);
    }});

    canvas.addEventListener('lostpointercapture', e => {{
        rects.forEach(r => r.dragging = false);
        activePointerId = null;
        canvas.style.cursor = 'default';
    }});

    canvas.setAttribute('tabindex', '0');

    function copyB64Fallback(b64) {{
        const ta = document.createElement('textarea');
        ta.value = b64;
        ta.style.position = 'fixed';
        ta.style.left = '-9999px';
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        try {{ document.execCommand('copy'); }} catch (e) {{}}
        ta.remove();
    }}

    function savePositions() {{
        const updated = rects.map(r => ({{
            plant_id: r.plant_id,
            name: r.name,
            index: r.index,
            bbox: [
                Math.round(r.sx / scale),
                Math.round(r.sy / scale),
                Math.round((r.sx + r.sw) / scale),
                Math.round((r.sy + r.sh) / scale),
            ]
        }}));
        const json = JSON.stringify(updated);
        const b64 = btoa(unescape(encodeURIComponent(json)));
        const info = document.getElementById('info-panel');

        function tryAssign(win) {{
            try {{
                const href = win.location.href;
                if (!href || href.startsWith('blob:') || href === 'about:blank') return false;
                const u = new URL(href);
                u.searchParams.set(EDITOR_Q, b64);
                win.location.assign(u.toString());
                info.innerHTML = '⏳ Mise à jour des emplacements…';
                return true;
            }} catch (e) {{
                return false;
            }}
        }}

        // parent = page Streamlit (même origine) ; top = souvent l’aperçu Cursor (bloqué) — parent en premier
        const candidates = [];
        try {{
            if (window.parent && window.parent !== window) candidates.push(window.parent);
        }} catch (e) {{}}
        candidates.push(window);
        try {{
            if (window.top && window.top !== window && candidates.indexOf(window.top) < 0)
                candidates.push(window.top);
        }} catch (e) {{}}

        for (const w of candidates) {{
            if (tryAssign(w)) return;
        }}

        if (STREAMLIT_PAGE_URL && STREAMLIT_PAGE_URL.length > 8) {{
            try {{
                const u = new URL(STREAMLIT_PAGE_URL);
                u.searchParams.set(EDITOR_Q, b64);
                const a = document.createElement('a');
                a.href = u.toString();
                a.target = '_top';
                a.rel = 'noopener noreferrer';
                document.body.appendChild(a);
                a.click();
                a.remove();
                info.innerHTML = '⏳ Ouverture / rechargement…';
                return;
            }} catch (e) {{}}
        }}

        const doneMsg = 'Code copié. Déplie <b>Secours : appliquer sans recharger</b> sous le canevas, '
            + 'colle (Ctrl+V), clique <b>Enregistrer les positions collées</b>, puis <b>Regénérer</b>. '
            + 'Ou ouvre l’app dans Safari/Chrome sur <code>http://localhost:8501</code>.';
        if (navigator.clipboard && navigator.clipboard.writeText) {{
            navigator.clipboard.writeText(b64)
                .then(() => {{ info.innerHTML = doneMsg; }})
                .catch(() => {{ copyB64Fallback(b64); info.innerHTML = doneMsg; }});
        }} else {{
            copyB64Fallback(b64);
            info.innerHTML = doneMsg;
        }}
    }}
    </script>
    """

    scale_ui = min(1.0, MAX_DISPLAY_W / max(img_w, 1))
    iframe_h = int(round(img_h * scale_ui)) + 220
    components.html(html, height=min(iframe_h, 1600), scrolling=True)


def _zone_color(index: int) -> str:
    colors = [
        "#4ade80", "#f59e0b", "#60a5fa", "#f472b6",
        "#a78bfa", "#34d399", "#fb923c", "#818cf8",
        "#e879f9", "#2dd4bf", "#facc15", "#f87171",
        "#a3e635", "#38bdf8", "#c084fc",
    ]
    return colors[index % len(colors)]
