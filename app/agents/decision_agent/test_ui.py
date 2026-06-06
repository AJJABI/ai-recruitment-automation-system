"""
test_ui.py — Interface Streamlit de test des Agents IA (v7.0)
=============================================================
Lancer : streamlit run test_ui.py

Agents testables :
  🧪 Agent Test      — Génération + Correction v7.0
  📊 Agent Test      — Correction
  📄 Agent CV        — Parsing CV PDF
  💼 Agent Matching  — Matching CV ↔ Offre
  ✉️ Agent Motivation — Analyse lettre de motivation
  🔴 Agent Décision  — Décision initiale + finale + rapport RH
  ⚡ Pipeline Complet — 4 tabs : Candidature → Test → Manager → Agent Décision → Récapitulatif

Nouveautés v7.0 :
  - Section "Décision Manager" dans Tab 2 : après correction du test,
    le manager saisit sa décision (VALIDÉ / À_APPROFONDIR / NON_RETENU) + note
  - NON_RETENU → rejet direct, pas d'Agent Décision
  - VALIDÉ / À_APPROFONDIR → priority_group (1/2) transmis à l'Agent 5
  - Classement candidats en 2 niveaux : groupe manager → score_global
  - _display_rh_report_v7 : affiche décision manager + score_global_decisional
"""

import json
import requests
import streamlit as st

# ─────────────────────────────────────────────────────────────────
# IMPORT DIRECT — decision_agent (Agent 5)
# Pas d'API nécessaire — appel Python direct sans modifier le backend
# ─────────────────────────────────────────────────────────────────

try:
    from decision_agent import run_decision_agent as _run_decision_agent
    DECISION_AGENT_AVAILABLE = True
except ImportError:
    DECISION_AGENT_AVAILABLE = False

try:
    from test_agent import run_manager_decision as _run_manager_decision
    MANAGER_DECISION_AVAILABLE = True
except ImportError:
    MANAGER_DECISION_AVAILABLE = False

# ─────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────

BASE_URL = "http://localhost:8000"

TIMEOUT_LLM_GENERATE = 300   # 5 min — génération test
TIMEOUT_LLM_EVALUATE = 240   # 4 min — correction test + décision finale
TIMEOUT_DEFAULT      = 120   # 2 min — tous les autres appels

st.set_page_config(
    page_title = "🤖 Recruitment AI — Test Interface v6.0",
    page_icon  = "🤖",
    layout     = "wide",
)

# ─────────────────────────────────────────────────────────────────
# HELPERS RÉSEAU
# ─────────────────────────────────────────────────────────────────

def post(endpoint: str, payload: dict, timeout: int = TIMEOUT_DEFAULT) -> tuple[dict, int]:
    try:
        r = requests.post(f"{BASE_URL}{endpoint}", json=payload, timeout=timeout)
        return r.json(), r.status_code
    except requests.exceptions.ReadTimeout:
        return {
            "error": (
                f"Read timed out (timeout={timeout}s)\n\n"
                "💡 Le serveur travaille toujours — augmentez le timeout ou vérifiez les logs uvicorn."
            )
        }, 500
    except requests.exceptions.ConnectionError:
        return {"error": "Backend non disponible — lancez uvicorn app.main:app"}, 503
    except Exception as e:
        return {"error": str(e)}, 500


def get(endpoint: str, timeout: int = TIMEOUT_DEFAULT) -> tuple[dict, int]:
    try:
        r = requests.get(f"{BASE_URL}{endpoint}", timeout=timeout)
        return r.json(), r.status_code
    except requests.exceptions.ConnectionError:
        return {"error": "Backend non disponible"}, 503
    except Exception as e:
        return {"error": str(e)}, 500


def post_files(endpoint: str, files: dict, data: dict, timeout: int = TIMEOUT_DEFAULT) -> tuple[dict, int]:
    try:
        r = requests.post(f"{BASE_URL}{endpoint}", files=files, data=data, timeout=timeout)
        return r.json(), r.status_code
    except requests.exceptions.ReadTimeout:
        return {
            "error": (
                f"Read timed out (timeout={timeout}s)\n\n"
                "💡 Le traitement prend du temps — le serveur travaille toujours."
            )
        }, 500
    except requests.exceptions.ConnectionError:
        return {"error": "Backend non disponible — lancez uvicorn app.main:app"}, 503
    except Exception as e:
        return {"error": str(e)}, 500


def show_result(result: dict, status_code: int) -> None:
    if status_code == 200:
        st.success(f"✅ Succès — HTTP {status_code}")
    elif status_code in (422, 404):
        st.warning(f"⚠️ Erreur client — HTTP {status_code}")
    elif status_code >= 500:
        st.error(f"❌ Erreur serveur — HTTP {status_code}")
    else:
        st.info(f"ℹ️ HTTP {status_code}")
    st.json(result)


def show_score_badge(score: float, status: str) -> None:
    icons = {"strong": "🟢", "medium": "🟡", "weak": "🔴"}
    icon  = icons.get(status, "⚪")
    st.metric(
        label = f"{icon} Score technique",
        value = f"{score}/100",
        delta = status.upper(),
    )


# ─────────────────────────────────────────────────────────────────
# HELPER — Rapport RH visuel
# ─────────────────────────────────────────────────────────────────

def _display_rh_report(result: dict) -> None:
    """
    Affiche le rapport RH de l'Agent Décision de façon lisible.
    Compatible avec la sortie de decision_agent.run_decision_agent()
    et avec les anciens endpoints /decide-initial et /decide-final.
    """
    decision  = result.get("rh_decision") or result.get("decision")
    priority  = result.get("rh_priority") or result.get("priority", "")
    summary   = result.get("rh_summary")  or result.get("summary", "")
    reason    = result.get("rh_reason")   or result.get("reason", "")
    questions = result.get("interview_questions", [])

    score_final  = result.get("score_final")   or result.get("score_global")
    score_match  = result.get("score_matching")
    score_motiv  = result.get("score_motivation")
    score_tech   = result.get("technical_score")

    if not decision:
        st.info("ℹ️ Aucune décision RH disponible pour cette candidature.")
        return

    # Badge décision principal
    decision_styles = {
        "ENTRETIEN"   : ("🟢", "success"),
        "PRÉSÉLECTION": ("🔵", "info"),
        "EN_ATTENTE"  : ("🟡", "warning"),
        "REJETÉ"      : ("🔴", "error"),
    }
    icon, style = decision_styles.get(decision, ("⚪", "info"))

    if style == "success":
        st.success(f"{icon} **Décision : {decision}**  —  Priorité : {priority.upper()}")
    elif style == "warning":
        st.warning(f"{icon} **Décision : {decision}**  —  Priorité : {priority.upper() if priority else 'N/A'}")
    elif style == "error":
        st.error(f"{icon} **Décision : {decision}**")
    else:
        st.info(f"{icon} **Décision : {decision}**")

    if summary:
        st.markdown(f"> {summary}")

    if reason:
        with st.expander("📋 Justification de la règle déclenchée"):
            st.caption(reason)

    # Scores
    st.markdown("---")
    cols = st.columns(4)
    with cols[0]:
        if score_final is not None:
            st.metric("Score global", f"{score_final}/100")
    with cols[1]:
        if score_match is not None:
            st.metric("Score matching", f"{score_match}/100")
    with cols[2]:
        if score_motiv is not None:
            st.metric("Score motivation", f"{score_motiv}/100")
    with cols[3]:
        if score_tech is not None:
            st.metric("Score technique", f"{score_tech}/100")

    # Questions d'entretien (anciens endpoints)
    if questions:
        st.markdown("---")
        st.subheader("🎤 Questions d'entretien générées par l'IA")
        st.caption(f"{len(questions)} questions personnalisées pour ce profil")
        for i, q in enumerate(questions, 1):
            st.markdown(f"**{i}.** {q}")


