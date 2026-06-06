"""
test_ui.py — Interface Streamlit pour l'Agent Test (v2)
=======================================================
Lancer : streamlit run test_ui.py

Structure :
  🏢 RH — Gérer les postes     : Créer un poste et son test
  👤 Candidat — Passer le test : Démarrer → Répondre → Soumettre
  📊 Résultats                 : Correction détaillée par question
  🔄 Pipeline complet          : /apply/{job_id} bout en bout

Logique de test partagé :
  Même job_id → même test pour tous les candidats
  Chaque candidat a son propre état (PENDING → STARTED → EVALUATED)
"""

import json
import time
import requests
import streamlit as st

# ─────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────

BASE_URL = "http://localhost:8000"

st.set_page_config(
    page_title = "🤖 Recruitment AI — Agent Test",
    page_icon  = "🤖",
    layout     = "wide",
)

# ─────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────

def api_post(endpoint: str, payload: dict, timeout: int = 90) -> tuple[dict, int]:
    try:
        r = requests.post(f"{BASE_URL}{endpoint}", json=payload, timeout=timeout)
        return r.json(), r.status_code
    except requests.exceptions.ConnectionError:
        return {"error": "Backend non disponible — lancez : uvicorn main:app --reload"}, 503
    except requests.exceptions.Timeout:
        return {"error": f"Timeout ({timeout}s) — le LLM met trop de temps"}, 504
    except Exception as e:
        return {"error": str(e)}, 500


def api_post_files(endpoint: str, files: dict, data: dict) -> tuple[dict, int]:
    try:
        r = requests.post(f"{BASE_URL}{endpoint}", files=files, data=data, timeout=120)
        return r.json(), r.status_code
    except requests.exceptions.ConnectionError:
        return {"error": "Backend non disponible"}, 503
    except Exception as e:
        return {"error": str(e)}, 500


def show_json(result: dict, status: int) -> None:
    if status == 200:
        st.success(f"✅ HTTP {status}")
    elif status in (422, 404):
        st.warning(f"⚠️ HTTP {status}")
    elif status >= 500:
        st.error(f"❌ HTTP {status}")
    st.json(result)


def render_score_card(score: float, status: str, earned: int, total: int) -> None:
    """Affiche le score principal avec badge coloré."""
    color_map = {"strong": "🟢", "medium": "🟡", "weak": "🔴"}
    icon = color_map.get(status, "⚪")

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.metric(f"{icon} Score technique", f"{score:.1f}/100", delta=status.upper())
    with col_b:
        st.metric("Points obtenus", f"{earned}/{total}")
    with col_c:
        bar_val = int(score)
        if score >= 70:
            st.progress(bar_val / 100, text=f"STRONG — {score:.1f}%")
        elif score >= 50:
            st.progress(bar_val / 100, text=f"MEDIUM — {score:.1f}%")
        else:
            st.progress(bar_val / 100, text=f"WEAK — {score:.1f}%")


def render_question_result(r: dict, questions: list[dict]) -> None:
    """Affiche le résultat détaillé d'une question avec l'énoncé."""
    earned = r["points_earned"]
    max_pt = r["points_max"]
    qtype  = r["type"].upper()
    diff   = r.get("difficulty", "")

    if earned == max_pt:
        icon = "✅"
    elif earned > 0:
        icon = "🟡"
    else:
        icon = "❌"

    header = f"{icon} Q{r['question_id']} — {qtype} | {diff} | {earned}/{max_pt} pts"

    with st.expander(header):
        # Retrouver l'énoncé
        q_text = next(
            (q["question"] for q in questions if q["id"] == r["question_id"]), ""
        )
        if q_text:
            st.markdown("**Énoncé :**")
            st.info(q_text[:600] + ("..." if len(q_text) > 600 else ""))

        st.markdown("**Feedback :**")
        st.write(r.get("feedback", "Pas de feedback"))

        # Flags de validation Python
        flags = r.get("python_flags", [])
        if flags:
            st.markdown("**Flags de validation :**")
            for f in flags:
                st.warning(f"⚙️ {f}")

        if r.get("validation_applied"):
            st.caption(
                "ℹ️ La validation Python a ajusté le score LLM sur cette question"
            )


