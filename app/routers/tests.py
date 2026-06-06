"""
tests.py — Router FastAPI pour la gestion des tests techniques.

Flow n8n :
  PARTIE 1 — GÉNÉRATION
    n8n webhook "generer-test"
      → POST /tests/generate          (génère le test, retourne questions au Manager)
      → POST /tests/regenerate        (si Manager veut régénérer)

  PARTIE 2 — VALIDATION + ENVOI PLANIFIÉ
    n8n webhook "valider-test"
      → POST /tests/{test_id}/validate
            payload : { job_id, send_date }
            retour  : { test_id, send_date, send_date_fr, job_title, candidates: [...] }
      → n8n envoie Email 1 immédiatement à chaque candidat ("test prévu le [DATE]")
      → n8n Wait jusqu'à send_date
      → POST /tests/{test_id}/send
            payload : { job_id }
            retour  : { candidates: [{email, name, test_link, expires_at}] }
      → n8n envoie Email 2 à chaque candidat (lien unique 24h)

  CANDIDAT
      → GET  /tests/{test_id}                        → charge les questions (TestPage)
      → POST /applications/{id}/open-test            → dans applications.py ✅
      → POST /applications/{id}/evaluate-test        → dans applications.py ✅
"""

import os
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app import models
from app.database import get_db
from app.routers.auth import require_role
from app.agents.test_agent.test_agent import run_generate_test

router = APIRouter(prefix="/tests", tags=["Tests"])

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")


# ─────────────────────────────────────────────────────────────────────────────
# SCHEMAS
# ─────────────────────────────────────────────────────────────────────────────

class GenerateTestInput(BaseModel):
    """
    Payload envoyé par n8n au webhook "generer-test" → relay vers POST /tests/generate.
    Le Manager saisit ces infos dans le dashboard avant de cliquer "Générer test".
    """
    job_id    : int
    role      : str
    seniority : str          # junior / mid / senior
    skills    : dict         # {"coding": [...], "platform": [...], "mixed": [...]}


class ValidateTestInput(BaseModel):
    """
    Payload envoyé par n8n au webhook "valider-test" → relay vers POST /tests/{test_id}/validate.
    Le Manager a validé les questions et choisi une date d'envoi.

    send_date : ISO 8601 — date/heure à laquelle les candidats reçoivent le lien test.
                Ex : "2025-06-15T09:00:00"
                n8n attend jusqu'à cette date via Wait node, puis appelle /send.
    """
    job_id    : int
    send_date : str          # ISO 8601 — ex: "2025-06-15T09:00:00"


class SendTestInput(BaseModel):
    """
    Payload pour POST /tests/{test_id}/send.
    Appelé par n8n automatiquement à la date planifiée (après le Wait node).
    """
    job_id : int


