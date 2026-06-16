"""
routers/decision.py — Endpoints FastAPI Agent Décision (v2.0)

Endpoints :
  POST /applications/{id}/decide-initial      → après matching (Phase 1)
  POST /applications/{id}/decide-final        → après test technique (Phase 4)
  POST /applications/{id}/manager-decision    → décision manager après meet (v2.0)
  GET  /applications/{id}/rh-report           → rapport RH complet depuis IA_Log
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
import json

from app.database import get_db
from app.models import Application, CVProfile, Job, IA_Log
from app.agents.decision_agent.decision_agent import (
    run_decision_initial,
    run_decision_final,
)
from app.agents.test_agent.test_agent import (
    run_manager_decision,
    get_manager_decision,
)

router = APIRouter(prefix="/applications", tags=["Decision Agent"])


# ─────────────────────────────────────────────────────────────────
# SCHEMAS LOCAUX
# ─────────────────────────────────────────────────────────────────

class DecisionInitialInput(BaseModel):
    """
    Payload POST /applications/{id}/decide-initial
    Reçoit les scores du matching_agent + motivation_agent
    """
    score_final     : float
    score_matching  : float
    score_motivation: float
    signal_final    : str = "medium"


class DecisionFinalInput(BaseModel):
    """
    Payload POST /applications/{id}/decide-final
    Reçoit les scores matching + résultat test technique
    """
    score_final     : float
    score_matching  : float
    score_motivation: float
    technical_score : float
    signal_final    : str = "medium"


class ManagerDecisionInput(BaseModel):
    """
    Payload POST /applications/{id}/manager-decision
    Reçoit la décision du manager après le meet technique (v2.0)
    """
    test_id          : str
    manager_decision : str            # "VALIDÉ" / "NON_RETENU"
    manager_note     : Optional[str] = ""
    manager_id       : Optional[int] = 0


# ─────────────────────────────────────────────────────────────────
# POST /applications/{id}/decide-initial
# ─────────────────────────────────────────────────────────────────

@router.post("/{application_id}/decide-initial")
async def decide_initial(
    application_id: int,
    body: DecisionInitialInput,
    db: Session = Depends(get_db),
):
    """
    Décision après les 3 agents d'analyse (CV + Motivation + Matching).

    Règle des 3 cas :
      score_final ≥ 70 → PRÉSÉLECTION (déclenche test technique)
      score_final 40-69 → EN_ATTENTE  (dashboard RH)
      score_final < 40  → REJETÉ      (email refus)
    """
    # Vérifier que la candidature existe
    application = db.query(Application).filter(
        Application.id == application_id
    ).first()
    if not application:
        raise HTTPException(
            status_code=404,
            detail=f"Candidature {application_id} introuvable"
        )

    # Récupérer le profil CV depuis la DB
    cv_profile_db = db.query(CVProfile).filter(
        CVProfile.application_id == application_id
    ).first()
    cv_profile = {}
    if cv_profile_db:
        cv_profile = {
            "full_name"              : cv_profile_db.full_name,
            "email"                  : cv_profile_db.email,
            "skills"                 : cv_profile_db.skills or [],
            "education"              : cv_profile_db.education or [],
            "professional_experience": cv_profile_db.professional_experience or [],
            "years_experience"       : cv_profile_db.years_experience,
        }

    # Récupérer les infos du poste
    job = db.query(Job).filter(Job.id == application.job_id).first()
    job_title  = job.title if job else ""
    job_skills = job.skills_required if job else ""

    # Appel agent décision
    result = await run_in_threadpool(
        run_decision_initial,
        application_id   = application_id,
        score_final      = body.score_final,
        score_matching   = body.score_matching,
        score_motivation = body.score_motivation,
        signal_final     = body.signal_final,
        cv_profile       = cv_profile,
        job_title        = job_title,
        job_skills       = job_skills,
        candidate_email  = application.candidate_email,
        db               = db,
    )

    if result.get("error"):
        raise HTTPException(
            status_code=500,
            detail={
                "error"  : "decision_failed",
                "message": result.get("error_reason", "Erreur Agent Décision"),
            }
        )

    return {
        "message"       : "Décision initiale appliquée",
        "application_id": application_id,
        **result,
    }


# ─────────────────────────────────────────────────────────────────
# POST /applications/{id}/decide-final
# ─────────────────────────────────────────────────────────────────

@router.post("/{application_id}/decide-final")
async def decide_final(
    application_id: int,
    body: DecisionFinalInput,
    db: Session = Depends(get_db),
):
    """
    Décision finale après test technique.

    Règle :
      technical_score ≥ 70 → ENTRETIEN   (high priority)
      technical_score 50-69 → EN_ATTENTE  (medium priority)
      technical_score < 50  → EN_ATTENTE  (low priority)

    Génère aussi les questions d'entretien si décision = ENTRETIEN.
    """
    application = db.query(Application).filter(
        Application.id == application_id
    ).first()
    if not application:
        raise HTTPException(
            status_code=404,
            detail=f"Candidature {application_id} introuvable"
        )

    # Profil CV
    cv_profile_db = db.query(CVProfile).filter(
        CVProfile.application_id == application_id
    ).first()
    cv_profile = {}
    if cv_profile_db:
        cv_profile = {
            "full_name"              : cv_profile_db.full_name,
            "email"                  : cv_profile_db.email,
            "skills"                 : cv_profile_db.skills or [],
            "education"              : cv_profile_db.education or [],
            "professional_experience": cv_profile_db.professional_experience or [],
            "years_experience"       : cv_profile_db.years_experience,
            "projects"               : cv_profile_db.projects or [],
        }

    # Infos poste
    job = db.query(Job).filter(Job.id == application.job_id).first()
    job_title  = job.title if job else ""
    job_skills = job.skills_required if job else ""

    # Appel agent décision finale
    result = await run_in_threadpool(
        run_decision_final,
        application_id   = application_id,
        score_final      = body.score_final,
        score_matching   = body.score_matching,
        score_motivation = body.score_motivation,
        technical_score  = body.technical_score,
        signal_final     = body.signal_final,
        cv_profile       = cv_profile,
        job_title        = job_title,
        job_skills       = job_skills,
        candidate_email  = application.candidate_email,
        db               = db,
    )

    if result.get("error"):
        raise HTTPException(
            status_code=500,
            detail={
                "error"  : "decision_failed",
                "message": result.get("error_reason", "Erreur Agent Décision"),
            }
        )

    # ── Garantir rh_decision explicite pour n8n If4 ──────────────────
    # If4 vérifie : rh_decision == "REJETÉ"       → True  → email rejet
    #               rh_decision == "MEET_PENDING"  → False → convocation meet
    rh_decision = result.get("rh_decision") or result.get("decision", "MEET_PENDING")

    return {
        "message"        : "Gate technique appliqué",
        "application_id" : application_id,
        "rh_decision"    : rh_decision,
        "status_v2"      : result.get("status_v2", "MEET_PENDING"),
        "technical_score": result.get("technical_score"),
        "tech_status"    : result.get("tech_status"),
        "priority"       : result.get("priority"),
        "candidate_name" : result.get("candidate_name"),
        "candidate_email": result.get("candidate_email"),
        "summary"        : result.get("summary"),
        "flags"          : result.get("flags", []),
        "score_matching" : result.get("score_matching"),
        "justification"  : result.get("justification"),
        "report"         : result.get("report"),
        "generated_at"   : result.get("generated_at"),
        "error"          : False,
    }


# ─────────────────────────────────────────────────────────────────
# POST /applications/{id}/manager-decision   (v2.0)
# ─────────────────────────────────────────────────────────────────

@router.post("/{application_id}/manager-decision")
async def manager_decision(
    application_id: int,
    body: ManagerDecisionInput,
    db: Session = Depends(get_db),
):
    """
    Enregistre la décision du manager après le meet technique.

    Règles :
      NON_RETENU → candidat rejeté définitivement (pass_to_agent5=False)
      VALIDÉ     → passe à l'Agent 5, priority_group=1
    """
    # Vérifier que la candidature existe
    application = db.query(Application).filter(
        Application.id == application_id
    ).first()
    if not application:
        raise HTTPException(
            status_code=404,
            detail=f"Candidature {application_id} introuvable"
        )

    # Appel test_agent.run_manager_decision()
    result = await run_in_threadpool(
        run_manager_decision,
        test_id          = body.test_id,
        application_id   = application_id,
        manager_decision = body.manager_decision,
        manager_note     = body.manager_note or "",
        manager_id       = body.manager_id or 0,
        db               = db,
    )

    if result.get("error"):
        raise HTTPException(
            status_code=400,
            detail={
                "error"  : result.get("error_type", "manager_decision_failed"),
                "message": result.get("error_reason", "Erreur décision manager"),
            }
        )

    # Si NON_RETENU → mettre à jour le statut en DB directement
    if result.get("rejected"):
        try:
            application.priority  = "low"
            application.status_v2 = "MANAGER_REJECTED"
            db.commit()
        except Exception as db_err:
            raise HTTPException(
                status_code=500,
                detail=f"Erreur mise à jour DB après NON_RETENU : {db_err}"
            )
        return {
            "message"        : "Candidat rejeté après entretien technique manager",
            "application_id" : application_id,
            "decision"       : "REJETÉ",
            "rejected"       : True,
            "pass_to_agent5" : False,
            "manager_decision": body.manager_decision,
            "manager_note"   : body.manager_note,
        }

    # VALIDÉ → mettre à jour status_v2
    try:
        application.status_v2 = "ACCEPTED"
        db.commit()
    except Exception as db_err:
        raise HTTPException(
            status_code=500,
            detail=f"Erreur mise à jour DB : {db_err}"
        )

    return {
        "message"         : "Décision manager enregistrée",
        "application_id"  : application_id,
        "manager_decision": result["manager_decision"],
        "manager_note"    : result["manager_note"],
        "rejected"        : False,
        "pass_to_agent5"  : True,
        "priority_group"  : 1,
    }


# ─────────────────────────────────────────────────────────────────
# GET /applications/{id}/rh-report
# ─────────────────────────────────────────────────────────────────

@router.get("/{application_id}/rh-report")
def get_rh_report(
    application_id: int,
    db: Session = Depends(get_db),
):
    """
    Retourne le dernier rapport RH depuis IA_Log.
    Utilisé par le dashboard Streamlit pour afficher l'état du candidat.
    """
    application = db.query(Application).filter(
        Application.id == application_id
    ).first()
    if not application:
        raise HTTPException(
            status_code=404,
            detail=f"Candidature {application_id} introuvable"
        )

    # Récupérer le dernier log decision_agent
    log = (
        db.query(IA_Log)
        .filter(
            IA_Log.application_id == application_id,
            IA_Log.agent_name.in_(["decision_agent_final", "decision_agent_initial"])
        )
        .order_by(IA_Log.created_at.desc())
        .first()
    )

    if not log:
        # Pas encore de décision — retourner l'état actuel DB
        return {
            "application_id": application_id,
            "status"        : application.status_v2,   # ← migré vers status_v2
            "score_final"   : application.score_final,
            "score_matching": application.score_matching,
            "decision"      : application.status_v2,    # ← migré vers status_v2
            "message"       : "Aucun rapport généré — décision agent non encore exécutée",
        }

    report = json.loads(log.output_json)
    return report