from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey, Boolean, Enum, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSON
from app.database import Base


# ============================================================
# TABLE — JOB
# ============================================================

class Job(Base):
    __tablename__ = "jobs"

    id              = Column(Integer, primary_key=True, index=True)
    title           = Column(String)
    company         = Column(String,   nullable=True)
    description     = Column(Text)
    skills_required = Column(Text)
    date_expiration = Column(DateTime)
    created_at      = Column(DateTime, server_default=func.now())

    # ── Champs existants Point 2 ─────────────────────────────
    level        = Column(String, nullable=True)
    skills_json  = Column(JSON,   nullable=True)   # {"coding": [], "platform": [], "mixed": []}
    bonus_skills = Column(JSON,   nullable=True)
    location     = Column(String, nullable=True)
    department   = Column(String, nullable=True)

    # ── RGPD ────────────────────────────────────────────────
    closed_at    = Column(DateTime, nullable=True)

    # ── Test technique ───────────────────────────────────────
    test_available_from = Column(DateTime, nullable=True)  # date/heure ouverture test
    test_duration       = Column(Integer,  default=60)     # durée en minutes
    test_validated      = Column(Boolean,  default=False)  # True quand Manager valide
    test_id_validated   = Column(String,   nullable=True)  # ID test validé
    test_scheduled_at   = Column(DateTime, nullable=True)  # date planifiée d'envoi du test
    test_sent_at        = Column(DateTime, nullable=True)  # date réelle d'envoi du test

    # ── Langue du poste ──────────────────────────────────────
    # "fr" → poste en français, "en" → poste en anglais
    # Utilisé par motivation_agent pour détecter mismatch langue lettre/poste
    lang = Column(String(5), nullable=True, default="fr")

    # ── Mode pipeline ────────────────────────────────────────
    # AUTO      → agent décide seul
    # SEMI_AUTO → RH reçoit rappel 48h — jamais auto-accept
    pipeline_mode = Column(String, default="SEMI_AUTO")

    # ── Élargir sélection (Cycle 2 / Cycle 3) ────────────────
    expand_requested = Column(Boolean, default=False)   # True quand RH clique "Élargir"
    expand_phase     = Column(String(10), nullable=True) # "cycle2" ou "cycle3"


# ============================================================
# TABLE — APPLICATION
# ============================================================