def _display_rh_report_v6(result: dict) -> None:
    """
    Affiche le rapport RH complet de decision_agent.py (v7.0).
    Gère ENTRETIEN / EN_ATTENTE / REJETÉ + décision manager + score_global_decisional.
    """
    decision         = result.get("decision", "")
    priority         = result.get("priority", "")
    summary          = result.get("summary", "")
    report           = result.get("report", {})
    manager_decision = result.get("manager_decision")
    manager_note     = result.get("manager_note", "")
    priority_group   = result.get("priority_group")

    # ── Badge décision ─────────────────────────────────────────────
    decision_styles = {
        "ENTRETIEN" : ("🟢", "success"),
        "EN_ATTENTE": ("🟡", "warning"),
        "REJETÉ"    : ("🔴", "error"),
    }
    icon, style = decision_styles.get(decision, ("⚪", "info"))
    priority_labels = {"high": "🔴 HAUTE", "medium": "🟡 MOYENNE", "low": "🔵 FAIBLE"}
    priority_label  = priority_labels.get(priority, priority.upper() if priority else "N/A")

    if style == "success":
        st.success(f"{icon} **DÉCISION FINALE : {decision}**  —  Priorité : {priority_label}")
    elif style == "error":
        st.error(f"{icon} **DÉCISION FINALE : {decision}**  —  Candidat non retenu par le manager")
    else:
        st.warning(f"{icon} **DÉCISION FINALE : {decision}**  —  Priorité : {priority_label}")

    if summary:
        st.markdown(f"> 📝 {summary}")

    # ── Décision manager ───────────────────────────────────────────
    if manager_decision:
        st.markdown("---")
        st.subheader("👔 Décision Manager")
        manager_icons = {
            "VALIDÉ"        : "✅",
            "À_APPROFONDIR" : "🔶",
            "NON_RETENU"    : "❌",
        }
        m_icon = manager_icons.get(manager_decision, "⚪")
        group_label = f"— Groupe {priority_group}" if priority_group else ""
        if manager_decision == "NON_RETENU":
            st.error(f"{m_icon} **{manager_decision}** — Rejeté après entretien technique")
        elif manager_decision == "VALIDÉ":
            st.success(f"{m_icon} **{manager_decision}** {group_label} — Profil solide, recommandé")
        else:
            st.warning(f"{m_icon} **{manager_decision}** {group_label} — Nécessite discussion complémentaire")
        if manager_note:
            st.caption(f"📋 Note manager : *{manager_note}*")

    # ── Scores ─────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("📊 Scores consolidés")
    score_decisional = result.get("score_global_decisional")
    nb_cols = 5 if score_decisional is not None else 4
    cols = st.columns(nb_cols)
    with cols[0]:
        score_t = result.get("technical_score", 0)
        color   = "🟢" if score_t >= 70 else ("🟡" if score_t >= 50 else "🔴")
        st.metric(f"{color} Score technique", f"{score_t:.1f}/100")
    with cols[1]:
        score_m = result.get("score_matching", 0)
        st.metric("🔵 Score matching", f"{score_m:.1f}/100")
    with cols[2]:
        score_mo = result.get("score_motivation", 0)
        st.metric("🟠 Score motivation", f"{score_mo:.1f}/100")
    with cols[3]:
        score_g = result.get("score_global", 0)
        st.metric("⭐ Score global", f"{score_g:.1f}/100")
    if score_decisional is not None and nb_cols == 5:
        with cols[4]:
            color_d = "🟢" if score_decisional >= 70 else ("🟡" if score_decisional >= 50 else "🔴")
            st.metric(
                f"{color_d} Score décisionnel",
                f"{score_decisional:.1f}/100",
                help="0.60×matching_final + 0.40×technique — pilote la décision"
            )

    # ── Classement groupe ──────────────────────────────────────────
    if priority_group:
        st.markdown("---")
        group_desc = {
            1: "🥇 Groupe 1 — VALIDÉ par le manager (classé en premier)",
            2: "🥈 Groupe 2 — À APPROFONDIR (classé en second)",
        }
        st.info(group_desc.get(priority_group, f"Groupe {priority_group}"))

    # ── Points forts & faibles ─────────────────────────────────────
    st.markdown("---")
    col_s, col_w = st.columns(2)
    strengths  = result.get("strengths", [])
    weaknesses = result.get("weaknesses", [])
    with col_s:
        st.subheader("✅ Points forts")
        if strengths:
            for s in strengths:
                st.success(f"• {s}")
        else:
            st.caption("Aucun point fort identifié.")
    with col_w:
        st.subheader("⚠️ Points faibles")
        if weaknesses:
            for w in weaknesses:
                st.warning(f"• {w}")
        else:
            st.caption("Aucun point faible identifié.")

    # ── Flags système ──────────────────────────────────────────────
    flags = result.get("flags", [])
    if flags:
        st.markdown("---")
        st.subheader("🏴 Flags système")
        for f in flags:
            st.caption(f"`{f}`")

    # ── Prochaine étape ────────────────────────────────────────────
    next_step = report.get("next_step") or (
        "Planifier un entretien (Phase 5 — Module Planning)"
        if decision == "ENTRETIEN"
        else "Envoyer email de refus au candidat"
        if decision == "REJETÉ"
        else "Conserver en réserve — décision RH manuelle requise"
    )
    st.markdown("---")
    if decision == "ENTRETIEN":
        st.info(f"➡️ **Prochaine étape :** {next_step}")
    elif decision == "REJETÉ":
        st.error(f"❌ **Prochaine étape :** {next_step}")
    else:
        st.warning(f"⏸️ **Prochaine étape :** {next_step}")

    # ── Candidat ───────────────────────────────────────────────────
    candidate = report.get("candidate", {})
    if candidate.get("name") or candidate.get("email"):
        st.markdown("---")
        st.subheader("👤 Candidat")
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.write(f"**Nom :** {candidate.get('name', 'N/A')}")
            st.write(f"**Email :** {candidate.get('email', 'N/A')}")
        with col_b:
            st.write(f"**Téléphone :** {candidate.get('phone') or 'N/A'}")
            st.write(f"**Expérience :** {candidate.get('years_experience', 0)} an(s)")
        with col_c:
            skills = candidate.get("skills_all", [])
            if skills:
                st.write(f"**Compétences ({len(skills)}) :**")
                st.caption(", ".join(skills[:10]) + (" ..." if len(skills) > 10 else ""))

    # ── Justification ──────────────────────────────────────────────
    justification = result.get("justification", {})
    if justification:
        with st.expander("📋 Justification complète (règles déclenchées)"):
            rule = justification.get("decision_rule", "")
            if rule:
                st.info(f"**Règle :** {rule}")
            st.json(justification)


# ─────────────────────────────────────────────────────────────────
# HELPER — Affichage questions générées
# ─────────────────────────────────────────────────────────────────

def _display_generated_questions(result: dict, session_keys: dict) -> None:
    test_id   = result.get("test_id")
    questions = result.get("questions", [])
    reused    = result.get("reused", False)

    if reused:
        st.info(
            f"♻️ **Test existant réutilisé** — `{test_id}` "
            "Cliquez **Regénérer** pour créer un nouveau test."
        )
    else:
        st.success(
            f"✅ **Nouveau test généré** — `{test_id}` — "
            f"{result.get('duration')} min — {len(questions)} questions"
        )

    st.session_state[session_keys["test_id"]]   = test_id
    st.session_state[session_keys["questions"]] = questions

    classification = result.get("classification", {})
    test_type      = result.get("test_type", "")
    q_structure    = result.get("question_structure", {})

    type_icons = {"tech": "🔵", "platform": "🟠", "mixed": "🟣"}
    t_icon     = type_icons.get(test_type, "⚪")

    st.markdown(
        f"**{t_icon} Type :** {test_type.upper()} · "
        f"**MCQ :** {q_structure.get('mcq', 0)} · "
        f"**Open :** {q_structure.get('open', 0)} · "
        f"**Durée :** {result.get('duration')} min"
    )

    if classification.get("corrections_applied"):
        with st.expander("⚠️ Corrections de classification appliquées"):
            for c in classification["corrections_applied"]:
                st.warning(
                    f"**{c['name']}** : {c['given']} → {c['corrected_to']} "
                    f"(confidence: {c['confidence']:.0%})"
                )

    if classification.get("skills_final"):
        skills_str = " · ".join(
            f"`{s['name']}` ({s['type']})"
            for s in classification["skills_final"]
        )
        st.caption(f"Skills validés : {skills_str}")

    st.markdown("---")

    type_q_icons = {"mcq": "🔵", "open": "🟢", "problem": "🟢", "scenario": "🟠"}
    for q in questions:
        q_icon = type_q_icons.get(q["type"], "⚪")
        with st.expander(
            f"{q_icon} Q{q['id']} — {q['type'].upper()} | "
            f"{q.get('difficulty', '')} | skill: {q.get('skill', '')} | {q['points']} pts"
        ):
            st.write(q["question"])
            if q["type"] == "mcq":
                for opt in q.get("options", []):
                    st.write(f"○ {opt}")
            elif q["type"] in ("problem", "open"):
                if q.get("starter_code"):
                    st.markdown("**Starter code :**")
                    st.code(q["starter_code"], language="python")
                criteria = q.get("answer_criteria", [])
                if criteria:
                    st.markdown("**Critères :**")
                    for c in criteria:
                        st.write(f"• {c}")


