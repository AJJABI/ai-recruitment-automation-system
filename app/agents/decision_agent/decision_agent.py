"""
decision_agent.py — Agent 5 : Décision RH Finale (v2.0)

Architecture :
═══════════════════════════════════════════════════════════════════
Reçoit les sorties des 4 agents précédents + la décision manager
et produit une décision RH finale structurée avec justification.

Inputs (4 agents + manager) :
  cv_data           ← cv_parser.run_cv_parser()
  motivation_result ← motivation_agent.run_motivation_agent()
  matching_result   ← matching_agent.run_matching_agent()
  test_result       ← test_agent.run_evaluate_test()
  manager_result    ← test_agent.run_manager_decision()  ← NOUVEAU v2.0

Logique de décision finale (v2.0) :

  ÉTAPE 0 — Rejet manager (prioritaire) :
    manager_decision = NON_RETENU → REJETÉ direct, stop.

  ÉTAPE 1 — Score global :
    score_global = 0.60 × score_final_matching   (contient déjà motivation)
                 + 0.40 × technical_score

  ÉTAPE 2 — Décision basée sur score_global :
    score_global >= 70  → ENTRETIEN   (priority: high)
    score_global 50–69  → EN_ATTENTE  (priority: medium)
    score_global < 50   → EN_ATTENTE  (priority: low)

  ÉTAPE 3 — Classement 2 niveaux :
    Niveau 1 : groupe par décision manager
      VALIDÉ        → groupe 1 (classé en premier)
      À_APPROFONDIR → groupe 2 (classé en second)
    Niveau 2 : au sein du groupe → classement par score_global

  Pas de rejet automatique sauf NON_RETENU manager.

Output :
  {
    "decision"          : "ENTRETIEN" | "EN_ATTENTE" | "REJETÉ",
    "priority"          : "high" | "medium" | "low",
    "priority_group"    : 1 | 2,           ← groupe manager (nouveau)
    "manager_decision"  : str,             ← décision manager (nouveau)
    "manager_note"      : str,             ← note manager (nouveau)
    "summary"           : str,
    "score_matching"    : float,
    "score_motivation"  : float,
    "technical_score"   : float,
    "score_global"      : float,
    "candidate_name"    : str,
    "candidate_email"   : str,
    "strengths"         : list[str],
    "weaknesses"        : list[str],
    "flags"             : list[str],
    "justification"     : dict,
    "report"            : dict,
    "error"             : bool,
  }
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────
# CONSTANTES
# ─────────────────────────────────────────────────────────────────

# Seuils décision finale — appliqués sur score_global (v2.0)
SEUIL_ENTRETIEN     = 70   # score_global >= 70 → ENTRETIEN
SEUIL_ATTENTE_MED   = 50   # score_global 50–69 → EN_ATTENTE (medium)
SEUIL_REJET         = 30   # score_global < 30  → REJETÉ automatique
                            # score_global 30–49 → EN_ATTENTE (low)

# Pondération score global (v2.0 — décisionnel)
# score_global = 0.60 × score_final_matching + 0.40 × technical_score
# Note : score_final_matching contient déjà la motivation (0.6×matching + 0.4×motivation)
# → la motivation n'est pas recomptée ici
POIDS_MATCHING_FINAL = 0.60   # score_final du matching agent (inclut motivation)
POIDS_TECHNIQUE      = 0.40   # technical_score du test agent

# Pondération score global affiché (dashboard — informatif uniquement)
POIDS_MATCHING    = 0.40
POIDS_MOTIVATION  = 0.20
POIDS_TECHNIQUE_DISPLAY = 0.40

# Groupes manager pour le classement (v2.0)
MANAGER_PRIORITY_GROUPS = {
    "VALIDÉ"        : 1,   # classé en premier
    "À_APPROFONDIR" : 2,   # classé en second
    "NON_RETENU"    : None, # rejeté direct
}

# Seuils confidence matching
CONFIDENCE_LOW_LEVELS = {"low", "very_low"}


# ─────────────────────────────────────────────────────────────────
# HELPERS — Extraction sécurisée des scores
# ─────────────────────────────────────────────────────────────────

def _safe_float(value, default: float = 0.0) -> float:
    """Convertit une valeur en float, retourne default si impossible."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _extract_cv_info(cv_data: dict) -> dict:
    """
    Extrait les informations clés du CV Parser.
    Retourne un dict normalisé — jamais d'exception.
    """
    if not cv_data or not isinstance(cv_data, dict):
        return {
            "full_name"        : "Candidat inconnu",
            "email"            : "",
            "phone"            : "",
            "cv_quality_score" : 0.0,
            "years_experience" : 0,
            "skills_all"       : [],
            "education"        : [],
        }
    return {
        "full_name"        : cv_data.get("full_name") or "Candidat inconnu",
        "email"            : cv_data.get("email") or "",
        "phone"            : cv_data.get("phone") or "",
        "cv_quality_score" : _safe_float(cv_data.get("cv_quality_score"), 0.0),
        "years_experience" : int(cv_data.get("years_experience") or 0),
        "skills_all"       : cv_data.get("skills_all") or [],
        "education"        : cv_data.get("education") or [],
    }


def _extract_motivation_info(motivation_result: dict) -> dict:
    """Extrait les infos clés de l'Agent Motivation."""
    if not motivation_result or not isinstance(motivation_result, dict):
        return {
            "score_motivation"  : 50.0,
            "signal_motivation" : "medium",
            "pertinence_poste"  : "moyenne",
            "points_forts"      : [],
            "lettre_generique"  : False,
            "error"             : True,
        }
    return {
        "score_motivation"  : _safe_float(motivation_result.get("score_motivation"), 50.0),
        "signal_motivation" : motivation_result.get("signal_motivation") or "medium",
        "pertinence_poste"  : motivation_result.get("pertinence_poste") or "moyenne",
        "points_forts"      : motivation_result.get("points_forts") or [],
        "lettre_generique"  : bool(motivation_result.get("lettre_generique", False)),
        "error"             : bool(motivation_result.get("error", False)),
    }


def _extract_matching_info(matching_result: dict) -> dict:
    """Extrait les infos clés de l'Agent Matching."""
    if not matching_result or not isinstance(matching_result, dict):
        return {
            "score_matching"    : 0.0,
            "score_final"       : 0.0,
            "signal_final"      : "weak",
            "decision_matching" : "EN_ATTENTE",
            "skills_matched"    : [],
            "skills_missing"    : [],
            "confidence_level"  : "low",
            "score_is_indicative": True,
            "error"             : True,
        }
    confidence = matching_result.get("confidence") or {}
    return {
        "score_matching"     : _safe_float(matching_result.get("score_matching"), 0.0),
        "score_final"        : _safe_float(matching_result.get("score_final"), 0.0),
        "signal_final"       : matching_result.get("signal_final") or "weak",
        "decision_matching"  : matching_result.get("decision") or "EN_ATTENTE",
        "skills_matched"     : matching_result.get("skills_matched") or [],
        "skills_missing"     : matching_result.get("skills_missing") or [],
        "confidence_level"   : confidence.get("level") or "low",
        "score_is_indicative": bool(matching_result.get("score_is_indicative", False)),
        "error"              : bool(matching_result.get("error", False)),
    }