class Application(Base):
    __tablename__ = "applications"

    id               = Column(Integer, primary_key=True, index=True)
    job_id           = Column(Integer, ForeignKey("jobs.id"))
    candidate_email  = Column(String)
    cv_path          = Column(String)
    letter_path      = Column(String)
    score_matching   = Column(Float,  nullable=True)
    score_motivation = Column(Float,  nullable=True)
    score_final      = Column(Float,  nullable=True)
    score_technique  = Column(Float,  nullable=True)
    signal_final     = Column(String, nullable=True)
    created_at       = Column(DateTime, server_default=func.now())

    # ── Status v2 — Pipeline complet ────────────────────────
    status_v2 = Column(
        Enum(
            # Phase 1 — Analyse
            "APPLIED",                   # candidat vient de postuler
            "ANALYZED",                  # CV parsé
            "MATCHED",                   # score matching calculé
            "PENDING",                   # score 40-69 → RH décide
            "PRESELECTED",               # score ≥ 70

            # Phase 2 — Test technique
            "TEST_READY",                # test validé Manager, pas encore envoyé
            "TEST_SENT",                 # email envoyé (lien 24h)
            "TEST_IN_PROGRESS",          # candidat a ouvert → timer 60min
            "TEST_COMPLETED", 
            "TEST_EXPIRED",           # candidat a soumis

            # Phase 3 — Décision après test (gate technique)
            "REJECTED_TECH",             # score technique < 50 → rejeté direct
            "WAITING_MEET",              # score technique 50-69 → en attente
            "MEET_PENDING",              # score technique >= 70 → convocation meet
            "TECHNICAL_REVIEW_PENDING",  # attente validation RH (SEMI_AUTO)
            "INTERVIEW_ELIGIBLE",        # score test >= 70 (ancien)

            # Phase 4 — Meet technique
            "INTERVIEW_SCHEDULED",       # créneau réservé
            "INTERVIEW_DONE",            # Meet terminé
            "TECH_EVALUATED",            # Manager a soumis avis

            # Phase 5 — Décision manager après meet
            "MANAGER_VALIDATED",         # manager valide groupe 1
            "MANAGER_TO_DEEPEN",         # manager approfondit groupe 2
            "MANAGER_REJECTED",          # manager rejette
            "NO_SHOW",                   # candidat no-show à l'entretien

            # Phase 6 — Décision finale
            "ACCEPTED",                  # retenu pour entretien présentiel RH
            "REJECTED_AUTO",             # rejeté automatiquement (matching)
            "REJECTED_FINAL",            # rejeté après entretien
            "HIRED",                     # candidat embauché par le RH
            "POSITION_FILLED",           # poste pourvu — autres candidats

            # Erreurs
            "ERROR",                     # erreur bloquante retry_count = 3
            "ERROR_RETRY",               # retry en cours retry_count < 3

            name="application_status_v2"
        ),
        nullable=True,
        index=True,
        default="APPLIED"
    )

    # ── Gestion erreurs ──────────────────────────────────────
    error_message = Column(Text,    nullable=True)
    error_stage   = Column(String,  nullable=True)  # "CV_PARSING" / "MATCHING" / ...
    retry_count   = Column(Integer, default=0)

    # ── Délais test ──────────────────────────────────────────
    test_sent_at        = Column(DateTime, nullable=True)  # email envoyé
    test_opened_at      = Column(DateTime, nullable=True)  # candidat ouvre → TEST_IN_PROGRESS
    test_expires_at     = Column(DateTime, nullable=True)  # test_opened_at + 60min
    test_available_from = Column(DateTime, nullable=True)  # copié depuis jobs

    # ── Délais créneaux Meet ─────────────────────────────────
    slot_offered_at = Column(DateTime, nullable=True)  # lien calendrier envoyé
    slot_expires_at = Column(DateTime, nullable=True)  # +48h

    # ── RGPD ─────────────────────────────────────────────────
    deletion_scheduled_at = Column(DateTime, nullable=True)
    is_anonymized         = Column(Boolean,  default=False)
    anonymized_at         = Column(DateTime, nullable=True)
    gdpr_consent          = Column(Boolean,  default=False)
    gdpr_consent_at       = Column(DateTime, nullable=True)


# ============================================================
# TABLE — CV PROFILE
# ============================================================

class CVProfile(Base):
    __tablename__ = "cv_profiles"

    id                        = Column(Integer, primary_key=True, index=True)
    application_id            = Column(Integer, ForeignKey("applications.id"))
    full_name                 = Column(String,  nullable=True)
    email                     = Column(String,  nullable=True)
    phone                     = Column(String,  nullable=True)
    skills                    = Column(JSON,    nullable=True)
    education                 = Column(JSON,    nullable=True)
    professional_experience   = Column(JSON,    nullable=True)
    internships               = Column(JSON,    nullable=True)
    alternance                = Column(JSON,    nullable=True)
    years_professional        = Column(Integer, nullable=True)
    months_internships        = Column(Integer, nullable=True)
    months_alternance         = Column(Integer, nullable=True)
    certifications            = Column(JSON,    nullable=True)
    projects                  = Column(JSON,    nullable=True)
    nb_internships            = Column(Integer, default=0)
    years_experience          = Column(Integer, nullable=True)
    languages                 = Column(JSON,    nullable=True)
    cv_quality_score          = Column(Float,   nullable=True)
    classification_confidence = Column(Float,   nullable=True)
    raw_text                  = Column(Text,    nullable=True)
    created_at                = Column(DateTime, server_default=func.now())


# ============================================================
# TABLE — IA LOG
# ============================================================

class IA_Log(Base):
    __tablename__ = "ia_logs"

    id             = Column(Integer, primary_key=True, index=True)
    application_id = Column(Integer)
    agent_name     = Column(String)
    output_json    = Column(Text)
    created_at     = Column(DateTime, server_default=func.now())


# ============================================================
# TABLE — APPLICATION EVENTS (logs métier)
# ============================================================