# ─────────────────────────────────────────────────────────────────
# HELPER — Affichage résultats correction
# ─────────────────────────────────────────────────────────────────

def _display_correction_results(result: dict) -> None:
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        show_score_badge(
            result.get("technical_score", 0),
            result.get("status", "weak")
        )
    with col_b:
        st.metric(
            "Points",
            f"{result.get('earned_points', 0)}/{result.get('total_points', 0)}"
        )
    with col_c:
        flags = result.get("flags", [])
        st.metric("Flags", ", ".join(flags) if flags else "Aucun")

    # Décision RH automatique (anciens endpoints)
    rh_decision = result.get("rh_decision")
    if rh_decision:
        st.markdown("---")
        st.subheader("🤖 Décision RH — Agent Décision")
        _display_rh_report(result)

    st.markdown("---")
    st.subheader("📋 Détail par question")

    for r in result.get("results", []):
        q_type     = r.get("type", "")
        pts_ok     = r["points_earned"] == r["points_max"]
        pts_par    = r["points_earned"] > 0
        icon       = "✅" if pts_ok else ("🟡" if pts_par else "❌")
        confidence = r.get("confidence")
        decision   = r.get("decision", "")
        flags_q    = r.get("python_flags", [])

        if q_type == "mcq":
            source_label = "🐍 Python pur"
        elif confidence == 1.0:
            source_label = "⚡ Execution Engine"
        elif confidence is not None and confidence < 1.0:
            source_label = "🧠 LLM Pipeline"
        else:
            source_label = ""

        conf_str = f" | conf: {confidence:.2f}" if confidence is not None else ""

        with st.expander(
            f"{icon} Q{r['question_id']} — {q_type.upper()} | "
            f"{r['points_earned']}/{r['points_max']} pts"
            + (f" | {source_label}" if source_label else "")
            + conf_str
        ):
            if decision:
                decision_labels = {
                    "auto_accept"         : "✅ Auto Accept",
                    "auto_reject"         : "❌ Auto Reject",
                    "auto"                : "✅ Auto",
                    "review_if_borderline": "⚠️ Review Borderline",
                    "human_review"        : "👤 Human Review",
                    "fallback_llm"        : "🔄 Fallback LLM",
                }
                st.markdown(f"**Décision :** {decision_labels.get(decision, decision)}")

            hr = r.get("hr_summary", {})
            if hr:
                if hr.get("message"):
                    st.info(hr["message"])
                if hr.get("breakdown"):
                    st.markdown("**Breakdown :**")
                    st.text(hr["breakdown"])
                if hr.get("risk"):
                    st.warning(hr["risk"])
            else:
                st.write(r.get("feedback", ""))

            if flags_q:
                with st.expander("🔧 Flags techniques"):
                    for f in flags_q:
                        st.caption(f"• {f}")


# ─────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────

st.sidebar.title("🤖 Recruitment AI v6.0")
st.sidebar.markdown("---")

page = st.sidebar.radio(
    "Navigation",
    [
        "🧪 Agent Test — Génération",
        "📊 Agent Test — Correction",
        "📄 Agent CV — Parsing",
        "💼 Agent Matching",
        "✉️ Agent Motivation",
        "🔴 Agent Décision",
        "⚡ Pipeline Complet",
    ]
)

st.sidebar.markdown("---")
st.sidebar.markdown(f"**Backend :** `{BASE_URL}`")

if st.sidebar.button("🔍 Vérifier le backend"):
    try:
        r = requests.get(f"{BASE_URL}/", timeout=5)
        if r.status_code == 200:
            st.sidebar.success("✅ Backend en ligne")
        else:
            st.sidebar.error(f"❌ HTTP {r.status_code}")
    except Exception:
        st.sidebar.error("❌ Backend non disponible")

# Status de l'import decision_agent
st.sidebar.markdown("---")
if DECISION_AGENT_AVAILABLE:
    st.sidebar.success("✅ decision_agent.py importé")
else:
    st.sidebar.error("❌ decision_agent.py non trouvé")
    st.sidebar.caption("Placez decision_agent.py dans le même dossier que test_ui.py")

st.sidebar.markdown("---")
st.sidebar.markdown("**Pipeline v6.0 :**")
st.sidebar.markdown("🔵 CV Parser")
st.sidebar.markdown("🟡 Motivation Agent")
st.sidebar.markdown("🟢 Matching Agent")
st.sidebar.markdown("🟣 Test Agent")
st.sidebar.markdown("🔴 Decision Agent ← Agent 5")
st.sidebar.markdown("---")
st.sidebar.markdown("**Règles décision initiale :**")
st.sidebar.markdown("≥ 70 → PRÉSÉLECTION")
st.sidebar.markdown("40-69 → EN_ATTENTE")
st.sidebar.markdown("< 40 → REJETÉ")
st.sidebar.markdown("**Règles décision finale :**")
st.sidebar.markdown("≥ 70 → ENTRETIEN (high)")
st.sidebar.markdown("50-69 → EN_ATTENTE (medium)")
st.sidebar.markdown("< 50 → EN_ATTENTE (low)")
st.sidebar.markdown("---")
st.sidebar.markdown("**Timeouts :**")
st.sidebar.markdown(f"⏱ Génération : {TIMEOUT_LLM_GENERATE}s")
st.sidebar.markdown(f"⏱ Correction : {TIMEOUT_LLM_EVALUATE}s")
st.sidebar.markdown(f"⏱ Autres : {TIMEOUT_DEFAULT}s")


# ═════════════════════════════════════════════════════════════════
# PAGE 1 — GÉNÉRATION TEST
# ═════════════════════════════════════════════════════════════════

if page == "🧪 Agent Test — Génération":
    st.title("🧪 Agent Test — Génération du test technique (v6.0)")
    st.markdown(
        "Génère un test de **10 questions** (MCQ + Open). "
        "Structure : tech=6MCQ+4Open, platform=5MCQ+5Open, mixed=5MCQ+5Open."
    )
    st.markdown("---")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📥 Paramètres")
        application_id = st.number_input("application_id", min_value=1, value=1, step=1)
        role           = st.text_input("Rôle", value="backend_python")
        seniority      = st.selectbox("Séniorité", ["junior", "mid", "senior"])

        st.markdown("**Skills Coding** *(nécessitent du code)*")
        coding_skills_input = st.text_area(
            "coding_skills (un par ligne)",
            value="python\nsql", height=90, key="coding_skills",
        )
        st.markdown("**Skills Platform** *(outils, dashboards, ERP)*")
        platform_skills_input = st.text_area(
            "platform_skills (un par ligne)",
            value="power bi\nsharepoint", height=90, key="platform_skills",
        )
        st.markdown("**Skills Mixed** *(code + outil)*")
        mixed_skills_input = st.text_area(
            "mixed_skills (un par ligne)",
            value="azure devops", height=70, key="mixed_skills",
        )

    with col2:
        st.subheader("ℹ️ Règles v6.0")
        st.info(
            "**10 questions toujours :**\n\n"
            "🔵 **TECH** : 6 MCQ + 4 Open\n\n"
            "🟠 **PLATFORM** : 5 MCQ + 5 Open\n\n"
            "🟣 **MIXED** : 5 MCQ + 5 Open\n\n"
            "---\n\n"
            "**MCQ :** Correction Python pur (binaire)\n"
            "**Open :** Évaluation LLM\n\n"
            "**Status :** strong ≥70 · medium ≥50 · weak <50\n\n"
            f"⏱ **Timeout requête :** {TIMEOUT_LLM_GENERATE}s"
        )

    st.markdown("---")
    btn_col1, btn_col2 = st.columns(2)
    with btn_col1:
        btn_generate  = st.button("🚀 Générer le test", type="primary", use_container_width=True)
    with btn_col2:
        btn_regenerate = st.button("🔄 Regénérer le test", type="secondary", use_container_width=True)

    if btn_generate or btn_regenerate:
        coding_skills   = [s.strip() for s in coding_skills_input.strip().split("\n") if s.strip()]
        platform_skills = [s.strip() for s in platform_skills_input.strip().split("\n") if s.strip()]
        mixed_skills    = [s.strip() for s in mixed_skills_input.strip().split("\n") if s.strip()]
        all_skills      = coding_skills + platform_skills + mixed_skills
        force           = btn_regenerate

        if not role.strip():
            st.error("Le rôle est obligatoire")
        elif not all_skills:
            st.error("Au moins 1 skill requis")
        else:
            msg = (
                "⏳ Régénération — nouvelles questions + self-test... (peut prendre 1-3 min)"
                if force else
                "⏳ Classification + Génération + Self-test... (peut prendre 1-3 min)"
            )
            with st.spinner(msg):
                result, status = post(
                    f"/applications/{application_id}/generate-test",
                    {
                        "role"            : role.strip(),
                        "coding_skills"   : coding_skills,
                        "platform_skills" : platform_skills,
                        "mixed_skills"    : mixed_skills,
                        "seniority"       : seniority,
                        "force_regenerate": force,
                    },
                    timeout=TIMEOUT_LLM_GENERATE,
                )

            if status == 200:
                _display_generated_questions(
                    result,
                    session_keys={"test_id": "last_test_id", "questions": "last_questions"}
                )
                st.session_state["last_app_id"] = application_id
                with st.expander("📦 JSON complet"):
                    show_result(result, status)
            else:
                show_result(result, status)