def _extract_test_info(test_result: dict) -> dict:
    """Extrait les infos clés de l'Agent Test."""
    if not test_result or not isinstance(test_result, dict):
        return {
            "technical_score" : 0.0,
            "status"          : "weak",
            "flags"           : ["test_missing"],
            "test_id"         : None,
            "error"           : True,
        }
    return {
        "technical_score" : _safe_float(test_result.get("technical_score"), 0.0),
        "status"          : test_result.get("status") or "weak",
        "flags"           : test_result.get("flags") or [],
        "test_id"         : test_result.get("test_id"),
        "error"           : bool(test_result.get("error", False)),
    }


# ─────────────────────────────────────────────────────────────────
# LOGIQUE DE DÉCISION FINALE
# ─────────────────────────────────────────────────────────────────

def _extract_manager_info(manager_result: Optional[dict]) -> dict:
    """Extrait les infos clés de la décision manager."""
    if not manager_result or not isinstance(manager_result, dict):
        return {
            "manager_decision" : None,
            "manager_note"     : "",
            "priority_group"   : None,
            "rejected"         : False,
            "pass_to_agent5"   : True,
        }
    return {
        "manager_decision" : manager_result.get("manager_decision"),
        "manager_note"     : manager_result.get("manager_note", ""),
        "priority_group"   : manager_result.get("priority_group"),
        "rejected"         : bool(manager_result.get("rejected", False)),
        "pass_to_agent5"   : bool(manager_result.get("pass_to_agent5", True)),
    }


# ─────────────────────────────────────────────────────────────────
# LOGIQUE DE DÉCISION FINALE
# ─────────────────────────────────────────────────────────────────

def _compute_score_global_decisional(
    score_final_matching: float,
    technical_score     : float,
) -> float:
    """
    Calcule le score global décisionnel (v2.0).

    score_global = 0.60 × score_final_matching
                 + 0.40 × technical_score

    score_final_matching = sortie du matching_agent (contient déjà
    la motivation à 40% : 0.6×matching + 0.4×motivation).
    La motivation n'est pas recomptée ici.
    """
    score = (
        score_final_matching * POIDS_MATCHING_FINAL +
        technical_score      * POIDS_TECHNIQUE
    )
    return round(max(0.0, min(100.0, score)), 2)


def _compute_final_decision(
    score_global     : float,
    decision_matching: str,
    confidence_level : str,
) -> tuple[str, str]:
    """
    Applique la règle de décision finale (v2.0).

    Basée sur score_global (matching + technique) — pas technical_score seul.

    Règles :
      score_global >= 70  → ENTRETIEN  (priority: high)
      score_global 50–69  → EN_ATTENTE (priority: medium)
      score_global < 50   → EN_ATTENTE (priority: low)

    Pas de rejet automatique ici — seul NON_RETENU manager rejette.

    Returns:
      (decision, priority)
    """
    if score_global >= SEUIL_ENTRETIEN:
        return "ENTRETIEN", "high"
    elif score_global >= SEUIL_ATTENTE_MED:
        return "EN_ATTENTE", "medium"
    elif score_global >= SEUIL_REJET:
        return "EN_ATTENTE", "low"
    else:
        return "REJETÉ", "low"


def _compute_score_global(
    score_matching  : float,
    score_motivation: float,
    technical_score : float,
) -> float:
    """
    Calcule le score global affiché sur le dashboard RH (informatif uniquement).
    La décision repose sur _compute_score_global_decisional().
    """
    score = (
        score_matching   * POIDS_MATCHING         +
        score_motivation * POIDS_MOTIVATION        +
        technical_score  * POIDS_TECHNIQUE_DISPLAY
    )
    return round(score, 2)


# ─────────────────────────────────────────────────────────────────
# FORCES & FAIBLESSES
# ─────────────────────────────────────────────────────────────────

def _build_strengths(
    cv_info        : dict,
    motivation_info: dict,
    matching_info  : dict,
    test_info      : dict,
) -> list[str]:
    """Génère la liste des points forts du candidat."""
    strengths = []

    # Score technique
    if test_info["technical_score"] >= SEUIL_ENTRETIEN:
        strengths.append(
            f"Score technique solide ({test_info['technical_score']:.0f}/100)"
        )
    elif test_info["technical_score"] >= SEUIL_ATTENTE_MED:
        strengths.append(
            f"Score technique correct ({test_info['technical_score']:.0f}/100)"
        )

    # Matching skills
    skills_matched = matching_info["skills_matched"]
    if skills_matched:
        n = len(skills_matched)
        preview = ", ".join(skills_matched[:3])
        suffix  = f" (+ {n - 3} autres)" if n > 3 else ""
        strengths.append(f"{n} compétence(s) clé(s) validée(s) : {preview}{suffix}")

    # Motivation
    if motivation_info["score_motivation"] >= 70:
        strengths.append(
            f"Lettre de motivation pertinente "
            f"(score {motivation_info['score_motivation']:.0f}/100)"
        )

    # Points forts motivation
    for pt in (motivation_info["points_forts"] or [])[:2]:
        if pt and pt not in strengths:
            strengths.append(pt)

    # Expérience
    years = cv_info["years_experience"]
    if years >= 3:
        strengths.append(f"{years} an(s) d'expérience professionnelle")

    # CV quality
    if cv_info["cv_quality_score"] >= 75:
        strengths.append("CV de bonne qualité et bien structuré")

    return strengths[:6]  # max 6 points forts