class ApplicationEvent(Base):
    """
    Traçabilité complète — logger SEULEMENT :
      ✅ Changement status_v2
      ✅ Action humaine (RH/Manager)
      ✅ Email envoyé
      ✅ Erreur agent
      ❌ Lectures de données
      ❌ Appels internes sans impact
    """
    __tablename__ = "application_events"

    id              = Column(Integer,  primary_key=True, index=True)
    application_id  = Column(Integer,  ForeignKey("applications.id"), nullable=False, index=True)
    event           = Column(String,   nullable=False)   # "TEST_SENT" / "STATUS_CHANGED" / ...
    actor           = Column(String,   nullable=False)   # "system" / "rh" / "manager" / "candidate"
    actor_id        = Column(Integer,  nullable=True)    # user_id si action humaine
    previous_status = Column(String,   nullable=True)
    new_status      = Column(String,   nullable=True)
    timestamp       = Column(DateTime, server_default=func.now())
    details         = Column(JSON,     nullable=True)    # {"email_sent": true, "score": 75}


# ============================================================
# TABLE — RH FEEDBACK
# ============================================================

class RH_Feedback(Base):
    __tablename__ = "rh_feedback"

    id             = Column(Integer, primary_key=True, index=True)
    application_id = Column(Integer, ForeignKey("applications.id"), nullable=False, index=True)
    decision_ai    = Column(String,  nullable=False)
    decision_rh    = Column(String,  nullable=False)
    main_reason    = Column(String,  nullable=True)
    score_final    = Column(Float,   nullable=False)
    agreement      = Column(Boolean, nullable=False)
    commentaire    = Column(Text,    nullable=True)
    is_validated   = Column(Boolean, nullable=False, default=False)
    created_at     = Column(DateTime, server_default=func.now())


# ============================================================
# TABLE — TEST
# ============================================================

class Test(Base):
    __tablename__ = "tests"

    test_id        = Column(String(64),  primary_key=True)
    application_id = Column(Integer, ForeignKey("applications.id"), nullable=True, index=True)
    job_id         = Column(Integer, ForeignKey("jobs.id"),         nullable=True, index=True)
    job_key        = Column(String(64),  nullable=True, index=True)
    role           = Column(String(255), nullable=False)
    skills         = Column(JSON,        nullable=False)
    seniority      = Column(String(100), nullable=False)
    questions      = Column(JSON,        nullable=False)
    duration       = Column(Integer,     nullable=False, default=60)
    created_at     = Column(DateTime,    server_default=func.now())


# ============================================================
# TABLE — USER
# ============================================================

class User(Base):
    __tablename__ = "users"

    id              = Column(Integer, primary_key=True, index=True)
    email           = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active       = Column(Boolean, default=True)
    role            = Column(String,  nullable=False, default="RH")  # "RH" / "MANAGER"
    full_name       = Column(String,  nullable=True)   # nom complet affiché
    poste           = Column(String,  nullable=True)   # intitulé du poste
    created_at      = Column(DateTime, server_default=func.now())


# ============================================================
# TABLE — INVITATION TOKEN
# ============================================================

class InvitationToken(Base):
    """Token unique 24h — RH invite Manager."""
    __tablename__ = "invitation_tokens"

    id         = Column(Integer, primary_key=True, index=True)
    token      = Column(String, unique=True, index=True, nullable=False)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used       = Column(Boolean,  default=False)
    created_at = Column(DateTime, server_default=func.now())


# ============================================================
# TABLE — MANAGER JOB
# ============================================================

class ManagerJob(Base):
    """1 seul Manager par job."""
    __tablename__ = "manager_jobs"

    id          = Column(Integer, primary_key=True, index=True)
    manager_id  = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    job_id      = Column(Integer, ForeignKey("jobs.id"),  nullable=False, index=True)
    assigned_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("job_id", name="uq_manager_jobs_job_id"),
    )


# ============================================================
# TABLE — INTERVIEW SLOT
# ============================================================

