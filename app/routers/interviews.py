from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app import models, schemas
from app.database import get_db
from app.routers.auth import require_role, get_current_user
from datetime import datetime, timedelta
from typing import List, Optional
from pydantic import BaseModel
import uuid
import os
import base64
import requests as http_requests
from datetime import timezone
from sqlalchemy import func, text


# ============================================================
# ZOOM MEET — Server-to-Server OAuth
# ============================================================

ZOOM_ACCOUNT_ID    = "jjsmAeUxSh-0cpKV6JQhjw"
ZOOM_CLIENT_ID     = "TmfVkG_SJagopJIXmwR7w"
ZOOM_CLIENT_SECRET = "FX6VoakDNfl44V9MAjxg0wDsqr8UhaAN"  # ← remplace par ton vrai secret

def generate_meet_link(start_datetime: datetime, end_datetime: datetime, title: str = "Entretien Dynamix") -> str:
    """Génère un lien Zoom via Server-to-Server OAuth — pas d'OAuth2 utilisateur, jamais d'expiration."""
    try:
        # 1. Obtenir le token Zoom
        credentials = base64.b64encode(f"{ZOOM_CLIENT_ID}:{ZOOM_CLIENT_SECRET}".encode()).decode()
        token_response = http_requests.post(
            f"https://zoom.us/oauth/token?grant_type=account_credentials&account_id={ZOOM_ACCOUNT_ID}",
            headers={"Authorization": f"Basic {credentials}"}
        )
        token_data = token_response.json()
        if "access_token" not in token_data:
            print(f"[ZOOM] Erreur token: {token_data}")
            return ""

        access_token = token_data["access_token"]

        # 2. Créer la réunion Zoom
        duration = int((end_datetime - start_datetime).total_seconds() / 60)
        meeting_response = http_requests.post(
            "https://api.zoom.us/v2/users/me/meetings",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            },
            json={
                "topic"      : title,
                "type"       : 2,
                "start_time" : start_datetime.strftime("%Y-%m-%dT%H:%M:%S"),
                "duration"   : duration,
                "timezone"   : "Africa/Tunis",
                "settings"   : {
                    "join_before_host"  : True,
                    "waiting_room"      : False,
                    "host_video"        : True,
                    "participant_video" : True,
                }
            }
        )
        meeting_data = meeting_response.json()
        if "join_url" not in meeting_data:
            print(f"[ZOOM] Error creating meeting: {meeting_data}")
            return ""

        join_url = meeting_data["join_url"]
        print(f"[ZOOM] Link generated: {join_url}")
        return join_url

    except Exception as e:
        print(f"[ZOOM] Erreur: {e}")
        return ""


router = APIRouter(prefix="/interviews", tags=["Interviews"])


# ============================================================
# SCHEMAS LOCAUX
# ============================================================

class SlotCreate(BaseModel):
    job_id    : int
    datetime  : datetime
    meet_link : str


class SlotResponse(BaseModel):
    id           : int
    job_id       : int
    datetime     : datetime
    meet_link    : str
    is_available : bool

    class Config:
        from_attributes = True


class BookingInput(BaseModel):
    token   : str
    slot_id : int


class DashboardSlotCreate(BaseModel):
    date       : str
    start_time : str
    end_time   : str
    meet_link  : str = ""
    job_id     : Optional[int] = None


class DashboardSlotResponse(BaseModel):
    id              : int
    job_id          : Optional[int] = None
    job_title       : Optional[str] = None   # ← ajouté
    date            : str
    start_time      : str
    end_time        : str
    status          : str
    candidate_name  : Optional[str] = None
    candidate_email : Optional[str] = None
    meet_link       : Optional[str] = None

    class Config:
        from_attributes = True


class BookCandidateInput(BaseModel):
    candidate_name  : str
    candidate_email : str


class InterviewCreate(BaseModel):
    candidate_name   : str
    candidate_email  : str
    role             : str
    round            : str
    scheduled_at     : datetime
    duration_minutes : int = 60
    meeting_link     : Optional[str] = None
    notes            : Optional[str] = None


class InterviewUpdate(BaseModel):
    status           : Optional[str] = None
    meeting_link     : Optional[str] = None
    notes            : Optional[str] = None
    scheduled_at     : Optional[datetime] = None
    duration_minutes : Optional[int] = None


# ============================================================
# ENDPOINTS MANAGER — CRÉNEAUX PIPELINE
# ============================================================

@router.post("/slots", response_model=SlotResponse)
def create_slot(
    payload: SlotCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("MANAGER"))
):
    manager_job = db.query(models.ManagerJob).filter(
        models.ManagerJob.manager_id == current_user.id,
        models.ManagerJob.job_id == payload.job_id
    ).first()
    if not manager_job:
        raise HTTPException(status_code=403, detail="You are not assigned to this job")

    slot = models.InterviewSlot(
        job_id       = payload.job_id,
        manager_id   = current_user.id,
        datetime     = payload.datetime,
        meet_link    = payload.meet_link,
        is_available = True
    )
    db.add(slot)
    db.commit()
    db.refresh(slot)
    return slot