def _build_weaknesses(
    motivation_info: dict,
    matching_info  : dict,
    test_info      : dict,
    flags          : list = None,
) -> list[str]:
    """Génère la liste des points faibles du candidat."""
    weaknesses = []
    flags = flags or []

    # Score technique insuffisant pour entretien (entre seuils)
    if SEUIL_ATTENTE_MED <= test_info["technical_score"] < SEUIL_ENTRETIEN:
        weaknesses.append(
            f"Score technique insuffisant pour entretien "
            f"({test_info['technical_score']:.0f}/100 — seuil requis : {SEUIL_ENTRETIEN})"
        )

    # Score technique très faible
    if test_info["technical_score"] < SEUIL_ATTENTE_MED:
        weaknesses.append(
            f"Score technique insuffisant ({test_info['technical_score']:.0f}/100 "
            f"— seuil requis : {SEUIL_ENTRETIEN})"
        )

    # Compétences manquantes
    skills_missing = matching_info["skills_missing"]
    if skills_missing:
        n       = len(skills_missing)
        preview = ", ".join(skills_missing[:3])
        suffix  = f" (+ {n - 3} autres)" if n > 3 else ""
        weaknesses.append(f"{n} compétence(s) requise(s) absente(s) : {preview}{suffix}")

    # Motivation faible
    if motivation_info["score_motivation"] < 40:
        weaknesses.append(
            f"Lettre de motivation peu pertinente "
            f"(score {motivation_info['score_motivation']:.0f}/100)"
        )
    elif motivation_info["lettre_generique"]:
        weaknesses.append("Lettre de motivation générique, peu personnalisée")

    # Flags test
    if "low_technical" in (test_info["flags"] or []):
        weaknesses.append("Niveau technique en dessous du seuil attendu")
    if "review_recommended" in (test_info["flags"] or []):
        weaknesses.append("Correction du test recommande une revue humaine")

    # Confidence matching faible
    if matching_info["confidence_level"] in CONFIDENCE_LOW_LEVELS:
        weaknesses.append(
            "Confiance de l'analyse matching faible — "
            "revue RH recommandée"
        )

    # Flags système → points faibles lisibles
    if "low_cv_quality" in flags:
        weaknesses.append("Qualité du CV insuffisante — données candidat limitées")
    if "motivation_agent_error" in flags:
        weaknesses.append("Analyse de motivation incomplète — lettre illisible ou inaccessible")

    return weaknesses[:5]  # max 5 points faibles


# ─────────────────────────────────────────────────────────────────
# FLAGS SYSTÈME
# ─────────────────────────────────────────────────────────────────

def _build_flags(
    cv_info        : dict,
    motivation_info: dict,
    matching_info  : dict,
    test_info      : dict,
) -> list[str]:
    """
    Génère des flags système pour le dashboard RH.
    Flags informatifs — ne modifient pas la décision.
    """
    flags = []

    # Erreurs agents
    if cv_info.get("error"):
        flags.append("cv_agent_error")
    if motivation_info.get("error"):
        flags.append("motivation_agent_error")
    if matching_info.get("error"):
        flags.append("matching_agent_error")
    if test_info.get("error"):
        flags.append("test_agent_error")

    # Score indicatif (TF-IDF fallback matching)
    if matching_info["score_is_indicative"]:
        flags.append("matching_score_indicative")

    # Confidence faible
    if matching_info["confidence_level"] in CONFIDENCE_LOW_LEVELS:
        flags.append(f"low_confidence_matching:{matching_info['confidence_level']}")

    # Test flags propagés
    for flag in (test_info["flags"] or []):
        if flag not in flags:
            flags.append(f"test:{flag}")

    # CV qualité faible
    if cv_info["cv_quality_score"] < 40:
        flags.append("low_cv_quality")

    return flags


# ─────────────────────────────────────────────────────────────────
# RÉSUMÉ TEXTUEL
# ─────────────────────────────────────────────────────────────────

def _build_summary(
    candidate_name  : str,
    decision        : str,
    priority        : str,
    technical_score : float,
    score_matching  : float,
    score_motivation: float,
    score_global    : float,
) -> str:
    """
    Génère un résumé textuel exploitable par le dashboard RH.
    """
    priority_label = {
        "high"  : "haute priorité",
        "medium": "priorité moyenne",
        "low"   : "faible priorité",
    }.get(priority, "priorité inconnue")

    if decision == "ENTRETIEN":
        return (
            f"{candidate_name} — Profil validé pour entretien ({priority_label}). "
            f"Score technique : {technical_score:.0f}/100 | "
            f"Matching : {score_matching:.0f}/100 | "
            f"Motivation : {score_motivation:.0f}/100 | "
            f"Score global : {score_global:.0f}/100."
        )
    elif priority == "medium":
        return (
            f"{candidate_name} — Profil en réserve, examen RH requis. "
            f"Score technique : {technical_score:.0f}/100 (seuil : {SEUIL_ENTRETIEN}). "
            f"Matching : {score_matching:.0f}/100 | "
            f"Motivation : {score_motivation:.0f}/100."
        )
    else:
        return (
            f"{candidate_name} — Profil conservé, faible priorité. "
            f"Score technique insuffisant ({technical_score:.0f}/100). "
            f"Matching : {score_matching:.0f}/100 | "
            f"Motivation : {score_motivation:.0f}/100."
        )


# ─────────────────────────────────────────────────────────────────
# JUSTIFICATION STRUCTURÉE
# ─────────────────────────────────────────────────────────────────

def _build_justification(
    decision        : str,
    priority        : str,
    technical_score : float,
    score_matching  : float,
    score_motivation: float,
    score_global    : float,
    matching_info   : dict,
    test_info       : dict,
    strengths       : list[str],
    weaknesses      : list[str],
    flags           : list[str],
) -> dict:
    """Construit la justification structurée pour le rapport RH."""

    # Règle principale déclenchée
    if technical_score >= SEUIL_ENTRETIEN:
        rule = f"technical_score={technical_score:.0f} >= {SEUIL_ENTRETIEN} → ENTRETIEN"
    elif technical_score >= SEUIL_ATTENTE_MED:
        rule = (
            f"technical_score={technical_score:.0f} entre {SEUIL_ATTENTE_MED} "
            f"et {SEUIL_ENTRETIEN - 1} → EN_ATTENTE (medium)"
        )
    else:
        rule = (
            f"technical_score={technical_score:.0f} < {SEUIL_ATTENTE_MED} "
            f"→ EN_ATTENTE (low priority)"
        )

    return {
        "decision_rule"    : rule,
        "decision"         : decision,
        "priority"         : priority,
        "scores": {
            "technical_score" : round(technical_score, 2),
            "score_matching"  : round(score_matching, 2),
            "score_motivation": round(score_motivation, 2),
            "score_global"    : score_global,
        },
        "weights": {
            "matching"   : POIDS_MATCHING,
            "motivation" : POIDS_MOTIVATION,
            "technique"  : POIDS_TECHNIQUE,
        },
        "matching_context": {
            "initial_decision"    : matching_info["decision_matching"],
            "signal_final"        : matching_info["signal_final"],
            "confidence"          : matching_info["confidence_level"],
            "score_is_indicative" : matching_info["score_is_indicative"],
        },
        "test_context": {
            "test_id"    : test_info["test_id"],
            "status"     : test_info["status"],
            "test_flags" : test_info["flags"],
        },
        "strengths"  : strengths,
        "weaknesses" : weaknesses,
        "flags"      : flags,
        "note": (
            "Pas de rejet automatique à cette étape. "
            "Les profils EN_ATTENTE restent disponibles pour examen RH manuel."
        ),
    }


# ─────────────────────────────────────────────────────────────────
# RAPPORT RH (Phase 6 — PDF)
# ─────────────────────────────────────────────────────────────────