# ═════════════════════════════════════════════════════════════════
# PAGE 2 — CORRECTION TEST
# ═════════════════════════════════════════════════════════════════

elif page == "📊 Agent Test — Correction":
    st.title("📊 Agent Test — Correction des réponses (v6.0)")
    st.markdown(
        "**MCQ** → Python pur (binaire) · "
        "**Open** → LLM evaluation"
    )
    st.markdown("---")

    default_test_id = st.session_state.get("last_test_id", "")
    default_app_id  = st.session_state.get("last_app_id", 1)
    questions       = st.session_state.get("last_questions", [])

    col1, col2 = st.columns(2)
    with col1:
        application_id = st.number_input("application_id", min_value=1, value=default_app_id, step=1)
        test_id        = st.text_input("test_id", value=default_test_id, placeholder="test_id généré")
    with col2:
        st.subheader("ℹ️ Scoring v6.0")
        st.info(
            "**MCQ :** Python pur — binaire (0 / points_max)\n\n"
            "**Open :** LLM — pertinence + justification\n\n"
            "**Status :** strong ≥70 · medium ≥50 · weak <50\n\n"
            f"⏱ **Timeout correction :** {TIMEOUT_LLM_EVALUATE}s"
        )

    st.markdown("---")
    st.subheader("📝 Réponses du candidat")

    if questions:
        st.info(f"✅ {len(questions)} questions chargées depuis la session")
        answers_input = {}

        for q in questions:
            q_type = q["type"]
            label  = (
                f"Q{q['id']} — {q_type.upper()} | "
                f"{q.get('difficulty', '')} | {q.get('skill', '')} ({q['points']} pts)"
            )

            if q_type == "mcq":
                answers_input[q["id"]] = st.selectbox(
                    label, options=q.get("options", []), key=f"ans_{q['id']}"
                )
            else:
                answers_input[q["id"]] = st.text_area(
                    label,
                    placeholder="Votre approche et justification...",
                    height=100, key=f"ans_{q['id']}",
                )

    else:
        st.warning("⚠️ Aucune question chargée — générez d'abord un test.")
        st.subheader("Mode manuel — JSON")
        answers_json = st.text_area(
            "Réponses (JSON)",
            value=json.dumps([
                {"question_id": 1, "answer": "Option A"},
                {"question_id": 2, "answer": "Option B"},
                {"question_id": 3, "answer": "J'utiliserais cette approche car..."},
            ], indent=2),
            height=220,
        )

    if st.button("📊 Corriger le test", type="primary", use_container_width=True):
        if not test_id.strip():
            st.error("Le test_id est obligatoire")
        else:
            if questions and answers_input:
                answers = [
                    {"question_id": qid, "answer": str(ans) if str(ans).strip() else "(pas de réponse)"}
                    for qid, ans in answers_input.items()
                ]
            else:
                try:
                    answers = json.loads(answers_json)
                except json.JSONDecodeError:
                    st.error("JSON invalide")
                    st.stop()

            payload = {"test_id": test_id.strip(), "answers": answers}

            with st.spinner("⏳ Correction... (peut prendre 1-3 min)"):
                post(f"/applications/{application_id}/start-test/{test_id}", {})
                result, status = post(
                    f"/applications/{application_id}/evaluate-test",
                    payload,
                    timeout=TIMEOUT_LLM_EVALUATE,
                )

            if status == 200:
                st.success("✅ Correction terminée !")
                st.session_state["last_eval_result"] = result
                st.session_state["last_eval_app_id"] = application_id
                _display_correction_results(result)
                with st.expander("📦 JSON complet"):
                    show_result(result, status)
            else:
                show_result(result, status)


# ═════════════════════════════════════════════════════════════════
# PAGE 3 — AGENT CV
# ═════════════════════════════════════════════════════════════════

elif page == "📄 Agent CV — Parsing":
    st.title("📄 Agent CV — Parsing")
    st.markdown("Parse un CV PDF et extrait les informations structurées.")
    st.markdown("---")

    col1, col2 = st.columns(2)
    with col1:
        application_id = st.number_input("application_id", min_value=1, value=1, step=1)
        uploaded_file  = st.file_uploader("CV (PDF)", type=["pdf"])
    with col2:
        st.info(
            "**Ce que l'agent extrait :**\n"
            "- Nom, email, téléphone\n"
            "- Compétences techniques\n"
            "- Expériences professionnelles\n"
            "- Formation · Langues"
        )

    if st.button("📄 Parser le CV", type="primary", use_container_width=True):
        if not uploaded_file:
            st.error("Veuillez uploader un CV PDF")
        else:
            with st.spinner("⏳ Parsing CV..."):
                result, status = post_files(
                    f"/applications/{application_id}/parse-cv",
                    files={"file": (uploaded_file.name, uploaded_file, "application/pdf")},
                    data={},
                )
            show_result(result, status)


# ═════════════════════════════════════════════════════════════════
# PAGE 4 — AGENT MATCHING
# ═════════════════════════════════════════════════════════════════

elif page == "💼 Agent Matching":
    st.title("💼 Agent Matching — CV ↔ Offre d'emploi")
    st.markdown("Calcule le score de matching entre un CV parsé et une offre.")
    st.markdown("---")

    col1, col2 = st.columns(2)
    with col1:
        application_id = st.number_input("application_id", min_value=1, value=1, step=1)
        job_id         = st.number_input("job_id", min_value=1, value=1, step=1)
    with col2:
        st.info(
            "**Le matching évalue :**\n"
            "- Compétences techniques\n"
            "- Expérience requise vs candidat\n"
            "- Formation et diplômes\n"
            "- Score global 0-100"
        )

    if st.button("💼 Lancer le matching", type="primary", use_container_width=True):
        with st.spinner("⏳ Matching..."):
            result, status = post(f"/applications/{application_id}/match", {"job_id": job_id})
        if status == 200:
            show_score_badge(result.get("matching_score", 0), result.get("matching_level", "weak"))
            st.markdown("---")
            show_result(result, status)
        else:
            show_result(result, status)


# ═════════════════════════════════════════════════════════════════
# PAGE 5 — AGENT MOTIVATION
# ═════════════════════════════════════════════════════════════════

elif page == "✉️ Agent Motivation":
    st.title("✉️ Agent Motivation — Analyse lettre de motivation")
    st.markdown("Analyse une lettre de motivation et retourne un score.")
    st.markdown("---")

    col1, col2 = st.columns(2)
    with col1:
        application_id       = st.number_input("application_id", min_value=1, value=1, step=1)
        motivation_file      = st.file_uploader(
            "Lettre de motivation (TXT ou PDF)",
            type=["txt", "pdf"],
            key="motivation_file_agent",
        )
        # Prévisualisation du contenu extrait
        motivation_letter = ""
        if motivation_file is not None:
            if motivation_file.type == "application/pdf":
                try:
                    import pypdf
                    reader = pypdf.PdfReader(motivation_file)
                    motivation_letter = "\n".join(
                        page.extract_text() or "" for page in reader.pages
                    ).strip()
                except Exception:
                    try:
                        import PyPDF2
                        reader = PyPDF2.PdfReader(motivation_file)
                        motivation_letter = "\n".join(
                            p.extract_text() or "" for p in reader.pages
                        ).strip()
                    except Exception as e:
                        st.error(f"Impossible de lire le PDF : {e}")
            else:
                motivation_letter = motivation_file.read().decode("utf-8", errors="ignore").strip()

            if motivation_letter:
                with st.expander("👁️ Aperçu de la lettre extraite"):
                    st.text(motivation_letter[:1500] + ("..." if len(motivation_letter) > 1500 else ""))
            else:
                st.warning("⚠️ Aucun texte extrait du fichier.")

    with col2:
        st.info(
            "**L'agent analyse :**\n"
            "- Motivation réelle vs générique\n"
            "- Cohérence avec le poste\n"
            "- Compétences mentionnées\n"
            "- Score 0-100\n\n"
            "**Formats acceptés :** `.txt` · `.pdf`"
        )

    if st.button("✉️ Analyser", type="primary", use_container_width=True):
        if not motivation_file:
            st.error("Veuillez uploader une lettre de motivation")
        elif not motivation_letter.strip():
            st.error("Aucun texte détecté dans le fichier")
        else:
            with st.spinner("⏳ Analyse..."):
                result, status = post(
                    f"/applications/{application_id}/analyze-motivation",
                    {"motivation_letter": motivation_letter}
                )
            show_result(result, status)


