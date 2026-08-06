from pydantic import BaseModel, validator
from datetime import date, datetime
from typing import Optional, List


# ============================================================
# SCHEMAS EXISTANTS — INCHANGÉS
# ============================================================

class ApplicationCreate(BaseModel):
    candidate_email: str


# ─────────────────────────────────────────────────────────────────
# FEEDBACK RH
# ─────────────────────────────────────────────────────────────────

DECISIONS_VALIDES = {"ENTRETIEN", "EN_ATTENTE", "REJETÉ"}


class FeedbackCreate(BaseModel):
    decision_rh : str
    commentaire : Optional[str] = None

    @validator("decision_rh")
    def valider_decision(cls, v):
        v = v.strip().upper()
        if v not in DECISIONS_VALIDES:
            raise ValueError(
                f"Décision '{v}' invalide. "
                f"Valeurs acceptées : {sorted(DECISIONS_VALIDES)}"
            )
        return v


class FeedbackResponse(BaseModel):
    message        : str
    application_id : int
    feedback_id    : int
    decision_ai    : str
    decision_rh    : str
    main_reason    : Optional[str]
    score_final    : float
    accord         : bool
    nb_feedbacks   : int


# ─────────────────────────────────────────────────────────────────
# AGENT TEST
# ─────────────────────────────────────────────────────────────────

class GenerateTestInput(BaseModel):
    role             : str
    skills           : List[str]
    seniority        : str = "junior"
    force_regenerate : bool = False
    application_id   : Optional[int] = None

    @validator("seniority")
    def validate_seniority(cls, v):
        allowed = {"junior", "mid", "senior"}
        v = v.lower().strip()
        if v not in allowed:
            raise ValueError(f"seniority doit être dans {allowed}")
        return v

    @validator("skills")
    def validate_skills(cls, v):
        cleaned = [s.strip() for s in v if s.strip()]
        if not cleaned:
            raise ValueError("La liste de skills ne peut pas être vide")
        return cleaned[:5]

    @validator("role")
    def validate_role(cls, v):
        if not v or not v.strip():
            raise ValueError("Le rôle ne peut pas être vide")
        return v.strip()


class CandidateAnswer(BaseModel):
    question_id : int
    answer      : str = ""  # réponse vide autorisée → score 0


class EvaluateTestInput(BaseModel):
    test_id        : str
    answers        : List[CandidateAnswer]
    application_id : Optional[int]  = None
    violations     : Optional[List[dict]] = None   # liste des violations enregistrées
    violation_flag : Optional[str]  = None          # "VIOLATION_3" si 3 violations
    forced_submit  : Optional[bool] = False         # True si soumission forcée par violations

    @validator("answers")
    def check_answers(cls, v):
        if not v:
            raise ValueError("La liste de réponses est vide")
        return v


# ─────────────────────────────────────────────────────────────────
# AUTH — INCHANGÉS
# ─────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    email: str
    password: str

class UserResponse(BaseModel):
    id: int
    email: str
    is_active: bool
    role: str

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None


# ─────────────────────────────────────────────────────────────────
# AUTH — NOUVEAUX SCHEMAS POINT 1
# ─────────────────────────────────────────────────────────────────

class InviteManagerCreate(BaseModel):
    email: str

    @validator("email")
    def validate_email(cls, v):
        v = v.strip().lower()
        if "@" not in v:
            raise ValueError("Email invalide")
        return v


class InvitationResponse(BaseModel):
    message    : str
    token      : str
    link       : str
    expires_at : datetime

    class Config:
        from_attributes = True


class SetupPasswordInput(BaseModel):
    token        : str
    new_password : str

    @validator("new_password")
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError("Le mot de passe doit contenir au moins 8 caractères")
        return v


class SetupPasswordResponse(BaseModel):
    message : str
    email   : str


# ─────────────────────────────────────────────────────────────────
# AUTH — MOT DE PASSE OUBLIÉ
# ─────────────────────────────────────────────────────────────────

class ForgotPasswordInput(BaseModel):
    email: str

    @validator("email")
    def validate_email(cls, v):
        v = v.strip().lower()
        if "@" not in v:
            raise ValueError("Email invalide")
        return v


# ─────────────────────────────────────────────────────────────────
# JOB — ENRICHI POINT 2
# ─────────────────────────────────────────────────────────────────

class JobCreate(BaseModel):
    """
    Payload POST /jobs/
    Champs existants conservés + nouveaux champs Point 2.
    Tous les nouveaux champs sont optionnels pour ne pas casser l'existant.
    """
    # ── Champs existants ──────────────────────────────────────
    title            : str
    description      : str
    skills_required  : str
    date_expiration  : date

    # ── Nouveaux champs Point 2 ───────────────────────────────
    company          : Optional[str]       = None
    level            : Optional[str]       = None   # "Junior" / "Mid" / "Senior"
    skills_json      : Optional[dict]      = None   # {"coding": [], "platform": [], "mixed": []} — structuré
    bonus_skills     : Optional[List[str]] = None   # skills optionnelles
    location         : Optional[str]       = None   # "Paris" / "Remote"
    department       : Optional[str]       = None   # "Backend" / "Data" / "DevOps"
    manager_id       : Optional[int]       = None   # Manager assigné
    pipeline_mode    : Optional[str]       = None   # "SEMI_AUTO" ou "AUTO"

    @validator("level")
    def validate_level(cls, v):
        if v is None:
            return v
        allowed = {"Junior", "Mid", "Senior"}
        if v not in allowed:
            raise ValueError(f"level doit être dans {allowed}")
        return v


class JobResponse(BaseModel):
    """Réponse GET /jobs/"""
    id              : int
    title           : str
    description     : str
    skills_required : str
    date_expiration : date
    created_at      : datetime
    company         : Optional[str]       = None
    level           : Optional[str]       = None
    skills_json     : Optional[List[str]] = None
    bonus_skills    : Optional[List[str]] = None
    location        : Optional[str]       = None
    department      : Optional[str]       = None
    closed_at       : Optional[datetime]  = None

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────────────────────────
# MANAGER REVIEW — POINT 8
# ─────────────────────────────────────────────────────────────────

class ManagerReviewCreate(BaseModel):
    """
    Payload POST /applications/{id}/manager-review
    Décision → Agent Décision
    Commentaire → RH uniquement
    """
    decision    : str
    commentaire : Optional[str] = None

    @validator("decision")
    def validate_decision(cls, v):
        allowed = {"RECOMMANDÉ", "REFUSÉ"}
        if v not in allowed:
            raise ValueError(f"Décision invalide. Valeurs acceptées : {allowed}")
        return v


class ManagerReviewResponse(BaseModel):
    message        : str
    application_id : int
    decision       : str