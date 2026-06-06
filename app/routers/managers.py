"""
managers.py — Router FastAPI pour la gestion des Managers (espace RH).

Endpoints :
  GET    /managers                        → liste tous les managers avec leurs jobs assignés
  POST   /managers/invite                 → inviter un nouveau manager (email only → n8n envoie le lien)
  GET    /managers/{manager_id}           → détail d'un manager + ses jobs
  GET    /managers/{manager_id}/jobs      → jobs assignés à un manager
  POST   /managers/{manager_id}/jobs      → assigner un job à un manager
  DELETE /managers/{manager_id}/jobs/{job_id} → désassigner un job d'un manager

Règles métier :
  - Un job ne peut avoir qu'un seul manager à la fois
  - Un manager ne voit que les jobs qui lui sont explicitement assignés
  - L'invitation passe par POST /auth/invite-manager (qui déclenche n8n)
  - RH uniquement pour tous les endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import List, Optional
from datetime import datetime

from app import models
from app.database import get_db
from app.routers.auth import require_role

router = APIRouter(prefix="/managers", tags=["Managers"])


# ============================================================
# SCHEMAS LOCAUX
# ============================================================

class InviteManagerPayload(BaseModel):
    """Payload RH pour inviter un manager — email uniquement."""
    email: EmailStr


class AssignJobPayload(BaseModel):
    """Payload pour assigner un job à un manager."""
    job_id: int


class JobSummary(BaseModel):
    """Résumé d'un job dans la réponse manager."""
    id:         int
    title:      str
    department: Optional[str] = None
    location:   Optional[str] = None
    status:     str   # "open" | "closed"

    class Config:
        from_attributes = True


class ManagerOut(BaseModel):
    """Réponse complète d'un manager."""
    id:           int
    email:        str
    is_active:    bool
    full_name:    Optional[str] = None
    poste:        Optional[str] = None
    created_at:   Optional[datetime] = None
    jobs_count:   int
    jobs:         List[JobSummary]

    class Config:
        from_attributes = True


# ============================================================
# HELPERS INTERNES
# ============================================================

def _build_manager_out(manager: models.User, db: Session) -> dict:
    """
    Construit le dict de réponse pour un manager :
    infos de base + liste de ses jobs assignés.
    """
    manager_jobs = db.query(models.ManagerJob).filter(
        models.ManagerJob.manager_id == manager.id
    ).all()

    jobs = []
    for mj in manager_jobs:
        job = db.query(models.Job).filter(models.Job.id == mj.job_id).first()
        if job:
            jobs.append({
                "id":         job.id,
                "title":      job.title,
                "department": job.department,
                "location":   job.location,
                "status":     "open" if not job.closed_at else "closed",
            })

    return {
        "id":          manager.id,
        "email":       manager.email,
        "is_active":   manager.is_active,
        "full_name":   getattr(manager, "full_name", None) or "",
        "poste":       getattr(manager, "poste",     None) or "",
        "created_at":  getattr(manager, "created_at", None),
        "jobs_count":  len(jobs),
        "jobs":        jobs,
    }


# ============================================================
# ENDPOINTS
# ============================================================

@router.get("", status_code=200)
def list_managers(
    db:           Session      = Depends(get_db),
    current_user: models.User  = Depends(require_role("RH")),
):
    """
    Liste tous les utilisateurs avec role=MANAGER.
    Pour chaque manager : statut (active/pending), nombre de jobs assignés,
    et la liste de ses jobs.
    Trié par date de création décroissante (plus récent en premier).
    """
    managers = (
        db.query(models.User)
        .filter(models.User.role == "MANAGER")
        .order_by(models.User.id.desc())
        .all()
    )

    return [_build_manager_out(m, db) for m in managers]


@router.post("/invite", status_code=201)
def invite_manager(
    payload:      InviteManagerPayload,
    db:           Session      = Depends(get_db),
    current_user: models.User  = Depends(require_role("RH")),
):
    """
    RH invite un nouveau manager par email.

    Flux :
      1. Vérifie que l'email n'est pas déjà utilisé
      2. Crée le compte User(role=MANAGER, is_active=False)
      3. Génère un token d'invitation unique (24h)
      4. Appelle le webhook n8n → n8n envoie l'email avec le lien setup-password
      RH ne voit jamais le mot de passe.
    """
    import uuid, secrets
    import httpx
    import os

    # 1. Email déjà utilisé ?
    existing = db.query(models.User).filter(
        models.User.email == payload.email
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Un compte avec cet email existe déjà"
        )

    # 2. Créer le compte Manager sans mot de passe utilisable
    from app.routers.auth import hash_password
    new_manager = models.User(
        email=payload.email,
        hashed_password=hash_password(secrets.token_hex(32)),  # hash aléatoire — inutilisable
        role="MANAGER",
        is_active=False,  # activé seulement après setup-password
    )
    db.add(new_manager)
    db.commit()
    db.refresh(new_manager)

    # 3. Générer le token d'invitation (24h)
    token = str(uuid.uuid4())
    invitation = models.InvitationToken(
        token=token,
        user_id=new_manager.id,
        expires_at=datetime.utcnow() + __import__("datetime").timedelta(hours=24),
        used=False,
    )
    db.add(invitation)
    db.commit()

    # 4. Appel webhook n8n → envoie email au manager
    n8n_url = os.getenv(
        "N8N_INVITE_WEBHOOK",
        "http://localhost:5678/webhook/invite-manager"
    )
    setup_link = f"{os.getenv('FRONTEND_URL', 'http://localhost:5173')}/setup-password?token={token}"

    try:
        httpx.post(
            n8n_url,
            json={
                "manager_email": payload.email,
                "setup_link":    setup_link,
            },
            timeout=5,
        )
    except Exception:
        # n8n indisponible → on ne bloque pas l'invitation, le compte est créé
        pass

    return {
        "message":    f"Invitation envoyée à {payload.email}",
        "manager_id": new_manager.id,
        "email":      payload.email,
        "is_active":  False,
        # setup_link retourné uniquement en développement — à masquer en prod
        "setup_link": setup_link if os.getenv("ENV", "dev") == "dev" else None,
    }