@router.get("/calendar/{job_id}")
def get_calendar(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("MANAGER"))
):
    slots = db.query(models.InterviewSlot).filter(
        models.InterviewSlot.job_id     == job_id,
        models.InterviewSlot.manager_id == current_user.id
    ).order_by(models.InterviewSlot.datetime).all()

    result = []
    for slot in slots:
        candidat = None
        if slot.application_id:
            app = db.query(models.Application).filter(models.Application.id == slot.application_id).first()
            cv  = db.query(models.CVProfile).filter(models.CVProfile.application_id == slot.application_id).first()
            candidat = {
                "application_id" : slot.application_id,
                "email"          : app.candidate_email if app else None,
                "full_name"      : cv.full_name if cv else "N/A",
                "interview_done" : slot.interview_done
            }
        result.append({
            "slot_id"      : slot.id,
            "datetime"     : slot.datetime,
            "meet_link"    : slot.meet_link,
            "is_available" : slot.is_available,
            "candidat"     : candidat
        })
    return result


@router.patch("/slots/{slot_id}/done")
def mark_interview_done(
    slot_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("MANAGER"))
):
    slot = db.query(models.InterviewSlot).filter(
        models.InterviewSlot.id         == slot_id,
        models.InterviewSlot.manager_id == current_user.id
    ).first()
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")
    if not slot.application_id:
        raise HTTPException(status_code=400, detail="No candidate booked on this slot")

    slot.interview_done = True
    app = db.query(models.Application).filter(models.Application.id == slot.application_id).first()
    if app:
        app.status_v2 = "INTERVIEW_DONE"
    db.commit()
    return {"message": "Interview marked as completed", "slot_id": slot_id}


# ============================================================
# ENDPOINTS CANDIDAT — RÉSERVATION
# ============================================================

@router.get("/slots/available/{job_id}")
def get_available_slots(job_id: int, token: str, db: Session = Depends(get_db)):
    booking_token = db.query(models.BookingToken).filter(
        models.BookingToken.token  == token,
        models.BookingToken.job_id == job_id
    ).first()
    if not booking_token:
        raise HTTPException(status_code=404, detail="Invalid link")
    if booking_token.used:
        raise HTTPException(status_code=400, detail="Link already used")
    if booking_token.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Link expired")

    slots = db.query(models.Interview).filter(
        models.Interview.job_id == job_id, 
        models.Interview.status == "available"
    ).order_by(models.Interview.scheduled_at).all()

    return [{"slot_id": slot.id, "datetime": slot.scheduled_at, "is_available": True} for slot in slots]


@router.post("/book")
def book_slot(payload: BookingInput, db: Session = Depends(get_db)):
    booking_token = db.query(models.BookingToken).filter(models.BookingToken.token == payload.token).first()
    if not booking_token:
        raise HTTPException(status_code=404, detail="Invalid link")
    if booking_token.used:
        raise HTTPException(status_code=400, detail="Link already used")
    if booking_token.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Link expired")

    # Récupérer infos candidat avant de chercher le slot
    app = db.query(models.Application).filter(models.Application.id == booking_token.application_id).first()
    cv = db.query(models.CVProfile).filter(models.CVProfile.application_id == booking_token.application_id).first()
    candidate_name  = cv.full_name if cv else (app.candidate_email if app else "")
    candidate_email = app.candidate_email if app else ""

    # Chercher dans Interview (même table que /public/slots)
    slot = db.query(models.Interview).filter(
        models.Interview.id     == payload.slot_id,
        models.Interview.job_id == booking_token.job_id,
        models.Interview.status == "available"
    ).first()
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found or already booked")

    # Réserver le créneau
    slot.status          = "booked"
    slot.candidate_name  = candidate_name
    slot.candidate_email = candidate_email

    # Mettre à jour le statut candidat
    if app:
        app.status_v2 = "INTERVIEW_SCHEDULED"

    # Marquer le token comme utilisé
    booking_token.used = True

    db.commit()
    return {"message": "Slot booked successfully!", "datetime": slot.scheduled_at, "meet_link": slot.meeting_link, "email": candidate_email}


# ============================================================
# ENDPOINT RH — GÉNÉRER BOOKING TOKENS
# ============================================================

