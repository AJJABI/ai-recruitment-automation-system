"""
test_ui.py — Dashboard Recrutement IA
Affichage résultats CV · Motivation · Matching sur une seule page
"""
import os
import sys
import json
import tempfile
import logging
import traceback
from pathlib import Path
from datetime import datetime

import streamlit as st

st.set_page_config(
    page_title="Recrutement IA",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Google Fonts + CSS ────────────────────────────────────────────────────────
# st.html() injecte le HTML brut sans passer par le parser Markdown de Streamlit,
# ce qui garantit que <style> et <link> sont bien interprétés par le navigateur.
st.html("""
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet">
<style>
* { box-sizing: border-box; }
html, body, [data-testid="stAppViewContainer"] {
    background: #0d0f14 !important;
    font-family: 'DM Sans', sans-serif;
}
[data-testid="stAppViewContainer"] > .main { padding: 0 !important; }
[data-testid="block-container"] { padding: 1.2rem 1.8rem !important; max-width: 100% !important; }
h1,h2,h3,h4 { font-family: 'Syne', sans-serif !important; }

/* ── TOPBAR ── */
.topbar {
    display: flex; align-items: center; justify-content: space-between;
    background: linear-gradient(90deg, #111420 0%, #161b2e 100%);
    border: 1px solid #1e2540;
    border-radius: 14px;
    padding: 1rem 1.6rem;
    margin-bottom: 1.4rem;
}
.topbar-title { font-family: 'Syne', sans-serif; font-size: 1.3rem; font-weight: 800;
    color: #fff; letter-spacing: -0.5px; }
.topbar-title span { color: #4f8ef7; }
.topbar-sub { font-size: 0.78rem; color: #6b7a9e; margin-top: 2px; }
.topbar-badge {
    background: #1a2040; border: 1px solid #2a3460;
    border-radius: 8px; padding: 0.35rem 0.8rem;
    font-size: 0.78rem; color: #4f8ef7; font-weight: 600;
}

/* ── CARDS ── */
.card {
    background: #111420;
    border: 1px solid #1e2540;
    border-radius: 14px;
    padding: 1.1rem 1.3rem;
    height: 100%;
}
.card-header {
    display: flex; align-items: center; gap: 0.5rem;
    font-family: 'Syne', sans-serif; font-size: 0.82rem;
    font-weight: 700; color: #4f8ef7;
    text-transform: uppercase; letter-spacing: 1px;
    margin-bottom: 1rem;
    padding-bottom: 0.6rem;
    border-bottom: 1px solid #1e2540;
}

/* ── SCORE RING ── */
.score-ring-wrap { text-align: center; padding: 0.5rem 0; }
.score-ring {
    display: inline-flex; flex-direction: column;
    align-items: center; justify-content: center;
    width: 110px; height: 110px; border-radius: 50%;
    border: 4px solid #1e2540;
    position: relative;
}
.score-ring.high  { border-color: #22c55e; box-shadow: 0 0 20px rgba(34,197,94,0.2); }
.score-ring.medium{ border-color: #f59e0b; box-shadow: 0 0 20px rgba(245,158,11,0.2); }
.score-ring.low   { border-color: #ef4444; box-shadow: 0 0 20px rgba(239,68,68,0.2); }
.score-num { font-family: 'Syne', sans-serif; font-size: 2rem; font-weight: 800; color: #fff; line-height: 1; }
.score-label { font-size: 0.65rem; color: #6b7a9e; text-transform: uppercase; letter-spacing: 0.5px; }

/* ── DECISION BANNER ── */
.decision-banner {
    display: flex; align-items: center; justify-content: center; gap: 1rem;
    border-radius: 12px; padding: 1rem 1.5rem;
    margin-bottom: 0.8rem;
}
.decision-ENTRETIEN  { background: rgba(34,197,94,0.1);  border: 1px solid rgba(34,197,94,0.3); }
.decision-EN_ATTENTE { background: rgba(245,158,11,0.1); border: 1px solid rgba(245,158,11,0.3); }
.decision-REJETE     { background: rgba(239,68,68,0.1);  border: 1px solid rgba(239,68,68,0.3); }
.decision-text { font-family: 'Syne', sans-serif; font-size: 1.4rem; font-weight: 800; }
.decision-ENTRETIEN  .decision-text { color: #22c55e; }
.decision-EN_ATTENTE .decision-text { color: #f59e0b; }
.decision-REJETE     .decision-text { color: #ef4444; }

/* ── METRIC ROW ── */
.metric-row { display: flex; gap: 0.6rem; margin-bottom: 0.7rem; flex-wrap: wrap; }
.metric-pill {
    flex: 1; min-width: 80px;
    background: #161b2e; border: 1px solid #1e2540; border-radius: 10px;
    padding: 0.55rem 0.7rem; text-align: center;
}
.metric-pill .mp-val { font-family: 'Syne', sans-serif; font-size: 1.1rem; font-weight: 700; color: #fff; }
.metric-pill .mp-lbl { font-size: 0.65rem; color: #6b7a9e; margin-top: 2px; }

/* ── PROGRESS BAR ── */
.prog-wrap { margin-bottom: 0.55rem; }
.prog-label { display: flex; justify-content: space-between;
    font-size: 0.72rem; color: #9aa5c4; margin-bottom: 3px; }
.prog-track { background: #1e2540; border-radius: 99px; height: 7px; overflow: hidden; }
.prog-fill   { border-radius: 99px; height: 100%; transition: width 0.6s; }
.prog-high   { background: linear-gradient(90deg,#22c55e,#4ade80); }
.prog-medium { background: linear-gradient(90deg,#f59e0b,#fcd34d); }
.prog-low    { background: linear-gradient(90deg,#ef4444,#f87171); }
.prog-blue   { background: linear-gradient(90deg,#4f8ef7,#818cf8); }

/* ── SKILL TAGS ── */
.tags-wrap { display: flex; flex-wrap: wrap; gap: 0.3rem; margin-top: 0.4rem; }
.tag { padding: 0.2rem 0.55rem; border-radius: 6px; font-size: 0.72rem; font-weight: 500; }
.tag-green { background: rgba(34,197,94,0.12); color: #4ade80; border: 1px solid rgba(34,197,94,0.2); }
.tag-red   { background: rgba(239,68,68,0.12); color: #f87171; border: 1px solid rgba(239,68,68,0.2); }
.tag-blue  { background: rgba(79,142,247,0.12); color: #818cf8; border: 1px solid rgba(79,142,247,0.2); }
.tag-gray  { background: rgba(107,122,158,0.12); color: #9aa5c4; border: 1px solid rgba(107,122,158,0.2); }

/* ── INFO ROWS ── */
.info-row  { display: flex; justify-content: space-between; align-items: center;
    padding: 0.35rem 0; border-bottom: 1px solid #1e2540; font-size: 0.78rem; }
.info-row:last-child { border-bottom: none; }
.info-key  { color: #6b7a9e; }
.info-val  { color: #e2e8f0; font-weight: 500; }
.info-ok   { color: #22c55e; }
.info-no   { color: #ef4444; }

/* ── SIGNAL BADGE ── */
.sig { padding: 0.2rem 0.6rem; border-radius: 6px; font-size: 0.72rem; font-weight: 700; text-transform: uppercase; }
.sig-strong { background:#1e3a5f; color:#60a5fa; }
.sig-medium { background:#1e3320; color:#4ade80; }
.sig-weak   { background:#2d2d2d; color:#9aa5c4; }
.sig-risk   { background:#3b1212; color:#f87171; }

/* ── DIVIDER ── */
.sec-div { border: none; border-top: 1px solid #1e2540; margin: 0.7rem 0; }

/* ── ALERT ── */
.alert { border-radius: 8px; padding: 0.5rem 0.8rem; font-size: 0.75rem; margin-top: 0.5rem; }
.alert-warn { background: rgba(245,158,11,0.1); border:1px solid rgba(245,158,11,0.25); color:#fcd34d; }
.alert-info { background: rgba(79,142,247,0.1); border:1px solid rgba(79,142,247,0.25); color:#93c5fd; }

/* ── Streamlit overrides ── */
[data-testid="stFileUploader"] > div { background: #111420 !important; border: 1px dashed #2a3460 !important; border-radius: 10px !important; }
[data-testid="stFileUploader"] label { color: #9aa5c4 !important; font-size: 0.82rem !important; }
div[data-testid="stNumberInput"] input { background: #161b2e !important; border: 1px solid #2a3460 !important; color: #fff !important; border-radius: 8px !important; }
div[data-testid="stTextInput"] input { background: #161b2e !important; border: 1px solid #2a3460 !important; color: #fff !important; border-radius: 8px !important; }
.stButton > button {
    background: linear-gradient(135deg,#2d4fd4,#4f8ef7) !important;
    color: #fff !important; border: none !important; border-radius: 10px !important;
    font-family: 'Syne', sans-serif !important; font-weight: 700 !important;
    font-size: 0.88rem !important; padding: 0.55rem 1.2rem !important;
    transition: opacity 0.2s !important;
}
.stButton > button:hover { opacity: 0.85 !important; }
.stButton > button:disabled { background: #1e2540 !important; color: #4a5568 !important; opacity: 1 !important; }
[data-testid="stExpander"] { background: #111420 !important; border: 1px solid #1e2540 !important; border-radius: 10px !important; }
[data-testid="stExpander"] summary { color: #9aa5c4 !important; font-size: 0.8rem !important; }
p, label, .stMarkdown { color: #c8d0e4 !important; }
[data-testid="stMetricLabel"] { color: #6b7a9e !important; }
[data-testid="stMetricValue"] { color: #fff !important; font-family: 'Syne', sans-serif !important; }
div[data-testid="stSidebarNav"] { display: none; }
footer { display: none !important; }
</style>
""")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_ui")

# ── PATH RESOLUTION ───────────────────────────────────────────────────────────
# ── Résolution robuste des chemins ───────────────────────────────────────
# Fonctionne quelle que soit la façon dont streamlit est lancé
import os as _os

# Cherche le dossier "app" qui contient test_ui.py en remontant depuis cwd
def _find_app_dir():
    # 1. Essai via __file__ (fonctionne si streamlit run app/test_ui.py)
    try:
        p = Path(__file__).resolve().parent
        if (p / "agents").exists():
            return p
    except Exception:
        pass
    # 2. Cherche "app" dans le répertoire courant et ses parents
    cwd = Path(_os.getcwd()).resolve()
    for candidate in [cwd / "app", cwd]:
        if (candidate / "agents").exists():
            return candidate
    # 3. Cherche en remontant l'arborescence
    for parent in cwd.parents:
        if (parent / "app" / "agents").exists():
            return parent / "app"
    return cwd

_BASE_DIR    = _find_app_dir()
_PROJECT_DIR = _BASE_DIR.parent
_AGENTS_DIR  = _BASE_DIR / "agents"

for _p in [str(_PROJECT_DIR), str(_BASE_DIR), str(_AGENTS_DIR)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from app.agents.cv_agent.cv_parser                import run_cv_parser
    from app.agents.cv_agent.cv_validator             import validate_and_fix
    from app.agents.motivation_agent.motivation_agent import analyze_motivation_letter
    from app.agents.matching_agent.matching_agent     import analyze_matching
except ImportError as e:
    AGENTS_OK    = False
    IMPORT_ERROR = str(e)

# ── HELPERS ──────────────────────────────────────────────────────────────────
def _sc(s):
    return "high" if s>=70 else ("medium" if s>=40 else "low")

def _prog(label, val, cls="blue", max_val=100):
    pct = min(100, int(val/max_val*100)) if max_val else 0
    color_cls = f"prog-{cls}"
    return f"""<div class="prog-wrap">
  <div class="prog-label"><span>{label}</span><span>{val}</span></div>
  <div class="prog-track"><div class="prog-fill {color_cls}" style="width:{pct}%"></div></div>
</div>"""

def _tags(items, cls="blue"):
    return "".join(f'<span class="tag tag-{cls}">{i}</span>' for i in (items or []))

def _sig_html(s):
    return f'<span class="sig sig-{s}">{s}</span>'

def _irow(k, v, ok=None):
    val_cls = "" if ok is None else ("info-ok" if ok else "info-no")
    icon = "" if ok is None else ("✓ " if ok else "✗ ")
    return f'<div class="info-row"><span class="info-key">{k}</span><span class="info-val {val_cls}">{icon}{v}</span></div>'

def load_job_from_db(job_id: int) -> dict | None:
    """
    Charge les données d'une offre depuis la base de données.
    Adaptez cette fonction à votre ORM / connexion DB.
    """
    try:
        # ── Tentative SQLAlchemy ──────────────────────────────────────────
        # test_ui.py est dans app/ → imports relatifs depuis le projet
        import importlib
        db_mod  = importlib.import_module("database")
        mod_mod = importlib.import_module("models")
        SessionLocal = db_mod.SessionLocal
        Job          = mod_mod.Job
        db  = SessionLocal()
        job = db.query(Job).filter(Job.id == job_id).first()
        db.close()
        if job:
            return {
                "title"          : job.title       or "",
                "description"    : job.description or "",
                "skills_required": getattr(job, "skills_required", None) or getattr(job, "skills", "") or "",
                "company"        : job.company     or "",
            }
        return None
    except Exception as _db_err:
        logger.debug(f"DB load failed: {_db_err}")

    # ── Fallback : lecture d'un fichier JSON jobs.json ────────────────────
    jobs_file = Path("jobs.json")
    if jobs_file.exists():
        try:
            with open(jobs_file, "r", encoding="utf-8") as f:
                jobs = json.load(f)
            # Support liste ou dict {id: {...}}
            if isinstance(jobs, list):
                for j in jobs:
                    if j.get("id") == job_id:
                        return j
            elif isinstance(jobs, dict):
                return jobs.get(str(job_id)) or jobs.get(job_id)
        except Exception as e:
            logger.warning(f"Erreur lecture jobs.json : {e}")

    return None

# ── SESSION STATE ─────────────────────────────────────────────────────────────
for _k, _v in {"cv":None,"mot":None,"mat":None,"job":None,"done":False,"err":""}.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ── TOP BAR ──────────────────────────────────────────────────────────────────
now = datetime.now().strftime("%d/%m/%Y %H:%M")
st.markdown(f"""
<div class="topbar">
  <div>
    <div class="topbar-title">🎯 Recrutement <span>IA</span></div>
    <div class="topbar-sub">Pipeline d\'analyse automatique des candidatures</div>
  </div>
  <div style="display:flex;gap:0.6rem;align-items:center;">
    <span class="topbar-badge">CV Parser</span>
    <span class="topbar-badge">Motivation</span>
    <span class="topbar-badge">Matching</span>
    <span style="font-size:0.72rem;color:#3a4460;margin-left:0.3rem">{now}</span>
  </div>
</div>
""", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════════════════
# LAYOUT : SAISIE (gauche) | RÉSULTATS (droite)
# ════════════════════════════════════════════════════════════════════════════
left, right = st.columns([1, 2.8], gap="medium")

# ─────────────────────────── PANNEAU GAUCHE — SAISIE ────────────────────────
with left:
    st.markdown('''<div class="card">
<div class="card-header">📤 Soumettre une candidature</div>''', unsafe_allow_html=True)

    uploaded_cv     = st.file_uploader("CV (PDF)", type=["pdf"], key="up_cv")
    uploaded_letter = st.file_uploader("Lettre de motivation (PDF / TXT)", type=["pdf","txt"], key="up_let")

    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
    job_id_input = st.number_input("ID Offre d'emploi", min_value=1, step=1, value=1, key="job_id")

    col_load, col_reset = st.columns(2)
    with col_load:
        if st.button("🔍 Charger offre", use_container_width=True):
            job = load_job_from_db(int(job_id_input))
            st.session_state.job = job
            if not job:
                st.error(f"Offre #{job_id_input} introuvable.")

    with col_reset:
        if st.button("↺ Reset", use_container_width=True):
            for k in ["cv","mot","mat","job","done","err"]:
                st.session_state[k] = None if k!="done" else False
            st.rerun()

    # Affiche offre chargée
    if st.session_state.job:
        job = st.session_state.job
        st.markdown(f"""
<div style="background:#161b2e;border:1px solid #2a3460;border-radius:10px;padding:0.7rem 0.9rem;margin-top:0.6rem;">
  <div style="color:#4f8ef7;font-size:0.75rem;font-weight:700;margin-bottom:0.4rem;">OFFRE CHARGÉE</div>
  {_irow("Titre", job.get("title","—"))}
  {_irow("Entreprise", job.get("company","—"))}
  {_irow("Skills", (job.get("skills_required","") or "—")[:60]+"..."
         if len(job.get("skills_required","") or "")>60
         else (job.get("skills_required","") or "—"))}
</div>""", unsafe_allow_html=True)

    st.markdown("<div style='height:0.8rem'></div>", unsafe_allow_html=True)

    can_run = uploaded_cv and uploaded_letter and st.session_state.job
    if st.button("🚀 Lancer l'analyse", disabled=not can_run,
                 use_container_width=True, type="primary"):

        import tempfile, os
        def _save(f):
            from pathlib import Path as _P
            suf = _P(f.name).suffix
            t = tempfile.NamedTemporaryFile(delete=False, suffix=suf)
            t.write(f.getbuffer()); t.close(); return t.name

        cv_path  = _save(uploaded_cv)
        let_path = _save(uploaded_letter)
        job      = st.session_state.job

        with st.spinner("Analyse en cours…"):
            try:
                # Agent 1
                cv_r = run_cv_parser(cv_path, use_cache=False)
                try:
                    cv_r, vr = validate_and_fix(cv_r, pdf_path=cv_path)
                    cv_r["_validation"] = vr
                except Exception: pass
                st.session_state.cv = cv_r

                # Agent 2
                mot_r = analyze_motivation_letter(
                    letter_path=let_path,
                    job_title=job.get("title",""),
                    job_description=job.get("description",""),
                    job_skills=job.get("skills_required",""),
                    job_company=job.get("company",""),
                )
                if mot_r is None:
                    mot_r = {"score_motivation":50,"signal_motivation":"medium",
                             "pertinence_poste":"moyenne","competences_citees":[],
                             "points_forts":[],"detail_criteres":{},"langue":"?",
                             "nb_mots":0,"lettre_generique":False,"error":True}
                st.session_state.mot = mot_r

                # Agent 3
                mat_r = analyze_matching(
                    cv_profile=cv_r,
                    job={"title":job.get("title",""),"description":job.get("description",""),
                         "skills_required":job.get("skills_required",""),"company":job.get("company","")},
                    score_motivation=mot_r.get("score_motivation",50),
                    signal_motivation=mot_r.get("signal_motivation","medium"),
                    job_id=int(job_id_input),
                )
                st.session_state.mat = mat_r
                st.session_state.done = True

            except Exception as e:
                st.session_state.err = traceback.format_exc()
                st.error(f"Erreur : {e}")
            finally:
                for p in [cv_path, let_path]:
                    try: os.unlink(p)
                    except: pass
        st.rerun()

    if st.session_state.err and not st.session_state.done:
        with st.expander("🔍 Erreur détaillée"):
            st.code(st.session_state.err)

    st.markdown("</div>", unsafe_allow_html=True)

    # ── Agents status ─────────────────────────────────────────────────────
    st.markdown("<div style='height:0.7rem'></div>", unsafe_allow_html=True)
    def _status_row(icon, label, done):
        col = "#22c55e" if done else "#2a3460"
        bg  = "rgba(34,197,94,0.08)" if done else "transparent"
        txt = "#4ade80" if done else "#4a5568"
        # Les backslashes sont interdits dans les expressions {} des f-strings
        # avant Python 3.12 → on précalcule le fragment HTML dans une variable.
        ok_badge = ("<span style='margin-left:auto;color:#22c55e;font-size:0.75rem'>✓ OK</span>"
                    if done else "")
        return f'''<div style="display:flex;align-items:center;gap:0.6rem;
            padding:0.5rem 0.8rem;background:{bg};border:1px solid {col};
            border-radius:8px;margin-bottom:0.4rem;">
          <span style="color:{col};font-size:1rem">{icon}</span>
          <span style="color:{txt};font-size:0.8rem;font-weight:500">{label}</span>
          {ok_badge}
        </div>'''

    st.markdown(
        _status_row("⚙️","Agent 1 — Parsing CV", bool(st.session_state.cv))  +
        _status_row("✉️","Agent 2 — Motivation", bool(st.session_state.mot)) +
        _status_row("🎯","Agent 3 — Matching",   bool(st.session_state.mat)),
        unsafe_allow_html=True
    )

# ─────────────────────────── PANNEAU DROIT — RÉSULTATS ───────────────────────
with right:

    if not st.session_state.done:
        st.markdown("""
<div style="height:400px;display:flex;flex-direction:column;align-items:center;
  justify-content:center;background:#111420;border:1px dashed #1e2540;border-radius:14px;">
  <div style="font-size:3rem;margin-bottom:1rem;">🎯</div>
  <div style="font-family:'Syne',sans-serif;font-size:1.1rem;font-weight:700;color:#fff;margin-bottom:0.5rem;">
    En attente d'analyse
  </div>
  <div style="color:#4a5568;font-size:0.82rem;">
    Uploadez un CV, une lettre et choisissez une offre
  </div>
</div>""", unsafe_allow_html=True)

    else:
        cv  = st.session_state.cv  or {}
        mot = st.session_state.mot or {}
        mat = st.session_state.mat or {}

        # ════════════════════════════════════════════════════
        # ROW 0 — DÉCISION FINALE (pleine largeur)
        # ════════════════════════════════════════════════════
        decision  = mat.get("decision","EN_ATTENTE")
        signal    = mat.get("signal_final","medium")
        score_f   = mat.get("score_final",0)
        score_m   = mat.get("score_matching",0)
        score_mot = mot.get("score_motivation",0)
        dec_key   = decision.replace("É","E").replace("È","E")

        icons = {"ENTRETIEN":"✅","EN_ATTENTE":"⏳","REJETE":"❌","REJETÉ":"❌"}
        icon  = icons.get(decision,"⏳")

        st.markdown(f"""
<div class="decision-banner decision-{dec_key}">
  <span style="font-size:2rem">{icon}</span>
  <span class="decision-text">{decision}</span>
  <span style="color:#6b7a9e;font-size:0.85rem;margin:0 0.5rem">·</span>
  {_sig_html(signal)}
  <span style="margin-left:auto;color:#6b7a9e;font-size:0.8rem">
    Score final : <strong style="color:#fff;font-family:'Syne',sans-serif">{score_f}</strong>/100
  </span>
</div>""", unsafe_allow_html=True)

        # ════════════════════════════════════════════════════
        # ROW 1 — 3 score rings
        # ════════════════════════════════════════════════════
        r1, r2, r3 = st.columns(3, gap="small")

        def _ring(col, val, label, sub=""):
            cls = _sc(val)
            col.markdown(f"""
<div class="card" style="text-align:center;padding:1rem;">
  <div class="score-ring-wrap">
    <div class="score-ring {cls}">
      <span class="score-num">{val}</span>
      <span class="score-label">/100</span>
    </div>
  </div>
  <div style="font-family:'Syne',sans-serif;font-size:0.85rem;font-weight:700;
      color:#e2e8f0;margin-top:0.6rem">{label}</div>
  <div style="font-size:0.7rem;color:#6b7a9e;margin-top:0.2rem">{sub}</div>
</div>""", unsafe_allow_html=True)

        _ring(r1, score_f,   "Score Final",      "0.6×matching + 0.4×motivation")
        _ring(r2, score_m,   "Score Matching",   "skills · sémantique · exp.")
        _ring(r3, score_mot, "Score Motivation", f"{mot.get('nb_mots',0)} mots · {mot.get('langue','?').upper()}")

        st.markdown("<div style='height:0.8rem'></div>", unsafe_allow_html=True)

        # ════════════════════════════════════════════════════
        # ROW 2 — Candidat | Matching détail | Motivation détail
        # ════════════════════════════════════════════════════
        c1, c2, c3 = st.columns([1, 1.1, 1], gap="small")

        # ── CANDIDAT ───────────────────────────────────────
        with c1:
            skills = cv.get("skills",{}) or {}
            tech   = (skills.get("technical",[]) or [])[:6]
            tools  = (skills.get("tools",[]) or [])[:4]

            # ── Expérience : pro + stages ──────────────────
            exps        = cv.get("professional_experience",[]) or []
            internships = cv.get("internships",[]) or []
            exp0        = exps[0] if exps else (internships[0] if internships else {})
            is_internship = not exps and bool(internships)
            yrs        = cv.get("years_experience", cv.get("years_professional", 0)) or 0
            mois_stage = cv.get("months_internships", 0) or 0
            if yrs > 0:
                exp_label = f"{yrs} an{'s' if yrs > 1 else ''}"
            elif mois_stage > 0:
                exp_label = f"{mois_stage} mois (stages)"
            else:
                exp_label = "0 ans"

            # ── Diplôme : champ direct ou dérivé de education ──
            diplome = cv.get("highest_degree") or cv.get("diploma") or ""
            if not diplome:
                edu_list = cv.get("education",[]) or []
                if edu_list:
                    diplome = edu_list[0].get("degree","—")

            # ── Localisation : champ direct ou extrait du raw_text ──
            import re as _re
            location = cv.get("location","") or ""
            if not location:
                raw = cv.get("raw_text","") or ""
                m = _re.search(r'([A-ZÀ-Ö][a-zà-ö]+(?:\s[A-ZÀ-Ö][a-zà-ö]+)*,\s*Tunisie)', raw)
                location = m.group(1) if m else "—"

            last_exp_label = "Dernier stage" if is_internship else "Dernière expérience"

            st.markdown(f"""<div class="card">
<div class="card-header">\U0001f464 Candidat</div>
{_irow("Nom",          cv.get("full_name","—"))}
{_irow("Email",        cv.get("email","—"))}
{_irow("Diplôme",      diplome or "—")}
{_irow("Expérience",   exp_label)}
{_irow("Localisation", location)}
<hr class="sec-div">
<div style="font-size:0.72rem;color:#6b7a9e;margin-bottom:0.4rem;text-transform:uppercase;letter-spacing:0.5px;">Compétences techniques</div>
<div class="tags-wrap">{_tags(tech,"blue")}{_tags(tools,"gray")}</div>
{"" if not exp0 else f'''<hr class="sec-div">
<div style="font-size:0.72rem;color:#6b7a9e;margin-bottom:0.3rem;text-transform:uppercase;letter-spacing:0.5px;">{last_exp_label}</div>
<div style="color:#e2e8f0;font-size:0.78rem;font-weight:600">{exp0.get("role","—")}</div>
<div style="color:#6b7a9e;font-size:0.72rem">{exp0.get("company","—")} · {exp0.get("duration","?")}</div>'''}
</div>""", unsafe_allow_html=True)


        # ── MATCHING DÉTAIL ────────────────────────────────
        with c2:
            sm = mat.get("skills_matched",[]) or []
            sx = mat.get("skills_missing",[]) or []
            sim = mat.get("similarity_cv_job",0)
            sr  = mat.get("skills_ratio",0)
            exp_ok    = mat.get("experience_ok", False)
            domain_ok = mat.get("domain_ok", False)
            title_ov  = mat.get("title_overlap",0)
            conf      = mat.get("confidence",{}) or {}
            swr       = mat.get("skills_weighted_ratio", 0) or 0
            shd       = mat.get("skills_high_density",[]) or []
            sld       = mat.get("skills_low_density",[])  or []

            swr_pct = round(swr * 100) if swr <= 1 else round(swr)

            st.markdown(f"""<div class="card">
<div class="card-header">🎯 Matching</div>
{_prog("Skills ratio",          round(sr*100),  _sc(round(sr*100)))}
{_prog("Skills pondéré",        swr_pct,        _sc(swr_pct))}
{_prog("Similarité sémantique", round(sim*100), _sc(round(sim*100)))}
{_prog("Score matching",        score_m,        _sc(score_m))}
<hr class="sec-div">
{_irow("Expérience", "Validée",    ok=exp_ok)}
{_irow("Domaine",    "Compatible", ok=domain_ok)}
{_irow("Overlap titre", f"{title_ov:.0%}")}
{_irow("Confiance",  conf.get("level","—"))}
<hr class="sec-div">
<div style="font-size:0.72rem;color:#4ade80;margin-bottom:0.3rem;text-transform:uppercase;letter-spacing:0.5px;">✓ Skills matchés ({len(sm)})</div>
<div class="tags-wrap">{_tags(sm[:8],"green")}</div>
{"" if not sx else f'''<div style="font-size:0.72rem;color:#f87171;margin:0.4rem 0 0.3rem;text-transform:uppercase;letter-spacing:0.5px;">✗ Manquants ({len(sx)})</div>
<div class="tags-wrap">{_tags(sx[:6],"red")}</div>'''}
{"" if not shd else f'''<hr class="sec-div">
<div style="font-size:0.72rem;color:#818cf8;margin-bottom:0.3rem;text-transform:uppercase;letter-spacing:0.5px;">⬆ High density ({len(shd)})</div>
<div class="tags-wrap">{"".join(f'<span class="tag tag-blue">{s}</span>' for s in shd[:6])}</div>'''}
{"" if not sld else f'''<div style="font-size:0.72rem;color:#9aa5c4;margin:0.4rem 0 0.3rem;text-transform:uppercase;letter-spacing:0.5px;">⬇ Low density ({len(sld)})</div>
<div class="tags-wrap">{"".join(f'<span class="tag tag-gray">{s}</span>' for s in sld[:6])}</div>'''}
</div>""", unsafe_allow_html=True)

        # ── MOTIVATION DÉTAIL ──────────────────────────────
        with c3:
            detail   = mot.get("detail_criteres",{}) or {}
            comps    = mot.get("competences_citees",[]) or []
            pts      = mot.get("points_forts",[]) or []
            pertinence = mot.get("pertinence_poste","—")
            generique  = mot.get("lettre_generique", False)

            crit_rows = ""
            crit_map = [
                ("coherence_poste",  "Cohérence poste", 35),
                ("competences",      "Compétences",     25),
                ("experience",       "Expérience",      20),
                ("personnalisation", "Personnalisation", 12),
                ("qualite",          "Qualité",          8),
            ]
            for key, label, pct in crit_map:
                v = detail.get(key, 0)
                crit_rows += _prog(f"{label} ({pct}%)", v, _sc(v))

            st.markdown(f"""<div class="card">
<div class="card-header">✉️ Motivation</div>
{_irow("Pertinence poste", pertinence)}
{_irow("Lettre générique", "Oui ⚠️" if generique else "Non ✓")}
<hr class="sec-div">
<div style="font-size:0.72rem;color:#6b7a9e;margin-bottom:0.5rem;text-transform:uppercase;letter-spacing:0.5px;">Critères détaillés</div>
{crit_rows}
{"" if not comps else f'''<hr class="sec-div">
<div style="font-size:0.72rem;color:#6b7a9e;margin-bottom:0.3rem;text-transform:uppercase;letter-spacing:0.5px;">Compétences citées</div>
<div class="tags-wrap">{_tags(comps[:6],"blue")}</div>'''}
{"" if not pts else f'''<div style="font-size:0.72rem;color:#6b7a9e;margin:0.5rem 0 0.3rem;text-transform:uppercase;letter-spacing:0.5px;">Points forts</div>
{"".join(f'<div style="color:#9aa5c4;font-size:0.75rem;padding:0.15rem 0">• {p}</div>' for p in pts[:3])}'''}
</div>""", unsafe_allow_html=True)

        # ════════════════════════════════════════════════════
        # ROW 2b — Bandeau JUSTIFICATION (pleine largeur)
        # ════════════════════════════════════════════════════
        jus = mat.get("justification", {}) or {}
        main_reason   = mat.get("main_reason","")  or jus.get("main_reason","")  or ""
        analyse_txt   = jus.get("analyse","")       or mat.get("analyse","")      or ""
        pts_forts     = jus.get("points_forts",[])  or mat.get("points_forts",[]) or []
        pts_faibles   = jus.get("points_faibles",[])or mat.get("points_faibles",[])or []

        if main_reason or analyse_txt or pts_forts or pts_faibles:
            st.markdown("<div style='height:0.6rem'></div>", unsafe_allow_html=True)

            _pf_html = "".join(
                f'<div style="color:#4ade80;font-size:0.78rem;padding:0.18rem 0">'
                f'<span style="margin-right:0.4rem">✓</span>{p}</div>'
                for p in (pts_forts or [])[:4]
            )
            _pw_html = "".join(
                f'<div style="color:#f87171;font-size:0.78rem;padding:0.18rem 0">'
                f'<span style="margin-right:0.4rem">✗</span>{p}</div>'
                for p in (pts_faibles or [])[:4]
            )

            # Colonnes internes : analyse + points
            _has_pts = bool(_pf_html or _pw_html)
            _analyse_col = f'''
<div style="flex:1;min-width:0;padding-right:{("1.5rem" if _has_pts else "0")}">
  {"" if not main_reason else f'<div style="font-family:Syne,sans-serif;font-size:0.88rem;font-weight:700;color:#e2e8f0;margin-bottom:0.5rem;line-height:1.4">{main_reason}</div>'}
  {"" if not analyse_txt else f'<div style="font-size:0.78rem;color:#9aa5c4;line-height:1.6">{analyse_txt}</div>'}
</div>'''
            _pts_col = f'''
<div style="display:flex;gap:1.2rem;flex-shrink:0;min-width:240px">
  {"" if not _pf_html else f'<div><div style="font-size:0.65rem;color:#4ade80;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:0.3rem;font-weight:700">Points forts</div>{_pf_html}</div>'}
  {"" if not _pw_html else f'<div><div style="font-size:0.65rem;color:#f87171;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:0.3rem;font-weight:700">Points faibles</div>{_pw_html}</div>'}
</div>''' if _has_pts else ""

            st.markdown(f"""
<div style="background:#111420;border:1px solid #1e2540;border-left:3px solid #4f8ef7;
    border-radius:14px;padding:1.1rem 1.4rem;">
  <div style="font-family:'Syne',sans-serif;font-size:0.75rem;font-weight:700;
      color:#4f8ef7;text-transform:uppercase;letter-spacing:1px;margin-bottom:0.7rem">
    🧠 Analyse &amp; Justification
  </div>
  <div style="display:flex;align-items:flex-start;gap:1rem;flex-wrap:wrap">
    {_analyse_col}
    {_pts_col}
  </div>
</div>""", unsafe_allow_html=True)

        # ════════════════════════════════════════════════════
        # ROW 3 — Alertes + JSON download
        # ════════════════════════════════════════════════════
        alerts = []
        if mat.get("keyword_stuffing_suspected"):
            alerts.append(("warn","⚠️ Keyword stuffing suspecté dans le CV"))
        if mat.get("fallback_used"):
            alerts.append(("info","ℹ️ Mode dégradé : TF-IDF utilisé (sentence-transformers indisponible)"))
        if mat.get("score_is_indicative"):
            alerts.append(("warn","⚠️ Score indicatif — confiance faible, revue manuelle recommandée"))
        if mot.get("error"):
            alerts.append(("warn","⚠️ Analyse lettre dégradée — vérifiez le PDF"))

        val = cv.get("_validation",{}) or {}
        if val.get("warnings"):
            alerts.append(("warn", f"⚠️ Validation CV : {val['warnings'][0]}"))

        if alerts:
            alert_html = "".join(
                f'<div class="alert alert-{t}">{msg}</div>'
                for t, msg in alerts
            )
            st.markdown(f"""
<div style="margin-top:0.5rem">{alert_html}</div>
""", unsafe_allow_html=True)

        # Download row
        st.markdown("<div style='height:0.6rem'></div>", unsafe_allow_html=True)
        dl1, dl2, dl3, dl4 = st.columns(4, gap="small")
        all_results = {
            "timestamp" : now,
            "job_id"    : int(job_id_input),
            "candidat"  : cv.get("full_name","—"),
            "cv"        : cv,
            "motivation": mot,
            "matching"  : mat,
        }
        dl1.download_button("⬇ Rapport complet", json.dumps(all_results,ensure_ascii=False,indent=2),
            "rapport_complet.json","application/json", use_container_width=True)
        dl2.download_button("⬇ CV JSON",      json.dumps(cv, ensure_ascii=False, indent=2),
            "cv.json", "application/json", use_container_width=True)
        dl3.download_button("⬇ Motivation",   json.dumps(mot,ensure_ascii=False,indent=2),
            "motivation.json","application/json", use_container_width=True)
        dl4.download_button("⬇ Matching",     json.dumps(mat,ensure_ascii=False,indent=2),
            "matching.json","application/json", use_container_width=True)

# ── FOOTER ───────────────────────────────────────────────────────────────────
st.markdown(f"""
<div style="text-align:center;padding:0.8rem;margin-top:0.8rem;
    font-size:0.68rem;color:#3a4460;border-top:1px solid #1e2540">
  Pipeline Recrutement IA · cv_parser · motivation_agent · matching_agent · {now}
</div>
""", unsafe_allow_html=True)