# ═════════════════════════════════════════════════════════════════
# PAGE 6 — AGENT DÉCISION
# ═════════════════════════════════════════════════════════════════

elif page == "🔴 Agent Décision":
    st.title("🔴 Agent Décision — Décision RH automatique")
    st.markdown(
        "Teste l'Agent Décision directement — sans passer par le pipeline complet. "
        "Utile pour tester les règles avec des scores simulés."
    )
    st.markdown("---")

    tabs = st.tabs([
        "1️⃣ Décision initiale",
        "2️⃣ Décision finale",
        "3️⃣ Rapport RH (depuis DB)",
    ])

    # ── Tab 1 — Décision initiale ────────────────────────────────
    with tabs[0]:
        st.subheader("Décision après matching (Phase 1)")
        st.info(
            "**Règle des 3 cas :**\n\n"
            "🟢 score_final ≥ 70 → **PRÉSÉLECTION** (test technique déclenché)\n\n"
            "🟡 score_final 40-69 → **EN_ATTENTE** (dashboard RH)\n\n"
            "🔴 score_final < 40 → **REJETÉ** (email refus automatique)"
        )

        col1, col2 = st.columns(2)
        with col1:
            di_app_id       = st.number_input("application_id", min_value=1, value=1, step=1, key="di_app")
            di_score_final  = st.slider("score_final", 0, 100, 65, key="di_final")
            di_score_match  = st.slider("score_matching", 0, 100, 60, key="di_match")
            di_score_motiv  = st.slider("score_motivation", 0, 100, 55, key="di_motiv")
        with col2:
            di_signal = st.selectbox("signal_final", ["strong", "medium", "weak", "risk"], index=1, key="di_sig")
            st.markdown("---")
            st.markdown("**Simulation rapide :**")
            if st.button("🟢 Simuler score 75 → PRÉSÉLECTION", use_container_width=True):
                st.session_state["di_final"] = 75
                st.rerun()
            if st.button("🟡 Simuler score 55 → EN_ATTENTE", use_container_width=True):
                st.session_state["di_final"] = 55
                st.rerun()
            if st.button("🔴 Simuler score 30 → REJETÉ", use_container_width=True):
                st.session_state["di_final"] = 30
                st.rerun()

        if st.button("🚀 Appeler decide-initial", type="primary", use_container_width=True, key="btn_di"):
            with st.spinner("⏳ Décision initiale..."):
                result, status = post(
                    f"/applications/{di_app_id}/decide-initial",
                    {
                        "score_final"     : di_score_final,
                        "score_matching"  : di_score_match,
                        "score_motivation": di_score_motiv,
                        "signal_final"    : di_signal,
                    },
                )
            if status == 200:
                st.success("✅ Décision initiale appliquée")
                _display_rh_report(result)
                with st.expander("📦 JSON complet"):
                    st.json(result)
            else:
                show_result(result, status)

    # ── Tab 2 — Décision finale ──────────────────────────────────
    with tabs[1]:
        st.subheader("Décision après test technique (Phase 4)")
        st.info(
            "**Règle décision finale :**\n\n"
            "🟢 technical_score ≥ 70 → **ENTRETIEN** (high priority)\n\n"
            "🟡 technical_score 50-69 → **EN_ATTENTE** (medium — réserve RH)\n\n"
            "🟠 technical_score < 50 → **EN_ATTENTE** (low — peu prioritaire)"
        )

        col1, col2 = st.columns(2)
        with col1:
            df_app_id      = st.number_input("application_id", min_value=1, value=1, step=1, key="df_app")
            df_score_final = st.slider("score_final (matching)", 0, 100, 72, key="df_final")
            df_score_match = st.slider("score_matching", 0, 100, 68, key="df_match")
            df_score_motiv = st.slider("score_motivation", 0, 100, 60, key="df_motiv")
            df_score_tech  = st.slider("technical_score", 0, 100, 74, key="df_tech")
        with col2:
            df_signal = st.selectbox("signal_final", ["strong", "medium", "weak", "risk"], index=0, key="df_sig")
            st.markdown("---")
            st.markdown("**Simulation rapide :**")
            if st.button("🟢 Simuler tech 80 → ENTRETIEN", use_container_width=True):
                st.session_state["df_tech"] = 80
                st.rerun()
            if st.button("🟡 Simuler tech 58 → EN_ATTENTE medium", use_container_width=True):
                st.session_state["df_tech"] = 58
                st.rerun()
            if st.button("🟠 Simuler tech 35 → EN_ATTENTE low", use_container_width=True):
                st.session_state["df_tech"] = 35
                st.rerun()

        if st.button("🚀 Appeler decide-final", type="primary", use_container_width=True, key="btn_df"):
            with st.spinner("⏳ Décision finale..."):
                result, status = post(
                    f"/applications/{df_app_id}/decide-final",
                    {
                        "score_final"     : df_score_final,
                        "score_matching"  : df_score_match,
                        "score_motivation": df_score_motiv,
                        "technical_score" : df_score_tech,
                        "signal_final"    : df_signal,
                    },
                    timeout=60,
                )
            if status == 200:
                st.success("✅ Décision finale appliquée")
                _display_rh_report(result)
                with st.expander("📦 JSON complet"):
                    st.json(result)
            else:
                show_result(result, status)

    # ── Tab 3 — Rapport depuis DB ────────────────────────────────
    with tabs[2]:
        st.subheader("Rapport RH depuis la base de données")
        st.markdown("Charge le dernier rapport RH sauvegardé pour une candidature.")

        col1, col2 = st.columns([1, 2])
        with col1:
            rh_app_id = st.number_input("application_id", min_value=1, value=1, step=1, key="rh_app")
            btn_load  = st.button("📋 Charger le rapport", type="primary", use_container_width=True)

        with col2:
            st.info(
                "Lit le dernier log `decision_agent` depuis la table `ia_logs` "
                "pour cette candidature.\n\n"
                "Si aucun rapport n'existe, retourne le statut actuel de la candidature."
            )

        if btn_load:
            with st.spinner("⏳ Chargement..."):
                result, status = get(f"/applications/{rh_app_id}/rh-report")
            if status == 200:
                _display_rh_report(result)
                with st.expander("📦 JSON complet"):
                    st.json(result)
            else:
                show_result(result, status)


# ═════════════════════════════════════════════════════════════════
# PAGE 7 — PIPELINE COMPLET (v6.0)
# Tabs : 1-Candidature | 2-Test | 3-Agent Décision | 4-Récapitulatif
# ═════════════════════════════════════════════════════════════════

