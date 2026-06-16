from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app import models, schemas
from app.database import get_db
from app.routers.auth import require_role, get_current_user

router = APIRouter(prefix="/jobs", tags=["Jobs"])


# ============================================================
# ENDPOINTS EXISTANTS — INCHANGÉS
# ============================================================

@router.post("/")
def create_job(
    job: schemas.JobCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("RH"))  # RH uniquement
):
    new_job = models.Job(
        # ── Champs existants ──────────────────────────────
        title=job.title,
        description=job.description,
        skills_required=job.skills_required,
        date_expiration=job.date_expiration,
        # ── Nouveaux champs Point 2 ───────────────────────
        level=job.level,
        skills_json=job.skills_json,
        bonus_skills=job.bonus_skills,
        location=job.location,
        department=job.department,
        company=job.company,
        pipeline_mode=job.pipeline_mode or "SEMI_AUTO",
    )
    db.add(new_job)
    db.commit()
    db.refresh(new_job)

    # Assigner le Manager au job si fourni
    if job.manager_id:
        # Vérifier que le Manager existe et a le bon rôle
        manager = db.query(models.User).filter(
            models.User.id == job.manager_id,
            models.User.role == "MANAGER"
        ).first()
        if not manager:
            raise HTTPException(status_code=404, detail="Manager non trouvé")

        # Vérifier que ce job n'a pas déjà un Manager (normalement impossible ici car nouveau job)
        manager_job = models.ManagerJob(
            manager_id=job.manager_id,
            job_id=new_job.id
        )
        db.add(manager_job)
        db.commit()

    return new_job


@router.get("/")
def get_jobs(db: Session = Depends(get_db)):
    """Retourne uniquement les jobs ouverts (closed_at IS NULL)."""
    return db.query(models.Job).filter(models.Job.closed_at == None).all()


# ============================================================
# NOUVEAUX ENDPOINTS — POINT 2
# ============================================================

@router.get("/rh/dashboard")
def rh_dashboard(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("RH"))
):
    """
    Dashboard RH — tous les jobs avec leur pipeline complet.
    Pour chaque job : nombre de candidats par statut.
    """
    jobs = db.query(models.Job).all()
    result = []

    for job in jobs:
        applications = db.query(models.Application).filter(
            models.Application.job_id == job.id
        ).all()

        # Compter par statut
        pipeline = {
            "total":               len(applications),
            "en_attente":          sum(1 for a in applications if a.status_v2 in ["APPLIED", "PENDING", "MATCHED", "EN_ATTENTE"]),
            "preselectionnes":     sum(1 for a in applications if a.status_v2 in ["PRESELECTED", "TEST_READY", "TEST_SENT", "TEST_IN_PROGRESS"]),
            "test_envoye":         sum(1 for a in applications if a.status_v2 in ["TEST_SENT", "TEST_IN_PROGRESS", "TEST_COMPLETED"]),
            "entretien_planifie":  sum(1 for a in applications if a.status_v2 in ["MEET_PENDING", "INTERVIEW_SCHEDULED", "INTERVIEW_DONE"]),
            "acceptes":            sum(1 for a in applications if a.status_v2 == "ACCEPTED"),
            "rejetes":             sum(1 for a in applications if a.status_v2 in ["REJECTED_AUTO", "REJECTED_FINAL", "REJECTED_TECH", "MANAGER_REJECTED"]),
            "waiting_meet_count":  sum(1 for a in applications if a.status_v2 == "WAITING_MEET"),
        }

        # Manager assigné
        manager_job = db.query(models.ManagerJob).filter(
            models.ManagerJob.job_id == job.id
        ).first()
        manager = None
        if manager_job:
            manager = db.query(models.User).filter(
                models.User.id == manager_job.manager_id
            ).first()

        result.append({
            "id":            job.id,
            "title":         job.title,
            "department":    job.department,
            "location":      job.location,
            "level":         job.level,
            "status":        "open" if not job.closed_at else "closed",
            "created_at":    job.created_at,
            "date_expiration": job.date_expiration,
            "pipeline":      pipeline,
            "manager":       {"id": manager.id, "email": manager.email} if manager else None,
        })

    return result