@router.post("/generate-booking-tokens/{job_id}")
def generate_booking_tokens(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("MANAGER"))
):
    """
    Génère un token de réservation pour chaque candidat MEET_PENDING (score fort >= 70).
    Appelé depuis le dashboard Manager quand il clique "Envoyer les invitations".
    Les candidats WAITING_MEET (score 50-69) ne reçoivent pas de lien.
    """
    preselected = db.query(models.Application).filter(
        models.Application.job_id    == job_id,
        models.Application.status_v2 == "MEET_PENDING"
    ).all()
    if not preselected:
        raise HTTPException(
            status_code=404,
            detail="No eligible candidates (MEET_PENDING) for this job"
        )

    # Calculer la date d'expiration = dernier créneau FUTUR disponible du job
    now_utc = datetime.now(timezone.utc)

    last_slot = db.query(models.Interview).filter(
        models.Interview.job_id    == job_id,
        models.Interview.status    == "available",
        models.Interview.scheduled_at > now_utc
    ).order_by(models.Interview.scheduled_at.desc()).first()

    expires_at = last_slot.scheduled_at if last_slot else datetime.now(timezone.utc) + timedelta(days=2)


    tokens_created = []
    job            = db.query(models.Job).filter(models.Job.id == job_id).first()
    job_title      = job.title if job else ""

    for app in preselected:
        cv             = db.query(models.CVProfile).filter(models.CVProfile.application_id == app.id).first()
        candidate_name = cv.full_name if cv else app.candidate_email

        existing = db.query(models.BookingToken).filter(
            models.BookingToken.application_id == app.id,
            models.BookingToken.used == False
        ).first()
        if existing:
            if existing.expires_at < datetime.now(timezone.utc):
                # Token expiré → supprimer et créer un nouveau
                db.delete(existing)
                db.flush()
            else:
                # Token encore valide → mettre à jour expires_at
                existing.expires_at = expires_at
                tokens_created.append({
                    "application_id"  : app.id,
                    "candidate_email" : app.candidate_email,
                    "candidate_name"  : candidate_name,
                    "job_title"       : job_title,
                    "token"           : existing.token,
                    "link"            : f"http://localhost:5173/booking?token={existing.token}&job_id={job_id}",
                    "expires_at"      : existing.expires_at
                })
                continue

        token = models.BookingToken(
            token          = str(uuid.uuid4()),
            application_id = app.id,
            job_id         = job_id,
            expires_at     = expires_at,
            used           = False
        )
        db.add(token)
        app.slot_offered_at = datetime.utcnow()
        app.slot_expires_at = expires_at
        tokens_created.append({
            "application_id"  : app.id,
            "candidate_email" : app.candidate_email,
            "candidate_name"  : candidate_name,
            "job_title"       : job_title,
            "token"           : token.token,
            "link"            : f"http://localhost:5173/booking?token={token.token}&job_id={job_id}",
            "expires_at"      : token.expires_at
        })

    db.commit()
    return {"message": f"{len(tokens_created)} token(s) generated", "tokens": tokens_created}


# ============================================================
# ENDPOINT N8N — TOKENS EXPIRÉS SANS RÉSERVATION
# ============================================================

@router.get("/booking-tokens/expired")
def get_expired_tokens(db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)

    expired_tokens = db.query(models.BookingToken).filter(
        models.BookingToken.used       == False,
        models.BookingToken.expires_at <= now,
    ).all()

    result = []
    for token in expired_tokens:
        app = db.query(models.Application).filter(
            models.Application.id == token.application_id
        ).first()
        if not app:
            continue

        if app.status_v2 in ["REJECTED_AUTO", "REJECTED_FINAL", "INTERVIEW_SCHEDULED"]:
            continue

        cv = db.query(models.CVProfile).filter(
            models.CVProfile.application_id == token.application_id
        ).first()

        job = db.query(models.Job).filter(
            models.Job.id == token.job_id
        ).first()

        result.append({
            "token_id"        : token.id,
            "application_id"  : token.application_id,
            "candidate_email" : app.candidate_email,
            "candidate_name"  : cv.full_name if cv else app.candidate_email,
            "job_title"       : job.title if job else "—",
            "job_id"          : token.job_id,
            "expires_at"      : token.expires_at,
        })

    return {"count": len(result), "expired": result}


@router.patch("/booking-tokens/{token_id}/reject")
def reject_expired_candidate(
    token_id : int,
    db       : Session = Depends(get_db),
):
    token = db.query(models.BookingToken).filter(
        models.BookingToken.id == token_id
    ).first()
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")

    app = db.query(models.Application).filter(
        models.Application.id == token.application_id
    ).first()
    if app:
        app.status_v2 = "REJECTED_AUTO"

    # Marquer le token comme utilisé pour ne plus le retrouver
    token.used = True

    db.commit()
    return {"message": "Candidate rejected", "application_id": token.application_id}


# ============================================================
# ENDPOINT N8N — ABSENCES À L'ENTRETIEN (NO-SHOW)
# ⚠️ Doit rester AVANT tous les /slots/{slot_id}/... pour éviter conflit de route
# ============================================================

@router.get("/slots/no-show")
def get_no_show_slots(db: Session = Depends(get_db)):
    """
    Appelé toutes les heures par n8n (Schedule Trigger).
    Retourne les créneaux "booked" dont scheduled_at est dépassé
    et qui concernent UNIQUEMENT la phase d'évaluation technique (round != "HR Round").

    n8n appelle cet endpoint puis pour chaque résultat :
      - PATCH /interviews/slots/{slot_id}/absent  → marque NO_SHOW + libère le créneau
      - Envoie un email au candidat l'informant de son absence

    Idempotent : les candidats déjà traités sont exclus du résultat pour éviter les doublons.

    Fix 1 — round != "HR Round" :
      Exclut les créneaux "Présentiel RH" (phase finale RH) du workflow no-show.
      Ce workflow ne concerne que la phase d'évaluation technique manager.

    Fix 2 — statuts étendus :
      Exclut les candidats dont la décision manager a déjà été soumise
      (ACCEPTED = "Validate"), même si
      un ancien slot technique est encore "booked" et non nettoyé.
    """
    now = datetime.now(timezone.utc)

    # Fix 1 : exclure les créneaux RH (round = "HR Round")
    slots = db.query(models.Interview).filter(
        models.Interview.status         == "booked",
        models.Interview.scheduled_at < func.now() - text("INTERVAL '5 minutes'"),
        models.Interview.round          != "HR Round",
    ).all()

    # Fix 2 : statuts exclus étendus
    EXCLUDED_STATUSES = [
        "NO_SHOW",  # déjà rejeté par ce workflow
        "INTERVIEW_DONE",    # entretien marqué fait
        "HIRED",             # embauché (statut final RH)
        "REJECTED_FINAL",    # rejeté définitivement (NON_RETENU)
        "POSITION_FILLED",   # poste pourvu
        "ACCEPTED",          # validé par manager (VALIDÉ → passe au RH)
    ]

    result = []
    for slot in slots:
        # Vérifier si l'application est déjà traitée
        app = db.query(models.Application).filter(
            models.Application.candidate_email == slot.candidate_email
        ).first()

        if app and app.status_v2 in EXCLUDED_STATUSES:
            continue

        job = None
        if slot.job_id:
            job = db.query(models.Job).filter(models.Job.id == slot.job_id).first()

        result.append({
            "slot_id"         : slot.id,
            "candidate_email" : slot.candidate_email,
            "candidate_name"  : slot.candidate_name or slot.candidate_email,
            "job_title"       : job.title if job else "—",
            "job_id"          : slot.job_id,
            "scheduled_at"    : slot.scheduled_at.isoformat() if slot.scheduled_at else None,
        })

    return {"count": len(result), "no_shows": result}


