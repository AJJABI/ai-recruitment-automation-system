from fastapi import UploadFile, File, APIRouter, Depends, Form, HTTPException, BackgroundTasks, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from typing import Optional
from sqlalchemy.orm import Session
from app.database import get_db, SessionLocal
from app.models import Application, CVProfile, Job, IA_Log, RH_Feedback, ApplicationEvent,User   
from app.schemas import FeedbackCreate, FeedbackResponse, EvaluateTestInput
from app.agents.cv_agent.cv_parser import run_cv_parser
from app.agents.motivation_agent.motivation_agent import run_motivation_agent
from app.agents.matching_agent.matching_agent import run_matching_agent
from app.agents.test_agent.test_agent import run_generate_test, run_evaluate_test, run_start_test
from app.agents.decision_agent.decision_agent import run_decision_final
from app.routers.auth import get_current_user, require_role, require_role
from app.routers.notifications import create_notification


import shutil
import os
import subprocess
import uuid
import re
import httpx
from app.circuit_breaker import n8n_breaker

router = APIRouter()

os.makedirs("uploads", exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# SCHEMA — GenerateTestInput v3
#
# Remplace l'ancien GenerateTestInput (skills: list[str]) par la nouvelle
# architecture 3 catégories documentée dans le document d'architecture.
#
# Le RH saisit les skills séparés par catégorie :
#   coding_skills   → nécessitent d'écrire du code  (python, sql, c#...)
#   platform_skills → usage d'outils / dashboards    (power bi, sharepoint...)
#   mixed_skills    → code ET outil                  (azure, azure devops...)
#
# Le skill_classifier valide + corrige cette classification via LLM.
# Le test_strategy_engine décide ensuite : tech / platform / mixed.
# ─────────────────────────────────────────────────────────────────────────────

class GenerateTestInput(BaseModel):
    role             : str
    coding_skills    : list[str] = Field(default_factory=list,
                                         description="Skills nécessitant du code (python, sql, c#...)")
    platform_skills  : list[str] = Field(default_factory=list,
                                         description="Tool-oriented skills (power bi, sharepoint...)")
    mixed_skills     : list[str] = Field(default_factory=list,
                                         description="Skills mixtes code+outil (azure, azure devops...)")
    seniority        : str       = "mid"
    force_regenerate : bool      = False
    auto_start       : bool      = False
    job_title        : Optional[str] = None


def _secure_filename(filename: str, max_length: int = 120) -> str:
    """Sanitize filename : alphanum + dot + underscore + dash. Tronque à max_length."""
    if not filename:
        return ""
    name = os.path.basename(filename)
    parts = name.rsplit('.', 1)
    if len(parts) == 2:
        base, ext = parts[0], '.' + parts[1]
    else:
        base, ext = parts[0], ''
    base = re.sub(r'[^A-Za-z0-9._-]+', '_', base)
    base = base.strip('._-')[:max_length]
    ext  = re.sub(r'[^A-Za-z0-9.]', '', ext)
    return base + ext


# ─────────────────────────────────────────────────────────────────────────────
# VALIDATION FORMATS CV
# ─────────────────────────────────────────────────────────────────────────────

ALLOWED_EXTENSIONS = {".pdf", ".docx"}
MAX_FILE_SIZE_MB   = 5

FORMAT_ERRORS = {
    ".png":  "PNG images are not accepted. Please convert your CV to PDF and try again.",
    ".jpg":  "JPG images are not accepted. Please convert your CV to PDF and try again.",
    ".jpeg": "JPEG images are not accepted. Please convert your CV to PDF and try again.",
    ".bmp":  "BMP images are not accepted. Please convert your CV to PDF and try again.",
    ".tiff": "TIFF images are not accepted. Please convert your CV to PDF and try again.",
    ".tif":  "TIF images are not accepted. Please convert your CV to PDF and try again.",
    ".pptx": "PowerPoint files are not accepted. Please export your CV as PDF.",
    ".xlsx": "Excel files are not accepted. Please export your CV as PDF.",
    ".txt":  "Plain text files are not accepted. Please upload a PDF or DOCX.",
    ".odt":  "ODT files are not accepted. Please export your CV as PDF or DOCX.",
}


def validate_cv_upload(cv: UploadFile) -> str:
    """Retourne l'extension ou lève HTTPException 422."""
    filename = cv.filename or ""
    ext      = os.path.splitext(filename)[1].lower()

    if ext in FORMAT_ERRORS:
        raise HTTPException(
            status_code=422,
            detail={
                "error":            "FORMAT_NON_SUPPORTE",
                "message":          FORMAT_ERRORS[ext],
                "format_recu":      ext,
                "formats_acceptes": sorted(ALLOWED_EXTENSIONS),
            }
        )

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail={
                "error":   "FORMAT_NON_SUPPORTE",
                "message": (
                    f"Format '{ext or 'unknown'}' not accepted. "
                    "Veuillez uploader votre CV en PDF ou DOCX uniquement."
                ),
                "format_recu":      ext or "inconnu",
                "formats_acceptes": sorted(ALLOWED_EXTENSIONS),
            }
        )
    return ext