# ─────────────────────────────────────────────────────────────────────────────
# PARTIE 1A — POST /tests/generate
# Appelé par n8n (webhook "generer-test") après clic Manager "Générer test"
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/generate")
def generate_test(
    payload      : GenerateTestInput,
    db           : Session     = Depends(get_db),
    current_user : models.User = Depends(require_role("MANAGER", "RH")),
):
    """
    n8n appelle cet endpoint avec les infos du job.

    L'agent génère le test et le stocke en DB (cache par job_id — équité entre candidats).
    Retourne les questions à n8n → n8n les renvoie au Manager pour review.

    Si un test existe déjà pour ce job_id, le cache est retourné (pas de regénération).
    Pour forcer une nouvelle génération → POST /tests/regenerate.
    """
    # ── 1. Vérifier le job ────────────────────────────────────────────────────
    job = db.query(models.Job).filter(models.Job.id == payload.job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job non trouvé")
    if job.closed_at:
        raise HTTPException(
            status_code=400,
            detail="Ce job est fermé — impossible de générer un test",
        )

    # ── 2. Appel agent test (LLM Groq — peut prendre 30-90s) ─────────────────
    result = run_generate_test(
        role            = payload.role,
        seniority       = payload.seniority.lower(),
        coding_skills   = payload.skills.get("coding",   []),
        platform_skills = payload.skills.get("platform", []),
        mixed_skills    = payload.skills.get("mixed",    []),
        job_id          = payload.job_id,
        job_title       = job.title,
        db              = db,
        force_regenerate= False,
    )

    # ── 3. Vérifier le résultat ───────────────────────────────────────────────
    if result.get("error"):
        raise HTTPException(
            status_code=500,
            detail=result.get("error_reason", "Erreur inconnue lors de la génération"),
        )

    # ── 4. Retourner les questions au Manager (via n8n) ───────────────────────
    return {
        "test_id"           : result["test_id"],
        "questions"         : result["questions"],
        "duration"          : result.get("duration", 60),
        "test_type"         : result.get("test_type", "tech"),
        "question_structure": result.get("question_structure", {}),
        "role"              : payload.role,
        "seniority"         : payload.seniority,
        "job_id"            : payload.job_id,
        "reused"            : result.get("reused", False),
        "created_at"        : datetime.utcnow().isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# PARTIE 1B — POST /tests/regenerate
# Manager clique "Régénérer" après avoir vu les questions
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/regenerate")
def regenerate_test(
    payload      : GenerateTestInput,
    db           : Session     = Depends(get_db),
    current_user : models.User = Depends(require_role("MANAGER", "RH")),
):
    """
    Force une nouvelle génération — ignore le cache du job.
    Appelé par n8n si Manager clique "Régénérer" après review des questions.
    """
    job = db.query(models.Job).filter(models.Job.id == payload.job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job non trouvé")
    if job.closed_at:
        raise HTTPException(status_code=400, detail="Ce job est fermé")

    result = run_generate_test(
        role            = payload.role,
        seniority       = payload.seniority.lower(),
        coding_skills   = payload.skills.get("coding",   []),
        platform_skills = payload.skills.get("platform", []),
        mixed_skills    = payload.skills.get("mixed",    []),
        job_id          = payload.job_id,
        job_title       = job.title,
        db              = db,
        force_regenerate= True,
    )

    if result.get("error"):
        raise HTTPException(
            status_code=500,
            detail=result.get("error_reason", "Erreur lors de la régénération"),
        )

    return {
        "test_id"           : result["test_id"],
        "questions"         : result["questions"],
        "duration"          : result.get("duration", 60),
        "test_type"         : result.get("test_type", "tech"),
        "question_structure": result.get("question_structure", {}),
        "role"              : payload.role,
        "seniority"         : payload.seniority,
        "job_id"            : payload.job_id,
        "reused"            : False,
        "created_at"        : datetime.utcnow().isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# PARTIE 2A — POST /tests/{test_id}/validate
# Manager valide les questions + choisit la date d'envoi
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/{test_id}/validate")
def validate_test(
    test_id      : str,
    payload      : ValidateTestInput,
    db           : Session     = Depends(get_db),
    current_user : models.User = Depends(require_role("MANAGER", "RH")),
):
    """
    Manager valide les questions et choisit la date d'envoi du test.

    Actions en DB :
      - job.test_validated    = True
      - job.test_id_validated = test_id
      - candidats PRESELECTED → TEST_READY (avec log ApplicationEvent)

    Ce que n8n fait avec la réponse :
      1. Envoie Email 1 immédiatement à chaque candidat
      2. Lance un Wait node jusqu'à send_date
      3. A la date → appelle POST /tests/{test_id}/send
    """
    # ── 1. Vérifier test + job ────────────────────────────────────────────────
    test = db.query(models.Test).filter(models.Test.test_id == test_id).first()
    if not test:
        raise HTTPException(status_code=404, detail="Test non trouvé")

    job = db.query(models.Job).filter(models.Job.id == payload.job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job non trouvé")

    # ── 2. Valider send_date ──────────────────────────────────────────────────
    try:
        send_date_dt = datetime.fromisoformat(payload.send_date)
    except ValueError:
        try:
            send_date_dt = datetime.strptime(payload.send_date, "%d/%m/%Y %H:%M")
        except ValueError:
            raise HTTPException(
                status_code=422, 
                detail="send_date invalide — formats acceptés : ISO 8601 ou DD/MM/YYYY HH:MM"
            )

    if send_date_dt <= datetime.utcnow():
        raise HTTPException(
            status_code=422,
            detail="send_date doit être dans le futur",
        )

    # ── 3. Marquer le job comme validé ───────────────────────────────────────
    job.test_validated    = True
    job.test_id_validated = test_id

    # ── 4. Passer PRESELECTED → TEST_READY ───────────────────────────────────
    preselected = db.query(models.Application).filter(
        models.Application.job_id    == payload.job_id,
        models.Application.status_v2 == "PRESELECTED",
    ).all()

    if not preselected:
        raise HTTPException(
            status_code=400,
            detail=(
                "Aucun candidat en statut PRESELECTED pour ce job. "
                "Le pipeline de matching doit être terminé avant de valider le test."
            ),
        )

    candidates_for_email1 = []
    for app in preselected:
        prev          = app.status_v2
        app.status_v2 = "TEST_READY"

        db.add(models.ApplicationEvent(
            application_id  = app.id,
            event           = "TEST_VALIDATED",
            actor           = "manager",
            actor_id        = current_user.id,
            previous_status = prev,
            new_status      = "TEST_READY",
            details         = {
                "test_id"  : test_id,
                "send_date": send_date_dt.isoformat(), 
            },
        ))

        cv_profile = db.query(models.CVProfile).filter(
            models.CVProfile.application_id == app.id
        ).first()
        candidate_name = cv_profile.full_name if cv_profile else "Candidat"

        candidates_for_email1.append({
            "application_id"  : app.id,
            "candidate_email" : app.candidate_email,
            "candidate_name"  : candidate_name,
        })

    db.commit()

    # ── 5. Formater la date en français pour Email 1 ──────────────────────────
    send_date_fr = send_date_dt.strftime("%d/%m/%Y à %H:%M")

    # ── 6. Retourner à n8n ────────────────────────────────────────────────────
    return {
        "send_date"       : payload.send_date,    # ISO 8601 — Wait node n8n
        "send_date_fr"    : send_date_fr,         # "15/06/2025 à 09:00" — Email 1
        "test_id"         : test_id,
        "job_id"          : payload.job_id,
        "job_title"       : job.title,
        "candidates"      : candidates_for_email1,
        "candidates_count": len(candidates_for_email1),
    }


# ─────────────────────────────────────────────────────────────────────────────
# PARTIE 2B — POST /tests/{test_id}/send
# Appelé par n8n à la date planifiée (après le Wait node)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/{test_id}/send")
def send_test(
    test_id      : str,
    payload      : SendTestInput,
    db           : Session     = Depends(get_db),
    current_user : models.User = Depends(require_role("MANAGER", "RH")),
):
    """
    Appelé automatiquement par n8n à la date planifiée (après le Wait node).

    Actions en DB :
      - candidats TEST_READY → TEST_SENT
      - test_sent_at    = maintenant
      - test_expires_at = maintenant + 24h

    Retourne à n8n la liste des candidats avec leur lien unique.
    n8n itère sur cette liste et envoie Email 2 à chacun.
    Le backend NE envoie PAS les emails — c'est le rôle de n8n.
    """
    # ── 1. Vérifier test + job ────────────────────────────────────────────────
    test = db.query(models.Test).filter(models.Test.test_id == test_id).first()
    if not test:
        raise HTTPException(status_code=404, detail="Test non trouvé")

    job = db.query(models.Job).filter(models.Job.id == payload.job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job non trouvé")

    if not job.test_validated:
        raise HTTPException(
            status_code=400,
            detail="Le test n'a pas été validé — appelez POST /tests/{test_id}/validate d'abord",
        )

    # ── 2. Récupérer les candidats TEST_READY ────────────────────────────────
    candidates = db.query(models.Application).filter(
        models.Application.job_id    == payload.job_id,
        models.Application.status_v2 == "TEST_READY",
    ).all()

    if not candidates:
        raise HTTPException(
            status_code=400,
            detail="Aucun candidat en statut TEST_READY — déjà envoyé ou aucun candidat validé.",
        )

    # ── 3. Générer les liens et passer TEST_READY → TEST_SENT ────────────────
    now     = datetime.utcnow()
    expires = now + timedelta(hours=24)

    candidates_for_email2 = []
    for app in candidates:
        test_link = (
            f"{FRONTEND_URL}/test"
            f"?application_id={app.id}"
            f"&test_id={test_id}"
        )

        cv_profile = db.query(models.CVProfile).filter(
            models.CVProfile.application_id == app.id
        ).first()
        candidate_name = cv_profile.full_name if cv_profile else "Candidat"

        prev                = app.status_v2
        app.status_v2       = "TEST_SENT"
        app.test_sent_at    = now
        app.test_expires_at = expires

        db.add(models.ApplicationEvent(
            application_id  = app.id,
            event           = "TEST_SENT",
            actor           = "system",
            previous_status = prev,
            new_status      = "TEST_SENT",
            details         = {
                "test_id"   : test_id,
                "expires_at": expires.isoformat(),
            },
        ))

        candidates_for_email2.append({
            "application_id"  : app.id,
            "candidate_email" : app.candidate_email,
            "candidate_name"  : candidate_name,
            "test_link"       : test_link,
            "expires_at"      : expires.isoformat(),
            "expires_at_fr"   : expires.strftime("%d/%m/%Y à %H:%M"),
            "duration_minutes": test.duration,
        })

    db.commit()

    return {
        "test_id"    : test_id,
        "job_title"  : job.title,
        "sent_count" : len(candidates_for_email2),
        "expires_at" : expires.isoformat(),
        "candidates" : candidates_for_email2,
    }


# ─────────────────────────────────────────────────────────────────────────────
# GET /tests/{test_id}
# Endpoint public — TestPage.tsx charge les questions du candidat
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{test_id}")
def get_test(test_id: str, db: Session = Depends(get_db)):
    """
    Charge les questions pour le candidat.

    Transformations appliquées pour TestPage.tsx :
      - "question" → "text"          (TestPage attend le champ "text")
      - "mcq"      → "MCQ"           (TestPage attend les majuscules)
      - "open"     → "Open"          (TestPage attend les majuscules)
      - timeLimit  ajouté            (90s MCQ / 180s Open)

    Les réponses correctes (correct_answer) ne sont jamais exposées.
    La DB reste intacte — transformation à la volée uniquement.
    """
    test = db.query(models.Test).filter(models.Test.test_id == test_id).first()
    if not test:
        raise HTTPException(status_code=404, detail="Test introuvable ou lien expiré")

    questions_safe = []
    for q in (test.questions or []):
        q_type = str(q.get("type", "open")).lower()

        is_mcq = q_type in ("mcq", "multiple_choice", "qcm")

        # ── Champs de base — adaptés à TestPage.tsx ───────────────────────────
        q_safe = {
            "id"        : q.get("id"),
            "type"      : "MCQ" if is_mcq else "Open",     # majuscules pour TestPage
            "text"      : q.get("question") or q.get("text") or q.get("prompt") or "",
            "skill"     : q.get("skill", ""),
            "difficulty": q.get("difficulty", ""),
            "points_max": q.get("points_max", 1),
            "timeLimit" : 90 if is_mcq else 180,            # secondes — timer par question
        }

        # ── MCQ — options (correct_answer masqué) ────────────────────────────
        if is_mcq:
            raw = q.get("options") or q.get("choices") or []
            if raw:
                if isinstance(raw[0], dict):
                    q_safe["options"] = [
                        o.get("text") or o.get("label") or str(o)
                        for o in raw
                    ]
                else:
                    q_safe["options"] = [str(o) for o in raw]

        # ── Open — contexte optionnel ─────────────────────────────────────────
        else:
            if q.get("context"):
                q_safe["context"] = q.get("context")

        questions_safe.append(q_safe)

    return {
        "test_id"   : test.test_id,
        "role"      : test.role,
        "seniority" : test.seniority,
        "duration"  : test.duration,
        "questions" : questions_safe,
        "total"     : len(questions_safe),
        "created_at": test.created_at,
    }