# ============================================================
# ENDPOINTS PUBLIC CANDIDAT — CALENDRIER BOOKING
# ============================================================

@router.get("/public/slots", response_model=List[DashboardSlotResponse])
def list_public_slots(
    month: Optional[str] = Query(None, description="Format YYYY-MM"),
    job_id: Optional[int] = Query(None, description="Filtrer par job (obligatoire pour le candidat)"),
    db: Session = Depends(get_db),
):
    if not job_id:
        raise HTTPException(status_code=400, detail="job_id is required")
    q = db.query(models.Interview).filter(
        models.Interview.status == "available",
        models.Interview.job_id == job_id,
    ).order_by(models.Interview.scheduled_at)
    if month:
        year, mon = month.split("-")
        from sqlalchemy import extract
        q = q.filter(
            extract("year",  models.Interview.scheduled_at) == int(year),
            extract("month", models.Interview.scheduled_at) == int(mon),
        )
    rows = q.all()
    result = []
    for r in rows:
        dt: datetime = r.scheduled_at
        result.append({
            "id"              : r.id,
            "date"            : dt.strftime("%Y-%m-%d"),
            "start_time"      : dt.strftime("%H:%M"),
            "end_time"        : _add_minutes(dt, r.duration_minutes).strftime("%H:%M"),
            "status"          : "available",
            "candidate_name"  : None,
            "candidate_email" : None,
        })
    return result


