"""
notifications.py — Router FastAPI pour les notifications in-app.

Endpoints :
  GET  /notifications               → liste des notifs du user connecté
  PATCH /notifications/{id}/read    → marquer une notif comme lue
  PATCH /notifications/read-all     → tout marquer lu
  POST  /notifications/internal     → créer une notif depuis le backend (interne)
  POST  /notifications/n8n          → créer une notif depuis n8n (sans auth)

Les notifications sont générées automatiquement par :
  - Le backend à chaque événement clé (test complété, décision soumise…)
  - n8n après la création d'un Google Meet (slot booked → notif manager)
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

from app import models
from app.database import get_db
from app.routers.auth import require_role, get_current_user

router = APIRouter(prefix="/notifications", tags=["Notifications"])


# ============================================================
# SCHEMAS LOCAUX
# ============================================================

class NotificationOut(BaseModel):
    id         : int
    message    : str
    type       : str
    read       : bool
    link       : Optional[str] = None
    created_at : datetime

    class Config:
        from_attributes = True


class CreateNotifInternal(BaseModel):
    """Payload pour créer une notif depuis le backend Python."""
    user_id : int
    message : str
    type    : str = "info"    # "info" | "success" | "warning" | "error"
    link    : Optional[str] = None


class CreateNotifN8N(BaseModel):
    """
    Payload pour créer une notif depuis n8n (sans auth JWT).
    n8n envoie un secret partagé pour sécuriser l'endpoint.
    """
    secret       : str
    user_email   : str          # email du manager/RH à notifier
    message      : str
    type         : str = "info"
    link         : Optional[str] = None


# ============================================================
# HELPER — créer une notification (utilisé en interne)
# ============================================================

def create_notification(
    db      : Session,
    user_id : int,
    message : str,
    type    : str = "info",
    link    : Optional[str] = None,
) -> models.Notification:
    """
    Fonction utilitaire appelée depuis d'autres routers
    pour créer une notification sans passer par HTTP.

    Usage :
        from app.routers.notifications import create_notification
        create_notification(db, user_id=manager.id,
                            message="New candidate preselected",
                            type="info",
                            link=f"/candidates/{job_id}/{app_id}")
    """
    notif = models.Notification(
        user_id = user_id,
        message = message,
        type    = type,
        link    = link,
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)
    return notif


# ============================================================
# ENDPOINTS MANAGER / RH
# ============================================================

@router.get("", response_model=List[NotificationOut])
def get_notifications(
    db           : Session = Depends(get_db),
    current_user : models.User = Depends(get_current_user),
):
    """
    Retourne toutes les notifications du user connecté,
    triées par date décroissante (les plus récentes en premier).
    """
    notifs = (
        db.query(models.Notification)
        .filter(models.Notification.user_id == current_user.id)
        .order_by(models.Notification.created_at.desc())
        .limit(50)   # max 50 notifs dans le dropdown
        .all()
    )
    return notifs


@router.patch("/{notif_id}/read", status_code=200)
def mark_as_read(
    notif_id     : int,
    db           : Session = Depends(get_db),
    current_user : models.User = Depends(get_current_user),
):
    """Marque une notification comme lue."""
    notif = db.query(models.Notification).filter(
        models.Notification.id      == notif_id,
        models.Notification.user_id == current_user.id,   # sécurité : seulement ses propres notifs
    ).first()

    if not notif:
        raise HTTPException(status_code=404, detail="Notification introuvable")

    notif.read = True
    db.commit()
    return {"message": "Notification marquée comme lue", "id": notif_id}


@router.patch("/read-all", status_code=200)
def mark_all_read(
    db           : Session = Depends(get_db),
    current_user : models.User = Depends(get_current_user),
):
    """Marque toutes les notifications du user comme lues."""
    db.query(models.Notification).filter(
        models.Notification.user_id == current_user.id,
        models.Notification.read    == False,
    ).update({"read": True})
    db.commit()
    return {"message": "Toutes les notifications marquées comme lues"}


@router.delete("/{notif_id}", status_code=200)
def delete_notification(
    notif_id     : int,
    db           : Session = Depends(get_db),
    current_user : models.User = Depends(get_current_user),
):
    """Supprime définitivement une notification du user connecté."""
    notif = db.query(models.Notification).filter(
        models.Notification.id      == notif_id,
        models.Notification.user_id == current_user.id,
    ).first()

    if not notif:
        raise HTTPException(status_code=404, detail="Notification introuvable")

    db.delete(notif)
    db.commit()
    return {"message": "Notification supprimée", "id": notif_id}


# ============================================================
# ENDPOINT INTERNE — créer une notif depuis le backend Python
# ============================================================

@router.post("/internal", status_code=201)
def create_notif_internal(
    body         : CreateNotifInternal,
    db           : Session = Depends(get_db),
    current_user : models.User = Depends(require_role("RH")),  # seulement RH ou appel interne
):
    """
    Crée une notification pour un user donné.
    Réservé aux appels internes (RH ou services backend).
    Pour un usage Python direct, préférer create_notification().
    """
    user = db.query(models.User).filter(models.User.id == body.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User introuvable")

    notif = create_notification(db, body.user_id, body.message, body.type, body.link)
    return {"message": "Notification créée", "id": notif.id}


# ============================================================
# ENDPOINT N8N — appelé par n8n après création d'un Google Meet
# ============================================================

import os

N8N_SECRET = os.getenv("N8N_NOTIF_SECRET", "dynamix-n8n-secret-2025")

@router.post("/n8n", status_code=201)
def create_notif_from_n8n(
    body : CreateNotifN8N,
    db   : Session = Depends(get_db),
):
    """
    Endpoint appelé par n8n (sans JWT) pour notifier un manager/RH.

    Sécurisé par un secret partagé dans la variable d'env N8N_NOTIF_SECRET.

    Flow typique n8n :
      Webhook4 (confirmer-reservation)
        → Create an event (Google Calendar)
        → POST /interviews/slots/{slot_id}/save-meet-link
        → POST /notifications/n8n          ← ici (notifie le manager)
        → Wait1 (15min avant)
        → Send an Email6 (email rappel)

    Body attendu depuis n8n :
    {
      "secret":       "dynamix-n8n-secret-2025",
      "user_email":   "{{ $json.manager_email }}",
      "message":      "Interview booked by {{ $json.candidate_name }} on {{ $json.slot_date }} at {{ $json.slot_time }}",
      "type":         "info",
      "link":         "/interviews"
    }
    """
    # Vérifier le secret partagé
    if body.secret != N8N_SECRET:
        raise HTTPException(status_code=403, detail="Secret invalide")

    # Retrouver le user par email
    user = db.query(models.User).filter(
        models.User.email == body.user_email
    ).first()

    if not user:
        # On ne crash pas si le manager n'existe pas — n8n continue son flow
        return {"message": f"User {body.user_email} introuvable — notification ignorée"}

    notif = create_notification(db, user.id, body.message, body.type, body.link)
    return {
        "message"  : "Notification créée",
        "id"       : notif.id,
        "user_id"  : user.id,
    }