@router.get("/{manager_id}", status_code=200)
def get_manager(
    manager_id:   int,
    db:           Session      = Depends(get_db),
    current_user: models.User  = Depends(require_role("RH")),
):
    """Détail d'un manager par ID + ses jobs assignés."""
    manager = db.query(models.User).filter(
        models.User.id   == manager_id,
        models.User.role == "MANAGER",
    ).first()

    if not manager:
        raise HTTPException(status_code=404, detail="Manager non trouvé")

    return _build_manager_out(manager, db)


@router.get("/{manager_id}/jobs", status_code=200)
def get_manager_jobs(
    manager_id:   int,
    db:           Session      = Depends(get_db),
    current_user: models.User  = Depends(require_role("RH")),
):
    """
    Liste les jobs assignés à un manager spécifique,
    avec le résumé pipeline pour chaque job.
    """
    manager = db.query(models.User).filter(
        models.User.id   == manager_id,
        models.User.role == "MANAGER",
    ).first()
    if not manager:
        raise HTTPException(status_code=404, detail="Manager non trouvé")

    manager_jobs = db.query(models.ManagerJob).filter(
        models.ManagerJob.manager_id == manager_id
    ).all()

    result = []
    for mj in manager_jobs:
        job = db.query(models.Job).filter(models.Job.id == mj.job_id).first()
        if not job:
            continue

        # Pipeline résumé
        applications = db.query(models.Application).filter(
            models.Application.job_id == job.id
        ).all()

        result.append({
            "id":         job.id,
            "title":      job.title,
            "department": job.department,
            "location":   job.location,
            "status":     "open" if not job.closed_at else "closed",
            "pipeline": {
                "total":      len(applications),
                "acceptes":   sum(1 for a in applications if a.status_v2 == "ACCEPTED"),
                "rejetes":    sum(1 for a in applications if a.status_v2 in ["REJECTED_AUTO", "REJECTED_FINAL"]),
                "en_attente": sum(1 for a in applications if a.status_v2 in ["APPLIED", "MATCHED", "EN_ATTENTE"]),
            },
        })

    return result


@router.post("/{manager_id}/jobs", status_code=201)
def assign_job(
    manager_id:   int,
    payload:      AssignJobPayload,
    db:           Session      = Depends(get_db),
    current_user: models.User  = Depends(require_role("RH")),
):
    """
    Assigne un job à un manager.

    Règles :
      - Le job doit exister et être ouvert
      - Le job ne doit pas déjà avoir un manager assigné
      - Un manager peut avoir plusieurs jobs
    """
    # Vérifier le manager
    manager = db.query(models.User).filter(
        models.User.id   == manager_id,
        models.User.role == "MANAGER",
    ).first()
    if not manager:
        raise HTTPException(status_code=404, detail="Manager non trouvé")

    # Vérifier le job
    job = db.query(models.Job).filter(models.Job.id == payload.job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job non trouvé")
    if job.closed_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Impossible d'assigner un job fermé"
        )

    # Vérifier que ce job n'a pas déjà un manager
    existing_assignment = db.query(models.ManagerJob).filter(
        models.ManagerJob.job_id == payload.job_id
    ).first()
    if existing_assignment:
        if existing_assignment.manager_id == manager_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ce job est déjà assigné à ce manager"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ce job est déjà assigné à un autre manager — désassignez-le d'abord"
            )

    # Créer l'assignation
    new_assignment = models.ManagerJob(
        manager_id=manager_id,
        job_id=payload.job_id,
    )
    db.add(new_assignment)
    db.commit()

    return {
        "message":    f"Job « {job.title} » assigné à {manager.email}",
        "manager_id": manager_id,
        "job_id":     payload.job_id,
    }


@router.delete("/{manager_id}/jobs/{job_id}", status_code=200)
def unassign_job(
    manager_id:   int,
    job_id:       int,
    db:           Session      = Depends(get_db),
    current_user: models.User  = Depends(require_role("RH")),
):
    """
    Désassigne un job d'un manager.
    Le manager perd immédiatement l'accès à ce job.
    """
    # Vérifier le manager
    manager = db.query(models.User).filter(
        models.User.id   == manager_id,
        models.User.role == "MANAGER",
    ).first()
    if not manager:
        raise HTTPException(status_code=404, detail="Manager non trouvé")

    # Trouver l'assignation
    assignment = db.query(models.ManagerJob).filter(
        models.ManagerJob.manager_id == manager_id,
        models.ManagerJob.job_id     == job_id,
    ).first()
    if not assignment:
        raise HTTPException(
            status_code=404,
            detail="Ce job n'est pas assigné à ce manager"
        )

    job = db.query(models.Job).filter(models.Job.id == job_id).first()

    db.delete(assignment)
    db.commit()

    return {
        "message":    f"Job « {job.title if job else job_id} » désassigné de {manager.email}",
        "manager_id": manager_id,
        "job_id":     job_id,
    }