def _build_hr_report(
    candidate_name  : str,
    candidate_email : str,
    decision        : str,
    priority        : str,
    summary         : str,
    score_matching  : float,
    score_motivation: float,
    technical_score : float,
    score_global    : float,
    cv_info         : dict,
    matching_info   : dict,
    test_info       : dict,
    strengths       : list[str],
    weaknesses      : list[str],
    flags           : list[str],
    generated_at    : str,
) -> dict:
    """
    Rapport complet généré pour le dashboard RH (Phase 6).
    Format : { "decision": "ENTRETIEN", "priority": "high", "summary": "..." }
    """
    return {
        "decision"         : decision,
        "priority"         : priority,
        "summary"          : summary,
        "generated_at"     : generated_at,

        # Identité candidat
        "candidate": {
            "name"            : candidate_name,
            "email"           : candidate_email,
            "phone"           : cv_info["phone"],
            "years_experience": cv_info["years_experience"],
            "cv_quality"      : cv_info["cv_quality_score"],
            "skills_all"      : cv_info["skills_all"],
        },

        # Scores consolidés
        "scores": {
            "technical_score" : round(technical_score, 2),
            "score_matching"  : round(score_matching, 2),
            "score_motivation": round(score_motivation, 2),
            "score_global"    : score_global,
        },

        # Détails matching
        "matching": {
            "initial_decision"  : matching_info["decision_matching"],
            "skills_matched"    : matching_info["skills_matched"],
            "skills_missing"    : matching_info["skills_missing"],
            "confidence"        : matching_info["confidence_level"],
        },

        # Détails test
        "test": {
            "test_id"      : test_info["test_id"],
            "status"       : test_info["status"],
            "flags"        : test_info["flags"],
        },

        # Synthèse RH
        "strengths"  : strengths,
        "weaknesses" : weaknesses,
        "flags"      : flags,

        # Prochaine étape recommandée
        "next_step": (
            "Planifier un entretien (Phase 5 — Module Planning)"
            if decision == "ENTRETIEN"
            else "Conserver en réserve — décision RH manuelle requise"
        ),
    }


# ─────────────────────────────────────────────────────────────────
# RÉSULTAT D'ERREUR
# ─────────────────────────────────────────────────────────────────

def _error_result(reason: str) -> dict:
    return {
        "decision"        : "EN_ATTENTE",
        "priority"        : "low",
        "summary"         : f"Erreur agent décision : {reason}",
        "score_matching"  : 0.0,
        "score_motivation": 0.0,
        "technical_score" : 0.0,
        "score_global"    : 0.0,
        "candidate_name"  : "Inconnu",
        "candidate_email" : "",
        "strengths"       : [],
        "weaknesses"      : [],
        "flags"           : ["decision_agent_error"],
        "justification"   : {},
        "report"          : {},
        "error"           : True,
        "error_reason"    : reason,
    }


# ─────────────────────────────────────────────────────────────────
# FONCTION PRINCIPALE
# ─────────────────────────────────────────────────────────────────

def analyze_final_decision(
    cv_data          : dict,
    motivation_result: dict,
    matching_result  : dict,
    test_result      : dict,
    manager_result   : Optional[dict] = None,   # ← NOUVEAU v2.0
) -> dict:
    """
    Analyse principale — produit la décision RH finale (v2.0).

    Paramètres :
      cv_data           : sortie de cv_parser.run_cv_parser()
      motivation_result : sortie de motivation_agent.run_motivation_agent()
      matching_result   : sortie de matching_agent.run_matching_agent()
      test_result       : sortie de test_agent.run_evaluate_test()
      manager_result    : sortie de test_agent.run_manager_decision() (optionnel)

    Retourne :
      dict complet avec décision, rapport, justification.
      Retourne toujours un dict — jamais None.
    """
    try:
        generated_at = datetime.now(timezone.utc).isoformat()

        # ── Étape 1 : Extraction sécurisée des données ────────────────
        cv_info         = _extract_cv_info(cv_data)
        motivation_info = _extract_motivation_info(motivation_result)
        matching_info   = _extract_matching_info(matching_result)
        test_info       = _extract_test_info(test_result)
        manager_info    = _extract_manager_info(manager_result)   # ← NOUVEAU

        # ── Étape 2 : Récupérer les scores ────────────────────────────
        technical_score     = test_info["technical_score"]
        score_matching      = matching_info["score_matching"]
        score_final_matching= matching_info["score_final"]   # inclut déjà motivation
        score_motivation    = motivation_info["score_motivation"]

        # ── ÉTAPE 0 : Rejet manager NON_RETENU (prioritaire) ──────────
        if manager_info["rejected"]:
            logger.info(
                f"[decision_agent] NON_RETENU manager — "
                f"candidat={cv_info['full_name']} rejeté direct."
            )
            result = {
                "decision"         : "REJETÉ",
                "priority"         : "low",
                "priority_group"   : None,
                "manager_decision" : manager_info["manager_decision"],
                "manager_note"     : manager_info["manager_note"],
                "summary"          : (
                    f"{cv_info['full_name']} — Rejeté après entretien technique. "
                    f"Décision manager : NON RETENU. "
                    f"Note : {manager_info['manager_note'] or 'Aucune note.'}"
                ),
                "score_matching"   : round(score_matching, 2),
                "score_motivation" : round(score_motivation, 2),
                "technical_score"  : round(technical_score, 2),
                "score_global"     : 0.0,
                "candidate_name"   : cv_info["full_name"],
                "candidate_email"  : cv_info["email"],
                "strengths"        : [],
                "weaknesses"       : ["Non retenu par le manager après entretien technique"],
                "flags"            : ["manager_non_retenu"],
                "justification"    : {
                    "decision_rule": "manager_decision=NON_RETENU → REJETÉ direct",
                    "manager_note" : manager_info["manager_note"],
                },
                "report"           : {
                    "decision"    : "REJETÉ",
                    "priority"    : "low",
                    "next_step"   : "Envoyer email de refus au candidat",
                    "manager_note": manager_info["manager_note"],
                    "generated_at": generated_at,
                },
                "generated_at" : generated_at,
                "error"        : False,
            }
            return result

        # ── Étape 3 : Score global décisionnel (v2.0) ─────────────────
        # 0.60 × score_final_matching + 0.40 × technical_score
        score_global_decisional = _compute_score_global_decisional(
            score_final_matching = score_final_matching,
            technical_score      = technical_score,
        )

        # Score global affiché (dashboard — informatif)
        score_global = _compute_score_global(
            score_matching, score_motivation, technical_score
        )

        # ── Étape 4 : Décision finale basée sur score_global ──────────
        decision, priority = _compute_final_decision(
            score_global      = score_global_decisional,
            decision_matching = matching_info["decision_matching"],
            confidence_level  = matching_info["confidence_level"],
        )

        # ── Étape 5 : Groupe manager pour classement 2 niveaux ────────
        priority_group   = manager_info["priority_group"]
        manager_decision = manager_info["manager_decision"]
        manager_note     = manager_info["manager_note"]

        # ── Étape 6 : Forces, faiblesses, flags ───────────────────────
        strengths  = _build_strengths(cv_info, motivation_info, matching_info, test_info)
        flags      = _build_flags(cv_info, motivation_info, matching_info, test_info)
        # Ajouter flag manager si À_APPROFONDIR
        if manager_decision == "À_APPROFONDIR":
            flags.append("manager_a_approfondir")
        weaknesses = _build_weaknesses(motivation_info, matching_info, test_info, flags=flags)

        # ── Étape 7 : Résumé textuel ──────────────────────────────────
        summary = _build_summary(
            candidate_name   = cv_info["full_name"],
            decision         = decision,
            priority         = priority,
            technical_score  = technical_score,
            score_matching   = score_matching,
            score_motivation = score_motivation,
            score_global     = score_global,
        )

        # ── Étape 8 : Justification structurée ───────────────────────
        justification = _build_justification(
            decision         = decision,
            priority         = priority,
            technical_score  = technical_score,
            score_matching   = score_matching,
            score_motivation = score_motivation,
            score_global     = score_global_decisional,
            matching_info    = matching_info,
            test_info        = test_info,
            strengths        = strengths,
            weaknesses       = weaknesses,
            flags            = flags,
        )

        # ── Étape 9 : Rapport RH complet ─────────────────────────────
        report = _build_hr_report(
            candidate_name   = cv_info["full_name"],
            candidate_email  = cv_info["email"],
            decision         = decision,
            priority         = priority,
            summary          = summary,
            score_matching   = score_matching,
            score_motivation = score_motivation,
            technical_score  = technical_score,
            score_global     = score_global,
            cv_info          = cv_info,
            matching_info    = matching_info,
            test_info        = test_info,
            strengths        = strengths,
            weaknesses       = weaknesses,
            flags            = flags,
            generated_at     = generated_at,
        )

        result = {
            "decision"         : decision,
            "priority"         : priority,
            "priority_group"   : priority_group,    # ← NOUVEAU : 1=VALIDÉ / 2=À_APPROFONDIR
            "manager_decision" : manager_decision,  # ← NOUVEAU
            "manager_note"     : manager_note,      # ← NOUVEAU
            "summary"          : summary,
            "score_matching"   : round(score_matching, 2),
            "score_motivation" : round(score_motivation, 2),
            "technical_score"  : round(technical_score, 2),
            "score_global"     : score_global,
            "score_global_decisional": score_global_decisional,  # ← score décisionnel
            "candidate_name"   : cv_info["full_name"],
            "candidate_email"  : cv_info["email"],
            "strengths"        : strengths,
            "weaknesses"       : weaknesses,
            "flags"            : flags,
            "justification"    : justification,
            "report"           : report,
            "generated_at"     : generated_at,
            "error"            : False,
        }

        logger.info(
            f"Décision finale — {decision} [{priority}] groupe={priority_group} | "
            f"score_global_decisional={score_global_decisional:.1f} "
            f"(matching_final={score_final_matching:.1f} × 0.60 + "
            f"technique={technical_score:.1f} × 0.40) | "
            f"manager={manager_decision} | candidat={cv_info['full_name']} | flags={flags}"
        )
        return result

    except Exception as e:
        logger.error(f"Erreur analyze_final_decision : {e}", exc_info=True)
        return _error_result(str(e))