@router.patch("/dashboard/slots/{slot_id}/cancel", status_code=200)
def cancel_dashboard_slot(
    slot_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("MANAGER", "RH"))
):
    """
    Annule un créneau — le status passe à 'cancelled'.
    Le candidat reste assigné mais l'entretien est marqué annulé.
    """
    row = db.query(models.Interview).filter(
        models.Interview.id == slot_id
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Slot not found")
    if row.status == "cancelled":
        raise HTTPException(status_code=400, detail="Slot already cancelled")

    row.status = "cancelled"
    db.commit()
    return {"message": "Slot cancelled", "slot_id": slot_id}



def book_dashboard_slot(
    slot_id: int,
    body: BookCandidateInput,
    db: Session = Depends(get_db),
):
    row = db.query(models.Interview).filter(
        models.Interview.id     == slot_id,
        models.Interview.status == "available",
    ).first()
    if not row:
        raise HTTPException(status_code=409, detail="This slot is no longer available or does not exist.")

    row.candidate_name  = body.candidate_name
    row.candidate_email = body.candidate_email
    row.status          = "booked"
    db.commit()

    dt: datetime = row.scheduled_at
    return {
        "message"    : "Slot booked successfully!",
        "slot_id"    : slot_id,
        "date"       : dt.strftime("%Y-%m-%d"),
        "start_time" : dt.strftime("%H:%M"),
        "end_time"   : _add_minutes(dt, row.duration_minutes).strftime("%H:%M"),
        "meet_link"  : row.meeting_link,
    }


# ============================================================
# ENDPOINTS DASHBOARD SCHEDULER — MANAGER/RH
# ============================================================

@router.get("/dashboard/slots", response_model=List[DashboardSlotResponse])
def list_dashboard_slots(
    month: Optional[str] = Query(None, description="Format YYYY-MM"),
    status: Optional[str] = Query(None, description="available | booked"),
    job_id: Optional[int] = Query(None, description="Filtrer par job"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("MANAGER", "RH"))
):
    # Un manager ne doit voir/interroger que les jobs qui lui sont assignés.
    manager_job_ids = None
    if current_user.role == "MANAGER":
        manager_job_ids = [
            mj.job_id for mj in db.query(models.ManagerJob)
            .filter(models.ManagerJob.manager_id == current_user.id).all()
        ]
        if job_id is not None and job_id not in manager_job_ids:
            raise HTTPException(status_code=403, detail="You are not assigned to this job")

    q = db.query(models.Interview).order_by(models.Interview.scheduled_at)
    if manager_job_ids is not None:
        q = q.filter(models.Interview.job_id.in_(manager_job_ids))
    if month:
        year, mon = month.split("-")
        from sqlalchemy import extract
        q = q.filter(
            extract("year",  models.Interview.scheduled_at) == int(year),
            extract("month", models.Interview.scheduled_at) == int(mon),
        )
    if status:
        q = q.filter(models.Interview.status == status)
    if job_id:
        q = q.filter(models.Interview.job_id == job_id)

    rows = q.all()
    result = []
    for r in rows:
        dt: datetime = r.scheduled_at
        # Récupérer le titre du job directement depuis job_id
        job_title = None
        if r.job_id:
            job = db.query(models.Job).filter(models.Job.id == r.job_id).first()
            if job:
                job_title = job.title

        result.append({
            "id"              : r.id,
            "job_id"          : r.job_id,
            "date"            : dt.strftime("%Y-%m-%d"),
            "start_time"      : dt.strftime("%H:%M"),
            "end_time"        : _add_minutes(dt, r.duration_minutes).strftime("%H:%M"),
            "status"          : r.status if r.status in ("available", "booked") else "available",
            "candidate_name"  : r.candidate_name,
            "candidate_email" : r.candidate_email,
            "meet_link"       : r.meeting_link or None,
            "job_title"       : job_title,
        })
    return result


@router.post("/dashboard/slots", response_model=DashboardSlotResponse, status_code=201)
def create_dashboard_slot(
    body: DashboardSlotCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("MANAGER", "RH"))
):
    """Crée un créneau et génère automatiquement un lien Zoom."""
    # ⚠️ scheduled_at reste NAIVE volontairement — ne pas ajouter tzinfo=timezone.utc ici.
    # Interview.scheduled_at est un TIMESTAMPTZ : Postgres interprète un datetime naive
    # comme étant déjà dans la timezone de session (locale), donc l'heure tapée par le
    # manager est stockée et relue telle quelle, sans décalage. Taguer explicitement UTC
    # ferait convertir Postgres (+1h avec une session en Africa/Tunis) → bug de décalage.
    scheduled_at = datetime.strptime(f"{body.date} {body.start_time}", "%Y-%m-%d %H:%M")

    if scheduled_at.date() < datetime.utcnow().date():
        raise HTTPException(status_code=400, detail="Cannot schedule a slot in the past.")

    start_dt = datetime.strptime(body.start_time, "%H:%M")
    end_dt   = datetime.strptime(body.end_time,   "%H:%M")
    duration = int((end_dt - start_dt).total_seconds() / 60)

    if duration <= 0:
        raise HTTPException(status_code=400, detail="End time must be after start time.")
    duration = max(duration, 15)

    # ── Vérification conflit horaire par job : pas deux slots qui se chevauchent pour le même job ──
    # Fix 1 : on compare l'intervalle réel de CHAQUE créneau existant (sa propre duration_minutes)
    # à l'intervalle du nouveau créneau, au lieu d'appliquer la durée du nouveau créneau à tout le monde.
    # Fix 2 : on exclut les créneaux annulés — un slot "cancelled" ne doit plus bloquer une création.
    end_scheduled = scheduled_at + timedelta(minutes=duration)
    from sqlalchemy import func as sqlfunc

    same_day_q = db.query(models.Interview).filter(
        sqlfunc.date(models.Interview.scheduled_at) == scheduled_at.date(),
        models.Interview.status != "cancelled",
    )
    if body.job_id:
        same_day_q = same_day_q.filter(models.Interview.job_id == body.job_id)

    existing = None
    for row in same_day_q.all():
        # row.scheduled_at revient toujours aware depuis Postgres (TIMESTAMPTZ), même si
        # l'insertion était naive → on retire juste le tzinfo pour comparer en Python,
        # sans jamais réécrire ni convertir la valeur stockée.
        row_scheduled = row.scheduled_at.replace(tzinfo=None) if row.scheduled_at.tzinfo else row.scheduled_at
        row_end = row_scheduled + timedelta(minutes=row.duration_minutes)
        if row_scheduled < end_scheduled and row_end > scheduled_at:
            existing = row
            break

    if existing:
        existing_scheduled = existing.scheduled_at.replace(tzinfo=None) if existing.scheduled_at.tzinfo else existing.scheduled_at
        existing_end = existing_scheduled + timedelta(minutes=existing.duration_minutes)
        raise HTTPException(
            status_code=409,
            detail=(
                f"Conflict: a slot already exists on {body.date} "
                f"from {existing.scheduled_at.strftime('%H:%M')} to {existing_end.strftime('%H:%M')}."
            )
        )
    # ─────────────────────────────────────────────────────────

    # ── Génération automatique du lien Zoom ──────────────────
    end_datetime = scheduled_at + timedelta(minutes=duration)
    meet_link = generate_meet_link(scheduled_at, end_datetime)
    # ─────────────────────────────────────────────────────────

    interview = models.Interview(
        job_id           = body.job_id,
        candidate_name   = "",
        candidate_email  = "",
        role             = "TBD",
        round            = "TBD",
        scheduled_at     = scheduled_at,
        duration_minutes = duration,
        status           = "available",
        meeting_link     = meet_link or body.meet_link or None,
    )
    db.add(interview)
    db.commit()
    db.refresh(interview)

    return {
        "id"              : interview.id,
        "job_id"          : interview.job_id,
        "date"            : body.date,
        "start_time"      : body.start_time,
        "end_time"        : body.end_time,
        "status"          : "available",
        "candidate_name"  : None,
        "candidate_email" : None,
        "meet_link"       : interview.meeting_link,
    }