@router.get("/manager/dashboard")
def manager_dashboard(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("MANAGER"))
):
    """
    Dashboard Manager — seulement les jobs qui lui sont assignés.
    Infos job : titre, domaine, niveau, skills, description.
    Pas de scores de matching visibles.
    """
    # Récupérer les jobs assignés à ce Manager
    manager_jobs = db.query(models.ManagerJob).filter(
        models.ManagerJob.manager_id == current_user.id
    ).all()

    result = []
    for mj in manager_jobs:
        job = db.query(models.Job).filter(models.Job.id == mj.job_id).first()
        if not job:
            continue

        REJECTED_STATUSES = ["REJECTED_AUTO", "REJECTED_FINAL", "REJECTED", "MANAGER_REJECTED"]
        all_applications = db.query(models.Application).filter(
            models.Application.job_id == job.id,
        ).all()

        kpi = {
            "total":            len(all_applications),
            "rejected":         sum(1 for a in all_applications if a.status_v2 in REJECTED_STATUSES),
            "interviews_done":  sum(1 for a in all_applications if a.status_v2 == "INTERVIEW_DONE"),
            "pending_review":   sum(1 for a in all_applications if a.status_v2 in [
                "PRESELECTED", "INTERVIEW_ELIGIBLE", "INTERVIEW_SCHEDULED"
            ]),
        }

        # Candidats WAITING_MEET — score technique 50-69, en attente après test (cycle 2)
        waiting_meet_count = sum(1 for a in all_applications if a.status_v2 == "WAITING_MEET")

        # Candidats PENDING — score matching 50-69, n'ont pas passé le test (cycle 3)
        matched_count = sum(1 for a in all_applications if a.status_v2 == "PENDING")

        # expand_requested : RH a demandé d'élargir la sélection
        # expand_phase     : "cycle2" | "cycle3" | None
        #   cycle2 → WAITING_MEET > 0 (candidats après test, score technique moyen)
        #   cycle3 → WAITING_MEET = 0 ET PENDING > 0 (candidats phase matching)
        from app.models import ApplicationEvent as AppEvent
        expand_requested = False
        expand_phase     = None

        app_ids = [a.id for a in all_applications]

        if waiting_meet_count > 0:
            expand_event = db.query(AppEvent).filter(
                AppEvent.event == "EXPAND_REQUESTED",
                AppEvent.application_id.in_(app_ids),
            ).first()
            if expand_event:
                expand_requested = True
                expand_phase     = "cycle2"

        elif matched_count > 0:
            expand_event = db.query(AppEvent).filter(
                AppEvent.event == "EXPAND_REQUESTED",
                AppEvent.application_id.in_(app_ids),
            ).first()
            if expand_event:
                expand_requested = True
                expand_phase     = "cycle3"

        applications = [a for a in all_applications if a.status_v2 not in REJECTED_STATUSES]

        candidats = []
        for app in applications:
            # Récupérer le nom depuis CVProfile
            cv_profile = db.query(models.CVProfile).filter(
                models.CVProfile.application_id == app.id
            ).first()
            candidats.append({
                "application_id": app.id,
                "full_name":      cv_profile.full_name if cv_profile else app.candidate_email,
                "email":          app.candidate_email,
                "status_v2":      app.status_v2,
                # ❌ score_final non exposé au Manager
            })

        result.append({
            "id":               job.id,
            "title":            job.title,
            "department":       job.department,
            "location":         job.location,
            "level":            job.level,
            "skills_json":      job.skills_json,
            "bonus_skills":     job.bonus_skills,
            "description":      job.description,
            "status":           "open" if not job.closed_at else "closed",
            "kpi":              kpi,
            # expand_requested   : True si RH a demandé d'élargir
            # expand_phase       : "cycle2" | "cycle3" | None
            # waiting_meet_count : candidats WAITING_MEET (après test, score moyen)
            # matched_count      : candidats MATCHED (phase matching, pas encore testés)
            "expand_requested":    expand_requested,
            "expand_phase":        expand_phase,
            "waiting_meet_count":  waiting_meet_count,
            "matched_count":       matched_count,
            "candidats_preselectionnes": candidats,
        })

    return result


@router.get("/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db)):
    """Détail d'un job par ID."""
    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job non trouvé")
    return job


@router.patch("/{job_id}/close")
def close_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("RH"))
):
    """
    RH ferme un job → déclenche le timer RGPD (Point 7).
    closed_at = maintenant → n8n calculera les dates de suppression.
    """
    from datetime import datetime
    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job non trouvé")
    if job.closed_at:
        raise HTTPException(status_code=400, detail="Job déjà fermé")

    job.closed_at = datetime.utcnow()
    db.commit()
    return {"message": f"Job '{job.title}' fermé. Timer RGPD démarré."}