elif page == "⚡ Pipeline Complet":
    st.title("⚡ Pipeline Complet — 5 Agents IA")
    st.markdown(
        "Simule une candidature complète :\n"
        "**CV → Motivation → Matching** *(Tab 1)* → "
        "**Test technique** *(Tab 2)* → "
        "**Agent Décision** *(Tab 3)* → "
        "**Récapitulatif** *(Tab 4)*"
    )
    st.markdown("---")

    tabs = st.tabs([
        "1️⃣ Candidature",
        "2️⃣ Test technique",
        "3️⃣ 🔴 Agent Décision (Agent 5)",
        "4️⃣ Récapitulatif",
    ])

    # ─────────────────────────────────────────────────────────────
    # TAB 1 — Candidature
    # Appelle /apply/{job_id} puis /parse-cv pour récupérer cv_data
    # ─────────────────────────────────────────────────────────────
    with tabs[0]:
        st.subheader("📋 Soumettre une candidature")
        col1, col2 = st.columns(2)
        with col1:
            job_id      = st.number_input("job_id", min_value=1, value=1, step=1)
            uploaded_cv = st.file_uploader("CV (PDF)", type=["pdf"], key="pipeline_cv")
        with col2:
            motivation_file_pipeline = st.file_uploader(
                "Lettre de motivation (TXT ou PDF)",
                type=["txt", "pdf"],
                key="pipeline_motivation",
            )
            motivation = ""
            if motivation_file_pipeline is not None:
                if motivation_file_pipeline.type == "application/pdf":
                    try:
                        import pypdf
                        reader = pypdf.PdfReader(motivation_file_pipeline)
                        motivation = "\n".join(
                            page.extract_text() or "" for page in reader.pages
                        ).strip()
                    except Exception:
                        try:
                            import PyPDF2
                            reader = PyPDF2.PdfReader(motivation_file_pipeline)
                            motivation = "\n".join(
                                p.extract_text() or "" for p in reader.pages
                            ).strip()
                        except Exception as e:
                            st.error(f"Impossible de lire le PDF : {e}")
                else:
                    motivation = motivation_file_pipeline.read().decode("utf-8", errors="ignore").strip()

                if motivation:
                    with st.expander("👁️ Aperçu de la lettre extraite"):
                        st.text(motivation[:1500] + ("..." if len(motivation) > 1500 else ""))
                else:
                    st.warning("⚠️ Aucun texte extrait du fichier.")

        st.caption(
            "💡 Le CV sera utilisé à la fois pour `/apply` et pour `/parse-cv` "
            "(récupération des données brutes pour l'Agent 5)."
        )

        if st.button("🚀 Soumettre la candidature", type="primary", use_container_width=True):
            if not uploaded_cv:
                st.error("CV obligatoire (PDF)")
            elif not motivation_file_pipeline:
                st.error("Lettre de motivation obligatoire")
            elif not motivation.strip():
                st.error("Aucun texte détecté dans le fichier de motivation")
            else:
                # Lire les bytes du CV pour les réutiliser
                cv_bytes = uploaded_cv.read()
                uploaded_cv.seek(0)

                # ── Étape 1 : /apply/{job_id} ──────────────────────
                with st.spinner("⏳ Analyse CV + Motivation + Matching... (peut prendre 1-2 min)"):
                    result_apply, status_apply = post_files(
                        f"/apply/{job_id}",
                        files={
                            "cv"    : (uploaded_cv.name, cv_bytes, "application/pdf"),
                            "lettre": ("lettre.txt", motivation.encode(), "text/plain"),
                        },
                        data={"candidate_email": "candidat@test.com"},
                        timeout=TIMEOUT_LLM_EVALUATE,
                    )

                if status_apply != 200:
                    show_result(result_apply, status_apply)
                    st.stop()

                app_id = result_apply.get("application_id")
                st.success(f"✅ Candidature soumise — application_id = **{app_id}**")
                st.session_state["pipeline_app_id"] = app_id

                # Stocker matching + motivation depuis /apply
                matching_result   = result_apply.get("matching_result", {})
                motivation_result = result_apply.get("motivation_analysed", {})

                st.session_state["pipeline_matching_result"]   = matching_result
                st.session_state["pipeline_motivation_result"] = motivation_result

                # ── Affichage décision initiale ─────────────────────
                col_a, col_b, col_c = st.columns(3)
                with col_a:
                    st.metric("Score final (matching)", f"{matching_result.get('score_final', 0)}/100")
                with col_b:
                    st.metric("Score matching", f"{matching_result.get('score_matching', 0)}/100")
                with col_c:
                    st.metric("Score motivation", f"{motivation_result.get('score_motivation', 0)}/100")

                decision_init = matching_result.get("decision", "")
                if decision_init:
                    st.markdown("---")
                    st.subheader("🤖 Décision initiale automatique (Phase 1)")
                    icons = {
                        "PRÉSÉLECTION": "🔵", "EN_ATTENTE": "🟡",
                        "REJETÉ"      : "🔴", "ENTRETIEN" : "🟢",
                    }
                    st.markdown(f"### {icons.get(decision_init, '⚪')} {decision_init}")
                    if matching_result.get("justification"):
                        with st.expander("📋 Justification matching"):
                            st.json(matching_result.get("justification", {}))

                # ── Étape 2 : /parse-cv → récupérer cv_data brut ───
                # Nécessaire pour enrichir le rapport de l'Agent Décision
                cv_data = {}
                if app_id:
                    with st.spinner("⏳ Récupération données CV brutes pour Agent 5..."):
                        uploaded_cv.seek(0)
                        result_cv, status_cv = post_files(
                            f"/applications/{app_id}/parse-cv",
                            files={"file": (uploaded_cv.name, cv_bytes, "application/pdf")},
                            data={},
                            timeout=TIMEOUT_LLM_EVALUATE,
                        )
                    if status_cv == 200:
                        cv_data = result_cv
                        st.caption(
                            f"✅ CV parsé — {result_cv.get('full_name', 'Inconnu')} "
                            f"| {result_cv.get('years_experience', 0)} an(s) exp. "
                            f"| {len(result_cv.get('skills_all', []))} compétences"
                        )
                    else:
                        st.caption(
                            "⚠️ Parse-CV non disponible — "
                            "données candidat limitées dans le rapport Agent 5."
                        )

                st.session_state["pipeline_cv_data"] = cv_data

                with st.expander("📦 JSON complet /apply"):
                    show_result(result_apply, status_apply)

    # ─────────────────────────────────────────────────────────────
    # TAB 2 — Test technique
    # ─────────────────────────────────────────────────────────────
    with tabs[1]:
        st.subheader("🧪 Test technique")

        default_app = st.session_state.get("pipeline_app_id", 1)
        app_id      = st.number_input(
            "application_id", min_value=1, value=default_app, step=1, key="tab2_app_id"
        )

        # ── Génération ─────────────────────────────────────────────
        st.markdown("#### 1️⃣ Générer le test")
        col1, col2 = st.columns(2)
        with col1:
            role      = st.text_input("Rôle", value="backend_python", key="tab2_role")
            seniority = st.selectbox("Séniorité", ["junior", "mid", "senior"], key="tab2_sen")
        with col2:
            st.markdown("**Skills Coding**")
            tab2_coding_raw   = st.text_area("coding_skills",   value="python\nsql", height=65, key="tab2_coding")
            st.markdown("**Skills Platform**")
            tab2_platform_raw = st.text_area("platform_skills", value="power bi",    height=55, key="tab2_platform")
            st.markdown("**Skills Mixed**")
            tab2_mixed_raw    = st.text_area("mixed_skills",    value="",            height=45, key="tab2_mixed")

        tab2_col1, tab2_col2 = st.columns(2)
        with tab2_col1:
            btn_gen   = st.button("🔨 Générer",   use_container_width=True, key="btn_gen")
        with tab2_col2:
            btn_regen = st.button("🔄 Regénérer", use_container_width=True, key="btn_regen")

        if btn_gen or btn_regen:
            tab2_coding   = [s.strip() for s in tab2_coding_raw.strip().split("\n")   if s.strip()]
            tab2_platform = [s.strip() for s in tab2_platform_raw.strip().split("\n") if s.strip()]
            tab2_mixed    = [s.strip() for s in tab2_mixed_raw.strip().split("\n")    if s.strip()]

            if not (tab2_coding + tab2_platform + tab2_mixed):
                st.error("Au moins 1 skill requis")
            else:
                with st.spinner("⏳ Génération test... (1-3 min)"):
                    result, status = post(
                        f"/applications/{app_id}/generate-test",
                        {
                            "role"            : role.strip(),
                            "coding_skills"   : tab2_coding,
                            "platform_skills" : tab2_platform,
                            "mixed_skills"    : tab2_mixed,
                            "seniority"       : seniority,
                            "force_regenerate": btn_regen,
                        },
                        timeout=TIMEOUT_LLM_GENERATE,
                    )
                if status == 200:
                    _display_generated_questions(
                        result,
                        session_keys={"test_id": "pipeline_test_id", "questions": "pipeline_questions"}
                    )
                    st.session_state["last_questions"] = result.get("questions", [])
                    st.session_state["last_test_id"]   = result.get("test_id")
                else:
                    show_result(result, status)

        # ── Réponses + Correction ──────────────────────────────────
        st.markdown("---")
        st.markdown("#### 2️⃣ Répondre et corriger")

        test_id   = st.text_input(
            "test_id",
            value=st.session_state.get("pipeline_test_id", ""),
            key="tab2_tid"
        )
        questions = st.session_state.get("pipeline_questions", [])

        if questions:
            st.info(f"✅ {len(questions)} questions chargées")
            answers_input = {}

            for q in questions:
                q_type = q["type"]
                label  = f"Q{q['id']} — {q_type.upper()} ({q['points']} pts)"

                if q_type == "mcq":
                    answers_input[q["id"]] = st.selectbox(
                        label, q.get("options", []), key=f"tab2_ans_{q['id']}"
                    )
                else:
                    answers_input[q["id"]] = st.text_area(
                        label,
                        placeholder="Votre approche et justification...",
                        height=100, key=f"tab2_ans_{q['id']}",
                    )

            if st.button("📊 Corriger le test", type="primary", use_container_width=True, key="btn_eval"):
                answers = [
                    {"question_id": qid, "answer": str(ans) if str(ans).strip() else "(pas de réponse)"}
                    for qid, ans in answers_input.items()
                ]
                with st.spinner("⏳ Correction... (1-3 min)"):
                    post(f"/applications/{app_id}/start-test/{test_id}", {})
                    result, status = post(
                        f"/applications/{app_id}/evaluate-test",
                        {"test_id": test_id, "answers": answers},
                        timeout=TIMEOUT_LLM_EVALUATE,
                    )

                if status == 200:
                    st.success("✅ Correction terminée !")
                    st.session_state["pipeline_eval"]          = result
                    st.session_state["pipeline_test_result"]   = result
                    _display_correction_results(result)
                else:
                    show_result(result, status)

        # ── Section Manager (après correction) ─────────────────────
        test_result_done = st.session_state.get("pipeline_test_result")
        if test_result_done:
            st.markdown("---")
            st.markdown("#### 3️⃣ Décision Manager (après meet technique)")
            st.info(
                "Le manager passe en revue le candidat après le test et donne sa décision. "
                "**NON RETENU** → rejet définitif. "
                "**VALIDÉ / À APPROFONDIR** → passage à l'Agent Décision."
            )

            col_m1, col_m2 = st.columns([1, 2])
            with col_m1:
                manager_decision = st.radio(
                    "Décision manager",
                    options=["VALIDÉ", "À_APPROFONDIR", "NON_RETENU"],
                    format_func=lambda x: {
                        "VALIDÉ"        : "✅ VALIDÉ — Profil solide, recommandé",
                        "À_APPROFONDIR" : "🔶 À APPROFONDIR — Discussion complémentaire",
                        "NON_RETENU"    : "❌ NON RETENU — Ne répond pas aux attentes",
                    }[x],
                    key="manager_decision_radio",
                )
            with col_m2:
                manager_note = st.text_area(
                    "Note du manager (optionnelle)",
                    placeholder="Ex: Bonne communication, maîtrise bien Python mais manque d'expérience Docker...",
                    height=120,
                    key="manager_note_input",
                )

            btn_manager = st.button(
                "👔 Soumettre la décision manager",
                type="primary",
                use_container_width=True,
                key="btn_manager_decision",
            )

            if btn_manager:
                tab2_tid_val = st.session_state.get("pipeline_test_id", "")
                tab2_app_val = st.session_state.get("pipeline_app_id", 0)

                if not tab2_tid_val:
                    st.error("❌ test_id introuvable — générez et corrigez d'abord le test.")
                elif not st.session_state.get("pipeline_test_result"):
                    st.error("❌ Le test doit être corrigé avant de soumettre la décision manager.")
                else:
                    # Construction directe du résultat manager depuis session_state
                    # (bypass _SUBMISSION_STATE — correction faite via FastAPI)
                    with st.spinner("⏳ Enregistrement décision manager..."):
                        try:
                            decision_val  = manager_decision.strip().upper()
                            priority_group = (
                                1 if decision_val == "VALIDÉ"
                                else 2 if decision_val == "À_APPROFONDIR"
                                else None
                            )
                            rejected = decision_val == "NON_RETENU"

                            result_mgr = {
                                "error"            : False,
                                "test_id"          : tab2_tid_val,
                                "manager_decision" : decision_val,
                                "manager_note"     : manager_note.strip(),
                                "rejected"         : rejected,
                                "pass_to_agent5"   : not rejected,
                                "priority_group"   : priority_group,
                            }
                            st.session_state["pipeline_manager_result"] = result_mgr

                        except Exception as e:
                            st.error(f"❌ Erreur décision manager : {e}")
                            result_mgr = {"error": True}

                    # Affichage résultat
                    result_mgr = st.session_state.get("pipeline_manager_result", {})
                    if result_mgr and not result_mgr.get("error"):
                        if result_mgr.get("rejected"):
                            st.error(
                                "❌ **Candidat NON RETENU** — rejet définitif après entretien technique.\n\n"
                                f"📋 Note : *{manager_note or 'Aucune note.'}*"
                            )
                            st.warning("⛔ Ce candidat ne sera pas transmis à l'Agent Décision.")
                        else:
                            group = result_mgr.get("priority_group", "?")
                            group_desc = {1: "Groupe 1 — VALIDÉ 🥇", 2: "Groupe 2 — À APPROFONDIR 🥈"}
                            st.success(
                                f"✅ Décision manager enregistrée : **{decision_val}** "
                                f"— {group_desc.get(group, f'Groupe {group}')}\n\n"
                                f"📋 Note : *{manager_note or 'Aucune note.'}*"
                            )
                            st.info("➡️ Rendez-vous dans l'onglet **Agent Décision** pour lancer l'Agent 5.")
                    elif result_mgr.get("error"):
                        st.error(f"❌ Erreur : {result_mgr.get('error_reason', 'Erreur inconnue')}")

            # Affichage résultat existant
            elif "pipeline_manager_result" in st.session_state:
                existing_mgr = st.session_state["pipeline_manager_result"]
                if not existing_mgr.get("error"):
                    if existing_mgr.get("rejected"):
                        st.error("❌ **Candidat NON RETENU** — décision manager déjà enregistrée.")
                    else:
                        st.success(
                            f"✅ Décision manager : **{existing_mgr.get('manager_decision')}** "
                            f"— Groupe {existing_mgr.get('priority_group')}"
                        )

    # ─────────────────────────────────────────────────────────────
    # TAB 3 — AGENT DÉCISION (Agent 5) — NOUVEAU v6.0
    # Appel DIRECT de decision_agent.py — sans API, sans modifier le backend
    # ─────────────────────────────────────────────────────────────
    with tabs[2]:
        st.subheader("🔴 Agent Décision — Décision RH Finale (Agent 5)")
        st.markdown(
            "Agrège les résultats des **4 agents** et produit la **décision finale**. "
            "Appel **Python direct** — aucun endpoint backend requis."
        )

        if not DECISION_AGENT_AVAILABLE:
            st.error(
                "❌ `decision_agent.py` non trouvé dans le dossier courant.\n\n"
                "Placez `decision_agent.py` dans le même répertoire que `test_ui.py` "
                "et relancez : `streamlit run test_ui.py`"
            )
            st.stop()

        # ── Récupérer les données depuis session_state ─────────────
        cv_data           = st.session_state.get("pipeline_cv_data", {})
        matching_result   = st.session_state.get("pipeline_matching_result", {})
        motivation_result = st.session_state.get("pipeline_motivation_result", {})
        test_result       = st.session_state.get("pipeline_test_result", {})
        manager_result    = st.session_state.get("pipeline_manager_result", {})
        app_id            = st.session_state.get("pipeline_app_id", 0)

        # ── Vérification NON_RETENU avant tout ─────────────────────
        if manager_result and manager_result.get("rejected"):
            st.error(
                "❌ Ce candidat a été **NON RETENU** par le manager après l'entretien technique.\n\n"
                f"📋 Note manager : *{manager_result.get('manager_note') or 'Aucune note.'}*\n\n"
                "L'Agent Décision ne sera pas exécuté pour ce candidat."
            )
            st.stop()

        # ── Statut des données disponibles ─────────────────────────
        st.markdown("#### 📊 Données disponibles pour l'Agent Décision")
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            if cv_data:
                st.success(f"✅ CV — {cv_data.get('full_name', 'N/A')}")
            else:
                st.warning("⚠️ CV — non disponible")
        with col2:
            if matching_result:
                st.success(f"✅ Matching — {matching_result.get('score_matching', 0)}/100")
            else:
                st.warning("⚠️ Matching — non disponible")
        with col3:
            if motivation_result:
                st.success(f"✅ Motivation — {motivation_result.get('score_motivation', 0)}/100")
            else:
                st.warning("⚠️ Motivation — non disponible")
        with col4:
            if test_result:
                st.success(f"✅ Test — {test_result.get('technical_score', 0)}/100")
            else:
                st.warning("⚠️ Test — non disponible")
        with col5:
            if manager_result and not manager_result.get("error"):
                grp = manager_result.get("priority_group")
                dec = manager_result.get("manager_decision", "")
                icons_m = {"VALIDÉ": "✅", "À_APPROFONDIR": "🔶"}
                st.success(f"{icons_m.get(dec,'⚪')} Manager — {dec} (Grp {grp})")
            else:
                st.warning("⚠️ Manager — non disponible")

        # ── Mode fallback : saisie manuelle si données manquantes ──
        missing = []
        if not matching_result:
            missing.append("matching")
        if not motivation_result:
            missing.append("motivation")
        if not test_result:
            missing.append("test")

        if missing:
            st.markdown("---")
            st.info(
                f"⚠️ Données manquantes : **{', '.join(missing)}**\n\n"
                "Complétez les onglets précédents OU utilisez les scores manuels ci-dessous."
            )
            st.markdown("#### ✏️ Saisie manuelle des scores")

            col_m1, col_m2, col_m3 = st.columns(3)
            with col_m1:
                manual_matching = st.slider(
                    "score_matching", 0, 100,
                    int(matching_result.get("score_matching", 65)) if matching_result else 65,
                    key="manual_matching"
                )
                manual_score_final = st.slider(
                    "score_final (matching)", 0, 100,
                    int(matching_result.get("score_final", 65)) if matching_result else 65,
                    key="manual_score_final"
                )
            with col_m2:
                manual_motivation = st.slider(
                    "score_motivation", 0, 100,
                    int(motivation_result.get("score_motivation", 60)) if motivation_result else 60,
                    key="manual_motivation"
                )
            with col_m3:
                manual_technical = st.slider(
                    "technical_score", 0, 100,
                    int(test_result.get("technical_score", 55)) if test_result else 55,
                    key="manual_technical"
                )

            # Construire des résultats partiels si nécessaires
            if not matching_result:
                matching_result = {
                    "score_matching"   : manual_matching,
                    "score_final"      : manual_score_final,
                    "signal_final"     : "medium",
                    "decision"         : "EN_ATTENTE",
                    "skills_matched"   : [],
                    "skills_missing"   : [],
                    "confidence"       : {"level": "low"},
                    "score_is_indicative": True,
                    "error"            : False,
                }
            if not motivation_result:
                motivation_result = {
                    "score_motivation"  : manual_motivation,
                    "signal_motivation" : "medium",
                    "pertinence_poste"  : "moyenne",
                    "lettre_generique"  : False,
                    "points_forts"      : [],
                    "error"             : False,
                }
            if not test_result:
                test_result = {
                    "technical_score" : manual_technical,
                    "status"          : (
                        "strong" if manual_technical >= 70
                        else "medium" if manual_technical >= 50
                        else "weak"
                    ),
                    "flags"  : [],
                    "test_id": None,
                    "error"  : False,
                }

        st.markdown("---")

        # ── Prévisualisation avant lancement ──────────────────────
        with st.expander("👁️ Prévisualisation — données envoyées à l'Agent 5"):
            col_p1, col_p2 = st.columns(2)
            with col_p1:
                st.markdown("**cv_data**")
                st.json(cv_data or {"note": "vide — données candidat limitées"})
                st.markdown("**motivation_result**")
                st.json({
                    "score_motivation" : motivation_result.get("score_motivation"),
                    "signal_motivation": motivation_result.get("signal_motivation"),
                    "pertinence_poste" : motivation_result.get("pertinence_poste"),
                    "points_forts"     : motivation_result.get("points_forts"),
                })
            with col_p2:
                st.markdown("**matching_result**")
                st.json({
                    "score_matching"   : matching_result.get("score_matching"),
                    "score_final"      : matching_result.get("score_final"),
                    "signal_final"     : matching_result.get("signal_final"),
                    "decision"         : matching_result.get("decision"),
                    "skills_matched"   : matching_result.get("skills_matched", [])[:5],
                    "skills_missing"   : matching_result.get("skills_missing", [])[:5],
                    "confidence"       : matching_result.get("confidence"),
                })
                st.markdown("**test_result**")
                st.json({
                    "technical_score"  : test_result.get("technical_score"),
                    "status"           : test_result.get("status"),
                    "flags"            : test_result.get("flags"),
                    "test_id"          : test_result.get("test_id"),
                })

        # ── Lancement Agent Décision ───────────────────────────────
        if st.button(
            "🔴 Lancer l'Agent Décision (Agent 5)",
            type="primary",
            use_container_width=True,
            key="btn_decision_agent"
        ):
            with st.spinner("⏳ Agent Décision en cours..."):
                try:
                    decision_result = _run_decision_agent(
                        cv_data           = cv_data,
                        motivation_result = motivation_result,
                        matching_result   = matching_result,
                        test_result       = test_result,
                        manager_result    = manager_result or None,   # ← NOUVEAU v7.0
                        application_id    = app_id or 0,
                        db                = None,
                    )
                    st.session_state["pipeline_decision_result"] = decision_result
                    success = True
                except Exception as e:
                    st.error(f"❌ Erreur Agent Décision : {e}")
                    success = False

            if success:
                decision_result = st.session_state.get("pipeline_decision_result", {})

                if decision_result.get("error"):
                    st.error(f"❌ Agent Décision a retourné une erreur : {decision_result.get('error_reason')}")
                else:
                    st.success("✅ Agent Décision exécuté avec succès !")

                # Affichage rapport complet v6.0
                _display_rh_report_v6(decision_result)

                with st.expander("📦 JSON complet — Agent Décision"):
                    st.json(decision_result)

        # ── Afficher résultat précédent si déjà lancé ──────────────
        elif "pipeline_decision_result" in st.session_state:
            existing = st.session_state["pipeline_decision_result"]
            st.info("ℹ️ Résultat précédent disponible — cliquez le bouton pour relancer.")
            _display_rh_report_v6(existing)

    # ─────────────────────────────────────────────────────────────
    # TAB 4 — Récapitulatif
    # ─────────────────────────────────────────────────────────────
    with tabs[3]:
        st.subheader("📊 Récapitulatif complet du pipeline")

        # ── Résumé toutes les étapes ───────────────────────────────
        all_ok = all([
            st.session_state.get("pipeline_matching_result"),
            st.session_state.get("pipeline_test_result"),
            st.session_state.get("pipeline_decision_result"),
        ])

        if all_ok:
            st.success("✅ Pipeline complet — tous les agents ont produit un résultat")
        else:
            done  = []
            todo  = []
            steps = {
                "pipeline_matching_result" : "Agent Matching",
                "pipeline_test_result"     : "Agent Test",
                "pipeline_decision_result" : "Agent Décision",
            }
            for key, label in steps.items():
                (done if st.session_state.get(key) else todo).append(label)
            if done:
                st.info(f"✅ Complétés : {', '.join(done)}")
            if todo:
                st.warning(f"⏳ En attente : {', '.join(todo)}")

        st.markdown("---")

        # ── Tableau de bord ────────────────────────────────────────
        matching   = st.session_state.get("pipeline_matching_result", {})
        motivation = st.session_state.get("pipeline_motivation_result", {})
        test       = st.session_state.get("pipeline_test_result", {})
        decision   = st.session_state.get("pipeline_decision_result", {})

        if matching or motivation or test or decision:
            st.subheader("📊 Tous les scores")
            c1, c2, c3, c4, c5 = st.columns(5)
            with c1:
                v = matching.get("score_matching", "—")
                st.metric("🔵 Matching", f"{v}/100" if v != "—" else "—")
            with c2:
                v = matching.get("score_final", "—")
                st.metric("🟢 Score final", f"{v}/100" if v != "—" else "—")
            with c3:
                v = motivation.get("score_motivation", "—")
                st.metric("🟠 Motivation", f"{v}/100" if v != "—" else "—")
            with c4:
                v = test.get("technical_score", "—")
                st.metric("🧪 Technique", f"{v}/100" if v != "—" else "—")
            with c5:
                v = decision.get("score_global", "—")
                st.metric("⭐ Global", f"{v}/100" if v != "—" else "—")

        # ── Décision finale ────────────────────────────────────────
        if decision:
            st.markdown("---")
            st.subheader("🔴 Décision finale Agent 5")
            _display_rh_report_v6(decision)

        # ── Résultats correction test ──────────────────────────────
        eval_result = st.session_state.get("pipeline_eval")
        if eval_result:
            st.markdown("---")
            st.subheader("🧪 Détail correction test")
            _display_correction_results(eval_result)

        # ── Rapport RH depuis DB ────────────────────────────────────
        st.markdown("---")
        st.subheader("📋 Rapport RH depuis la base de données")
        default_app_rh = st.session_state.get("pipeline_app_id", 1)
        app_id_logs    = st.number_input(
            "application_id", min_value=1, value=default_app_rh, step=1, key="logs_app_id"
        )
        if st.button("🔍 Charger le rapport RH depuis DB", use_container_width=True):
            result, status = get(f"/applications/{app_id_logs}/rh-report")
            if status == 200:
                _display_rh_report(result)
                with st.expander("📦 JSON complet"):
                    st.json(result)
            else:
                show_result(result, status)