# ─────────────────────────────────────────────────────────────────
# WRAPPER FASTAPI / n8n
# ─────────────────────────────────────────────────────────────────

def run_decision_agent(
    cv_data          : dict,
    motivation_result: dict,
    matching_result  : dict,
    test_result      : dict,
    manager_result   : Optional[dict] = None,   # ← NOUVEAU v2.0
    application_id   : int = 0,
    db               = None,
) -> dict:
    """
    Wrapper FastAPI / n8n — retourne toujours un dict.

    Appelle analyze_final_decision() puis :
      - Met à jour Application.status + Application.priority en BDD
      - Sauvegarde le résultat complet dans IA_Log

    Paramètres :
      cv_data, motivation_result, matching_result, test_result : sorties agents
      manager_result   : sortie de test_agent.run_manager_decision() (optionnel)
      application_id   : ID de la candidature en base de données
      db               : session SQLAlchemy (Depends(get_db))

    Retourne :
      dict résultat — toujours non-None
    """
    try:
        result = analyze_final_decision(
            cv_data           = cv_data,
            motivation_result = motivation_result,
            matching_result   = matching_result,
            test_result       = test_result,
            manager_result    = manager_result,   # ← NOUVEAU
        )
    except Exception as e:
        logger.error(
            f"  [decision_agent] Exception inattendue "
            f"application_id={application_id} : {e}",
            exc_info=True,
        )
        result = _error_result(str(e))

    # ── Sauvegarder en BDD ────────────────────────────────────────────
    if db and application_id:
        try:
            from app.models import Application, IA_Log

            application = db.query(Application).filter(
                Application.id == application_id
            ).first()

            if application:
                application.priority  = result["priority"]
                # Mapper la décision vers le bon status_v2
                _FINAL_STATUS_MAP = {
                    "ENTRETIEN" : "INTERVIEW_ELIGIBLE",
                    "EN_ATTENTE": "TECH_EVALUATED",
                    "REJETÉ"    : "REJECTED_FINAL",
                }
                application.status_v2 = _FINAL_STATUS_MAP.get(
                    result.get("decision", "EN_ATTENTE"), "TECH_EVALUATED"
                )
                db.commit()
                logger.info(
                    f"Application {application_id} mise à jour : "
                    f"status_v2={application.status_v2} priority={result['priority']}"
                    + (" [ERROR_FALLBACK]" if result.get("error") else "")
                )
            else:
                logger.warning(
                    f"  [decision_agent] Application {application_id} introuvable "
                    f"— status non sauvegardé"
                )

            # Sauvegarder dans IA_Log
            log = IA_Log(
                application_id = application_id,
                agent_name     = "decision_agent",
                output_json    = json.dumps(result, ensure_ascii=False, default=str),
            )
            db.add(log)
            db.commit()
            logger.info(
                f"IA_Log sauvegardé — agent: decision_agent, "
                f"app: {application_id}"
            )

        except Exception as db_error:
            logger.error(
                f"  [decision_agent] Erreur BDD application_id={application_id} : "
                f"{db_error}",
                exc_info=True,
            )

    return result


# ─────────────────────────────────────────────────────────────────
# WRAPPERS PHASE 1 (initiale) ET PHASE 4 (finale)
# Attendus par app/routers/decision.py
# ─────────────────────────────────────────────────────────────────