class InterviewSlot(Base):
    """
    Créneaux Meet créés par Manager.
    DB lock → is_available=False dès réservation.
    Candidat voit libre/occupé — jamais les noms.
    """
    __tablename__ = "interview_slots"

    id             = Column(Integer, primary_key=True, index=True)
    job_id         = Column(Integer, ForeignKey("jobs.id"),         nullable=False, index=True)
    manager_id     = Column(Integer, ForeignKey("users.id"),        nullable=False)
    datetime       = Column(DateTime, nullable=False)
    meet_link      = Column(String,   nullable=False)
    is_available   = Column(Boolean,  default=True)
    application_id = Column(Integer, ForeignKey("applications.id"), nullable=True)
    interview_done = Column(Boolean,  default=False)
    created_at     = Column(DateTime, server_default=func.now())


# ============================================================
# TABLE — BOOKING TOKEN
# ============================================================

class BookingToken(Base):
    """
    Lien unique candidat → réserver créneau Meet.
    Usage unique — expire après 48h ou après réservation.
    """
    __tablename__ = "booking_tokens"

    id             = Column(Integer, primary_key=True, index=True)
    token          = Column(String, unique=True, index=True, nullable=False)
    application_id = Column(Integer, ForeignKey("applications.id"), nullable=False)
    job_id         = Column(Integer, ForeignKey("jobs.id"),         nullable=False)
    expires_at     = Column(DateTime(timezone=True), nullable=False)   # +48h — timezone-aware
    used           = Column(Boolean,  default=False)
    created_at     = Column(DateTime, server_default=func.now())


# ============================================================
# TABLE — MANAGER REVIEW
# ============================================================

class ManagerReview(Base):
    """
    Avis Manager après Meet technique.
    Commentaire → RH uniquement — jamais transmis à l'agent.

    RECOMMENDED → combiné score test → ACCEPTED ou RH décide
    TO_REVIEW   → RH décide manuellement
    REFUSED     → REJECTED_FINAL direct
    """
    __tablename__ = "manager_reviews"

    id             = Column(Integer, primary_key=True, index=True)
    application_id = Column(Integer, ForeignKey("applications.id"), nullable=False, index=True)
    manager_id     = Column(Integer, ForeignKey("users.id"),        nullable=False)
    decision       = Column(
        Enum("RECOMMENDED", "TO_REVIEW", "REFUSED", name="manager_decision_v2"),
        nullable=False
    )
    commentaire    = Column(Text, nullable=True)
    created_at     = Column(DateTime, server_default=func.now())

# ============================================================
# TABLE — INTERVIEW  (planification manuelle Manager)
# ============================================================

class Interview(Base):
    """
    Entretien planifié manuellement depuis InterviewDashboard.
    Indépendant du pipeline Application — usage direct Manager.
    """
    __tablename__ = "interviews"

    id               = Column(Integer,  primary_key=True, index=True)
    job_id           = Column(Integer,  ForeignKey("jobs.id"), nullable=True, index=True)  # ← lié au job
    candidate_name   = Column(String,   nullable=False)
    candidate_email  = Column(String,   nullable=False)
    role             = Column(String,   nullable=False)
    round            = Column(String,   nullable=False)           # "HR Round", "Technical Round"...
    scheduled_at     = Column(DateTime(timezone=True), nullable=False)
    duration_minutes = Column(Integer,  default=60)
    status           = Column(String,   default="scheduled")      # scheduled / completed / cancelled
    meeting_link     = Column(String,   nullable=True)
    notes            = Column(Text,     nullable=True)
    created_at       = Column(DateTime, server_default=func.now())


# ============================================================
# TABLE — NOTIFICATION
# ============================================================

class Notification(Base):
    """
    Notifications in-app pour Manager et RH.
    Générées par le backend ou n8n à chaque événement clé :
      - Nouveau candidat préselectionné
      - Test complété
      - Entretien réservé par un candidat
      - Décision manager soumise
    """
    __tablename__ = "notifications"

    id         = Column(Integer,  primary_key=True, index=True)
    user_id    = Column(Integer,  ForeignKey("users.id"), nullable=False, index=True)
    message    = Column(Text,     nullable=False)
    type       = Column(String,   default="info")    # "info" | "success" | "warning" | "error"
    read       = Column(Boolean,  default=False)
    link       = Column(String,   nullable=True)     # route frontend optionnelle ex: "/candidates/12/34"
    created_at = Column(DateTime, server_default=func.now())