def convert_docx_to_pdf(docx_path: str) -> str:
    """Convertit .docx → .pdf via LibreOffice headless."""
    out_dir  = os.path.dirname(os.path.abspath(docx_path))
    pdf_path = os.path.splitext(docx_path)[0] + ".pdf"

    try:
        result = subprocess.run(
            ["soffice", "--headless", "--convert-to", "pdf", "--outdir", out_dir, docx_path],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr or "Erreur inconnue LibreOffice")
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"Generated PDF not found: {pdf_path}")
        return pdf_path

    except FileNotFoundError as e:
        if "soffice" in str(e):
            raise HTTPException(
                status_code=500,
                detail={
                    "error":   "CONVERSION_DOCX_ECHOUEE",
                    "message": "LibreOffice is not installed. Please upload a PDF directly.",
                }
            )
        raise HTTPException(
            status_code=500,
            detail={"error": "CONVERSION_DOCX_ECHOUEE", "message": str(e)}
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(
            status_code=500,
            detail={
                "error":   "CONVERSION_DOCX_ECHOUEE",
                "message": "DOCX → PDF conversion timed out (30s).",
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"error": "CONVERSION_DOCX_ECHOUEE", "message": str(e)}
        )


# ─────────────────────────────────────────────────────────────────────────────
# POST /apply/{job_id} — Dépôt de candidature
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/apply/{job_id}")
async def apply_job(
    job_id: int,
    candidate_email: str = Form(...),
    cv: UploadFile = File(...),
    lettre: UploadFile = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db)
):
    # ── 0. Job existe ? ───────────────────────────────────────────────────────
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    # ── Vérifier si candidat a déjà postulé à ce job ─────────────────────────
    existing = db.query(Application).filter(
        Application.job_id          == job_id,
        Application.candidate_email == candidate_email,
        Application.is_anonymized   == False
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail={
                "error"         : "ALREADY_APPLIED",
                "message"       : "You have already applied for this position.",
                "application_id": existing.id,
                "status_v2"     : existing.status_v2,
                "applied_at"    : str(existing.created_at),
            }
        )

    # ── 1. Validation format CV ───────────────────────────────────────────────
    cv_ext = validate_cv_upload(cv)

    # ── 2. Sauvegarde fichiers ────────────────────────────────────────────────
    cv_safe     = _secure_filename(cv.filename)     or uuid.uuid4().hex
    letter_safe = _secure_filename(lettre.filename) or uuid.uuid4().hex

    cv_path     = os.path.join("uploads", f"{uuid.uuid4().hex}_{cv_safe}")
    letter_path = os.path.join("uploads", f"{uuid.uuid4().hex}_{letter_safe}")

    with open(cv_path, "wb") as buffer:
        shutil.copyfileobj(cv.file, buffer)
    with open(letter_path, "wb") as buffer:
        shutil.copyfileobj(lettre.file, buffer)

    # ── 3. Conversion DOCX → PDF ──────────────────────────────────────────────
    pdf_path      = cv_path
    docx_converti = False

    if cv_ext == ".docx":
        pdf_path      = convert_docx_to_pdf(cv_path)
        docx_converti = True
        try:
            os.remove(cv_path)
        except OSError:
            pass

    # ── 4. Enregistrement candidature ────────────────────────────────────────
    application = Application(
        job_id          = job_id,
        candidate_email = candidate_email,
        cv_path         = pdf_path,
        letter_path     = letter_path,
    )
    db.add(application)
    db.commit()
    db.refresh(application)
    application.status_v2 = "APPLIED"
    db.commit()

    # ── Log événement ─────────────────────────────────────────────────────────
    db.add(ApplicationEvent(
        application_id  = application.id,
        event           = "APPLICATION_RECEIVED",
        actor           = "candidate",
        new_status      = "APPLIED",
        details         = {"cv_path": pdf_path, "job_id": job_id}
    ))
    db.commit()

    # ── 5. Pipeline en arrière-plan → réponse immédiate ─────────────────────
    n8n_payload = {
        "application_id"  : application.id,
        "job_id"          : job_id,
        "candidate_email" : candidate_email,
        "cv_path"         : pdf_path,
        "letter_path"     : letter_path,
        "job_title"       : job.title           or "",
        "job_description" : job.description     or "",
        "job_skills"      : job.skills_required or "",
        "job_company"     : job.company         or "",
        "job_level"       : job.level           or "",
        "coding_skills"   : job.skills_json.get("coding", [])   if isinstance(job.skills_json, dict) else [],
        "platform_skills" : job.skills_json.get("platform", []) if isinstance(job.skills_json, dict) else [],
        "mixed_skills"    : job.skills_json.get("mixed", [])    if isinstance(job.skills_json, dict) else [],
    }

    # Lance le pipeline en arrière-plan — candidat reçoit réponse immédiate
    background_tasks.add_task(
        _run_pipeline_background,
        application_id  = application.id,
        job_id          = job_id,
        candidate_email = candidate_email,
        cv_path         = pdf_path,
        letter_path     = letter_path,
        job_title       = job.title           or "",
        job_description = job.description     or "",
        job_skills      = job.skills_required or "",
        job_company     = job.company         or "",
        n8n_payload     = n8n_payload,
    )

    # ── 6. Réponse immédiate au candidat ──────────────────────────────────────
    return {
        "message"       : "Application submitted! You will receive an email with the result.",
        "application_id": application.id,
        "status_v2"     : "APPLIED",
        "format_info"   : {
            "fichier_original"    : cv.filename,
            "format_original"     : cv_ext,
            "docx_converti_en_pdf": docx_converti,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# BACKGROUND TASK — Pipeline complet (n8n ou fallback FastAPI)
# ─────────────────────────────────────────────────────────────────────────────

async def _run_pipeline_background(
    application_id  : int,
    job_id          : int,
    candidate_email : str,
    cv_path         : str,
    letter_path     : str,
    job_title       : str,
    job_description : str,
    job_skills      : str,
    job_company     : str,
    n8n_payload     : dict,
):
    """
    Lance le pipeline en arrière-plan après réponse immédiate au candidat.
    Tente n8n → si down → FastAPI orchestre lui-même.
    """
    import logging
    logger = logging.getLogger(__name__)

    db = SessionLocal()
    try:
        application = db.query(Application).filter(
            Application.id == application_id
        ).first()

        # ── Tenter n8n via Circuit Breaker ────────────────────────────────────
        n8n_result = n8n_breaker.call(
            "http://localhost:5678/webhook/pipeline-recrutement",
            n8n_payload
        )

        if n8n_result is not None:
            logger.info(f"[Background] n8n orchestre app {application_id} ✅")
            return

        # ── Fallback FastAPI ──────────────────────────────────────────────────
        logger.warning(f"[Background] n8n indisponible — FastAPI orchestre app {application_id}")

        # CV Parser
        cv_data = run_cv_parser(cv_path)
        cv_profile = CVProfile(
            application_id            = application_id,
            full_name                 = cv_data.get("full_name"),
            email                     = cv_data.get("email"),
            phone                     = cv_data.get("phone"),
            skills                    = cv_data.get("skills"),
            education                 = cv_data.get("education"),
            professional_experience   = cv_data.get("professional_experience"),
            internships               = cv_data.get("internships"),
            alternance                = cv_data.get("alternance"),
            years_professional        = cv_data.get("years_professional", 0),
            months_internships        = cv_data.get("months_internships", 0),
            months_alternance         = cv_data.get("months_alternance", 0),
            certifications            = cv_data.get("certifications"),
            projects                  = cv_data.get("projects"),
            nb_internships            = cv_data.get("nb_internships", 0),
            years_experience          = cv_data.get("years_experience"),
            languages                 = cv_data.get("languages"),
            cv_quality_score          = cv_data.get("cv_quality_score"),
            classification_confidence = cv_data.get("classification_confidence"),
            raw_text                  = cv_data.get("raw_text"),
        )
        db.add(cv_profile)
        db.commit()
        db.refresh(cv_profile)
        application.status_v2 = "ANALYZED"
        db.commit()

        # Motivation Agent
        motivation_result = run_motivation_agent(
            letter_path     = letter_path,
            job_title       = job_title,
            job_description = job_description,
            job_skills      = job_skills,
            job_company     = job_company,
            application_id  = application_id,
            db              = db,
        )
        motivation_result = motivation_result or {}
        score_motivation  = int(motivation_result.get("score_motivation", 50) or 50)
        signal_motivation = str(motivation_result.get("signal_motivation", "medium") or "medium")

        # Matching Agent
        cv_profile_dict = {
            "full_name"               : cv_profile.full_name,
            "skills"                  : cv_profile.skills,
            "professional_experience" : cv_profile.professional_experience,
            "internships"             : cv_profile.internships,
            "alternance"              : cv_profile.alternance,
            "certifications"          : cv_profile.certifications,
            "projects"                : cv_profile.projects or [],
            "education"               : cv_profile.education,
            "years_experience"        : cv_profile.years_experience,
            "years_professional"      : cv_profile.years_professional,
            "months_internships"      : cv_profile.months_internships,
            "months_alternance"       : cv_profile.months_alternance,
            "cv_quality_score"        : cv_profile.cv_quality_score or 0.0,
            "languages"               : cv_profile.languages or [],
        }
        application.status_v2 = "MATCHED"
        db.commit()

        run_matching_agent(
            cv_profile        = cv_profile_dict,
            job_title         = job_title,
            job_description   = job_description,
            job_skills        = job_skills,
            job_company       = job_company,
            score_motivation  = score_motivation,
            signal_motivation = signal_motivation,
            application_id    = application_id,
            job_id            = job_id,
            db                = db,
        )

        db.add(ApplicationEvent(
            application_id = application_id,
            event          = "FALLBACK_FASTAPI_USED",
            actor          = "system",
            previous_status= "APPLIED",
            new_status     = "MATCHED",
            details        = {"reason": "n8n_unavailable", "circuit_state": n8n_breaker.state}
        ))
        db.commit()

    except Exception as e:
        logger.error(f"[Background] Erreur pipeline app {application_id}: {e}")
        try:
            app = db.query(Application).filter(Application.id == application_id).first()
            if app:
                app.status_v2     = "ERROR_RETRY"
                app.error_stage   = "PIPELINE"
                app.error_message = str(e)
                app.retry_count   = (app.retry_count or 0) + 1
                db.add(ApplicationEvent(
                    application_id = application_id,
                    event          = "ERROR",
                    actor          = "system",
                    new_status     = "ERROR_RETRY",
                    details        = {"stage": "PIPELINE", "error": str(e)}
                ))
                db.commit()
        except Exception:
            pass
    finally:
        db.close()



@router.get("/applications")
def get_all_applications(db: Session = Depends(get_db)):
    return db.query(Application).all()


@router.get("/applications/rh-final-ranking")
def rh_final_ranking(
    job_id       : int,
    db           : Session = Depends(get_db),
    current_user = Depends(require_role("RH")),
):
    from app.models import ManagerReview

    apps = db.query(Application).filter(
        Application.job_id   == job_id,
        Application.status_v2.in_(["ACCEPTED", "TECH_EVALUATED"]),
    ).all()

    groupe_1 = []
    groupe_2 = []

    for app in apps:
        cv = db.query(CVProfile).filter(CVProfile.application_id == app.id).first()
        review = db.query(ManagerReview).filter(
            ManagerReview.application_id == app.id
        ).order_by(ManagerReview.created_at.desc()).first()

        score_final  = float(app.score_final    or 0)
        tech_score   = float(app.score_technique or 0)
        score_global = round(0.60 * score_final + 0.40 * tech_score, 2)

        candidat = {
            "application_id"  : app.id,
            "candidate_name"  : cv.full_name if cv else app.candidate_email,
            "candidate_email" : app.candidate_email,
            "score_final"     : score_final,
            "technical_score" : tech_score,
            "score_global"    : score_global,
            "manager_note"    : review.commentaire if review else "",
            "status_v2"       : app.status_v2,
        }

        if app.status_v2 == "ACCEPTED":
            groupe_1.append(candidat)
        else:
            groupe_2.append(candidat)

    groupe_1.sort(key=lambda x: x["score_global"], reverse=True)
    groupe_2.sort(key=lambda x: x["score_global"], reverse=True)

    return {
        "job_id"   : job_id,
        "groupe_1" : {"label": "Validated",       "candidats": groupe_1},
        "groupe_2" : {"label": "To review", "candidats": groupe_2},
    }


@router.get("/applications/by-job/{job_id}")
def get_applications_by_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    REJECTED = {"REJECTED", "REJECTED_AUTO", "REJECTED_FINAL", "REJECTED_TECH", "MANAGER_REJECTED", "ERROR", "ERROR_RETRY", "POSITION_FILLED"}
    HIDDEN_FOR_MANAGER = {"APPLIED", "ANALYZED"}

    IN_PROGRESS = {
        "TEST_READY", "TEST_SENT", "TEST_IN_PROGRESS", "TEST_COMPLETED",
        "TECHNICAL_REVIEW_PENDING", "INTERVIEW_ELIGIBLE", "TECH_EVALUATED",
        "INTERVIEW_SCHEDULED", "INTERVIEW_DONE", "ACCEPTED",
    }

    query = db.query(models.Application).filter(
        models.Application.job_id == job_id
    ).order_by(models.Application.score_final.desc().nullslast())

    # Compter les rejetés séparément
    rejected_count = sum(
        1 for a in query.all() if a.status_v2 in REJECTED
    )

    result = []
    for app in query.all():
        if app.status_v2 in REJECTED:
            continue
        if current_user.role == "MANAGER" and app.status_v2 in HIDDEN_FOR_MANAGER:
            continue

        cv = db.query(models.CVProfile).filter(
            models.CVProfile.application_id == app.id
        ).first()

        full_name = (cv.full_name if cv and cv.full_name else None) or app.candidate_email

        if app.status_v2 == "PRESELECTED":
            group = "PRESELECTED"
        elif app.status_v2 in {"PENDING", "MATCHED"}:
            group = "PENDING"
        elif app.status_v2 in IN_PROGRESS:
            group = "IN_PROGRESS"
        else:
            group = "OTHER"

        result.append({
            "application_id": app.id,
            "full_name":      full_name,
            "email":          app.candidate_email,
            "status_v2":      app.status_v2,
            "group":          group,
            "score_final":    app.score_final if current_user.role == "RH" else None,
        })

    return {"candidates": result, "rejected_count": rejected_count}


# ─────────────────────────────────────────────────────────────────────────────
# GET /applications/waiting-candidates/{job_id}
# Retourne les candidats WAITING_MEET groupés par score décroissant
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/applications/waiting-candidates/{job_id}")
def get_waiting_candidates(
    job_id       : int,
    db           : Session = Depends(get_db),
    current_user = Depends(require_role("RH", "MANAGER")),
):
    apps = db.query(Application).filter(
        Application.job_id    == job_id,
        Application.status_v2 == "WAITING_MEET",
    ).order_by(Application.score_final.desc().nullslast()).all()

    candidates = []
    for app in apps:
        cv = db.query(CVProfile).filter(CVProfile.application_id == app.id).first()
        candidates.append({
            "id"              : app.id,
            "candidate_name"  : cv.full_name if cv and cv.full_name else app.candidate_email,
            "candidate_email" : app.candidate_email,
            "score_final"     : float(app.score_final or 0),
            "score_technique" : float(app.score_technique or 0),
            "status_v2"       : app.status_v2,
            "job_title"       : db.query(Job).filter(Job.id == job_id).first().title if db.query(Job).filter(Job.id == job_id).first() else "",
        })

    return {
        "job_id"    : job_id,
        "count"     : len(candidates),
        "candidates": candidates,
    }


# ─────────────────────────────────────────────────────────────────────────────
# PATCH /applications/{application_id}/promote
# Promeut un candidat WAITING_MEET → MEET_PENDING
# ─────────────────────────────────────────────────────────────────────────────

@router.patch("/applications/{application_id}/promote")
def promote_candidate(
    application_id : int,
    db             : Session = Depends(get_db),
    current_user   = Depends(require_role("RH", "MANAGER")),
):
    application = db.query(Application).filter(Application.id == application_id).first()
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    if application.status_v2 != "WAITING_MEET":
        raise HTTPException(
            status_code=422,
            detail=f"Impossible de promouvoir — statut actuel : {application.status_v2} (attendu : WAITING_MEET)"
        )

    application.status_v2 = "MEET_PENDING"
    db.commit()
    db.refresh(application)

    cv  = db.query(CVProfile).filter(CVProfile.application_id == application_id).first()
    job = db.query(Job).filter(Job.id == application.job_id).first()

    candidate_name  = cv.full_name if cv and cv.full_name else application.candidate_email
    candidate_email = application.candidate_email
    job_title       = job.title if job else "Position not specified"

    # Log événement
    db.add(ApplicationEvent(
        application_id = application_id,
        event          = "PROMOTED_TO_MEET_PENDING",
        actor          = "rh",
        actor_id       = current_user.id,
        details        = {"old_status": "WAITING_MEET", "new_status": "MEET_PENDING"},
    ))
    db.commit()

    # Notification RH
    create_notification(
        db      = db,
        user_id = current_user.id,
        message = f"⬆️ {candidate_name} promoted — {job_title}",
        type    = "info",
        link    = f"/rh/ranking/{application.job_id}",
    )

    return {
        "message"        : f"{candidate_name} promoted to MEET_PENDING",
        "application_id" : application_id,
        "candidate_name" : candidate_name,
        "candidate_email": candidate_email,
        "job_title"      : job_title,
        "old_status"     : "WAITING_MEET",
        "new_status"     : "MEET_PENDING",
    }


# ─────────────────────────────────────────────────────────────────────────────
# POST /applications/request-expand/{job_id}
# RH signale que les candidats actuels ne conviennent pas
# → notifie le manager pour qu'il relance la sélection (WAITING_MEET → MEET_PENDING)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/applications/request-expand/{job_id}")
def request_expand(
    job_id       : int,
    db           : Session = Depends(get_db),
    current_user = Depends(require_role("RH")),
):
    """
    RH clique "Élargir la sélection".

    Ce que ça fait :
      1. Vérifie que le job existe et a un manager assigné
      2. Vérifie qu'il y a des candidats WAITING_MEET (sinon inutile)
      3. Crée une notification in-app pour le manager
         → lien vers /manager/jobs/{job_id}
      4. Log EXPAND_REQUESTED sur chaque candidat WAITING_MEET du job
      5. Retourne success

    Le manager reçoit la notif, va sur sa page, clique "Relancer la sélection"
    → son frontend appelle le webhook n8n /elargir-selection
    → n8n change WAITING_MEET → MEET_PENDING
    → manager planifie les meets via /envoyer-invitations (flow existant)
    """
    from app.models import ManagerJob

    # ── 1. Job existe ? ───────────────────────────────────────────────────────
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # ── 2. Manager assigné ? ──────────────────────────────────────────────────
    manager_job = db.query(ManagerJob).filter(
        ManagerJob.job_id == job_id
    ).first()
    if not manager_job:
        raise HTTPException(
            status_code=404,
            detail="No manager assigned to this job"
        )

    manager = db.query(User).filter(User.id == manager_job.manager_id).first()
    if not manager:
        raise HTTPException(status_code=404, detail="Manager not found")

    # ── 3. Détecter le cycle — WAITING_MEET (cycle 2) ou MATCHED (cycle 3) ──────
    waiting = db.query(Application).filter(
        Application.job_id    == job_id,
        Application.status_v2 == "WAITING_MEET",
    ).all()

    matched = db.query(Application).filter(
        Application.job_id    == job_id,
        Application.status_v2 == "PENDING",
    ).all()

    # Priorité : cycle 2 d'abord, cycle 3 ensuite
    if waiting:
        expand_phase    = "cycle2"
        candidates      = waiting
        expand_detail   = "Restart the selection with candidates waiting for the meet."
    elif matched:
        expand_phase    = "cycle3"
        candidates      = matched
        expand_detail   = "Restart the selection with candidates waiting for the technical test."
    else:
        raise HTTPException(
            status_code=400,
            detail="No candidates available — all profiles have been reviewed"
        )

    # ── 4. Mettre à jour expand_requested et expand_phase dans jobs ───────────
    job.expand_requested = True
    job.expand_phase     = expand_phase
    db.commit()

    # ── 4. Notification in-app → manager ──────────────────────────────────────
    create_notification(
        db      = db,
        user_id = manager.id,
        message = (
            f"Candidates do not match for \"{job.title}\". "
            f"{expand_detail}"
        ),
        type    = "warning",
        link    = f"/manager/jobs/{job_id}",
    )

    # ── 5. Log EXPAND_REQUESTED sur chaque candidat concerné ─────────────────
    for app in candidates:
        db.add(ApplicationEvent(
            application_id = app.id,
            event          = "EXPAND_REQUESTED",
            actor          = "rh",
            actor_id       = current_user.id,
            details        = {
                "job_id"       : job_id,
                "job_title"    : job.title,
                "manager_id"   : manager.id,
                "manager_email": manager.email,
                "expand_phase" : expand_phase,
            },
        ))
    db.commit()

    return {
        "message"       : f"Request sent to manager {manager.email}",
        "job_id"        : job_id,
        "job_title"     : job.title,
        "manager_email" : manager.email,
        "expand_phase"  : expand_phase,
        "candidates_count": len(candidates),
    }



# ─────────────────────────────────────────────────────────────────────────────
# GET /applications/matched-candidates/{job_id}
# Retourne les candidats MATCHED (phase matching, score 50-69, n'ont pas passé le test)
# Utilisé par n8n dans le flow /elargir-selection cycle 3
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/applications/matched-candidates/{job_id}")
def get_matched_candidates(
    job_id       : int,
    db           : Session = Depends(get_db),
    current_user = Depends(require_role("RH", "MANAGER")),
):
    apps = db.query(Application).filter(
        Application.job_id    == job_id,
        Application.status_v2 == "PENDING",
    ).order_by(Application.score_final.desc().nullslast()).all()

    candidates = []
    for app in apps:
        cv  = db.query(CVProfile).filter(CVProfile.application_id == app.id).first()
        job = db.query(Job).filter(Job.id == job_id).first()
        candidates.append({
            "id"              : app.id,
            "candidate_name"  : cv.full_name if cv and cv.full_name else app.candidate_email,
            "candidate_email" : app.candidate_email,
            "score_final"     : float(app.score_final or 0),
            "status_v2"       : app.status_v2,
            "job_title"       : job.title if job else "",
        })

    return {
        "job_id"    : job_id,
        "count"     : len(candidates),
        "candidates": candidates,
    }


# ─────────────────────────────────────────────────────────────────────────────
# PATCH /applications/{application_id}/promote-matched
# Promeut un candidat MATCHED → PRESELECTED (cycle 3)
# Appelé par n8n /elargir-selection branche cycle 3
# Après ce changement, le candidat sera inclus dans le prochain envoi de test
# ─────────────────────────────────────────────────────────────────────────────

@router.patch("/applications/{application_id}/promote-matched")
def promote_matched_candidate(
    application_id : int,
    db             : Session = Depends(get_db),
    current_user   = Depends(require_role("RH", "MANAGER")),
):
    application = db.query(Application).filter(Application.id == application_id).first()
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    if application.status_v2 != "PENDING":
        raise HTTPException(
            status_code=422,
            detail=f"Impossible de promouvoir — statut actuel : {application.status_v2} (attendu : PENDING)"
        )

    application.status_v2 = "PRESELECTED"
    db.commit()
    db.refresh(application)

    cv  = db.query(CVProfile).filter(CVProfile.application_id == application_id).first()
    job = db.query(Job).filter(Job.id == application.job_id).first()

    candidate_name  = cv.full_name if cv and cv.full_name else application.candidate_email
    candidate_email = application.candidate_email
    job_title       = job.title if job else "Position not specified"

    db.add(ApplicationEvent(
        application_id = application_id,
        event          = "PROMOTED_TO_PRESELECTED",
        actor          = "system",
        actor_id       = current_user.id,
        details        = {
            "old_status" : "MATCHED",
            "new_status" : "PRESELECTED",
            "reason"     : "expand_cycle3",
        },
    ))
    db.commit()

    return {
        "message"        : f"{candidate_name} promoted to PRESELECTED — will take the technical test",
        "application_id" : application_id,
        "candidate_name" : candidate_name,
        "candidate_email": candidate_email,
        "job_title"      : job_title,
        "old_status"     : "MATCHED",
        "new_status"     : "PRESELECTED",
    }

@router.get("/applications/{application_id}")
def get_application(application_id: int, db: Session = Depends(get_db)):
    app = db.query(Application).filter(Application.id == application_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    return app


@router.get("/cv-profiles")
def get_all_cv_profiles(db: Session = Depends(get_db)):
    return db.query(CVProfile).all()


@router.get("/cv-profiles/{application_id}")
def get_cv_profile(application_id: int, db: Session = Depends(get_db)):
    profile = db.query(CVProfile).filter(
        CVProfile.application_id == application_id
    ).first()
    if not profile:
        raise HTTPException(status_code=404, detail="CV profile not found")
    return profile


# ─────────────────────────────────────────────────────────────────────────────
# FEEDBACK RH — Dataset pour calibration V2
# ─────────────────────────────────────────────────────────────────────────────

import json as _json


@router.post("/applications/{application_id}/feedback", response_model=FeedbackResponse)
def submit_feedback_rh(
    application_id: int,
    feedback: FeedbackCreate,
    db: Session = Depends(get_db),
):
    """
    Enregistre la correction RH pour constituer le dataset V2.
    Body : {"decision_rh": "ENTRETIEN", "commentaire": "Bon profil NAV"}
    Valeurs acceptées : ENTRETIEN | EN_ATTENTE | REJETÉ
    """
    application = db.query(Application).filter(
        Application.id == application_id
    ).first()
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    last_log = (
        db.query(IA_Log)
        .filter(
            IA_Log.application_id == application_id,
            IA_Log.agent_name     == "matching_agent",
        )
        .order_by(IA_Log.created_at.desc())
        .first()
    )

    decision_ai = application.status_v2 or "INCONNU"  # ← status_v2 prioritaire
    score_final = float(application.score_final or 0)
    main_reason = None

    if last_log:
        try:
            last_result = _json.loads(last_log.output_json)
            decision_ai = last_result.get("decision", decision_ai)
            score_final = float(last_result.get("score_final", score_final))
            main_reason = last_result.get("main_reason")
        except Exception:
            pass

    agreement = (decision_ai == feedback.decision_rh)

    fb = RH_Feedback(
        application_id = application_id,
        decision_ai    = decision_ai,
        decision_rh    = feedback.decision_rh,
        main_reason    = main_reason,
        score_final    = score_final,
        agreement      = agreement,
        commentaire    = (feedback.commentaire or "").strip() or None,
        is_validated   = False,
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)

    nb_feedbacks = db.query(RH_Feedback).filter(
        RH_Feedback.application_id == application_id
    ).count()

    accord_label = "AI/HR agreement" if agreement else f"disagreement (AI={decision_ai})"
    return FeedbackResponse(
        message        = f"HR feedback recorded — {accord_label}",
        application_id = application_id,
        feedback_id    = fb.id,
        decision_ai    = decision_ai,
        decision_rh    = feedback.decision_rh,
        main_reason    = main_reason,
        score_final    = score_final,
        accord         = agreement,
        nb_feedbacks   = nb_feedbacks,
    )


@router.get("/feedback/stats")
def get_feedback_stats(db: Session = Depends(get_db)):
    """Statistiques globales des feedbacks RH pour calibration V2."""
    from sqlalchemy import func as _func

    subq = (
        db.query(
            RH_Feedback.application_id,
            _func.max(RH_Feedback.id).label("last_id"),
        )
        .group_by(RH_Feedback.application_id)
        .subquery()
    )

    derniers = (
        db.query(RH_Feedback)
        .join(subq, RH_Feedback.id == subq.c.last_id)
        .all()
    )

    if not derniers:
        return {
            "message"        : "No feedback recorded yet.",
            "total_feedbacks": 0,
            "accord_pct"     : None,
            "desaccord_pct"  : None,
            "by_main_reason" : {},
            "by_decision_ai" : {},
        }

    total      = len(derniers)
    accords    = sum(1 for f in derniers if f.agreement)
    accord_pct = round(accords / total * 100, 1)

    by_reason: dict = {}
    for f in derniers:
        if not f.agreement:
            reason = f.main_reason or "unknown"
            by_reason[reason] = by_reason.get(reason, 0) + 1

    by_decision_ai: dict = {}
    for f in derniers:
        if not f.agreement:
            key = f"{f.decision_ai}→{f.decision_rh}"
            by_decision_ai[key] = by_decision_ai.get(key, 0) + 1

    return {
        "total_feedbacks" : total,
        "accord_pct"      : accord_pct,
        "desaccord_pct"   : round(100 - accord_pct, 1),
        "accords"         : accords,
        "desaccords"      : total - accords,
        "by_main_reason"  : by_reason,
        "by_decision_ai"  : by_decision_ai,
        "note"            : (
            "Stats calculated on the latest feedback per application. "
            "is_validated=False inclus — filtrer sur is_validated=True pour dataset V2 propre."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# POST /applications/{id}/generate-test — Génération du test technique
#
# ✅ CORRECTIF TIMEOUT : endpoint converti en async + run_in_threadpool
#    La génération LLM peut prendre 30-90s (skill_classifier + 4 tentatives Groq
#    × 8192 tokens + self-tests). Sans async, uvicorn bloque tout le serveur.
#    run_in_threadpool délègue l'appel bloquant dans un thread pool séparé,
#    libérant le event loop pour répondre aux autres requêtes pendant ce temps.
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/applications/{application_id}/generate-test")
async def generate_test(
    application_id : int,
    body           : GenerateTestInput,
    db             : Session = Depends(get_db),
):
    """
    Génère un test technique adapté au profil skills du poste.

    Pipeline interne (document architecture) :
      Phase 2 — skill_classifier valide/corrige les 3 catégories via LLM
      Phase 3 — compute_test_strategy() détermine tech/platform/mixed
      Phase 4 — structure des questions imposée (LLM ne décide pas)
      Phase 5 — génération LLM avec contraintes strictes
      Phase 6 — validation JSON + intégrité

    Cache : même job_id → même test pour tous les candidats (équité).
    force_regenerate=True invalide le cache et génère de nouvelles questions.
    """
    # ── Candidature existe ? ──────────────────────────────────────────────────
    application = db.query(Application).filter(
        Application.id == application_id
    ).first()
    if not application:
        raise HTTPException(
            status_code=404,
            detail=f"Application {application_id} not found"
        )

    # ── Validation : au moins un skill fourni ─────────────────────────────────
    all_input_skills = (
        (body.coding_skills   or []) +
        (body.platform_skills or []) +
        (body.mixed_skills    or [])
    )
    if not all_input_skills:
        raise HTTPException(
            status_code=422,
            detail={
                "error"  : "NO_SKILLS_PROVIDED",
                "message": (
                    "Au moins un skill est requis dans coding_skills, "
                    "platform_skills ou mixed_skills."
                ),
            }
        )

    # ── Récupérer job_title depuis la DB pour le test_id lisible ─────────────
    job_title = body.job_title
    if not job_title and application.job_id:
        job = db.query(Job).filter(Job.id == application.job_id).first()
        if job:
            job_title = job.title

    # ── Appel run_generate_test dans un thread pool (non-bloquant) ────────────
    result = await run_in_threadpool(
        run_generate_test,
        role             = body.role,
        seniority        = body.seniority,
        coding_skills    = body.coding_skills   or [],
        platform_skills  = body.platform_skills or [],
        mixed_skills     = body.mixed_skills    or [],
        job_id           = application.job_id,
        job_title        = job_title,
        application_id   = application_id,
        db               = db,
        force_regenerate = body.force_regenerate,
        auto_start       = body.auto_start,
    )

    if result.get("error"):
        # ── Point 9 : ERROR handling TEST_SENT ───────────────────────────────
        _app = db.query(Application).filter(Application.id == application_id).first()
        if _app:
            _app.status_v2    = "ERROR"
            _app.error_stage   = "TEST_GENERATION"
            _app.error_message = str(result.get("error_reason", "Erreur LLM inconnue"))
            _app.retry_count   = (_app.retry_count or 0) + 1
            db.commit()
        raise HTTPException(
            status_code=500,
            detail={
                "error"  : "generation_failed",
                "message": result.get("error_reason", "Erreur LLM inconnue"),
            }
        )

    # ── Point 9 : TEST_SENT ──────────────────────────────────────────────────
    application = db.query(Application).filter(Application.id == application_id).first()
    if application:
        application.status_v2   = "TEST_SENT"
        application.test_sent_at   = __import__("datetime").datetime.utcnow()
        application.test_expires_at = __import__("datetime").datetime.utcnow() + __import__("datetime").timedelta(days=1)
        db.commit()

    # ── Réponse enrichie avec les nouveaux champs v3 ─────────────────────────
    response = {
        "message"           : "Technical test generated successfully",
        "application_id"    : application_id,
        "test_id"           : result["test_id"],
        "duration"          : result["duration"],
        "test_type"         : result["test_type"],           # tech / platform / mixed
        "question_structure": result["question_structure"],  # {mcq: 2, problem: 1, scenario: 2}
        "questions"         : result["questions"],           # sans réponses (stripped)
        "reused"            : result.get("reused", False),
        "classification"    : result.get("classification"),  # skills_final + corrections
    }

    # Ajouter started_at si auto_start=True
    if body.auto_start and result.get("started_at"):
        response["started_at"] = result["started_at"]

    return response


# ─────────────────────────────────────────────────────────────────────────────
# POST /applications/{id}/start-test/{test_id} — Démarrage du timer
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/applications/{application_id}/start-test/{test_id}")
def start_test(application_id: int, test_id: str, db: Session = Depends(get_db)):
    """
    Démarre le chronomètre pour la combinaison test_id + application_id.

    À appeler APRÈS generate-test et AVANT evaluate-test.
    Si auto_start=True dans generate-test, cet endpoint n'est pas nécessaire.
    """
    app_rec = db.query(Application).filter(Application.id == application_id).first()
    if not app_rec:
        raise HTTPException(
            status_code=404,
            detail=f"Application {application_id} not found"
        )

    result = run_start_test(test_id=test_id, application_id=application_id)

    if result.get("error"):
        raise HTTPException(
            status_code=422,
            detail={
                "error"  : "start_failed",
                "message": result.get("error_reason"),
            }
        )

    return {
        "message"        : "Test started — timer running",
        "test_id"        : result.get("test_id"),
        "started_at"     : result.get("started_at"),
        "already_started": result.get("already_started", False),
    }



@router.post("/applications/{application_id}/evaluate-test")
async def evaluate_test(
    application_id: int,
    body          : EvaluateTestInput,
    db            : Session = Depends(get_db),
):
    """
    Corrige les réponses du candidat et retourne le score technique.
    Déclenche automatiquement l'Agent Décision finale après correction.

    Scoring v4.0 :
      MCQ      : binaire (0 / points_max) — Python pur, zéro LLM
      PROBLEM  : Execution Engine (déterministe) → Fallback Signal+Core si pseudo-code
      SCENARIO : Signal Extractor → Evaluation Core → Decision Engine

    Status : strong (≥70) / medium (≥50) / weak (<50)
    """
    application = db.query(Application).filter(
        Application.id == application_id
    ).first()
    if not application:
        raise HTTPException(
            status_code=404,
            detail=f"Application {application_id} not found"
        )

    # ── Correction dans un thread pool (non-bloquant) ─────────────────────────
    result = await run_in_threadpool(
        run_evaluate_test,
        test_id        = body.test_id,
        answers        = [
            {"question_id": a.question_id, "answer": a.answer}
            for a in body.answers
        ],
        application_id = application_id,
        db             = db,
    )

    if result.get("error"):
        error_type = result.get("error_type", "")

        if error_type == "invalid_submission":
            raise HTTPException(
                status_code=422,
                detail={
                    "error"  : "invalid_submission",
                    "message": result.get("error_reason"),
                }
            )

        if error_type == "too_fast":
            raise HTTPException(
                status_code=429,
                detail={
                    "error"  : "too_fast",
                    "message": result.get("error_reason"),
                }
            )

        if "introuvable" in result.get("error_reason", ""):
            raise HTTPException(
                status_code=404,
                detail={
                    "error"  : "test_not_found",
                    "message": result.get("error_reason"),
                }
            )

        # ── Point 9 : ERROR handling TEST_CORRECTION ─────────────────────────
        _app = db.query(Application).filter(Application.id == application_id).first()
        if _app:
            _app.status_v2    = "ERROR"
            _app.error_stage   = "TEST_CORRECTION"
            _app.error_message = str(result.get("error_reason", "Erreur LLM inconnue"))
            _app.retry_count   = (_app.retry_count or 0) + 1
            db.commit()
        raise HTTPException(
            status_code=503,
            detail={
                "error"  : "evaluation_failed",
                "message": result.get("error_reason", "Erreur LLM inconnue"),
            }
        )

    # ── Point 9 : TEST_COMPLETED ─────────────────────────────────────────────
    application = db.query(Application).filter(Application.id == application_id).first()
    if application:
        application.status_v2   = "TEST_COMPLETED"
        application.score_technique = result.get("technical_score")
        # ── Enregistrer le flag violation si soumission forcée ───────────────
        violation_flag = getattr(body, "violation_flag", None)
        forced_submit  = getattr(body, "forced_submit", False)
        if violation_flag or forced_submit:
            from app.models import ApplicationEvent
            db.add(ApplicationEvent(
                application_id = application_id,
                event_type     = "VIOLATION_FLAG",
                details        = f"flag={violation_flag} | forced_submit={forced_submit} | violations={len(getattr(body, 'violations', []))}",
            ))
        db.commit()

    # ── Agent Décision finale — déclenché automatiquement ────────────────────
    technical_score_val = result["technical_score"]
    rh_report           = {}

    try:
        # Récupérer le profil CV pour les questions d'entretien
        cv_profile_db = db.query(CVProfile).filter(
            CVProfile.application_id == application_id
        ).first()

        cv_profile_dict = {}
        if cv_profile_db:
            cv_profile_dict = {
                "full_name"              : cv_profile_db.full_name,
                "email"                  : cv_profile_db.email,
                "skills"                 : cv_profile_db.skills or [],
                "education"              : cv_profile_db.education or [],
                "professional_experience": cv_profile_db.professional_experience or [],
                "internships"            : cv_profile_db.internships or [],
                "certifications"         : cv_profile_db.certifications or [],
                "projects"               : cv_profile_db.projects or [],
                "years_experience"       : cv_profile_db.years_experience,
            }

        # Récupérer les infos du poste
        job = db.query(Job).filter(Job.id == application.job_id).first()
        job_title  = job.title           if job else ""
        if job and isinstance(job.skills_json, dict):
            all_skills = []
            for cat in ["coding", "platform", "mixed"]:
                    all_skills.extend(job.skills_json.get(cat, []))
            job_skills = ", ".join(all_skills)
        else:
            job_skills = job.skills_required if job else ""

        # Appel Agent Décision dans un thread pool (génération questions LLM)
        rh_report = await run_in_threadpool(
            run_decision_final,
            application_id   = application_id,
            score_final      = float(application.score_final      or 0),
            score_matching   = float(application.score_matching   or 0),
            score_motivation = float(application.score_motivation or 0),
            technical_score  = technical_score_val,
            signal_final     = application.signal_final or "medium",
            cv_profile       = cv_profile_dict,
            job_title        = job_title,
            job_skills       = job_skills,
            candidate_email  = application.candidate_email,
            db               = db,
        )

    except Exception as e:
        # L'Agent Décision ne doit jamais bloquer la réponse du test
        # On log l'erreur mais on retourne quand même le résultat du test
        import logging
        logging.getLogger(__name__).error(
            f"[evaluate_test] Decision Agent error app={application_id}: {e}",
            exc_info=True,
        )
        rh_report = {"error": True, "error_reason": str(e)}

    # ── Réponse complète test + décision RH ──────────────────────────────────
    return {
        "message"        : "Test evaluated successfully",
        "application_id" : application_id,
        "test_id"        : result["test_id"],
        "technical_score": technical_score_val,
        "status"         : result["status"],          # strong / medium / weak
        "flags"          : result["flags"],
        "results"        : result["results"],
        "total_points"   : result["total_points"],
        "earned_points"  : result["earned_points"],
        # ── Infos candidat/poste pour les emails n8n ──────────────────────────────
        "candidate_email": application.candidate_email,
        "candidate_name" : cv_profile_db.full_name if cv_profile_db and cv_profile_db.full_name else application.candidate_email,
        "job_title"      : job_title,
        # ── Décision RH ajoutée automatiquement ──────────────────────────────
        "rh_decision"          : rh_report.get("decision"),           # ENTRETIEN / EN_ATTENTE
        "rh_priority"          : rh_report.get("priority"),           # high / medium / low
        "rh_summary"           : rh_report.get("summary"),            # résumé 1 ligne
        "rh_reason"            : rh_report.get("reason"),             # justification règle
        "interview_questions"  : rh_report.get("interview_questions", []),  # questions si ENTRETIEN
    }


@router.post("/applications/{application_id}/parse-cv")
async def parse_cv(
    application_id: int,
    db: Session = Depends(get_db),
):
    application = db.query(Application).filter(
        Application.id == application_id
    ).first()
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    cv_profile = db.query(CVProfile).filter(
        CVProfile.application_id == application_id
    ).first()
    if not cv_profile:
        raise HTTPException(status_code=404, detail="CV not parsed")

    return {
        "application_id" : application_id,
        "cv_profile_id"  : cv_profile.id,
        "full_name"      : cv_profile.full_name,
        "email"          : cv_profile.email,
        "skills"         : cv_profile.skills,
        "years_experience": cv_profile.years_experience,
        "education"      : cv_profile.education,
        "professional_experience": cv_profile.professional_experience,
    }




# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINTS N8N — Appelés par n8n pour chaque agent séparément
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/applications/{application_id}/run-cv-parser")
async def run_cv_parser_endpoint(
    application_id: int,
    db: Session = Depends(get_db)
):
    """
    n8n appelle cet endpoint pour parser le CV.
    APPLIED → ANALYZED
    """
    application = db.query(Application).filter(Application.id == application_id).first()
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    try:
        cv_data = await run_in_threadpool(run_cv_parser, application.cv_path)

        cv_profile = db.query(CVProfile).filter(CVProfile.application_id == application_id).first()
        if not cv_profile:
            cv_profile = CVProfile(application_id=application_id)
            db.add(cv_profile)

        cv_profile.full_name                 = cv_data.get("full_name")
        cv_profile.email                     = cv_data.get("email")
        cv_profile.phone                     = cv_data.get("phone")
        cv_profile.skills                    = cv_data.get("skills")
        cv_profile.education                 = cv_data.get("education")
        cv_profile.professional_experience   = cv_data.get("professional_experience")
        cv_profile.internships               = cv_data.get("internships")
        cv_profile.alternance                = cv_data.get("alternance")
        cv_profile.years_professional        = cv_data.get("years_professional", 0)
        cv_profile.months_internships        = cv_data.get("months_internships", 0)
        cv_profile.months_alternance         = cv_data.get("months_alternance", 0)
        cv_profile.certifications            = cv_data.get("certifications")
        cv_profile.projects                  = cv_data.get("projects")
        cv_profile.nb_internships            = cv_data.get("nb_internships", 0)
        cv_profile.years_experience          = cv_data.get("years_experience")
        cv_profile.languages                 = cv_data.get("languages")
        cv_profile.cv_quality_score          = cv_data.get("cv_quality_score")
        cv_profile.classification_confidence = cv_data.get("classification_confidence")
        cv_profile.raw_text                  = cv_data.get("raw_text")

        application.status_v2 = "ANALYZED"
        db.commit()
        db.refresh(cv_profile)

        return {
            "status"         : "ANALYZED",
            "application_id" : application_id,
            "cv_profile_id"  : cv_profile.id,
            "full_name"      : cv_profile.full_name,
            "skills"         : cv_profile.skills,
            "years_experience": cv_profile.years_experience,
        }

    except Exception as e:
        application.status_v2    = "ERROR_RETRY"
        application.error_stage   = "CV_PARSING"
        application.error_message = str(e)
        application.retry_count   = (application.retry_count or 0) + 1
        db.commit()
        raise HTTPException(status_code=500, detail={"error": "CV_PARSE_ERROR", "message": str(e)})


@router.post("/applications/{application_id}/run-motivation")
async def run_motivation_endpoint(
    application_id: int,
    db: Session = Depends(get_db)
):
    """
    n8n appelle cet endpoint pour analyser la lettre de motivation.
    """
    application = db.query(Application).filter(Application.id == application_id).first()
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    job = db.query(Job).filter(Job.id == application.job_id).first()

    try:
        result = await run_in_threadpool(
            run_motivation_agent,
            letter_path     = application.letter_path,
            job_title       = job.title           if job else "",
            job_description = job.description     if job else "",
            job_skills      = job.skills_required if job else "",
            job_company     = job.company         if job else "",
            application_id  = application_id,
            db              = db,
        )
        result = result or {}
        return {
            "status"           : "MOTIVATION_DONE",
            "application_id"   : application_id,
            "score_motivation" : result.get("score_motivation", 50),
            "signal_motivation": result.get("signal_motivation", "medium"),
        }

    except Exception as e:
        application.status_v2    = "ERROR_RETRY"
        application.error_stage   = "MOTIVATION"
        application.error_message = str(e)
        application.retry_count   = (application.retry_count or 0) + 1
        db.commit()
        raise HTTPException(status_code=500, detail={"error": "MOTIVATION_ERROR", "message": str(e)})


@router.post("/applications/{application_id}/run-matching")
async def run_matching_endpoint(
    application_id: int,
    db: Session = Depends(get_db)
):
    """
    n8n appelle cet endpoint pour calculer le score de matching.
    ANALYZED → MATCHED
    Nécessite que run-cv-parser et run-motivation soient déjà appelés.
    """
    application = db.query(Application).filter(Application.id == application_id).first()
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    cv_profile = db.query(CVProfile).filter(CVProfile.application_id == application_id).first()
    if not cv_profile:
        raise HTTPException(status_code=400, detail="CV not parsed — please call run-cv-parser first")

    job = db.query(Job).filter(Job.id == application.job_id).first()

    # Récupérer score motivation depuis IA_Log
    import json as _json
    motivation_log = (
        db.query(IA_Log)
        .filter(IA_Log.application_id == application_id, IA_Log.agent_name == "motivation_agent")
        .order_by(IA_Log.created_at.desc())
        .first()
    )
    score_motivation  = 50
    signal_motivation = "medium"
    if motivation_log:
        try:
            mot_data          = _json.loads(motivation_log.output_json)
            score_motivation  = int(mot_data.get("score_motivation", 50) or 50)
            signal_motivation = str(mot_data.get("signal_motivation", "medium") or "medium")
        except Exception:
            pass

    cv_profile_dict = {
        "full_name"               : cv_profile.full_name,
        "skills"                  : cv_profile.skills,
        "professional_experience" : cv_profile.professional_experience,
        "internships"             : cv_profile.internships,
        "alternance"              : cv_profile.alternance,
        "certifications"          : cv_profile.certifications,
        "projects"                : cv_profile.projects or [],
        "education"               : cv_profile.education,
        "years_experience"        : cv_profile.years_experience,
        "years_professional"      : cv_profile.years_professional,
        "months_internships"      : cv_profile.months_internships,
        "months_alternance"       : cv_profile.months_alternance,
        "cv_quality_score"        : cv_profile.cv_quality_score or 0.0,
        "languages"               : cv_profile.languages or [],
    }

    application.status_v2 = "MATCHED"
    db.commit()

    try:
        # Utilise skills_json si disponible (mots-clés structurés)
        # sinon fallback sur skills_required (texte libre)
        if job and isinstance(job.skills_json, dict):
            _all_skills = []
            for _cat in ["coding", "platform", "mixed"]:
                _all_skills.extend(job.skills_json.get(_cat, []))
            _job_skills = ", ".join(_all_skills)
        else:
            _job_skills = job.skills_required if job else ""

        result = await run_in_threadpool(
            run_matching_agent,
            cv_profile        = cv_profile_dict,
            job_title         = job.title           if job else "",
            job_description   = job.description     if job else "",
            job_skills        = _job_skills,
            job_company       = job.company         if job else "",
            score_motivation  = score_motivation,
            signal_motivation = signal_motivation,
            application_id    = application_id,
            job_id            = application.job_id,
            db                = db,
        )
        result = result or {}
        return {
            "status"          : "MATCHED",
            "application_id"  : application_id,
            "score_final"     : result.get("score_final", 0),
            "score_matching"  : result.get("score_matching", 0),
            "score_motivation": score_motivation,
            "signal_final"    : result.get("signal_final", "medium"),
        }

    except Exception as e:
        application.status_v2    = "ERROR_RETRY"
        application.error_stage   = "MATCHING"
        application.error_message = str(e)
        application.retry_count   = (application.retry_count or 0) + 1
        db.commit()
        raise HTTPException(status_code=500, detail={"error": "MATCHING_ERROR", "message": str(e)})


@router.post("/applications/{application_id}/open-test")
async def open_test(
    application_id: int,
    db: Session = Depends(get_db)
):
    """
    Candidat ouvre le lien du test → timer 60min démarre.
    TEST_SENT → TEST_IN_PROGRESS
    """
    from datetime import datetime, timedelta
    application = db.query(Application).filter(Application.id == application_id).first()
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    if application.status_v2 not in ["TEST_SENT", "TEST_READY"]:
        # Bug 3 — si déjà en cours, retourner les infos existantes sans reset le timer
        if application.status_v2 == "TEST_IN_PROGRESS":
            return {
                "status"          : "TEST_IN_PROGRESS",
                "application_id"  : application_id,
                "test_opened_at"  : str(application.test_opened_at),
                "test_expires_at" : str(application.test_expires_at),
                "duration_minutes": 60,
                "already_opened"  : True,
            }
        # Test déjà soumis → accès bloqué
        if application.status_v2 == "TEST_COMPLETED":
            raise HTTPException(
                status_code=403,
                detail={
                    "error"  : "TEST_ALREADY_SUBMITTED",
                    "message": "This test has already been submitted. You can no longer access it.",
                }
            )
        raise HTTPException(status_code=400, detail=f"Statut invalide : {application.status_v2}")

    # Vérifier que le test est disponible (test_available_from)
    if application.test_available_from and datetime.utcnow() < application.test_available_from:
        raise HTTPException(
            status_code=400,
            detail={
                "error"             : "TEST_NOT_YET_AVAILABLE",
                "message"           : "Le test n'est pas encore disponible.",
                "available_from"    : str(application.test_available_from),
            }
        )

    # Démarrer le timer
    application.status_v2      = "TEST_IN_PROGRESS"
    application.test_opened_at  = datetime.utcnow()
    application.test_expires_at = datetime.utcnow() + timedelta(minutes=60)
    db.commit()

    return {
        "status"         : "TEST_IN_PROGRESS",
        "application_id" : application_id,
        "test_opened_at" : str(application.test_opened_at),
        "test_expires_at": str(application.test_expires_at),
        "duration_minutes": 60,
    }

# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
# GET /tests/{test_id} — Questions pour le candidat (sans réponses correctes)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/tests/{test_id}")
def get_test_by_id(test_id: str, db: Session = Depends(get_db)):
    from app.models import Test as TestModel

    test = db.query(TestModel).filter(TestModel.test_id == test_id).first()
    if not test:
        raise HTTPException(status_code=404, detail="Test not found")

    questions_safe = []
    for q in (test.questions or []):
        q_type = str(q.get("type", "open")).lower()
        
        q_safe = {
            "id"         : q.get("id"),
            "type"       : q_type,   # "mcq" / "open" / "problem" / "scenario"
            "question"   : q.get("question") or q.get("text") or q.get("prompt") or "",
            "skill"      : q.get("skill", ""),
            "difficulty" : q.get("difficulty", ""),
            "points_max" : q.get("points_max", 1),
        }

        # MCQ — inclure options, masquer correct_answer
        if q_type in ("mcq", "multiple_choice", "qcm"):
            raw = q.get("options") or q.get("choices") or []
            if raw:
                if isinstance(raw[0], dict):
                    # Format dict: [{"text": "..."}, ...] ou [{"id": 0, "text": "..."}]
                    q_safe["options"] = [
                        o.get("text") or o.get("label") or str(o)
                        for o in raw
                    ]
                else:
                    # Format liste de strings
                    q_safe["options"] = [str(o) for o in raw]
        
        # PROBLEM / SCENARIO — inclure contexte si présent
        elif q_type in ("problem", "open", "scenario", "open_ended"):
            if q.get("context"):
                q_safe["context"] = q.get("context")
            if q.get("expected_concepts"):
                pass  # Ne pas exposer les concepts attendus

        questions_safe.append(q_safe)

    return {
        "test_id"    : test.test_id,
        "duration"   : test.duration or 60,
        "test_type"  : "tech",
        "role"       : test.role,
        "seniority"  : test.seniority,
        "questions"  : questions_safe,
        "total"      : len(questions_safe),
    }

# POINT 8 — AVIS MANAGER après entretien technique
# ─────────────────────────────────────────────────────────────────────────────

from app.models import ManagerReview
from app.routers.auth import require_role
from app.schemas import ManagerReviewCreate
from app import models

@router.post("/applications/{application_id}/manager-review")
def submit_manager_review(
    application_id : int,
    payload        : ManagerReviewCreate,
    db             : Session = Depends(get_db),
    current_user   = Depends(require_role("MANAGER"))
):
    """
    Manager soumet son avis après l'entretien technique.

    Décision  → transmise à l'Agent Décision (combinée avec score test)
    Commentaire → stocké pour RH uniquement — jamais transmis à l'agent

    Logique :
      REFUSÉ      → candidat rejeté directement
      À_REVOIR    → RH décide manuellement
      RECOMMANDÉ  → Agent Décision combine avec score test → ACCEPTÉ ou RH décide
    """
    # Vérifier que la candidature existe
    application = db.query(Application).filter(
        Application.id == application_id
    ).first()
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    # Vérifier que l'entretien a bien eu lieu
    if application.status_v2 not in ["INTERVIEW_DONE", "INTERVIEW_SCHEDULED"]:
        raise HTTPException(
            status_code=400,
            detail="Interview has not taken place yet for this application"
        )

    # Enregistrer l'avis Manager
    review = ManagerReview(
        application_id = application_id,
        manager_id     = current_user.id,
        decision       = payload.decision,
        commentaire    = payload.commentaire   # RH uniquement — jamais dans l'agent
    )
    db.add(review)

    # Mettre à jour le status
    application.status_v2 = "TECH_EVALUATED"

    # Appliquer la logique de décision
    if payload.decision == "REFUSÉ":
        application.status_v2 = "REJECTED_FINAL"

    db.commit()

    return {
        "message"        : "Manager review saved successfully",
        "application_id" : application_id,
        "decision"       : payload.decision,
        "status_v2"      : application.status_v2,
        # Commentaire non retourné ici — réservé au dashboard RH
    }


@router.get("/applications/{application_id}/manager-review")
def get_manager_review(
    application_id : int,
    db             : Session = Depends(get_db),
    current_user   = Depends(require_role("RH"))   # RH uniquement
):
    """
    RH consulte l'avis Manager sur un candidat.
    Inclut le commentaire — jamais exposé au Manager ni à l'agent.
    """
    review = db.query(ManagerReview).filter(
        ManagerReview.application_id == application_id
    ).order_by(ManagerReview.created_at.desc()).first()

    if not review:
        raise HTTPException(status_code=404, detail="Aucun avis Manager pour cette candidature")

    # Récupérer infos Manager
    manager = db.query(models.User).filter(
        models.User.id == review.manager_id  # type: ignore
    ).first() if hasattr(models, 'User') else None

    return {
        "application_id" : application_id,
        "decision"       : review.decision,
        "commentaire"    : review.commentaire,   # visible RH uniquement
        "manager_email"  : manager.email if manager else None,
        "created_at"     : review.created_at,
    }
@router.get("/applications/{application_id}/rh-report")
def get_rh_report(
    application_id : int,
    db             : Session = Depends(get_db),
    current_user   = Depends(get_current_user),
):
    # ── 1. Vérifier que la candidature existe ─────────────────────────────────
    application = db.query(Application).filter(
        Application.id == application_id
    ).first()
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
 
    # ── 2. Informations générales ─────────────────────────────────────────────
    cv = db.query(CVProfile).filter(
        CVProfile.application_id == application_id
    ).first()
 
    candidate_name  = (
        cv.full_name if cv and cv.full_name else application.candidate_email
    )
    candidate_email = application.candidate_email
 
    job = db.query(Job).filter(Job.id == application.job_id).first()
    job_title = job.title if job else "Position not specified"
 
    # ── 3. Score matching ─────────────────────────────────────────────────────
    score_matching   = float(application.score_matching   or 0)
    score_motivation = float(application.score_motivation or 0)
    signal_final     = application.signal_final or "medium"
 
    # ── 4. Note manager — dernière décision soumise ───────────────────────────
    from app.models import ManagerReview
 
    review = (
        db.query(ManagerReview)
        .filter(ManagerReview.application_id == application_id)
        .order_by(ManagerReview.created_at.desc())
        .first()
    )
 
    # Mapper la décision interne vers un label lisible pour le RH
    decision_label_map = {
        "RECOMMENDED" : "Validated",
        "TO_REVIEW"   : "To review",
        "REFUSED"     : "Non retenu",
    }
 
    manager_section = None
    if review:
        manager_user = db.query(User).filter(
            User.id == review.manager_id
        ).first()
 
        manager_section = {
            "decision"      : decision_label_map.get(review.decision, review.decision),
            "note"          : review.commentaire or "",
            "manager_email" : manager_user.email if manager_user else None,
            "submitted_at"  : review.created_at,
        }
 
    # ── 5. Réponse structurée en 3 sections ───────────────────────────────────
    return {
        # Section 1 — Informations générales
        "informations": {
            "candidate_name"  : candidate_name,
            "candidate_email" : candidate_email,
            "job_title"       : job_title,
            "applied_at"      : application.created_at,
            "status_v2"       : application.status_v2,
        },
 
        # Section 2 — Score matching
        "matching": {
            "score_matching"   : score_matching,
            "score_motivation" : score_motivation,
            "signal_final"     : signal_final,
        },
 
        # Section 3 — Note manager (None si pas encore soumise)
        "manager_review" : manager_section,
    }
# ─────────────────────────────────────────────────────────────────────────────
# POST /applications/{id}/manager-decision — Décision Manager (CandidateDetail)
# ─────────────────────────────────────────────────────────────────────────────

class ManagerDecisionInput(BaseModel):
    """
    Payload envoyé depuis le panneau 'Évaluation Manager' de CandidateDetail.
    test_id n'est plus obligatoire (legacy n8n) — on accepte aussi manager_decision direct.
    """
    test_id          : Optional[str] = None
    manager_decision : str           # "VALIDÉ" | "À_APPROFONDIR" | "NON_RETENU"
    manager_note     : Optional[str] = None


# Mapping décision manager → status_v2 (valeurs dans l'enum application_status_v2)
DECISION_TO_STATUS = {
    "VALIDÉ"        : "ACCEPTED",        # Retenu — passe au RH
    "À_APPROFONDIR" : "TECH_EVALUATED",  # Évalué — RH décide la suite
    "NON_RETENU"    : "REJECTED_FINAL",  # Rejeté définitivement
}

# Mapping décision manager → enum manager_decision_v2 (valeurs PostgreSQL)
DECISION_TO_REVIEW = {
    "VALIDÉ"        : "RECOMMENDED",
    "À_APPROFONDIR" : "TO_REVIEW",
    "NON_RETENU"    : "REFUSED",
}

# URL webhook n8n — workflow "Manager Decision"
N8N_MANAGER_DECISION_WEBHOOK = "http://localhost:5678/webhook/manager-decision"


@router.post("/applications/{application_id}/manager-decision")
def submit_manager_decision(
    application_id : int,
    payload        : ManagerDecisionInput,
    db             : Session = Depends(get_db),
    current_user   = Depends(require_role("MANAGER")),
):
    """
    Manager soumet sa décision finale depuis CandidateDetail.

    Décision → status_v2 :
      VALIDÉ        → ACCEPTED       + données RH dans réponse
      À_APPROFONDIR → TECH_EVALUATED + données RH dans réponse
      NON_RETENU    → REJECTED_FINAL + webhook n8n → email rejet candidat
    """
    # ── 1. Vérifier que la candidature existe ─────────────────────────────────
    application = db.query(Application).filter(
        Application.id == application_id
    ).first()
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    # ── 2. Valider la décision ────────────────────────────────────────────────
    valid_decisions = {"VALIDÉ", "À_APPROFONDIR", "NON_RETENU"}
    if payload.manager_decision not in valid_decisions:
        raise HTTPException(
            status_code=422,
            detail={
                "error"   : "INVALID_DECISION",
                "message" : f"Invalid decision. Accepted values: {', '.join(valid_decisions)}",
            }
        )

    # ── 3. Récupérer les infos nécessaires ────────────────────────────────────
    cv = db.query(CVProfile).filter(
        CVProfile.application_id == application_id
    ).first()
    candidate_name  = cv.full_name if cv and cv.full_name else application.candidate_email
    candidate_email = application.candidate_email

    job = db.query(Job).filter(Job.id == application.job_id).first()
    job_title = job.title if job else "Position not specified"

    # ── 4. Capturer le statut AVANT modification (pour le log) ───────────────
    previous_status = application.status_v2

    # ── 5. Appliquer le nouveau statut ────────────────────────────────────────
    new_status = DECISION_TO_STATUS[payload.manager_decision]
    application.status_v2 = new_status

    # ── 6. Sauvegarder dans ManagerReview avec enum PostgreSQL correct ────────
    from app.models import ManagerReview

    review = ManagerReview(
        application_id = application_id,
        manager_id     = current_user.id,
        decision       = DECISION_TO_REVIEW[payload.manager_decision],  # RECOMMENDED / TO_REVIEW / REFUSED
        commentaire    = payload.manager_note or "",
    )
    db.add(review)

    # ── 7. Logger l'événement ─────────────────────────────────────────────────
    db.add(ApplicationEvent(
        application_id  = application_id,
        event           = "MANAGER_DECISION",
        actor           = "manager",
        actor_id        = current_user.id,
        previous_status = previous_status,   # capturé AVANT la modif ligne 4
        new_status      = new_status,
        details         = {
            "decision"     : payload.manager_decision,
            "note_present" : bool(payload.manager_note),
            "job_title"    : job_title,
        },
    ))

    # ── 8. Commit DB ──────────────────────────────────────────────────────────
    db.commit()

    # ── 9. Actions post-commit selon la décision ──────────────────────────────

    # CAS VALIDÉ → notifier tous les RH que le candidat est accepté
    if payload.manager_decision == "VALIDÉ":
        rh_users = db.query(User).filter(User.role == "RH").all()
        for rh in rh_users:
            create_notification(
                db,
                user_id = rh.id,
                message = f"{candidate_name} has been accepted for the '{job_title}' role",
                type    = "success",
                link    = f"/candidates/{application.job_id}/{application_id}",
            )

    # CAS NON_RETENU → webhook n8n synchrone → email rejet au candidat
    if payload.manager_decision == "NON_RETENU":
        n8n_payload = {
            "candidate_email" : candidate_email,
            "candidate_name"  : candidate_name,
            "job_title"       : job_title,
            "application_id"  : application_id,
        }
        try:
            resp = httpx.post(
                N8N_MANAGER_DECISION_WEBHOOK,
                json    = n8n_payload,
                timeout = 10.0,
            )
            resp.raise_for_status()
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=504,
                detail={
                    "error"   : "N8N_TIMEOUT",
                    "message" : (
                        "Decision saved, but the rejection email could not be sent "
                        "(n8n timeout). Please retry from n8n if needed."
                    ),
                }
            )
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=502,
                detail={
                    "error"   : "N8N_ERROR",
                    "message" : (
                        f"Decision saved, but n8n returned an error "
                        f"({e.response.status_code}). Please check the 'Manager Decision' workflow."
                    ),
                }
            )
        except Exception as e:
            raise HTTPException(
                status_code=502,
                detail={
                    "error"   : "N8N_UNREACHABLE",
                    "message" : f"Decision saved, but n8n is unreachable. Detail: {str(e)}",
                }
            )

        return {
            "message"        : "Candidate rejected. Notification email sent.",
            "application_id" : application_id,
            "candidate_name" : candidate_name,
            "decision"       : payload.manager_decision,
            "status_v2"      : new_status,
            "email_sent"     : True,
        }

    # CAS VALIDÉ ou À_APPROFONDIR → notifier le RH + données dans la réponse
    # Récupérer tous les RH pour notifier
    rh_users = db.query(User).filter(User.role == "RH").all()
    for rh in rh_users:
        if payload.manager_decision == "VALIDÉ":
            create_notification(
                db,
                user_id = rh.id,
                message = f"{candidate_name} has been approved by the manager for the '{job_title}' role",
                type    = "success",
                link    = f"/candidates/{application.job_id}/{application_id}",
            )
        else:  # À_APPROFONDIR
            create_notification(
                db,
                user_id = rh.id,
                message = f"{candidate_name} needs further review for the '{job_title}' role",
                type    = "warning",
                link    = f"/candidates/{application.job_id}/{application_id}",
            )

    # CAS VALIDÉ ou À_APPROFONDIR → données RH dans la réponse
    return {
        "message"        : (
            "Candidate validated. File forwarded to HR."
            if payload.manager_decision == "VALIDÉ"
            else "Candidate needs further review. File forwarded to HR."
        ),
        "application_id" : application_id,
        "candidate_name" : candidate_name,
        "decision"       : payload.manager_decision,
        "status_v2"      : new_status,
        "rh_summary"     : {
            "application_id"  : application_id,
            "candidate_name"  : candidate_name,
            "candidate_email" : candidate_email,
            "job_title"       : job_title,
            "decision"        : payload.manager_decision,
            "manager_note"    : payload.manager_note or "",
            "score_final"     : float(application.score_final    or 0),
            "score_technique" : float(application.score_technique or 0),
            "signal_final"    : application.signal_final or "medium",
            "priority_group"  : 1 if payload.manager_decision == "VALIDÉ" else 2,
        },
    }

# ─────────────────────────────────────────────────────────────────────────────
# GET /applications/{id}/test-results — Résultats du test technique
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/applications/{application_id}/test-results")
def get_test_results(
    application_id : int,
    db             : Session = Depends(get_db),
    current_user   = Depends(get_current_user),
):
    import json as _json
    from app.models import Test as TestModel

    log = (
        db.query(IA_Log)
        .filter(
            IA_Log.application_id == application_id,
            IA_Log.agent_name == "test_agent_evaluate",
        )
        .order_by(IA_Log.created_at.desc())
        .first()
    )

    if not log:
        return { "available": False, "results": [], "technical_score": None, "status": None, "flags": [] }

    try:
        data = _json.loads(log.output_json) or {}
    except Exception:
        data = {}

    results = data.get("results", [])

    # Enrichir avec les questions depuis la table tests
    test_id = data.get("test_id")
    questions_map = {}

    if test_id:
        test = db.query(TestModel).filter(TestModel.test_id == test_id).first()
        if test and test.questions:
            try:
                qs = test.questions if isinstance(test.questions, list) else _json.loads(test.questions)
                for q in qs:
                    qid = q.get("id") or q.get("question_id")
                    if qid is not None:
                        questions_map[int(qid)] = q.get("question", "")
            except Exception:
                pass

    # Injecter la question dans chaque résultat
    enriched = []
    for r in results:
        qid = r.get("question_id")
        enriched.append({
            **r,
            "question": questions_map.get(int(qid), "") if qid is not None else "",
        })

    return {
        "available"       : True,
        "test_id"         : test_id,
        "technical_score" : data.get("technical_score"),
        "status"          : data.get("status"),
        "flags"           : data.get("flags", []),
        "results"         : enriched,
    }

# ─────────────────────────────────────────────────────────────────────────────
# GET /applications/rh-final-ranking — Classement final RH par job
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/applications/rh-final-ranking")
def rh_final_ranking(
    job_id       : int,
    db           : Session = Depends(get_db),
    current_user = Depends(require_role("RH")),
):
    """
    Retourne les candidats classés en 2 groupes pour le RH :
    - Groupe 1 : VALIDÉ par manager (ACCEPTED)
    - Groupe 2 : À_APPROFONDIR par manager (TECH_EVALUATED)
    Chaque groupe classé par score_global décroissant.
    score_global = 0.60 × score_final + 0.40 × technical_score
    """
    from app.models import ManagerReview

    apps = db.query(Application).filter(
        Application.job_id   == job_id,
        Application.status_v2.in_(["ACCEPTED", "TECH_EVALUATED"]),
    ).all()

    groupe_1 = []
    groupe_2 = []

    for app in apps:
        cv = db.query(CVProfile).filter(CVProfile.application_id == app.id).first()
        review = db.query(ManagerReview).filter(
            ManagerReview.application_id == app.id
        ).order_by(ManagerReview.created_at.desc()).first()

        score_final    = float(app.score_final    or 0)
        tech_score     = float(app.score_technique or 0)
        score_global   = round(0.60 * score_final + 0.40 * tech_score, 2)

        candidat = {
            "application_id"  : app.id,
            "candidate_name"  : cv.full_name if cv else app.candidate_email,
            "candidate_email" : app.candidate_email,
            "score_final"     : score_final,
            "technical_score" : tech_score,
            "score_global"    : score_global,
            "manager_note"    : review.note if review else "",
            "status_v2"       : app.status_v2,
        }

        if app.status_v2 == "ACCEPTED":
            groupe_1.append(candidat)
        else:
            groupe_2.append(candidat)

    # Classer chaque groupe par score_global décroissant
    groupe_1.sort(key=lambda x: x["score_global"], reverse=True)
    groupe_2.sort(key=lambda x: x["score_global"], reverse=True)

    return {
        "job_id"   : job_id,
        "groupe_1" : {"label": "Validated", "candidats": groupe_1},
        "groupe_2" : {"label": "To review", "candidats": groupe_2},
    }

# ─────────────────────────────────────────────────────────────────────────────
# GET /applications/{id}/rh-full-report — Rapport complet RH
# ─────────────────────────────────────────────────────────────────────────────
 
@router.get("/applications/{application_id}/rh-full-report")
def get_rh_full_report(
    application_id : int,
    db             : Session = Depends(get_db),
    current_user   = Depends(require_role("RH")),
):
    """
    Rapport complet pour la page RH Candidat :
    - Informations générales
    - Scores
    - Décision manager + note
    - Compétences extraites du CV (hard skills + soft skills)
    - Entretien technique (booked)
    - URL du CV téléchargeable
    """
    import json as _json

    application = db.query(Application).filter(
        Application.id == application_id
    ).first()
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    cv  = db.query(CVProfile).filter(CVProfile.application_id == application_id).first()
    job = db.query(Job).filter(Job.id == application.job_id).first()

    candidate_name = cv.full_name if cv and cv.full_name else application.candidate_email
    job_title      = job.title if job else "Position not specified"

    # ── Scores ────────────────────────────────────────────────────────────────
    score_final     = float(application.score_final     or 0)
    score_technique = float(application.score_technique or 0)
    score_matching  = float(application.score_matching  or 0)
    score_global    = round(0.60 * score_final + 0.40 * score_technique, 2)

    # ── Décision manager ──────────────────────────────────────────────────────
    from app.models import ManagerReview
    review = db.query(ManagerReview).filter(
        ManagerReview.application_id == application_id
    ).order_by(ManagerReview.created_at.desc()).first()

    manager_review = None
    if review:
        manager_user = db.query(User).filter(User.id == review.manager_id).first()
        decision_map = {
            "RECOMMENDED": "Validated",
            "TO_REVIEW"  : "To review",
            "REFUSED"    : "Non retenu",
        }
        manager_review = {
            "decision"     : decision_map.get(review.decision, review.decision),
            "note"         : review.commentaire or "",
            "manager_email": manager_user.email if manager_user else None,
            "submitted_at" : review.created_at,
        }

    # ── Expérience & formation extraites du CV ───────────────────────────────
    def _normalize_json_list(value):
        if isinstance(value, str):
            try:
                value = _json.loads(value)
            except Exception:
                return []
        return value if isinstance(value, list) else []

    experience_entries = []
    education_entries = []

    if cv:
        raw_pro = _normalize_json_list(cv.professional_experience)
        raw_internships = _normalize_json_list(cv.internships)
        raw_alternance = _normalize_json_list(cv.alternance)
        raw_education = _normalize_json_list(cv.education)

        for exp in raw_pro:
            if isinstance(exp, dict):
                experience_entries.append({
                    "type"     : "Professionnelle",
                    "role"     : str(exp.get("role", "")) or "Work experience",
                    "company"  : exp.get("company") or "",
                    "duration" : exp.get("duration") or exp.get("dates") or "",
                    "details"  : exp.get("description") or exp.get("missions") or exp.get("achievements") or "",
                })
        for exp in raw_internships:
            if isinstance(exp, dict):
                experience_entries.append({
                    "type"     : "Stage",
                    "role"     : str(exp.get("role", "")) or "Stage",
                    "company"  : exp.get("company") or "",
                    "duration" : exp.get("duration") or exp.get("dates") or "",
                    "details"  : exp.get("description") or exp.get("missions") or "",
                })
        for exp in raw_alternance:
            if isinstance(exp, dict):
                experience_entries.append({
                    "type"     : "Alternance",
                    "role"     : str(exp.get("role", "")) or "Alternance",
                    "company"  : exp.get("company") or "",
                    "duration" : exp.get("duration") or exp.get("dates") or "",
                    "details"  : exp.get("description") or exp.get("missions") or "",
                })

        for edu in raw_education:
            if isinstance(edu, dict):
                education_entries.append({
                    "degree"   : str(edu.get("degree") or edu.get("title") or "Formation"),
                    "school"   : edu.get("school") or edu.get("institution") or "",
                    "duration" : edu.get("duration") or edu.get("dates") or "",
                    "details"  : edu.get("description") or edu.get("field") or "",
                })

    # ── Entretien technique Manager (booked, pas HR Round) ───────────────────
    from app.models import Interview
    interview = db.query(Interview).filter(
        Interview.candidate_email == application.candidate_email,
        Interview.job_id          == application.job_id,
        Interview.status          == "booked",
        Interview.round           != "HR Round",
    ).order_by(Interview.scheduled_at.desc()).first()

    interview_info = None
    if interview:
        interview_info = {
            "scheduled_at": interview.scheduled_at,
            "meeting_link": interview.meeting_link,
            "status"      : interview.status,
        }

    # ── Entretien présentiel RH (HR Round uniquement) ─────────────────────────
    presentiel = db.query(Interview).filter(
        Interview.candidate_email == application.candidate_email,
        Interview.job_id          == application.job_id,
        Interview.round           == "HR Round",
    ).order_by(Interview.scheduled_at.desc()).first()

    presentiel_info = None
    if presentiel:
        presentiel_info = {
            "scheduled_at": presentiel.scheduled_at,
            "meeting_link": presentiel.meeting_link,
            "status"      : presentiel.status,
        }

    # ── URL CV téléchargeable ─────────────────────────────────────────────────
    # application.cv_path contient le chemin relatif ("uploads/xxxx.pdf").
    # On construit une URL publique accessible depuis le frontend.
    cv_url = None
    if application.cv_path:
        cv_url = f"{os.environ.get('APP_BASE_URL', 'http://localhost:8000')}/{application.cv_path}"

    return {
        "informations": {
            "candidate_name"  : candidate_name,
            "candidate_email" : application.candidate_email,
            "job_title"       : job_title,
            "job_id"          : application.job_id,
            "applied_at"      : application.created_at,
            "status_v2"       : application.status_v2,
        },
        "scores": {
            "score_matching"  : score_matching,
            "score_technique" : score_technique,
            "score_final"     : score_final,
            "score_global"    : score_global,
        },
        "manager_review" : manager_review,
        "experience"     : experience_entries,
        "education"      : education_entries,
        "interview"      : interview_info,
        "presentiel"     : presentiel_info,
        "cv_url"         : cv_url,
    }

# ─────────────────────────────────────────────────────────────────────────────
# POST /applications/{id}/schedule-presentiel
# Planifier un entretien présentiel RH depuis le rapport candidat
# ─────────────────────────────────────────────────────────────────────────────

from datetime import datetime as _dt
from app.models import Interview as InterviewModel

class SchedulePresentielInput(BaseModel):
    scheduled_at : str   # ISO 8601 — ex: "2025-06-12T14:00:00"
    notes        : Optional[str] = None


@router.post("/applications/{application_id}/schedule-presentiel", status_code=201)
def schedule_presentiel(
    application_id : int,
    body           : SchedulePresentielInput,
    db             : Session = Depends(get_db),
    current_user   : User    = Depends(require_role("RH")),
):
    """
    Planifie un entretien présentiel RH pour un candidat.

    - Crée (ou met à jour) une ligne Interview (round="HR Round")
    - Génère une notification in-app pour le RH courant
    - Retourne les détails de l'entretien créé

    Le frontend envoie : { scheduled_at: "2025-06-12T14:00:00" }
    """
    # ── 1. Vérifier que la candidature existe ─────────────────────────────────
    application = db.query(Application).filter(Application.id == application_id).first()
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    # ── 2. Récupérer infos candidat + job ─────────────────────────────────────
    cv      = db.query(CVProfile).filter(CVProfile.application_id == application_id).first()
    job     = db.query(Job).filter(Job.id == application.job_id).first()

    candidate_name  = cv.full_name if cv and cv.full_name else application.candidate_email
    candidate_email = application.candidate_email
    job_title       = job.title if job else "Position not specified"

    # ── 3. Parser la date ──────────────────────────────────────────────────────
    try:
        from zoneinfo import ZoneInfo
        scheduled_dt = _dt.fromisoformat(body.scheduled_at)
        # Si pas de timezone → on l'interprète comme Africa/Tunis (UTC+1)
        if scheduled_dt.tzinfo is None:
            scheduled_dt = scheduled_dt.replace(tzinfo=ZoneInfo("Africa/Tunis"))
    except ValueError:
        raise HTTPException(status_code=422, detail="Format de date invalide — attendu ISO 8601")

    # ── 4. Vérifier si un entretien présentiel existe déjà → le mettre à jour ─
    existing = db.query(InterviewModel).filter(
        InterviewModel.candidate_email == candidate_email,
        InterviewModel.job_id          == application.job_id,
        InterviewModel.round           == "HR Round",
    ).first()

    if existing:
        # Mise à jour du créneau existant
        existing.scheduled_at = scheduled_dt
        existing.status       = "scheduled"
        if body.notes:
            existing.notes = body.notes
        db.commit()
        db.refresh(existing)
        interview = existing
        action = "updated"
    else:
        # Création d'un nouvel entretien présentiel
        interview = InterviewModel(
            job_id          = application.job_id,
            candidate_name  = candidate_name,
            candidate_email = candidate_email,
            role            = job_title,
            round           = "HR Round",
            scheduled_at    = scheduled_dt,
            duration_minutes= 60,
            status          = "scheduled",
            notes           = body.notes or f"In-person interview scheduled by HR ({current_user.email})",
        )
        db.add(interview)
        db.commit()
        db.refresh(interview)
        action = "created"

    # ── 5. Notification in-app pour le RH courant ─────────────────────────────
    scheduled_at_str = scheduled_dt.strftime("%Y-%m-%d %H:%M")
    create_notification(
        db      = db,
        user_id = current_user.id,
        message = f"📅 In-person interview scheduled — {candidate_name} · {job_title} · {scheduled_at_str}",
        type    = "success",
        link    = f"/rh/candidates/{application.job_id}/{application_id}",
    )

    # ── 6. Log événement ──────────────────────────────────────────────────────
    event = ApplicationEvent(
        application_id = application_id,
        event          = "PRESENTIEL_SCHEDULED",
        actor          = "rh",
        actor_id       = current_user.id,
        details        = {
            "scheduled_at"   : body.scheduled_at,
            "interview_id"   : interview.id,
            "candidate_name" : candidate_name,
        },
    )
    db.add(event)
    db.commit()

    return {
        "message"       : f"In-person interview {action}",
        "interview_id"  : interview.id,
        "candidate_name": candidate_name,
        "job_title"     : job_title,
        "scheduled_at"  : interview.scheduled_at,
        "status"        : interview.status,
    }

# ─────────────────────────────────────────────────────────────────────────────
# POST /applications/{id}/rh-decision — Décision finale RH
# ─────────────────────────────────────────────────────────────────────────────

class RHDecisionInput(BaseModel):
    decision      : str
    interview_date: Optional[str] = None
    note          : Optional[str] = None


@router.post("/applications/{application_id}/rh-decision")
def submit_rh_decision(
    application_id : int,
    payload        : RHDecisionInput,
    request        : Request,
    db             : Session = Depends(get_db),
    current_user   = Depends(require_role("RH")),
):
    application = db.query(Application).filter(Application.id == application_id).first()
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    valid = {"HIRED", "REJECTED_FINAL"}
    if payload.decision not in valid:
        raise HTTPException(status_code=422, detail=f"Invalid decision. Accepted values: {valid}")

    cv  = db.query(CVProfile).filter(CVProfile.application_id == application_id).first()
    job = db.query(Job).filter(Job.id == application.job_id).first()
    candidate_name  = cv.full_name if cv and cv.full_name else application.candidate_email
    candidate_email = application.candidate_email
    job_title       = job.title if job else "Position not specified"

    application.status_v2 = payload.decision
    db.commit()

    if payload.decision == "HIRED":
        from datetime import datetime
        if job and not job.closed_at:
            job.closed_at = datetime.utcnow()

        others = db.query(Application).filter(
            Application.job_id == application.job_id,
            Application.id     != application_id,
            Application.status_v2.notin_(["REJECTED_FINAL", "REJECTED_AUTO", "REJECTED_TECH", "HIRED"]),
        ).all()
        for other in others:
            other.status_v2 = "POSITION_FILLED"
        db.commit()

        rh_users = db.query(User).filter(User.role == "RH").all()
        for rh in rh_users:
            create_notification(db, user_id=rh.id,
                message=f"✅ Role '{job_title}' filled — {candidate_name} hired",
                type="success", link=f"/rh/ranking/{application.job_id}")

        try:
            rh_token = request.headers.get("Authorization", "").replace("Bearer ", "")
            httpx.post("http://localhost:5678/webhook/rh-decision", json={
                "decision"        : "HIRED",
                "candidate_email" : candidate_email,
                "candidate_name"  : candidate_name,
                "job_title"       : job_title,
                "job_id"          : application.job_id,
                "application_id"  : application_id,
                "interview_date"  : payload.interview_date or "",
                "note"            : payload.note or "",
                "token"           : rh_token,
            }, timeout=10.0)
        except Exception:
            pass

        return {
            "message"         : f"{candidate_name} hired — position filled",
            "application_id"  : application_id,
            "status_v2"       : "HIRED",
            "job_closed"      : True,
            "others_notified" : len(others),
        }

    else:  # REJECTED_FINAL
        rh_users = db.query(User).filter(User.role == "RH").all()
        for rh in rh_users:
            create_notification(db, user_id=rh.id,
                message=f"❌ {candidate_name} was rejected for the '{job_title}' role",
                type="warning", link=f"/rh/ranking/{application.job_id}")

        try:
            httpx.post("http://localhost:5678/webhook/rh-decision", json={
                "decision"        : "REJECTED_FINAL",
                "candidate_email" : candidate_email,
                "candidate_name"  : candidate_name,
                "job_title"       : job_title,
                "job_id"          : application.job_id,
                "application_id"  : application_id,
            }, timeout=10.0)
        except Exception:
            pass

        return {
            "message"       : f"{candidate_name} rejected",
            "application_id": application_id,
            "status_v2"     : "REJECTED_FINAL",
        }