def run_decision_initial(
    application_id  : int,
    score_final     : float,
    score_matching  : float,
    score_motivation: float,
    signal_final    : str,
    cv_profile      : dict,
    job_title       : str,
    job_skills      : str,
    candidate_email : str,
    db              = None,
) -> dict:
    """
    Décision après Phase 1 (CV + Motivation + Matching) — sans test technique.

    Règles :
      score_final >= 70  → PRÉSÉLECTION  (priority: high)
      score_final 40-69  → EN_ATTENTE    (priority: medium)
      score_final < 40   → REJETÉ        (priority: low)

    Sauvegarde Application.status + IA_Log (agent_name="decision_agent_initial").
    """
    try:
        # ── Construire cv_data compatible _extract_cv_info ────────────
        cv_data = {
            "full_name"        : cv_profile.get("full_name", "Candidat inconnu"),
            "email"            : candidate_email or cv_profile.get("email", ""),
            "phone"            : cv_profile.get("phone", ""),
            "cv_quality_score" : 0.0,
            "years_experience" : cv_profile.get("years_experience", 0),
            "skills_all"       : cv_profile.get("skills", []),
            "education"        : cv_profile.get("education", []),
        }

        # ── Décision initiale basée sur score_final ───────────────────
        if score_final >= 70:
            initial_decision = "PRÉSÉLECTION"
            priority         = "high"
            next_step        = "Envoyer test technique"
        elif score_final >= 40:
            initial_decision = "EN_ATTENTE"
            priority         = "medium"
            next_step        = "Mise en attente RH"
        else:
            initial_decision = "REJETÉ"
            priority         = "low"
            next_step        = "Envoyer email de refus"

        score_global = round(score_matching * 0.6 + score_motivation * 0.4, 1)
        generated_at = datetime.now(timezone.utc).isoformat()

        result = {
            "decision"        : initial_decision,
            "priority"        : priority,
            "summary"         : (
                f"{cv_data['full_name']} — Décision initiale : {initial_decision}. "
                f"Score global : {score_final:.0f}/100 | "
                f"Matching : {score_matching:.0f}/100 | "
                f"Motivation : {score_motivation:.0f}/100."
            ),
            "score_final"     : round(score_final, 2),
            "score_matching"  : round(score_matching, 2),
            "score_motivation": round(score_motivation, 2),
            "technical_score" : None,
            "score_global"    : score_global,
            "candidate_name"  : cv_data["full_name"],
            "candidate_email" : cv_data["email"],
            "signal_final"    : signal_final,
            "job_title"       : job_title,
            "strengths"       : [],
            "weaknesses"      : [],
            "flags"           : [],
            "justification"   : {
                "score_final"     : score_final,
                "score_matching"  : score_matching,
                "score_motivation": score_motivation,
                "rule_applied"    : "initial_phase",
                "thresholds"      : {"presélection": 70, "en_attente": 40},
            },
            "report": {
                "decision"    : initial_decision,
                "priority"    : priority,
                "next_step"   : next_step,
                "summary"     : f"Décision initiale basée sur score global {score_final:.0f}/100",
                "candidate"   : {
                    "name" : cv_data["full_name"],
                    "email": cv_data["email"],
                },
                "scores": {
                    "score_final"     : round(score_final, 2),
                    "score_matching"  : round(score_matching, 2),
                    "score_motivation": round(score_motivation, 2),
                    "score_global"    : score_global,
                },
                "generated_at": generated_at,
            },
            "generated_at"    : generated_at,
            "error"           : False,
        }

        # ── Sauvegarder en BDD ────────────────────────────────────────
        if db and application_id:
            try:
                from app.models import Application, IA_Log

                application = db.query(Application).filter(
                    Application.id == application_id
                ).first()
                if application:
                    # ── Mapping décision initiale → status_v2 ────────────
                    _STATUS_V2_MAP = {
                        "PRÉSÉLECTION": "PRESELECTED",
                        "EN_ATTENTE"  : "PENDING",
                        "REJETÉ"      : "REJECTED_AUTO",
                    }
                    application.priority       = priority
                    application.score_final    = score_final
                    application.score_matching = score_matching
                    application.status_v2      = _STATUS_V2_MAP.get(initial_decision, "PENDING")
                    db.commit()
                    logger.info(
                        f"Application {application_id} mise à jour (initial) : "
                        f"status_v2={application.status_v2} priority={priority}"
                    )
                else:
                    logger.warning(
                        f"[run_decision_initial] Application {application_id} "
                        f"introuvable — status non sauvegardé"
                    )

                log = IA_Log(
                    application_id = application_id,
                    agent_name     = "decision_agent_initial",
                    output_json    = json.dumps(result, ensure_ascii=False, default=str),
                )
                db.add(log)
                db.commit()
                logger.info(
                    f"IA_Log decision_agent_initial sauvegardé — app: {application_id}"
                )

            except Exception as db_err:
                logger.error(
                    f"[run_decision_initial] Erreur BDD app={application_id} : {db_err}",
                    exc_info=True,
                )

        logger.info(
            f"Décision initiale — {initial_decision} [{priority}] | "
            f"score_final={score_final:.1f} matching={score_matching:.1f} "
            f"motivation={score_motivation:.1f} | candidat={cv_data['full_name']}"
        )
        return result

    except Exception as e:
        logger.error(f"[run_decision_initial] Erreur : {e}", exc_info=True)
        return {"error": True, "error_reason": str(e)}