@router.delete("/dashboard/slots/{slot_id}", status_code=204)
def delete_dashboard_slot(
    slot_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("MANAGER", "RH"))
):
    row = db.query(models.Interview).filter(models.Interview.id == slot_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Slot not found")
    db.delete(row)
    db.commit()


@router.patch("/dashboard/slots/{slot_id}/cancel-booking", status_code=200)
def cancel_dashboard_booking(
    slot_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("MANAGER", "RH"))
):
    """Annule la réservation d'un slot : remet le créneaau disponible et réinitialise le candidat."""
    row = db.query(models.Interview).filter(models.Interview.id == slot_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Slot not found")
    if row.status != "booked":
        raise HTTPException(status_code=400, detail="This slot is not booked.")

    # Remettre le candidat en PRESELECTED si on trouve son application
    if row.candidate_email:
        app = db.query(models.Application).filter(
            models.Application.candidate_email == row.candidate_email
        ).first()
        if app and app.status_v2 == "INTERVIEW_SCHEDULED":
            app.status_v2 = "PRESELECTED"

    # Libérer le slot
    row.status          = "available"
    row.candidate_name  = ""
    row.candidate_email = ""
    row.meeting_link    = None

    db.commit()
    return {"message": "Booking cancelled, slot released.", "slot_id": slot_id}


# ============================================================
# ENDPOINTS INTERVIEW DASHBOARD — MANAGER/RH
# ============================================================

@router.get("/dashboard/interviews/summary")
def get_interview_summary(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("MANAGER", "RH"))
):
    rows = db.query(models.Interview).filter(models.Interview.candidate_name != "").all()
    return {
        "total"           : len(rows),
        "scheduled"       : sum(1 for r in rows if r.status == "scheduled"),
        "completed"       : sum(1 for r in rows if r.status == "completed"),
        "cancelled"       : sum(1 for r in rows if r.status == "cancelled"),
        "available_slots" : db.query(models.Interview).filter(models.Interview.status == "available").count(),
    }


@router.get("/dashboard/interviews")
def list_interviews(
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("MANAGER", "RH"))
):
    q = db.query(models.Interview).filter(models.Interview.candidate_name != "")
    if status:
        q = q.filter(models.Interview.status == status)
    return q.order_by(models.Interview.scheduled_at).all()


@router.post("/dashboard/interviews", status_code=201)
def create_interview(
    body: InterviewCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("MANAGER", "RH"))
):
    interview = models.Interview(
        candidate_name   = body.candidate_name,
        candidate_email  = body.candidate_email,
        role             = body.role,
        round            = body.round,
        scheduled_at     = body.scheduled_at,
        duration_minutes = body.duration_minutes,
        status           = "scheduled",
        meeting_link     = body.meeting_link,
        notes            = body.notes,
    )
    db.add(interview)
    db.commit()
    db.refresh(interview)
    return interview


