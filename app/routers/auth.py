from fastapi import APIRouter, Depends, HTTPException, status, Form
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.database import get_db
from app import models, schemas
import os
import uuid
import secrets
import httpx

router = APIRouter(prefix="/auth", tags=["auth"])

SECRET_KEY = os.getenv("SECRET_KEY", "changeme-secret-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 8  # 8 heures

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# ============================================================
# FONCTIONS UTILITAIRES — INCHANGÉES
# ============================================================

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# ============================================================
# HELPERS RÉUTILISABLES — AJOUTS POINT 1
# ============================================================

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> models.User:
    """
    Décode le JWT et retourne l'utilisateur connecté.
    Utilisable dans tous les endpoints avec : user = Depends(get_current_user)
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        if not email:
            raise HTTPException(status_code=401, detail="Token invalide")
    except JWTError:
        raise HTTPException(status_code=401, detail="Token invalide")
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    return user


def require_role(*roles: str):
    """
    Middleware de vérification de rôle.
    Usage : user = Depends(require_role("RH"))
            user = Depends(require_role("RH", "MANAGER"))
    """
    def checker(current_user: models.User = Depends(get_current_user)) -> models.User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Accès refusé — rôle requis : {list(roles)}"
            )
        return current_user
    return checker


# ============================================================
# ENDPOINTS EXISTANTS — INCHANGÉS
# ============================================================

@router.post("/register", response_model=schemas.UserResponse)
def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.email == user.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email déjà utilisé")
    new_user = models.User(
        email=user.email,
        hashed_password=hash_password(user.password)
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@router.post("/login", response_model=schemas.Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == form.username).first()
    if not user or not user.is_active or not verify_password(form.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou mot de passe incorrect",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # ── Ajout Point 1 : role inclus dans le token ──
    token = create_access_token({"sub": user.email, "role": user.role})
    return {"access_token": token, "token_type": "bearer"}


@router.get("/me")
def me(current_user: models.User = Depends(get_current_user)):
    """Retourne le profil complet du manager connecté."""
    return {
        "id":        current_user.id,
        "email":     current_user.email,
        "role":      current_user.role,
        "is_active": current_user.is_active,
        "full_name": getattr(current_user, "full_name", None) or "",
        "poste":     getattr(current_user, "poste",     None) or "",
    }


# ============================================================
# NOUVEAUX ENDPOINTS — POINT 1 : INVITATION MANAGER
# ============================================================

@router.post("/invite-manager", response_model=schemas.InvitationResponse)
def invite_manager(
    payload: schemas.InviteManagerCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("RH"))   # RH uniquement
):
    """
    RH invite un Manager technique.
    - Crée un compte User avec role=MANAGER (sans mot de passe encore)
    - Génère un token unique valable 24h
    - Envoie un email via n8n avec le lien d'activation
    """
    # Vérifier si email déjà utilisé
    existing = db.query(models.User).filter(models.User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email déjà utilisé")

    # Créer le compte Manager sans mot de passe (placeholder)
    new_manager = models.User(
        email=payload.email,
        hashed_password=hash_password(secrets.token_hex(32)),  # hash aléatoire inutilisable — remplacé lors du setup-password
        role="MANAGER",
        is_active=False            # inactif jusqu'à ce qu'il choisisse son mot de passe
    )
    db.add(new_manager)
    db.commit()
    db.refresh(new_manager)

    # Générer le token d'invitation unique
    token = str(uuid.uuid4())
    invitation = models.InvitationToken(
        token=token,
        user_id=new_manager.id,
        expires_at=datetime.utcnow() + timedelta(hours=24),
        used=False
    )
    db.add(invitation)
    db.commit()

    # Appel Webhook n8n → envoie email au Manager
    try:
        httpx.post(
            "http://localhost:5678/webhook/invite-manager",
            json={
                "manager_email": payload.email,
                "setup_link": f"http://localhost:5173/setup-password?token={token}"
            },
            timeout=5
        )
    except Exception:
        pass  # n8n indisponible — ne bloque pas l'invitation

    return {
        "message": f"Invitation créée pour {payload.email}",
        "token": token,
        "link": f"http://localhost:5173/setup-password?token={token}",
        "expires_at": invitation.expires_at
    }


@router.post("/setup-password", response_model=schemas.SetupPasswordResponse)
def setup_password(
    payload: schemas.SetupPasswordInput,
    db: Session = Depends(get_db)
):
    """
    Manager choisit son mot de passe via le lien unique reçu par email.
    - Vérifie que le token existe, n'est pas expiré, et n'a pas été utilisé
    - Met à jour le mot de passe + active le compte
    - Marque le token comme utilisé (lien mort après)
    """
    # Chercher le token
    invitation = db.query(models.InvitationToken).filter(
        models.InvitationToken.token == payload.token
    ).first()

    if not invitation:
        raise HTTPException(status_code=404, detail="Lien invalide")
    if invitation.used:
        raise HTTPException(status_code=400, detail="Lien déjà utilisé")
    if invitation.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Lien expiré")

    # Mettre à jour le mot de passe + activer le compte
    user = db.query(models.User).filter(models.User.id == invitation.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

    user.hashed_password = hash_password(payload.new_password)
    user.is_active = True

    # Marquer le token comme utilisé → lien mort
    invitation.used = True

    db.commit()

    # Notify all HR users that the manager has activated their account
    from app.routers.notifications import create_notification
    rh_users = db.query(models.User).filter(models.User.role == "RH").all()
    for rh in rh_users:
        create_notification(
            db,
            user_id = rh.id,
            message = f"Manager {user.email} has activated their account",
            type    = "info",
            link    = "/rh/managers",
        )

    return {
        "message": "Mot de passe défini avec succès. Vous pouvez maintenant vous connecter.",
        "email": user.email
    }

# ============================================================
# NOUVEAUX ENDPOINTS — COMPTE MANAGER
# ============================================================

@router.patch("/profile")
def update_profile(
    full_name: str = Form(None),
    poste: str = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Met à jour le profil du manager connecté.
    - full_name : nom complet
    - poste     : intitulé du poste
    Tous les champs sont optionnels — seul ce qui est envoyé est modifié.
    """
    if full_name is not None:
        current_user.full_name = full_name

    if poste is not None:
        current_user.poste = poste

    db.commit()
    db.refresh(current_user)

    return {
        "message": "Profil mis à jour avec succès",
        "full_name": current_user.full_name,
        "email": current_user.email,
        "poste": current_user.poste,
    }



@router.post("/change-password")
def change_password(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Change le mot de passe du manager connecté.
    Body JSON : { "current_password": "...", "new_password": "..." }
    """
    current_pwd = payload.get("current_password", "")
    new_pwd     = payload.get("new_password", "")

    # Vérifier l'ancien mot de passe
    if not verify_password(current_pwd, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mot de passe actuel incorrect"
        )

    # Vérifier la longueur minimale
    if len(new_pwd) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le nouveau mot de passe doit contenir au moins 8 caractères"
        )

    current_user.hashed_password = hash_password(new_pwd)
    db.commit()

    return {"message": "Mot de passe modifié avec succès"}