def run_decision_final(
    application_id  : int,
    score_final     : float,
    score_matching  : float,
    score_motivation: float,
    technical_score : float,
    signal_final    : str,
    cv_profile      : dict,
    job_title       : str,
    job_skills      : str,
    candidate_email : str,
    db              = None,
) -> dict:
    """
    Gate technique après Phase 4 (test technique).

    ══════════════════════════════════════════════════════════
    LOGIQUE v3.0 — Gate bloquant UNIQUEMENT sur score technique
    ══════════════════════════════════════════════════════════

    Le score décisionnel fusionné (matching + technique) N'EST PAS
    calculé ici. Il sera calculé APRÈS le meet technique manager,
    lors de l'appel à /manager-decision → run_manager_decision().

    Règles :
      technical_score < 50   → REJETÉ direct (gate bloquant)
                               status_v2 = REJECTED_TECH
                               rh_decision = "REJETÉ"

      technical_score 50–69  → Convocation meet technique
                               status_v2 = MEET_PENDING
                               priority  = medium
                               rh_decision = "MEET_PENDING"

      technical_score >= 70  → Convocation meet technique (profil fort)
                               status_v2 = MEET_PENDING
                               priority  = strong
                               rh_decision = "MEET_PENDING"

    Retourne un dict contenant rh_decision pour n8n If4.
    """
    try:
        candidate_name  = cv_profile.get("full_name", "Candidat inconnu")
        candidate_email = candidate_email or cv_profile.get("email", "")
        generated_at    = datetime.now(timezone.utc).isoformat()

        tech_status = (
            "strong" if technical_score >= SEUIL_ENTRETIEN else
            "medium" if technical_score >= SEUIL_ATTENTE_MED else
            "weak"
        )

        # ── GATE BLOQUANT — score technique insuffisant ───────────────
        if technical_score < SEUIL_ATTENTE_MED:
            logger.info(
                f"[run_decision_final] REJETÉ — score technique {technical_score:.1f}/100 "
                f"< seuil {SEUIL_ATTENTE_MED} | candidat={candidate_name} | app={application_id}"
            )

            result = {
                "decision"        : "REJETÉ",
                "rh_decision"     : "REJETÉ",
                "priority"        : "low",
                "status_v2"       : "REJECTED_TECH",
                "technical_score" : round(technical_score, 2),
                "tech_status"     : "weak",
                "score_matching"  : round(score_matching, 2),
                "score_motivation": round(score_motivation, 2),
                "score_global"    : None,   # pas calculé — gate bloquant
                "candidate_name"  : candidate_name,
                "candidate_email" : candidate_email,
                "summary"         : (
                    f"{candidate_name} — Rejeté après test technique. "
                    f"Score technique insuffisant : {technical_score:.1f}/100 "
                    f"(seuil requis : {SEUIL_ATTENTE_MED}/100)."
                ),
                "flags"           : ["low_technical", "rejected_by_tech_gate"],
                "strengths"       : [],
                "weaknesses"      : [
                    f"Score technique insuffisant ({technical_score:.0f}/100 "
                    f"— seuil requis : {SEUIL_ATTENTE_MED})"
                ],
                "justification"   : {
                    "decision_rule"  : (
                        f"technical_score={technical_score:.1f} < {SEUIL_ATTENTE_MED} "
                        f"→ REJETÉ (gate bloquant — indépendant du CV matching)"
                    ),
                    "gate_version"   : "v3.0",
                    "score_global"   : "non calculé — gate technique bloquant",
                },
                "report"          : {
                    "decision"    : "REJETÉ",
                    "priority"    : "low",
                    "next_step"   : "Envoyer email de refus au candidat",
                    "generated_at": generated_at,
                },
                "generated_at"    : generated_at,
                "error"           : False,
            }

            # ── Sauvegarder en BDD ────────────────────────────────────
            if db and application_id:
                try:
                    from app.models import Application, IA_Log
                    application = db.query(Application).filter(
                        Application.id == application_id
                    ).first()
                    if application:
                        application.status_v2 = "REJECTED_TECH"
                        application.priority  = "low"
                        db.commit()
                        logger.info(
                            f"Application {application_id} mise à jour : "
                            f"status_v2=REJECTED_TECH priority=low"
                        )
                    log = IA_Log(
                        application_id = application_id,
                        agent_name     = "decision_agent_final",
                        output_json    = __import__("json").dumps(
                            result, ensure_ascii=False, default=str
                        ),
                    )
                    db.add(log)
                    db.commit()
                    logger.info(
                        f"IA_Log sauvegardé — agent: decision_agent_final (REJECTED_TECH), "
                        f"app: {application_id}"
                    )
                except Exception as db_err:
                    logger.error(
                        f"[run_decision_final] Erreur BDD app={application_id} : {db_err}",
                        exc_info=True,
                    )

            return result

        # ── CAS 2 : WAITING_MEET — score moyen (50-69) ──────────────────
        if technical_score < SEUIL_ENTRETIEN:
            logger.info(
                f"[run_decision_final] WAITING_MEET — score technique {technical_score:.1f}/100 "
                f"(50-69) | candidat={candidate_name} | app={application_id}"
            )

            result = {
                "decision"        : "WAITING_MEET",
                "rh_decision"     : "WAITING_MEET",
                "priority"        : "medium",
                "status_v2"       : "WAITING_MEET",
                "technical_score" : round(technical_score, 2),
                "tech_status"     : "medium",
                "score_matching"  : round(score_matching, 2),
                "score_motivation": round(score_motivation, 2),
                "score_global"    : None,
                "candidate_name"  : candidate_name,
                "candidate_email" : candidate_email,
                "summary"         : (
                    f"{candidate_name} — Score technique moyen "
                    f"({technical_score:.1f}/100). "
                    f"Dossier en attente d'examen."
                ),
                "flags"           : ["medium_technical"],
                "strengths"       : [f"Score technique acceptable ({technical_score:.0f}/100)"],
                "weaknesses"      : [
                    f"Score technique en dessous du seuil fort "
                    f"({technical_score:.0f}/100 — seuil fort : {SEUIL_ENTRETIEN})"
                ],
                "justification"   : {
                    "decision_rule" : (
                        f"technical_score={technical_score:.1f} entre "
                        f"{SEUIL_ATTENTE_MED} et {SEUIL_ENTRETIEN} → WAITING_MEET"
                    ),
                    "gate_version"  : "v3.0",
                    "score_global"  : "non calculé — en attente décision manager",
                    "next_stage"    : "rh_review",
                },
                "report"          : {
                    "decision"    : "WAITING_MEET",
                    "priority"    : "medium",
                    "next_step"   : "Dossier transmis pour examen",
                    "generated_at": generated_at,
                },
                "generated_at"    : generated_at,
                "error"           : False,
            }

            if db and application_id:
                try:
                    from app.models import Application, IA_Log
                    application = db.query(Application).filter(
                        Application.id == application_id
                    ).first()
                    if application:
                        application.status_v2 = "WAITING_MEET"
                        application.priority  = "medium"
                        db.commit()
                        logger.info(
                            f"Application {application_id} mise à jour : "
                            f"status_v2=WAITING_MEET priority=medium"
                        )
                    log = IA_Log(
                        application_id = application_id,
                        agent_name     = "decision_agent_final",
                        output_json    = __import__("json").dumps(
                            result, ensure_ascii=False, default=str
                        ),
                    )
                    db.add(log)
                    db.commit()
                    logger.info(
                        f"IA_Log sauvegardé — agent: decision_agent_final (WAITING_MEET), "
                        f"app: {application_id}"
                    )
                except Exception as db_err:
                    logger.error(
                        f"[run_decision_final] Erreur BDD app={application_id} : {db_err}",
                        exc_info=True,
                    )

            return result

        # ── CAS 3 : MEET_PENDING — score fort (>= 70) ────────────────────
        logger.info(
            f"[run_decision_final] MEET_PENDING — score technique {technical_score:.1f}/100 "
            f"(>=70) | candidat={candidate_name} | app={application_id}"
        )

        result = {
            "decision"        : "MEET_PENDING",
            "rh_decision"     : "MEET_PENDING",
            "priority"        : "strong",
            "status_v2"       : "MEET_PENDING",
            "technical_score" : round(technical_score, 2),
            "tech_status"     : "strong",
            "score_matching"  : round(score_matching, 2),
            "score_motivation": round(score_motivation, 2),
            "score_global"    : None,
            "candidate_name"  : candidate_name,
            "candidate_email" : candidate_email,
            "summary"         : (
                f"{candidate_name} — Excellent score technique "
                f"({technical_score:.1f}/100). "
                f"Convocation entretien technique en cours."
            ),
            "flags"           : [],
            "strengths"       : [f"Score technique fort ({technical_score:.0f}/100)"],
            "weaknesses"      : [],
            "justification"   : {
                "decision_rule" : (
                    f"technical_score={technical_score:.1f} >= {SEUIL_ENTRETIEN} "
                    f"→ MEET_PENDING (convocation entretien)"
                ),
                "gate_version"  : "v3.0",
                "score_global"  : "non calculé — sera calculé après décision manager",
                "next_stage"    : "meet_technique_manager",
            },
            "report"          : {
                "decision"    : "MEET_PENDING",
                "priority"    : "strong",
                "next_step"   : "Envoyer invitation entretien technique au candidat",
                "generated_at": generated_at,
            },
            "generated_at"    : generated_at,
            "error"           : False,
        }

        # ── Sauvegarder en BDD ────────────────────────────────────────
        if db and application_id:
            try:
                from app.models import Application, IA_Log
                application = db.query(Application).filter(
                    Application.id == application_id
                ).first()
                if application:
                    application.status_v2 = "MEET_PENDING"
                    application.priority  = "strong"
                    db.commit()
                    logger.info(
                        f"Application {application_id} mise à jour : "
                        f"status_v2=MEET_PENDING priority=strong"
                    )
                log = IA_Log(
                    application_id = application_id,
                    agent_name     = "decision_agent_final",
                    output_json    = __import__("json").dumps(
                        result, ensure_ascii=False, default=str
                    ),
                )
                db.add(log)
                db.commit()
                logger.info(
                    f"IA_Log sauvegardé — agent: decision_agent_final (MEET_PENDING), "
                    f"app: {application_id}"
                )
            except Exception as db_err:
                logger.error(
                    f"[run_decision_final] Erreur BDD app={application_id} : {db_err}",
                    exc_info=True,
                )

        return result

    except Exception as e:
        logger.error(f"[run_decision_final] Erreur : {e}", exc_info=True)
        return {"error": True, "error_reason": str(e)}