@router.patch("/dashboard/interviews/{interview_id}")
def update_interview(
    interview_id: int,
    body: InterviewUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("MANAGER", "RH"))
):
    row = db.query(models.Interview).filter(models.Interview.id == interview_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Interview not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/dashboard/interviews/{interview_id}", status_code=204)
def delete_interview(
    interview_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("MANAGER", "RH"))
):
    row = db.query(models.Interview).filter(models.Interview.id == interview_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Interview not found")
    db.delete(row)
    db.commit()


# ============================================================
# ENDPOINTS N8N → SAUVEGARDE MEET LINK
# ============================================================

class SaveMeetLinkInput(BaseModel):
    meet_link       : str
    candidate_name  : Optional[str] = None
    candidate_email : Optional[str] = None
    slot_date       : Optional[str] = None
    slot_time       : Optional[str] = None


@router.post("/slots/{slot_id}/save-meet-link", status_code=200)
def save_meet_link(
    slot_id : int,
    body    : SaveMeetLinkInput,
    db      : Session = Depends(get_db),
):
    row = db.query(models.Interview).filter(models.Interview.id == slot_id).first()

    if not row:
        if body.slot_date and body.slot_time:
            try:
                target_dt = datetime.strptime(f"{body.slot_date} {body.slot_time}", "%Y-%m-%d %H:%M")
                from sqlalchemy import func as sqlfunc
                row = db.query(models.Interview).filter(
                    sqlfunc.date(models.Interview.scheduled_at) == target_dt.date(),
                    sqlfunc.extract("hour",   models.Interview.scheduled_at) == target_dt.hour,
                    sqlfunc.extract("minute", models.Interview.scheduled_at) == target_dt.minute,
                ).first()
            except ValueError:
                pass

    if not row:
        raise HTTPException(status_code=404, detail="Slot not found.")

    row.meeting_link = body.meet_link
    if body.candidate_name:
        row.candidate_name  = body.candidate_name
    if body.candidate_email:
        row.candidate_email = body.candidate_email

    if body.slot_date and body.slot_time:
        try:
            target_dt = datetime.strptime(f"{body.slot_date} {body.slot_time}", "%Y-%m-%d %H:%M")
            from sqlalchemy import func as sqlfunc2
            legacy_slot = db.query(models.InterviewSlot).filter(
                sqlfunc2.date(models.InterviewSlot.datetime) == target_dt.date(),
                sqlfunc2.extract("hour",   models.InterviewSlot.datetime) == target_dt.hour,
                sqlfunc2.extract("minute", models.InterviewSlot.datetime) == target_dt.minute,
            ).first()
            if legacy_slot:
                legacy_slot.meet_link = body.meet_link
        except (ValueError, Exception):
            pass

    db.commit()
    return {"message": "Meet link saved successfully.", "slot_id": slot_id, "meet_link": body.meet_link}


# ============================================================
# HELPERS
# ============================================================

def _add_minutes(dt: datetime, minutes: int) -> datetime:
    return dt + timedelta(minutes=minutes)


# ============================================================
# DASHBOARD MANAGER TODAY
# ============================================================

@router.get("/dashboard/manager-today")
def get_manager_today(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("MANAGER", "RH"))
):
    now_utc = datetime.now(timezone.utc)
    today = now_utc.date()

    start_of_day = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
    end_of_day   = datetime.combine(today, datetime.max.time(), tzinfo=timezone.utc)

    # Jobs assignés au manager connecté — calculé en amont pour filtrer dashboard_today
    manager_job_rows = db.query(models.ManagerJob).filter(models.ManagerJob.manager_id == current_user.id).all()
    job_ids = [mj.job_id for mj in manager_job_rows]

    dashboard_today_q = db.query(models.Interview).filter(
        models.Interview.candidate_name != "",
        models.Interview.status.in_(["scheduled", "booked"]),
        models.Interview.scheduled_at >= start_of_day,
        models.Interview.scheduled_at <  end_of_day,
    )
    if current_user.role == "MANAGER":
        # Un manager ne doit voir que les entretiens des jobs qui lui sont assignés.
        # Le RH garde une vue globale (aucun filtre supplémentaire).
        dashboard_today_q = dashboard_today_q.filter(models.Interview.job_id.in_(job_ids))
    dashboard_today = dashboard_today_q.order_by(models.Interview.scheduled_at).all()

    slot_today = db.query(models.InterviewSlot).filter(
        models.InterviewSlot.manager_id   == current_user.id,
        models.InterviewSlot.is_available == False,
        models.InterviewSlot.interview_done == False,
        db.func.date(models.InterviewSlot.datetime) == today,
    ).order_by(models.InterviewSlot.datetime).all()

    today_interviews = []

    for iv in dashboard_today:
        now   = now_utc
        start = iv.scheduled_at
        end   = start + timedelta(minutes=iv.duration_minutes)
        status = "live" if start <= now <= end else ("done" if now > end else "upcoming")
        today_interviews.append({
            "id"              : iv.id,
            "source"          : "scheduler",
            "candidate_name"  : iv.candidate_name,
            "candidate_email" : iv.candidate_email,
            "role"            : iv.role,
            "start_time"      : start.strftime("%H:%M"),
            "end_time"        : end.strftime("%H:%M"),
            "meet_link"       : iv.meeting_link,
            "status"          : status,
        })

    for slot in slot_today:
        app = db.query(models.Application).filter(models.Application.id == slot.application_id).first()
        cv  = db.query(models.CVProfile).filter(models.CVProfile.application_id == slot.application_id).first() if app else None
        job = db.query(models.Job).filter(models.Job.id == slot.job_id).first()
        now    = datetime.now()
        end_dt = slot.datetime + timedelta(hours=1)
        status = "live" if slot.datetime <= now <= end_dt else ("done" if now > end_dt else "upcoming")
        today_interviews.append({
            "id"              : slot.id,
            "source"          : "pipeline",
            "candidate_name"  : cv.full_name if cv else (app.candidate_email if app else "Unknown"),
            "candidate_email" : app.candidate_email if app else None,
            "role"            : job.title if job else "—",
            "start_time"      : slot.datetime.strftime("%H:%M"),
            "end_time"        : end_dt.strftime("%H:%M"),
            "meet_link"       : slot.meet_link,
            "status"          : status,
            "application_id"  : slot.application_id,
        })

    today_interviews.sort(key=lambda x: x["start_time"])

    pending_actions = []

    for job_id in job_ids:
        job = db.query(models.Job).filter(models.Job.id == job_id).first()
        if not job or job.closed_at:
            continue

        blocked = db.query(models.Application).filter(
            models.Application.job_id == job_id,
            models.Application.status_v2 == "PRESELECTED",
        ).all()
        if blocked:
            oldest = min((a.created_at for a in blocked if a.created_at), default=datetime.utcnow())
            days_waiting = (datetime.utcnow() - oldest).days
            pending_actions.append({
                "type": "test_not_launched", "severity": "danger",
                "job_id": job_id, "job_title": job.title,
                "count": len(blocked), "days_waiting": days_waiting,
                "message": "Technical test not launched",
                "detail": f"{job.title} · {len(blocked)} applicant{'s' if len(blocked) > 1 else ''} on hold for {days_waiting}d",
            })

        interview_done = db.query(models.Application).filter(
            models.Application.job_id == job_id,
            models.Application.status_v2 == "INTERVIEW_DONE",
        ).all()
        for app in interview_done:
            review = db.query(models.ManagerReview).filter(models.ManagerReview.application_id == app.id).first()
            if not review:
                cv   = db.query(models.CVProfile).filter(models.CVProfile.application_id == app.id).first()
                slot = db.query(models.InterviewSlot).filter(
                    models.InterviewSlot.application_id == app.id,
                    models.InterviewSlot.interview_done == True,
                ).order_by(models.InterviewSlot.datetime.desc()).first()
                days_ago = (datetime.utcnow() - slot.datetime).days if slot else 0
                pending_actions.append({
                    "type": "feedback_missing", "severity": "warning",
                    "application_id": app.id, "job_id": job_id,
                    "candidate_name": cv.full_name if cv else app.candidate_email,
                    "job_title": job.title, "days_ago": days_ago,
                    "message": "Interview feedback missing",
                    "detail": f"{cv.full_name if cv else app.candidate_email} · interview completed {days_ago}d ago",
                })

        awaiting = db.query(models.Application).filter(
            models.Application.job_id == job_id,
            models.Application.status_v2.in_(["ACCEPTED"]),
        ).all()
        for app in awaiting:
            cv = db.query(models.CVProfile).filter(models.CVProfile.application_id == app.id).first()
            pending_actions.append({
                "type": "decision_awaited", "severity": "warning",
                "application_id": app.id, "job_id": job_id,
                "candidate_name": cv.full_name if cv else app.candidate_email,
                "job_title": job.title, "status": app.status_v2,
                "message": "Decision awaited",
                "detail": f"{cv.full_name if cv else app.candidate_email} · HR-approved, waiting for your review",
            })

    new_jobs = []
    cutoff = datetime.utcnow() - timedelta(days=7)
    for job_id in job_ids:
        job = db.query(models.Job).filter(
            models.Job.id == job_id,
            models.Job.closed_at == None,
            models.Job.created_at >= cutoff,
        ).first()
        if not job:
            continue
        applicants_count = db.query(models.Application).filter(
            models.Application.job_id == job_id,
            ~models.Application.status_v2.in_(["REJECTED_AUTO", "REJECTED_FINAL"]),
        ).count()
        days_ago = (datetime.utcnow() - job.created_at).days
        new_jobs.append({
            "id": job.id, "title": job.title, "department": job.department,
            "applicants_count": applicants_count, "test_launched": job.test_validated, "days_ago": days_ago,
        })

    return {"today_interviews": today_interviews, "pending_actions": pending_actions, "new_jobs": new_jobs}