def format_time_remaining(start_ts: float, duration_min: int) -> tuple[int, bool]:
    """Retourne (secondes_restantes, is_expired)."""
    elapsed  = time.time() - start_ts
    total    = duration_min * 60
    remaining = int(total - elapsed)
    return max(0, remaining), elapsed >= total


# ─────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────

st.sidebar.title("🤖 Recruitment AI")
st.sidebar.caption("Agent Test v2")
st.sidebar.markdown("---")

page = st.sidebar.radio(
    "Navigation",
    [
        "🏢 RH — Générer un test",
        "👤 Candidat — Passer le test",
        "📊 Résultats détaillés",
        "⚡ Pipeline Complet",
    ],
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

# Statut de la session courante
if "test_id" in st.session_state:
    tid = st.session_state["test_id"]
    state_label = st.session_state.get("test_state", "PENDING")
    state_icons = {"PENDING": "⏳", "STARTED": "🟡", "EVALUATED": "✅"}
    st.sidebar.markdown(
        f"**Test en cours :**\n`{tid[:16]}...`\n\n"
        f"État : {state_icons.get(state_label, '?')} {state_label}"
    )


# ═══════════════════════════════════════════════════════════════════
# PAGE 1 — RH : GÉNÉRER UN TEST POUR UN POSTE
# ═══════════════════════════════════════════════════════════════════

if page == "🏢 RH — Générer un test":
    st.title("🏢 RH — Générer le test technique d'un poste")
    st.markdown(
        "Crée le test pour un poste. Tous les candidats de ce poste recevront **exactement "
        "le même test**. Si un test existe déjà pour ce job_id, il sera réutilisé automatiquement."
    )
    st.info(
        "**Pourquoi le même test par poste ?**\n\n"
        "L'équité entre candidats exige que chacun réponde aux mêmes questions dans les "
        "mêmes conditions. Un test différent par candidat rendrait les scores incomparables."
    )
    st.markdown("---")

    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("📥 Paramètres du poste")
        app_id    = st.number_input("application_id", min_value=1, value=1, step=1)
        job_id    = st.number_input(
            "job_id (même ID = même test pour tous les candidats)",
            min_value=1, value=1, step=1,
            help="Tous les candidats postulant à ce job_id recevront le même test"
        )
        role      = st.text_input("Rôle du poste", value="Backend Python Developer",
                                  placeholder="Ex: Senior Data Engineer, Frontend React Dev...")
        seniority = st.selectbox("Séniorité", ["junior", "mid", "senior"],
                                  help="junior: 0-2 ans | mid: 2-5 ans | senior: 5+ ans")
        skills_raw = st.text_area(
            "Skills requis (un par ligne, max 5)",
            value="python\napi\nsql\ndocker",
            height=130,
            help="Utilisez les mêmes skills que dans l'offre d'emploi"
        )

    with col2:
        st.subheader("ℹ️ Structure du test")
        st.markdown("""
**5 questions automatiquement générées :**

| # | Type | Difficulté | Points |
|---|------|-----------|--------|
| Q1 | MCQ | Easy | 1 pt |
| Q2 | MCQ | Easy | 1 pt |
| Q3 | MCQ | Medium | 2 pts |
| Q4 | Debug | Medium | 3 pts |
| Q5 | Practical | Hard | 4 pts |
| **Total** | | | **11 pts** |

**Qualité des questions :**
- Scénarios réels de production
- Anti-trivia syntaxique (aucune question "what does print output")
- Distracteurs MCQ plausibles (erreurs réelles)
- Debug = bug de code review réel
- Practical = tâche bornée en 10-15 min
        """)

    st.markdown("---")

    if st.button("🚀 Générer le test", type="primary", use_container_width=True):
        skills = [s.strip() for s in skills_raw.strip().split("\n") if s.strip()]

        if not role.strip():
            st.error("Le rôle est obligatoire")
        elif not skills:
            st.error("Au moins 1 skill requis")
        else:
            payload = {
                "role"     : role.strip(),
                "skills"   : skills,
                "seniority": seniority,
                "job_id"   : job_id,
            }

            with st.spinner("⏳ Génération via LLM (20-40 secondes)..."):
                result, status = api_post(
                    f"/applications/{app_id}/generate-test", payload, timeout=120
                )

            if status == 200:
                is_reused = result.get("reused", False)
                if is_reused:
                    st.success(
                        f"✅ Test existant récupéré pour job_id={job_id} "
                        f"(équité garantie — même questions pour tous les candidats)"
                    )
                else:
                    st.success(f"✅ Nouveau test généré pour job_id={job_id}")

                st.info(
                    f"**test_id :** `{result.get('test_id')}` | "
                    f"**Durée :** {result.get('duration')} min | "
                    f"**Questions :** {len(result.get('questions', []))}"
                )

                # Sauvegarder en session
                st.session_state["test_id"]       = result.get("test_id")
                st.session_state["full_questions"] = result.get("questions", [])
                st.session_state["test_app_id"]   = app_id
                st.session_state["test_state"]    = "PENDING"
                st.session_state["test_duration"] = result.get("duration", 25)

                # Afficher les questions
                st.markdown("---")
                st.subheader("📋 Questions générées (vue RH — avec réponses masquées)")
                questions = result.get("questions", [])
                for q in questions:
                    icon_map = {"easy": "🟢", "medium": "🟡", "hard": "🔴"}
                    diff_icon = icon_map.get(q.get("difficulty", ""), "⚪")
                    with st.expander(
                        f"{diff_icon} Q{q['id']} — {q['type'].upper()} | "
                        f"{q['difficulty']} | skill: {q['skill']} | {q['points']} pts"
                    ):
                        st.markdown("**Énoncé :**")
                        st.write(q["question"])
                        if q["type"] == "mcq":
                            st.markdown("**Options :**")
                            for opt in q.get("options", []):
                                st.write(f"  ○ {opt}")
                        elif q["type"] in ("debug", "practical"):
                            criteria = q.get("answer_criteria", [])
                            if criteria:
                                st.markdown("**Critères de correction :**")
                                for c in criteria:
                                    st.write(f"  • {c}")

                st.markdown("---")
                st.info(
                    "👆 Copiez le **test_id** ci-dessus et passez à l'onglet "
                    "**👤 Candidat — Passer le test** pour simuler un candidat."
                )
            else:
                show_json(result, status)


# ═══════════════════════════════════════════════════════════════════
# PAGE 2 — CANDIDAT : PASSER LE TEST
# ═══════════════════════════════════════════════════════════════════

elif page == "👤 Candidat — Passer le test":
    st.title("👤 Candidat — Passer le test technique")
    st.markdown("---")

    # ── Récupérer test_id et questions depuis la session ──────────────────────
    default_test_id = st.session_state.get("test_id", "")
    default_app_id  = st.session_state.get("test_app_id", 1)
    test_state      = st.session_state.get("test_state", "PENDING")
    full_questions  = st.session_state.get("full_questions", [])

    # ── ÉTAPE 0 : Saisir le test_id si pas en session ──────────────────────────
    if not default_test_id or not full_questions:
        st.info(
            "Pour simuler un candidat, générez d'abord un test dans l'onglet "
            "**🏢 RH — Générer un test**, ou entrez un test_id existant ci-dessous."
        )
        col1, col2 = st.columns(2)
        with col1:
            manual_test_id = st.text_input("test_id", placeholder="UUID du test...")
            manual_app_id  = st.number_input("application_id", min_value=1, value=1)
        if st.button("🔍 Charger le test") and manual_test_id:
            st.session_state["test_id"]     = manual_test_id
            st.session_state["test_app_id"] = manual_app_id
            st.session_state["test_state"]  = "PENDING"
            st.rerun()
        st.stop()

    test_id    = default_test_id
    app_id     = default_app_id
    questions  = full_questions

    # ══════════════════════════════════════════════════════════════
    # ÉTAPE 1 : DÉMARRER LE TEST
    # ══════════════════════════════════════════════════════════════
    if test_state == "PENDING":
        st.subheader("🚦 Prêt à commencer ?")

        col1, col2 = st.columns([2, 1])
        with col1:
            st.markdown(f"""
**Informations sur le test :**
- 📋 **{len(questions)} questions** (3 MCQ + 1 Debug + 1 Practical)
- ⏱️ **{st.session_state.get('test_duration', 25)} minutes** pour répondre
- 🔒 Une fois commencé, vous ne pouvez pas relancer le chronomètre
- ⚠️ Toutes les réponses sont obligatoires avant soumission
            """)

        with col2:
            st.markdown("**Distribution des points :**")
            total_pts = sum(q.get("points", 0) for q in questions)
            for q in questions:
                st.write(f"Q{q['id']} ({q['type']}): {q.get('points', 0)} pts")
            st.markdown(f"**Total : {total_pts} pts**")

        st.markdown("---")

        if st.button(
            "▶️ Démarrer le test — le chronomètre se lance",
            type="primary",
            use_container_width=True,
        ):
            # Appeler run_start_test via API (si backend dispo) ou en local
            result, status = api_post(
                f"/applications/{app_id}/start-test/{test_id}", {}
            )

            if status == 200 or status == 503:
                # 503 = backend non dispo → mode standalone OK
                st.session_state["test_state"]    = "STARTED"
                st.session_state["start_time"]    = time.time()
                st.session_state["answers_input"] = {}
                st.rerun()
            else:
                st.error(f"Impossible de démarrer le test : {result.get('error_reason', result)}")

    # ══════════════════════════════════════════════════════════════
    # ÉTAPE 2 : RÉPONDRE AUX QUESTIONS
    # ══════════════════════════════════════════════════════════════
    elif test_state == "STARTED":
        # ── Chronomètre ───────────────────────────────────────────────────────
        start_time   = st.session_state.get("start_time", time.time())
        duration_min = st.session_state.get("test_duration", 25)
        remaining, expired = format_time_remaining(start_time, duration_min)

        mins = remaining // 60
        secs = remaining % 60

        if expired:
            st.error(
                f"⏰ Temps écoulé ! Vous pouvez toujours soumettre vos réponses actuelles."
            )
        else:
            if remaining < 300:   # < 5 minutes
                st.error(f"⏰ Temps restant : {mins:02d}:{secs:02d}")
            elif remaining < 600:  # < 10 minutes
                st.warning(f"⏱️ Temps restant : {mins:02d}:{secs:02d}")
            else:
                st.info(f"⏱️ Temps restant : {mins:02d}:{secs:02d}")

        st.markdown("---")
        st.subheader("📝 Répondez à toutes les questions")

        answers_input = st.session_state.get("answers_input", {})

        # Grouper par type pour l'affichage
        mcq_questions  = [q for q in questions if q["type"] == "mcq"]
        open_questions = [q for q in questions if q["type"] in ("debug", "practical")]

        # ── MCQ ───────────────────────────────────────────────────────────────
        if mcq_questions:
            st.markdown("### 📌 Questions à choix multiple (MCQ)")
            for q in mcq_questions:
                qid  = q["id"]
                diff = q.get("difficulty", "easy")
                pts  = q.get("points", 1)
                icon = {"easy": "🟢", "medium": "🟡", "hard": "🔴"}.get(diff, "⚪")

                st.markdown(
                    f"**Q{qid} — {icon} {diff.capitalize()} | {q.get('skill','')} | {pts} pt(s)**"
                )
                st.write(q["question"])

                opts = q.get("options", [])
                # Ajouter "— Sélectionnez —" au début pour éviter la sélection auto
                display_opts = ["— Sélectionnez votre réponse —"] + opts
                choice = st.selectbox(
                    f"Votre réponse — Q{qid}",
                    options=display_opts,
                    key=f"mcq_{qid}",
                    label_visibility="collapsed",
                )
                if choice != "— Sélectionnez votre réponse —":
                    answers_input[qid] = choice
                else:
                    answers_input.pop(qid, None)

                st.markdown("---")

        # ── Debug et Practical ────────────────────────────────────────────────
        if open_questions:
            st.markdown("### 💻 Questions ouvertes")
            for q in open_questions:
                qid   = q["id"]
                qtype = q["type"]
                diff  = q.get("difficulty", "medium")
                pts   = q.get("points", 3)
                icon  = {"easy": "🟢", "medium": "🟡", "hard": "🔴"}.get(diff, "⚪")

                if qtype == "debug":
                    st.markdown(
                        f"**Q{qid} — 🐛 Debug | {icon} {diff.capitalize()} | "
                        f"{q.get('skill','')} | {pts} pts**"
                    )
                    st.write(q["question"])
                    criteria = q.get("answer_criteria", [])
                    if criteria:
                        with st.expander("📋 Critères de correction"):
                            for c in criteria:
                                st.write(f"• {c}")
                    hint = (
                        "Identifiez le bug précisément (ligne, raison) "
                        "et fournissez le code corrigé complet."
                    )
                else:
                    st.markdown(
                        f"**Q{qid} — ⚙️ Practical | {icon} {diff.capitalize()} | "
                        f"{q.get('skill','')} | {pts} pts**"
                    )
                    st.write(q["question"])
                    criteria = q.get("answer_criteria", [])
                    if criteria:
                        with st.expander("📋 Critères de correction"):
                            for c in criteria:
                                st.write(f"• {c}")
                    hint = "Fournissez une solution complète et fonctionnelle."

                current_val = answers_input.get(qid, "")
                answer_text = st.text_area(
                    hint,
                    value=current_val,
                    height=200,
                    key=f"open_{qid}",
                    placeholder=(
                        "Pour Debug : 1) Le bug est... 2) Code corrigé :\n\n```python\n# votre code\n```"
                        if qtype == "debug"
                        else "Votre solution complète ici..."
                    ),
                )
                if answer_text.strip():
                    answers_input[qid] = answer_text
                else:
                    answers_input.pop(qid, None)

                st.markdown("---")

        # Sauvegarder l'état en temps réel
        st.session_state["answers_input"] = answers_input

        # ── Bouton soumettre ──────────────────────────────────────────────────
        all_answered  = len(answers_input) == len(questions)
        open_answered = all(
            qid in answers_input and len(str(answers_input[qid]).strip()) > 10
            for q in questions if q["type"] in ("debug", "practical")
            for qid in [q["id"]]
        )
        mcq_answered = all(
            qid in answers_input
            for q in questions if q["type"] == "mcq"
            for qid in [q["id"]]
        )

        if not all_answered:
            answered_count = len(answers_input)
            total_count    = len(questions)
            st.warning(
                f"⚠️ {answered_count}/{total_count} questions répondues. "
                "Toutes les questions sont obligatoires."
            )

        col_submit, col_reset = st.columns([3, 1])
        with col_submit:
            submit_disabled = not (mcq_answered and open_answered)
            if st.button(
                "📤 Soumettre le test",
                type="primary",
                use_container_width=True,
                disabled=submit_disabled,
            ):
                st.session_state["test_state"] = "SUBMITTED"
                st.rerun()

        with col_reset:
            if st.button("🔄 Réinitialiser", use_container_width=True):
                for key in ["test_id", "full_questions", "test_state", "start_time",
                            "answers_input", "test_app_id", "correction_result"]:
                    st.session_state.pop(key, None)
                st.rerun()

    # ══════════════════════════════════════════════════════════════
    # ÉTAPE 3 : SOUMETTRE ET CORRIGER
    # ══════════════════════════════════════════════════════════════
    elif test_state == "SUBMITTED":
        st.subheader("📤 Soumission en cours...")

        answers_input = st.session_state.get("answers_input", {})
        answers = [
            {"question_id": qid, "answer": str(ans)}
            for qid, ans in answers_input.items()
        ]

        if not answers:
            st.error("Aucune réponse à soumettre — retournez remplir les questions")
            if st.button("← Retour aux questions"):
                st.session_state["test_state"] = "STARTED"
                st.rerun()
        else:
            with st.spinner(
                f"⏳ Correction en cours ({len(answers)} réponses) — environ 30 secondes..."
            ):
                payload = {"test_id": test_id, "answers": answers}
                result, status = api_post(
                    f"/applications/{app_id}/evaluate-test", payload, timeout=120
                )

            if status == 200 and not result.get("error"):
                st.session_state["test_state"]      = "EVALUATED"
                st.session_state["correction_result"] = result
                st.success("✅ Test corrigé avec succès !")
                st.balloons()
                st.rerun()
            elif result.get("error_type") == "test_not_started":
                # Standalone mode : corriger directement
                st.warning("Mode standalone — correction directe sans state machine API")
                st.session_state["test_state"]      = "EVALUATED"
                st.session_state["correction_result"] = result
                st.rerun()
            else:
                st.error(f"❌ Erreur lors de la correction : {result.get('error_reason', result)}")
                if st.button("← Retour aux questions"):
                    st.session_state["test_state"] = "STARTED"
                    st.rerun()

    # ══════════════════════════════════════════════════════════════
    # ÉTAPE 4 : RÉSULTATS
    # ══════════════════════════════════════════════════════════════
    elif test_state == "EVALUATED":
        result = st.session_state.get("correction_result", {})
        if not result:
            st.warning("Aucun résultat disponible")
            st.stop()

        st.subheader("📊 Résultats de votre test")
        render_score_card(
            result.get("technical_score", 0),
            result.get("status", "weak"),
            result.get("earned_points", 0),
            result.get("total_points", 0),
        )

        flags = result.get("flags", [])
        if flags:
            for flag in flags:
                if flag == "review_recommended":
                    st.warning("👁️ La correction a détecté des incohérences — revue humaine recommandée")
                elif flag == "low_technical":
                    st.error("⚠️ Score technique insuffisant (< 50%)")

        st.markdown("---")
        st.subheader("📋 Détail par question")

        full_q = st.session_state.get("full_questions", [])
        for r in result.get("results", []):
            render_question_result(r, full_q)

        st.markdown("---")
        if st.button("🔄 Nouveau test (réinitialiser)", use_container_width=True):
            for key in ["test_id", "full_questions", "test_state", "start_time",
                        "answers_input", "correction_result"]:
                st.session_state.pop(key, None)
            st.rerun()

        with st.expander("📦 JSON complet de la correction"):
            st.json(result)


# ═══════════════════════════════════════════════════════════════════
# PAGE 3 — RÉSULTATS DÉTAILLÉS
# ═══════════════════════════════════════════════════════════════════

elif page == "📊 Résultats détaillés":
    st.title("📊 Résultats détaillés")

    if "correction_result" in st.session_state:
        result = st.session_state["correction_result"]
        full_q = st.session_state.get("full_questions", [])

        render_score_card(
            result.get("technical_score", 0),
            result.get("status", "weak"),
            result.get("earned_points", 0),
            result.get("total_points", 0),
        )

        st.markdown("---")

        # Analyse par type et difficulté
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**Analyse par type :**")
            type_scores = {}
            for r in result.get("results", []):
                t = r["type"]
                if t not in type_scores:
                    type_scores[t] = {"earned": 0, "max": 0}
                type_scores[t]["earned"] += r["points_earned"]
                type_scores[t]["max"]    += r["points_max"]

            for qtype, scores in type_scores.items():
                pct = scores["earned"] / scores["max"] * 100 if scores["max"] else 0
                icon = "✅" if pct >= 70 else ("🟡" if pct >= 40 else "❌")
                st.write(
                    f"{icon} **{qtype.upper()}** : "
                    f"{scores['earned']}/{scores['max']} pts ({pct:.0f}%)"
                )

        with col2:
            st.markdown("**Analyse par difficulté :**")
            diff_scores = {}
            for r in result.get("results", []):
                d = r.get("difficulty", "unknown")
                if d not in diff_scores:
                    diff_scores[d] = {"earned": 0, "max": 0}
                diff_scores[d]["earned"] += r["points_earned"]
                diff_scores[d]["max"]    += r["points_max"]

            diff_order = ["easy", "medium", "hard"]
            for diff in diff_order:
                if diff in diff_scores:
                    scores = diff_scores[diff]
                    pct    = scores["earned"] / scores["max"] * 100 if scores["max"] else 0
                    icon   = {"easy": "🟢", "medium": "🟡", "hard": "🔴"}.get(diff, "⚪")
                    st.write(
                        f"{icon} **{diff.capitalize()}** : "
                        f"{scores['earned']}/{scores['max']} pts ({pct:.0f}%)"
                    )

        st.markdown("---")
        st.subheader("📋 Détail question par question")
        for r in result.get("results", []):
            render_question_result(r, full_q)

        # Validation globale
        gv = result.get("global_validation", {})
        if gv:
            st.markdown("---")
            st.subheader("🔍 Rapport de validation")
            gv_flags = gv.get("flags", [])
            if gv_flags:
                for f in gv_flags:
                    st.warning(f"⚙️ {f}")
            else:
                st.success("✅ Aucune anomalie détectée dans la correction")

            if gv.get("review_recommended"):
                st.error(
                    "⚠️ **Revue humaine recommandée** — "
                    "certains scores semblent incohérents avec les réponses fournies"
                )

    else:
        st.info("Aucun résultat disponible — passez d'abord un test dans l'onglet Candidat")


# ═══════════════════════════════════════════════════════════════════
# PAGE 4 — PIPELINE COMPLET
# ═══════════════════════════════════════════════════════════════════

elif page == "⚡ Pipeline Complet":
    st.title("⚡ Pipeline Complet — /apply/{job_id}")
    st.markdown(
        "Teste le pipeline complet depuis l'upload CV jusqu'à la décision de matching. "
        "L'agent test vient après le matching si le score est ≥ 70."
    )
    st.markdown("---")

    tabs = st.tabs([
        "📤 Candidature",
        "🧪 Test technique",
        "📊 Résultats globaux"
    ])

    with tabs[0]:
        st.subheader("📤 Déposer une candidature complète")
        col1, col2 = st.columns(2)
        with col1:
            job_id = st.number_input("job_id", min_value=1, value=1)
            email  = st.text_input("Email candidat", value="candidat@test.com")
        with col2:
            st.info(
                "Pipeline exécuté :\n"
                "1. Parsing CV (OCR si nécessaire)\n"
                "2. Analyse lettre de motivation\n"
                "3. Matching CV ↔ Offre\n"
                "4. Décision automatique"
            )

        cv_file     = st.file_uploader("CV (PDF ou DOCX)", type=["pdf", "docx"], key="cv")
        letter_file = st.file_uploader("Lettre de motivation", type=["pdf", "docx"], key="letter")

        if st.button("🚀 Soumettre", type="primary", use_container_width=True):
            if not cv_file or not letter_file:
                st.error("CV et lettre obligatoires")
            else:
                with st.spinner("⏳ Pipeline en cours (30-90s)..."):
                    result, status = api_post_files(
                        f"/apply/{job_id}",
                        files={
                            "cv"    : (cv_file.name, cv_file.getvalue(), cv_file.type),
                            "lettre": (letter_file.name, letter_file.getvalue(), letter_file.type),
                        },
                        data={"candidate_email": email},
                    )

                if status == 200:
                    st.success("✅ Candidature traitée !")
                    st.session_state["pipeline_result"] = result
                    st.session_state["pipeline_app_id"] = result.get("application_id")

                    matching = result.get("matching_result", {})
                    motiv    = result.get("motivation_analysed", {})

                    c1, c2, c3, c4 = st.columns(4)
                    with c1: st.metric("Score final",    matching.get("score_final", "N/A"))
                    with c2: st.metric("Score matching", matching.get("score_matching", "N/A"))
                    with c3: st.metric("Score lettre",   motiv.get("score_motivation", "N/A"))
                    with c4:
                        decision = matching.get("decision", "N/A")
                        icons = {"ENTRETIEN": "🟢", "EN_ATTENTE": "🟡", "REJETÉ": "🔴"}
                        st.metric("Décision", f"{icons.get(decision,'')} {decision}")
                else:
                    show_json(result, status)

    with tabs[1]:
        st.subheader("🧪 Générer le test (après sélection)")
        default_app = st.session_state.get("pipeline_app_id", 1)
        app_id = st.number_input(
            "application_id", min_value=1, value=default_app, step=1
        )

        col1, col2 = st.columns(2)
        with col1:
            role      = st.text_input("Rôle", value="Backend Developer", key="pipe_role")
            seniority = st.selectbox("Séniorité", ["junior", "mid", "senior"], key="pipe_sen")
        with col2:
            skills_raw = st.text_area("Skills", value="python\napi\nsql", height=80, key="pipe_sk")

        if st.button("🔨 Générer le test", use_container_width=True, key="pipe_gen"):
            skills  = [s.strip() for s in skills_raw.strip().split("\n") if s.strip()]
            payload = {"role": role, "skills": skills, "seniority": seniority}

            with st.spinner("⏳ Génération..."):
                result, status = api_post(f"/applications/{app_id}/generate-test", payload)

            if status == 200:
                st.success(f"✅ test_id = `{result.get('test_id')}`")
                st.session_state["test_id"]       = result.get("test_id")
                st.session_state["full_questions"] = result.get("questions", [])
                st.session_state["test_app_id"]   = app_id
                st.session_state["test_state"]    = "PENDING"
                st.info("→ Allez dans **👤 Candidat — Passer le test** pour simuler la réponse")
            else:
                show_json(result, status)

    with tabs[2]:
        st.subheader("📊 Résultats complets")
        if "pipeline_result" in st.session_state:
            show_json(st.session_state["pipeline_result"], 200)
        if "correction_result" in st.session_state:
            st.markdown("**Correction test technique :**")
            show_json(st.session_state["correction_result"], 200)
        if "pipeline_result" not in st.session_state:
            st.info("Soumettez une candidature pour voir les résultats ici")