# ─────────────────────────────────────────────────────────────────
# MAIN — Test standalone
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import logging as _logging
    _logging.basicConfig(
        level=_logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

    print("=" * 65)
    print("decision_agent.py — Test standalone (Agent 5)")
    print("=" * 65)

    # ── Données simulées (sorties des 4 agents) ───────────────────
    fake_cv = {
        "full_name"        : "Anis Boubaker",
        "email"            : "anis.boubaker@email.com",
        "phone"            : "+216 55 123 456",
        "cv_quality_score" : 82.0,
        "years_experience" : 4,
        "skills_all"       : ["Python", "FastAPI", "SQL", "Docker", "Git", "Linux"],
        "education"        : [{"degree": "Licence Informatique", "institution": "ESPRIT"}],
    }

    fake_motivation = {
        "score_motivation"  : 74,
        "signal_motivation" : "strong",
        "pertinence_poste"  : "élevée",
        "lettre_generique"  : False,
        "points_forts"      : ["Expérience Python backend", "Connaissance API REST"],
        "langue"            : "fr",
        "nb_mots"           : 320,
        "detail_criteres"   : {
            "coherence_poste": 80, "competences": 75,
            "experience": 70, "personnalisation": 65, "qualite": 72,
        },
    }

    fake_matching = {
        "score_matching"    : 78,
        "score_final"       : 75,
        "signal_final"      : "strong",
        "decision"          : "PRÉSÉLECTION",
        "skills_matched"    : ["Python", "FastAPI", "SQL", "Docker"],
        "skills_missing"    : ["Kubernetes", "Redis"],
        "confidence"        : {"level": "high", "score": 85},
        "score_is_indicative": False,
        "error"             : False,
    }

    fake_test = {
        "test_id"        : "python-backend-2025-01-15-abc12345",
        "technical_score": 72.5,
        "status"         : "strong",
        "flags"          : [],
        "total_points"   : 26,
        "earned_points"  : 19,
        "error"          : False,
    }

    # ── Exécuter l'agent ──────────────────────────────────────────
    fake_manager = {
        "manager_decision" : "VALIDÉ",
        "manager_note"     : "Bon profil, communication claire, maîtrise bien Python et FastAPI.",
        "priority_group"   : 1,
        "rejected"         : False,
        "pass_to_agent5"   : True,
    }

    result = run_decision_agent(
        cv_data           = fake_cv,
        motivation_result = fake_motivation,
        matching_result   = fake_matching,
        test_result       = fake_test,
        manager_result    = fake_manager,
        application_id    = 0,
        db                = None,
    )

    # ── Affichage ─────────────────────────────────────────────────
    print(f"{'─'*65}")
    print(f"  DÉCISION FINALE   : {result['decision']}")
    print(f"  PRIORITÉ          : {result['priority'].upper()}")
    print(f"  GROUPE MANAGER    : {result.get('priority_group', 'N/A')}")
    print(f"  DÉCISION MANAGER  : {result.get('manager_decision', 'N/A')}")
    print(f"  CANDIDAT          : {result['candidate_name']}")
    print(f"  EMAIL             : {result['candidate_email']}")
    print(f"{'─'*65}")
    print(f"  Score Technique   : {result['technical_score']}/100")
    print(f"  Score Matching    : {result['score_matching']}/100")
    print(f"  Score Motivation  : {result['score_motivation']}/100")
    print(f"  Score Global      : {result['score_global']}/100")
    print(f"  Score Décisionnel : {result.get('score_global_decisional', 'N/A')}/100")
    print(f"{'─'*65}")
    print(f"  RÉSUMÉ : {result['summary']}")
    print(f"{'─'*65}")

    if result["strengths"]:
        print("\n  ✅ POINTS FORTS :")
        for s in result["strengths"]:
            print(f"     • {s}")

    if result["weaknesses"]:
        print("\n  ⚠️  POINTS FAIBLES :")
        for w in result["weaknesses"]:
            print(f"     • {w}")

    if result["flags"]:
        print(f"\n  🏴 FLAGS : {result['flags']}")

    print(f"\n  PROCHAINE ÉTAPE : {result['report'].get('next_step', 'N/A')}")
    print(f"\n  ERROR : {result['error']}")
    print("=" * 65)

    # JSON complet (optionnel)
    print("\n[JSON complet — rapport RH]")
    print(json.dumps(result["report"], indent=2, ensure_ascii=False))