@router.get("/slots/{slot_id}/manager")
def get_slot_manager(slot_id: int, db: Session = Depends(get_db)):
    interview = db.query(models.Interview).filter(models.Interview.id == slot_id).first()
    if not interview:
        raise HTTPException(status_code=404, detail="Slot not found")

    applications = db.query(models.Application).filter(
        models.Application.candidate_email == interview.candidate_email
    ).all()

    for application in applications:
        manager_job = db.query(models.ManagerJob).filter(models.ManagerJob.job_id == application.job_id).first()
        if manager_job:
            manager = db.query(models.User).filter(models.User.id == manager_job.manager_id).first()
            if manager:
                return {"manager_email": manager.email}

    return {"manager_email": None}

@router.patch("/slots/{slot_id}/absent")
def mark_candidate_absent(
    slot_id: int,
    db: Session = Depends(get_db),
):
    row = db.query(models.Interview).filter(
        models.Interview.id == slot_id
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Slot not found")

    candidate_email = row.candidate_email

    if candidate_email:
        app = db.query(models.Application).filter(
            models.Application.candidate_email == candidate_email
        ).first()
        if app:
            app.status_v2 = "NO_SHOW"

    db.delete(row)
    db.commit()

    db.commit()
    return {"message": "Candidate rejected, slot released", "slot_id": slot_id}


@router.get("/candidate-meet-link/{application_id}")
def get_candidate_meet_link(
    application_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("MANAGER", "RH"))
):
    app = db.query(models.Application).filter(
        models.Application.id == application_id
    ).first()
    if not app:
        return {"meet_link": None}

    row = db.query(models.Interview).filter(
        models.Interview.candidate_email == app.candidate_email,
        models.Interview.status == "booked",
        models.Interview.meeting_link != None,
    ).order_by(models.Interview.scheduled_at.desc()).first()

    return {"meet_link": row.meeting_link if row else None}


# ============================================================
# ENDPOINT MANAGER — CANDIDATS REJETÉS AUTO (token expiré)
# ============================================================

@router.get("/rejected-auto/{job_id}")
def get_rejected_auto_candidates(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("MANAGER", "RH"))
):
    """
    Retourne uniquement les candidats REJECTED_AUTO qui ont reçu une invitation
    d'entretien (BookingToken existant) mais n'ont pas réservé = vrais No-Shows.
    Exclut les candidats rejetés pour lien test expiré (sans BookingToken).
    """
    apps = db.query(models.Application).filter(
        models.Application.job_id    == job_id,
        models.Application.status_v2 == "REJECTED_AUTO"
    ).all()

    result = []
    for app in apps:
        # Vérifier qu'un BookingToken existe = candidat a reçu une invitation entretien
        token = db.query(models.BookingToken).filter(
            models.BookingToken.application_id == app.id,
            models.BookingToken.job_id         == job_id,
        ).order_by(models.BookingToken.expires_at.desc()).first()

        # Ignorer les candidats sans BookingToken (rejetés pour lien test expiré)
        if not token:
            continue

        cv = db.query(models.CVProfile).filter(
            models.CVProfile.application_id == app.id
        ).first()

        result.append({
            "application_id"  : app.id,
            "candidate_name"  : cv.full_name if cv else app.candidate_email,
            "candidate_email" : app.candidate_email,
            "expired_at"      : token.expires_at,
        })

    return {"count": len(result), "candidates": result}