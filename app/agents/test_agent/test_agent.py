"""
test_agent.py — Agent Test Technique (v7.0 - MCQ + OPEN + Manager Decision)

ARCHITECTURE v7.0 :
══════════════════════════════════════════════════════════════════════════
Types de questions réduits à 2 uniquement :
  1. MCQ (QCM)     — Choix multiple, 4 options, correction binaire Python
  2. OPEN          — Question ouverte de type « Comment résoudre ce problème ? »
                     Évaluation via LLM direct (pas de pipeline signal/core/decision)

Ajout v7.0 — Décision Manager (après meet technique) :
  run_manager_decision() — Enregistre la décision du manager :
    VALIDÉ        → candidat passe à l'Agent 5, priority_group=1
    À_APPROFONDIR → candidat passe à l'Agent 5, priority_group=2
    NON_RETENU    → rejet direct, pass_to_agent5=False
  get_manager_decision()  — Récupère la décision pour l'Agent 5

  Le technical_score reste inchangé — la décision manager est stockée
  séparément. Le classement Agent 5 se fait en 2 niveaux :
    Niveau 1 : groupe par décision manager (VALIDÉ avant À_APPROFONDIR)
    Niveau 2 : au sein du groupe, classement par score_global

Suppressions par rapport à v5.0 :
  - Type PROBLEM (coding / exécution de code)  → supprimé
  - execution_engine.py                         → plus utilisé
  - signal_extractor.py, evaluation_core.py, decision_engine.py → plus utilisés
  - Toute la logique test_cases, function_name, starter_code     → supprimée

Structure des questions par test_type (10 questions) :
  tech     : MCQ=6, OPEN=4
  platform : MCQ=5, OPEN=5
  mixed    : MCQ=5, OPEN=5

Correction :
  MCQ  → Python pur, binaire (0 / points_max), zéro LLM
  OPEN → LLM (_evaluate_open_questions)
"""

import hashlib
import uuid
import json
import logging
import os
import re
from collections import Counter
from datetime import datetime, timezone, date
from typing import Optional
from groq import Groq

from dotenv import load_dotenv
#from openai import OpenAI
from app.agents.test_agent.skill_classifier import classify_and_validate_skills, compute_test_strategy
from app.agents.test_agent.correction_validator import (
    validate_candidate_answer,
    validate_test_integrity,
    validate_full_correction,
)
from app.agents.test_agent.template_registry import select_template, build_template_guidance

load_dotenv()
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────
# CONSTANTES
# ─────────────────────────────────────────────────────────────────

OPENROUTER_MODEL_GENERATE = "llama-3.3-70b-versatile"
OPENROUTER_MODEL_EVALUATE  = "llama-3.3-70b-versatile"
MAX_RETRY           = 3
MIN_QUESTION_LENGTH = 60

SCORE_STRONG = 70
SCORE_MEDIUM = 50

# Score qualité minimum pour accepter un test généré (0-100)
# En dessous de ce seuil, le test est rejeté et régénéré automatiquement.
# Valeur 60 : tolère 4 warnings qualité max avant rejet.
# Augmenter à 70-80 pour une qualité plus stricte (plus de retries).
QUALITY_SCORE_MIN = 60

# Structure des 10 questions par test_type (v6.0 — MCQ + OPEN uniquement)
QUESTION_STRUCTURE_10 = {
    "tech"    : {"mcq": 6, "open": 4},
    "platform": {"mcq": 5, "open": 5},
    "mixed"   : {"mcq": 5, "open": 5},
}

# Points par type de question
POINTS_MCQ  = 1
POINTS_OPEN = 4

# Timer par type (minutes)
TIMER_MCQ  = 3
TIMER_OPEN = 8

# Guard temps configurable
_DEV_MODE = os.getenv("TEST_AGENT_DEV_MODE", "0").strip() == "1"
MIN_SUBMISSION_SECONDS = 0 if _DEV_MODE else 60

if _DEV_MODE:
    logger.warning("[test_agent] DEV MODE actif — guard temps 60s désactivé.")

# ─────────────────────────────────────────────────────────────────
# CACHE JOB → TEST
# ─────────────────────────────────────────────────────────────────

_JOB_TEST_CACHE   : dict[str, dict] = {}
_SUBMISSION_STATE : dict[str, dict] = {}

# ─────────────────────────────────────────────────────────────────
# DÉCISION MANAGER — Stockage en mémoire
# ─────────────────────────────────────────────────────────────────

# Décisions manager valides
VALID_MANAGER_DECISIONS = {"VALIDÉ", "À_APPROFONDIR", "NON_RETENU"}

# Stockage { "test_id:application_id" : dict }
_MANAGER_DECISION_STATE : dict[str, dict] = {}


def _make_job_key(
    job_id    : Optional[int],
    role      : str,
    all_skills: list[str],
    seniority : str,
) -> str:
    skills_hash = hashlib.md5(
        str(sorted(s.lower() for s in all_skills)).encode()
    ).hexdigest()[:8]
    if job_id:
        raw = f"job:{job_id}:{seniority.lower()}:{skills_hash}"
    else:
        raw = f"{role.lower()}:{sorted(s.lower() for s in all_skills)}:{seniority.lower()}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def _normalize_role(role: str) -> str:
    """
    Normalise un role string pour éviter les duplications dans les test_id.
    ex: "Full Stack Developer" / "fullstack_developer" / "full-stack" → "full_stack_developer"
    """
    s = role.strip().lower()
    s = re.sub(r'[\s\-/\\]+', '_', s)           # espaces, tirets → underscore
    s = re.sub(r'[^a-z0-9_\u00e0-\u024f]', '', s)  # supprimer chars spéciaux
    s = re.sub(r'_+', '_', s).strip('_')        # nettoyer underscores multiples
    return s[:40]


def _make_test_id(
    role            : str,
    job_id          : Optional[int],
    job_key         : str,
    job_title       : Optional[str] = None,
    force_regenerate: bool          = False,
) -> str:
    today      = date.today().isoformat()   # 10 chars  e.g. "2026-04-24"
    short_hash = uuid.uuid4().hex[:8]       #  8 chars  e.g. "853925ed"

    # RÈGLE ABSOLUE : utiliser UNIQUEMENT le rôle brut passé en input.
    # Jamais job_title, jamais la classification, jamais le template.
    # "Mobile Developer" → "mobile_developer"
    # "Full Stack Developer" → "full_stack_developer"
    s         = role.strip().lower()
    s         = re.sub(r'[\s\-/\\]+', '_', s)
    s         = re.sub(r'[^a-z0-9_]', '', s)
    s         = re.sub(r'_+', '_', s).strip('_')
    role_slug = s

    if job_id:
        raw = f"{role_slug}-job{job_id}-{today}-{short_hash}"
    else:
        raw = f"{role_slug}-{today}-{short_hash}"

    # Garantir que le test_id ne dépasse pas 36 chars (VARCHAR(36) en DB)
    if len(raw) > 36:
        suffix     = f"-{today}-{short_hash}"
        suffix_job = f"-job{job_id}{suffix}" if job_id else suffix
        max_slug   = 36 - len(suffix_job)
        role_slug  = role_slug[:max_slug].rstrip("_")
        raw        = f"{role_slug}{suffix_job}"

    return raw


def _get_cached_test(job_key: str, db=None) -> Optional[dict]:
    if job_key in _JOB_TEST_CACHE:
        logger.info(f"  [test_agent] Cache mémoire HIT pour job_key={job_key}")
        return _JOB_TEST_CACHE[job_key]

    if db:
        try:
            from app.models import Test
            record = (
                db.query(Test)
                .filter(Test.job_key == job_key)
                .order_by(Test.created_at.desc())
                .first()
            )
            if record:
                cached = {
                    "test_id"  : record.test_id,
                    "questions": record.questions,
                    "job_key"  : job_key,
                }
                _JOB_TEST_CACHE[job_key] = cached
                logger.info(f"  [test_agent] Cache DB HIT — test_id={record.test_id}")
                return cached
        except Exception as e:
            try:
                if hasattr(db, 'rollback'):
                    db.rollback()
            except Exception:
                pass
            logger.warning(f"  [test_agent] Cache DB indisponible : {e}")
    return None


def _invalidate_cache(job_key: str, db=None) -> None:
    if job_key in _JOB_TEST_CACHE:
        del _JOB_TEST_CACHE[job_key]
        logger.warning(f"  [test_agent] Cache mémoire INVALIDÉ pour job_key={job_key}")

    if db:
        try:
            from app.models import Test
            record = (
                db.query(Test)
                .filter(Test.job_key == job_key)
                .order_by(Test.created_at.desc())
                .first()
            )
            if record and hasattr(record, 'is_valid'):
                record.is_valid = False
                db.commit()
        except Exception as e:
            try:
                if hasattr(db, 'rollback'):
                    db.rollback()
            except Exception:
                pass
            logger.warning(f"  [test_agent] Invalidation DB échouée : {e}")


# ─────────────────────────────────────────────────────────────────
# CLIENT LLM
# ─────────────────────────────────────────────────────────────────

_openrouter_client = None


def _get_openrouter_client():
    global _openrouter_client
    if _openrouter_client is None:
        api_key = os.getenv("GROQ_AGENT_TEST_MODEL", "")
        if not api_key:
            raise EnvironmentError("GROQ_AGENT_TEST_MODEL manquant dans .env")
        _openrouter_client = Groq(api_key=api_key)   # ← assign la GLOBALE
    return _openrouter_client


# ─────────────────────────────────────────────────────────────────
# PROFILS DE SÉNIORITÉ
# ─────────────────────────────────────────────────────────────────

SENIORITY_PROFILES = {
    "junior": {
        "description" : "0-2 years experience, knows fundamentals",
        "mcq_target"  : "basic syntax usage, common beginner mistakes, simple real-world patterns",
        "open_target" : (
            "a SIMPLE situational question: 'What would you do if...' or "
            "'How would you approach...' with a very concrete, well-defined scenario. "
            "No architecture decisions, no multi-system integration."
        ),
        "expectations": "Simple clear explanation, obvious tool choice with one-sentence justification",
        "open_example": "A dashboard is loading slowly in Power BI. What steps would you take to diagnose and fix the issue?",
        "forbidden"   : (
            "FORBIDDEN for junior OPEN: multi-system integration, migration strategy, "
            "architecture decisions, concurrency."
        ),
    },
    "mid": {
        "description" : "2-5 years, builds features independently",
        "mcq_target"  : "performance, security basics, architecture decisions",
        "open_target" : "a real-world scenario requiring structured reasoning and tool/approach justification",
        "expectations": "Structured answer with clear reasoning and trade-offs",
        "open_example": "Your team needs to centralize reporting for 5 departments with different data sources. How would you approach this with Power BI?",
        "forbidden"   : "",
    },
    "senior": {
        "description" : "5+ years, designs systems, mentors",
        "mcq_target"  : "subtle bugs, concurrency, scale issues seniors catch immediately",
        "open_target" : (
            "compare 2-3 competing tools or approaches, explain trade-offs, "
            "justify choice with real constraints (budget, scale, security, team size)"
        ),
        "expectations": "Deep reasoning, trade-offs, edge cases, scale/security awareness",
        "open_example": "Your team must choose between Azure DevOps, GitHub Actions, and Jenkins for CI/CD. Constraint: Azure-hosted infra, 5 devs, free-tier budget. Which and why?",
        "forbidden"   : (
            "FORBIDDEN for senior OPEN: questions with obvious single answers, "
            "no competing alternatives, no real constraints."
        ),
    },
}

BUSINESS_SCENARIOS = [
    "e-commerce platform (orders, products, payments, inventory)",
    "healthcare appointment scheduling system",
    "fintech transaction processing and fraud detection",
    "SaaS multi-tenant user management system",
    "HR recruitment and applicant tracking system",
    "real-time delivery tracking and logistics",
    "banking core system with audit logs",
    "IoT device data collection and alerting",
    "Dynamics 365 CRM rollout for a 500-user manufacturing enterprise",
    "Power BI dashboard deployment for retail group KPIs (sales, stock, margins)",
    "SharePoint intranet migration for a 200-employee professional services firm",
    "Azure DevOps CI/CD pipeline for a .NET Core microservices project",
    "Power Automate workflow automation for HR approval processes",
    "ERP integration connecting Dynamics 365 to a legacy accounting system",
    "SSIS data migration from on-premise SQL Server to Azure SQL Database",
]


# ─────────────────────────────────────────────────────────────────
# FILTRAGE ET PRIORISATION DES SKILLS (v7.3)
# ─────────────────────────────────────────────────────────────────

# Skills platform qui ne génèrent que des questions "outil/process" inutiles
_BANNED_PLATFORM_SKILLS = {"jira", "confluence", "trello", "notion"}

# Skills platform limités à 1 question max (contexte seulement)
_LIMITED_PLATFORM_SKILLS = {"git", "github", "gitlab", "bitbucket", "svn"}

# Mapping skill → domaine pour le rééquilibrage fullstack
SKILL_DOMAIN_MAP = {
    # Frontend
    "react": "frontend", "vue": "frontend", "angular": "frontend",
    "html": "frontend", "css": "frontend", "javascript": "frontend",
    "typescript": "frontend", "next.js": "frontend", "svelte": "frontend",
    # Backend
    "python": "backend", "java": "backend", "go": "backend", "c#": "backend",
    "node.js": "backend", "fastapi": "backend", "django": "backend",
    "flask": "backend", "spring": "backend", "asp.net": "backend",
    # Database
    "sql": "database", "postgresql": "database", "mysql": "database",
    "mongodb": "database", "redis": "database", "elasticsearch": "database",
    "oracle": "database", "t-sql": "database", "sqlite": "database",
    # Infra / DevOps
    "docker": "infra", "kubernetes": "infra", "terraform": "infra",
    "aws": "infra", "gcp": "infra", "azure": "infra", "linux": "infra",
    "jenkins": "infra", "github actions": "infra", "ansible": "infra",
    "kafka": "infra", "rabbitmq": "infra",
    # Data / BI
    "power bi": "data", "tableau": "data", "spark": "data",
    "airflow": "data", "dbt": "data", "snowflake": "data",
    "databricks": "data", "ssis": "data", "pandas": "data",
    # Microsoft Power Platform / Dynamics (overflow → mixed → doivent être MCQ-eligible)
    "power apps": "platform_tool", "powerapps": "platform_tool",
    "power automate": "platform_tool", "sharepoint": "platform_tool",
    "dynamics 365": "platform_tool", "microsoft dynamics": "platform_tool",
    "dynamics": "platform_tool", "power platform": "platform_tool",
    "copilot studio": "platform_tool", "power virtual agents": "platform_tool",
    # Salesforce ecosystem
    "salesforce": "platform_tool", "pardot": "platform_tool",
    "service cloud": "platform_tool", "sales cloud": "platform_tool",
    "marketing cloud": "platform_tool", "experience cloud": "platform_tool",
    # Google Workspace
    "google workspace": "platform_tool", "looker": "platform_tool",
    "google data studio": "platform_tool", "google analytics": "platform_tool",
}


# ─────────────────────────────────────────────────────────────────
# ECOSYSTEM CAP — anti-surreprésentation d'un même écosystème
# ─────────────────────────────────────────────────────────────────
#
# Problème : si Power Apps / Power Automate / SharePoint sont tous
# convertis en mixed, le moteur peut planifier 3 questions du même
# écosystème Microsoft → test déséquilibré.
#
# Solution : cap de 2 questions max par écosystème (MCQ + OPEN cumulés).
# Le 3ème skill du même écosystème est remplacé par un skill d'un
# autre domaine disponible.

MAX_QUESTIONS_PER_ECOSYSTEM = 2

# Mapping skill → identifiant d'écosystème
_SKILL_ECOSYSTEM: dict[str, str] = {
    # Microsoft Power Platform / Dynamics
    "power apps"         : "msft_power", "powerapps"           : "msft_power",
    "power automate"     : "msft_power", "sharepoint"          : "msft_power",
    "dynamics 365"       : "msft_power", "microsoft dynamics"  : "msft_power",
    "dynamics"           : "msft_power", "power platform"      : "msft_power",
    "copilot studio"     : "msft_power", "power virtual agents": "msft_power",
    "power bi"           : "msft_power",
    # Salesforce
    "salesforce"         : "salesforce", "pardot"              : "salesforce",
    "service cloud"      : "salesforce", "sales cloud"         : "salesforce",
    "marketing cloud"    : "salesforce", "experience cloud"    : "salesforce",
    # Google Workspace
    "google workspace"   : "google_ws",  "looker"              : "google_ws",
    "google data studio" : "google_ws",  "google analytics"    : "google_ws",
    "google sheets"      : "google_ws",  "google forms"        : "google_ws",
}


def _apply_ecosystem_cap(
    plan      : list[str],
    max_per   : int = MAX_QUESTIONS_PER_ECOSYSTEM,
    all_skills: list[str] | None = None,
    eco_used  : dict[str, int] | None = None,
) -> tuple[list[str], dict[str, int]]:
    """
    Remplace les skills en surreprésentation d'écosystème par d'autres
    skills disponibles (hors écosystème saturé).

    Paramètres :
      plan      — liste de skills à corriger (MCQ ou OPEN)
      max_per   — cap max par écosystème (MCQ + OPEN cumulés)
      all_skills — pool de remplacement candidates
      eco_used  — compteurs existants à respecter (pour cumuler MCQ+OPEN)

    Comportement :
      CAS 1 — alternative disponible : remplacer le skill cap-dépassé
      CAS 2 — aucune alternative     : conserver le skill MAIS le marquer
               over_cap=True dans le log ET ne PAS incrémenter eco_used
               → le cap strict n'est pas faussé pour les slots suivants

    Retourne : (plan_corrigé, eco_used_mis_à_jour)
    """
    if not plan:
        return plan, (eco_used or {})

    eco_count : dict[str, int] = dict(eco_used) if eco_used else {}
    result    : list[str]      = []
    over_cap_flags: list[str]  = []   # skills conservés hors-cap (log seulement)

    # Candidats de remplacement : skills sans écosystème reconnu
    fallback: list[str] = []
    if all_skills:
        fallback = [
            sk for sk in all_skills
            if _SKILL_ECOSYSTEM.get(sk.lower()) is None
        ]

    for sk in plan:
        eco = _SKILL_ECOSYSTEM.get(sk.lower())
        if eco:
            count = eco_count.get(eco, 0)
            if count >= max_per:
                # Cap atteint → chercher un remplacement non déjà utilisé
                replacement = next(
                    (fb for fb in fallback if fb not in result), None
                )
                if replacement:
                    logger.info(
                        f"[ecosystem_cap] '{sk}' remplacé par '{replacement}' "
                        f"(écosystème '{eco}' cap={max_per} atteint)"
                    )
                    result.append(replacement)
                else:
                    # CAS 2 : aucune alternative — conserver SANS incrémenter eco_count
                    # → le cap reste strict pour les slots suivants
                    over_cap_flags.append(sk)
                    logger.warning(
                        f"[ecosystem_cap] '{sk}' conservé over_cap "
                        f"(écosystème '{eco}' cap={max_per}, aucune alternative disponible) "
                        f"— eco_count NON incrémenté"
                    )
                    result.append(sk)
                continue
            eco_count[eco] = count + 1
        result.append(sk)

    if over_cap_flags:
        logger.warning(
            f"[ecosystem_cap] Skills over_cap (conservés sans alternative) : "
            f"{over_cap_flags} — vérifier la diversité du profil RH"
        )

    return result, eco_count


def _apply_ecosystem_cap_mcq(
    plan      : list[str],
    max_per   : int = MAX_QUESTIONS_PER_ECOSYSTEM,
    all_skills: list[str] | None = None,
) -> tuple[list[str], dict[str, int]]:
    """
    Applique le cap sur le plan MCQ seul (sans eco_used initial).
    Retourne (plan_corrigé, eco_used) pour transmission à la phase OPEN.
    """
    return _apply_ecosystem_cap(plan, max_per=max_per, all_skills=all_skills, eco_used=None)


def _is_platform_dominant(platform_skills: list[str]) -> bool:
    """
    Détecte un profil "platform-dominant" : stack cohérente d'outils métier
    (ex: Microsoft ecosystem — Dynamics, Power Apps, Power Automate, SharePoint).

    Conditions :
      - Au moins 3 platform skills déclarés
      - Au moins 3 appartiennent au même écosystème métier reconnu

    Écosystèmes reconnus :
      Microsoft Power/Dynamics : dynamics, power apps, power automate, sharepoint,
                                  power bi, power platform, copilot studio
      Salesforce               : salesforce, pardot, service cloud, sales cloud,
                                  marketing cloud, tableau
      Google Workspace         : google workspace, looker, google data studio,
                                  google analytics, bigquery (admin)
      Atlassian                : jira, confluence, bitbucket, trello (mais bannis → peu probable)
    """
    if len(platform_skills) < 3:
        return False

    _ECOSYSTEMS = [
        # Microsoft Power Platform / Dynamics
        {"dynamics", "dynamics 365", "microsoft dynamics", "power apps", "powerapps",
         "power automate", "sharepoint", "power bi", "power platform",
         "copilot studio", "power virtual agents"},
        # Salesforce
        {"salesforce", "pardot", "service cloud", "sales cloud",
         "marketing cloud", "experience cloud", "tableau"},
        # Google
        {"google workspace", "looker", "google data studio", "google analytics",
         "bigquery", "google sheets", "google forms"},
    ]

    names_lower = [s.lower() for s in platform_skills]

    for ecosystem in _ECOSYSTEMS:
        matches = sum(
            any(kw in name for kw in ecosystem)
            for name in names_lower
        )
        if matches >= 3:
            return True

    return False


def _filter_and_prioritize_skills(
    coding_skills   : list[str],
    platform_skills : list[str],
    mixed_skills    : list[str],
) -> tuple[list[str], list[str], list[str]]:
    """
    Filtre et priorise les skills avant classification :
      1. Supprime les skills platform inutiles (jira, confluence…)
      2. Limite les skills git-like à 1 max
      3. Priorise coding + mixed comme core ; platform en support max 1
         EXCEPTION — profil platform-dominant (stack écosystème ≥ 3 outils) :
           → 1er skill conservé en "platform"
           → les suivants convertis en "mixed" (pas perdus, évalués différemment)

    Règle métier :
      - On ne génère JAMAIS plus d'1 question de type platform pur
      - Mais les tools d'un écosystème cohérent (Power Platform, Salesforce…)
        méritent d'être évalués → conversion en mixed au lieu de suppression
    """
    # 1. Supprimer les skills bannis
    platform_skills = [s for s in platform_skills if s.lower() not in _BANNED_PLATFORM_SKILLS]
    coding_skills   = [s for s in coding_skills   if s.lower() not in _BANNED_PLATFORM_SKILLS]
    mixed_skills    = [s for s in mixed_skills     if s.lower() not in _BANNED_PLATFORM_SKILLS]

    # 2. Limiter git-like à 1 occurrence au total
    git_like_found = False
    def _keep_git(s):
        nonlocal git_like_found
        if s.lower() in _LIMITED_PLATFORM_SKILLS:
            if git_like_found:
                return False
            git_like_found = True
        return True

    coding_skills   = [s for s in coding_skills   if _keep_git(s)]
    mixed_skills    = [s for s in mixed_skills     if _keep_git(s)]
    platform_skills = [s for s in platform_skills if _keep_git(s)]

    # 3. Règle platform : max 1 — avec exception écosystème
    core_platform = [s for s in platform_skills if s.lower() not in _LIMITED_PLATFORM_SKILLS]

    if _is_platform_dominant(core_platform):
        # Profil platform-dominant détecté :
        # → garder 1 seul skill en "platform" (le plus représentatif = premier)
        # → convertir les suivants en "mixed" pour qu'ils soient évalués
        platform_final  = core_platform[:1]
        overflow        = core_platform[1:]
        mixed_skills    = mixed_skills + overflow   # ajout en fin de mixed

        logger.info(
            f"[skill_filter] Profil platform-dominant détecté — "
            f"platform conservé : {platform_final} | "
            f"convertis en mixed : {overflow}"
        )
    else:
        # Règle standard : max 1 platform, le reste est supprimé
        platform_final = core_platform[:1]

        dropped = [s for s in core_platform[1:] if s not in platform_final]
        if dropped:
            logger.info(
                f"[skill_filter] Platform réduit : {core_platform} → {platform_final} "
                f"(supprimés car profil non platform-dominant : {dropped})"
            )

    platform_skills = platform_final
    return coding_skills, platform_skills, mixed_skills


def _enforce_skill_distribution(all_skills: list[str]) -> dict[str, list[str]]:
    """
    Calcule la distribution réelle des skills par domaine.
    Utile pour le logging et la vérification de rééquilibrage fullstack.
    """
    buckets: dict[str, list[str]] = {
        "frontend": [], "backend": [], "database": [],
        "infra": [], "data": [], "platform_tool": [], "other": [],
    }
    for s in all_skills:
        domain = SKILL_DOMAIN_MAP.get(s.lower(), "other")
        buckets[domain].append(s)
    return buckets



# ─────────────────────────────────────────────────────────────────
# ANTI-GENERIC GUARD (v7.4)
# ─────────────────────────────────────────────────────────────────
# All patterns are anchored to the START of the question (^).
# Rationale: the prompt requires scenario openers like "Your team...",
# "A developer...", "Given this code...". A legitimate scenario question
# may contain "what is the best approach" mid-sentence — that is NOT generic.
# We only reject questions whose OPENING is a generic/definition pattern.

GENERIC_PATTERNS = [
    r"^which tool\b",
    r"^what is the best\b",
    r"^which library\b",
    r"^define\b",
    r"^best practice",
    r"^what is the purpose of",
    r"^what is the role of",
    r"^what is the primary benefit",
    r"^which of the following is true",
]

_GENERIC_RE = re.compile(
    "|".join(GENERIC_PATTERNS), re.IGNORECASE
)


def _is_generic_question(q_text: str) -> bool:
    """
    Détecte les questions génériques ou trop courtes.
    Retourne True si la question doit être rejetée.
    """
    text = q_text.strip()
    if len(text.split()) < 12:
        return True   # trop courte → suspecte
    if _GENERIC_RE.search(text):
        return True
    return False


def _post_generation_generic_check(questions: list[dict]) -> list[str]:
    """
    Post-génération : détecte les questions génériques et retourne les warnings.
    """
    warnings_out = []
    for q in questions:
        q_text = q.get("question", "")
        if _is_generic_question(q_text):
            warnings_out.append(
                f"Q{q.get('id', '?')} [{q.get('type', '?').upper()}]: "
                f"question générique ou trop courte — "
                f"'{q_text[:80]}'"
            )
    return warnings_out


# ─────────────────────────────────────────────────────────────────
# SKILL DISTRIBUTION ENGINE (v8.0)
# ─────────────────────────────────────────────────────────────────
#
# Garantit une distribution équilibrée des skills sur les MCQ
# selon le domaine (frontend/backend/database/infra/data/other)
# et la séniorité du candidat.
#
# Pourquoi c'est nécessaire :
#   Sans ce moteur, le round-robin naïf peut générer 3 questions
#   PostgreSQL et 0 React sur un profil fullstack — le test ne
#   reflète pas le poste réel.
#
# Architecture :
#   1. _group_skills_by_domain()  → buckets par domaine
#   2. _target_mcq_distribution() → nb questions par domaine selon séniorité
#   3. _build_mcq_skill_plan()    → liste ordonnée des skills MCQ
#   4. _assign_skills_to_questions() → intègre le plan dans strategy
#   5. validate_mcq_skill_distribution() → validation post-génération

# Cibles MCQ par domaine selon séniorité
# Total = n_mcq (5 ou 6 selon test_type)
# Les domaines absents du profil sont ignorés silencieusement.
_MCQ_TARGET_DISTRIBUTION: dict[str, dict[str, int]] = {
    "junior": {
        "frontend"     : 2, "backend"      : 2, "database": 1,
        "infra"        : 1, "data"         : 1, "other"   : 1,
        "platform_tool": 1,   # Power Apps, SharePoint, etc. — au moins 1 MCQ si présent
    },
    "mid": {
        "frontend"     : 2, "backend"      : 2, "database": 1,
        "infra"        : 1, "data"         : 1, "other"   : 1,
        "platform_tool": 1,
    },
    "senior": {
        "frontend"     : 1, "backend"      : 2, "database": 1,
        "infra"        : 2, "data"         : 1, "other"   : 1,
        "platform_tool": 1,
    },
}


def _group_skills_by_domain(all_skills: list[str]) -> dict[str, list[str]]:
    """
    Groupe les skills par domaine en utilisant SKILL_DOMAIN_MAP.
    Retourne un dict {domain: [skill, ...]} — domaines vides exclus.
    """
    buckets: dict[str, list[str]] = {}
    for sk in all_skills:
        domain = SKILL_DOMAIN_MAP.get(sk.lower(), "other")
        buckets.setdefault(domain, [])
        if sk not in buckets[domain]:
            buckets[domain].append(sk)
    return buckets


def _build_mcq_skill_plan(
    groups    : dict[str, list[str]],
    seniority : str,
    n_mcq     : int,
    all_skills: list[str],
) -> list[str]:
    """
    Construit la liste ordonnée des skills pour les questions MCQ.

    Algorithme :
      1. Lire la distribution cible pour la séniorité
      2. Pour chaque domaine présent dans groups, allouer min(target, available) slots
      3. Si total < n_mcq → compléter en round-robin sur all_skills
      4. Si total > n_mcq → tronquer en priorisant les domaines les plus représentés
      5. Résultat final shufflé pour éviter la répétition de domaine en séquence

    Garanties :
      - Chaque skill de all_skills apparaît au moins 1 fois si n_mcq >= len(all_skills)
      - Jamais de skill hors all_skills dans le plan
      - Toujours exactement n_mcq éléments retournés
    """
    import random as _random

    targets = _MCQ_TARGET_DISTRIBUTION.get(seniority, _MCQ_TARGET_DISTRIBUTION["mid"])
    plan: list[str] = []

    # Ordre de priorité des domaines (les plus importants en premier)
    domain_priority = ["backend", "frontend", "infra", "database", "data", "platform_tool", "other"]

    # Étape 1 — remplir selon la distribution cible
    for domain in domain_priority:
        available = groups.get(domain, [])
        if not available:
            continue
        quota = targets.get(domain, 1)
        # Cycler sur les skills du domaine pour ne pas mettre 2x le même
        for i in range(quota):
            plan.append(available[i % len(available)])
        if len(plan) >= n_mcq:
            break

    # Étape 2 — si on manque de slots, compléter en round-robin
    if len(plan) < n_mcq:
        idx = 0
        while len(plan) < n_mcq:
            sk = all_skills[idx % len(all_skills)]
            plan.append(sk)
            idx += 1

    # Étape 3 — tronquer si trop de slots
    plan = plan[:n_mcq]

    # Étape 4 — garantir que chaque skill est couvert au moins 1 fois
    # (remplacer des doublons si nécessaire)
    plan_set  = set(plan)
    missing   = [sk for sk in all_skills if sk not in plan_set]
    if missing:
        counts = Counter(plan)
        duplicates = [sk for sk, c in sorted(counts.items(), key=lambda x: -x[1]) if c > 1]
        for miss_sk in missing:
            if not duplicates:
                break
            dup_sk = duplicates.pop(0)
            # Remplacer la dernière occurrence du duplicaté
            for i in range(len(plan) - 1, -1, -1):
                if plan[i] == dup_sk:
                    plan[i] = miss_sk
                    break

    # Étape 5 — cap écosystème : max MAX_QUESTIONS_PER_ECOSYSTEM (MCQ+OPEN cumulés)
    # Retourne aussi eco_used pour transmission à la phase OPEN
    plan, _mcq_eco_used = _apply_ecosystem_cap_mcq(plan, max_per=MAX_QUESTIONS_PER_ECOSYSTEM, all_skills=all_skills)

    # Étape 6 — shuffle pour éviter pattern frontend→backend→infra répété
    _random.shuffle(plan)

    logger.info(
        f"[skill_dist] MCQ plan ({n_mcq} slots) → {plan} "
        f"| seniority={seniority}"
    )
    return plan, _mcq_eco_used


def _validate_mcq_skill_distribution(
    questions     : list[dict],
    expected_plan : list[str],
) -> tuple[bool, str]:
    """
    Valide que les skills MCQ générés correspondent au plan attendu.
    Compare les listes triées (l'ordre peut différer).

    Retourne (valid, error_message).
    """
    actual = [q["skill"] for q in questions if q.get("type") == "mcq"]
    if sorted(actual) != sorted(expected_plan):
        diff_missing = sorted(set(expected_plan) - set(actual))
        diff_extra   = sorted(set(actual) - set(expected_plan))
        return False, (
            f"Distribution MCQ incorrecte — "
            f"attendu={sorted(expected_plan)} obtenu={sorted(actual)} | "
            f"manquants={diff_missing} extras={diff_extra}"
        )
    return True, ""


def _assign_skills_to_questions(strategy: dict, seniority: str = "mid") -> dict:
    """
    Distribue les skills sur les questions MCQ et OPEN.

    v8.0 — Skill Distribution Engine :
      - MCQ : distribution intelligente par domaine via _build_mcq_skill_plan()
        → garantit l'équilibre frontend/backend/database/infra selon séniorité
      - OPEN : round-robin sur tous les skills pour couvrir chaque skill 1 fois
      - Injection forcée des skills manquants dans les deux listes

    Le plan MCQ est stocké dans strategy["_mcq_skill_plan"] pour être
    réutilisé par la validation post-génération dans _generate_questions().
    """
    all_skills = strategy.get("all_skills", [])
    structure  = strategy.get("question_structure", {})
    n_mcq      = structure.get("mcq",  0)
    n_open     = structure.get("open", 0)

    if not all_skills:
        return {"mcq": ["general"] * n_mcq, "open": ["general"] * n_open}

    # ── MCQ : distribution par domaine ───────────────────────────
    groups              = _group_skills_by_domain(all_skills)
    mcq_plan, eco_used  = _build_mcq_skill_plan(groups, seniority, n_mcq, all_skills)

    # Stocker le plan dans strategy pour validation post-génération
    strategy["_mcq_skill_plan"] = mcq_plan

    # ── OPEN : round-robin pour couvrir tous les skills ───────────
    # Cap écosystème appliqué globalement (MCQ + OPEN cumulés)
    open_plan  : list[str] = []
    covered    = set(mcq_plan)   # les skills déjà couverts en MCQ
    # eco_used récupéré directement depuis _build_mcq_skill_plan
    # → contient déjà les compteurs réels post-cap MCQ (over_cap NON comptés)
    # → garantit que le cap MCQ+OPEN est calculé sur les vrais slots MCQ

    for i in range(n_open):
        uncovered = [s for s in all_skills if s not in covered]

        # Filtrer les skills dont l'écosystème n'a pas atteint le cap (cumulé MCQ+OPEN)
        eco_ok = [
            s for s in uncovered
            if eco_used.get(_SKILL_ECOSYSTEM.get(s.lower()), 0) < MAX_QUESTIONS_PER_ECOSYSTEM
        ]

        if eco_ok:
            sk = eco_ok[0]
            eco = _SKILL_ECOSYSTEM.get(sk.lower())
            if eco:
                eco_used[eco] = eco_used.get(eco, 0) + 1   # incrémenter cap réel
        elif uncovered:
            # CAS 2 : aucune alternative hors-écosystème saturé
            # → conserver le skill SANS incrémenter eco_used (over_cap non compté)
            sk = uncovered[0]
            logger.warning(
                f"[ecosystem_cap] OPEN slot {i+1} : '{sk}' conservé over_cap "
                f"(aucune alternative disponible) — eco_used NON incrémenté"
            )
        else:
            sk = all_skills[i % len(all_skills)]

        covered.add(sk)
        open_plan.append(sk)

    # Injection forcée des skills manquants (pas couverts ni MCQ ni OPEN)
    missing = [s for s in all_skills if s not in covered]
    if missing:
        logger.warning(f"[skill_dist] Skills non couverts : {missing} — injection forcée")
        counts     = Counter(mcq_plan + open_plan)
        duplicates = [sk for sk, c in counts.items() if c > 1]
        for miss_sk in missing:
            if not duplicates:
                break
            dup_sk = duplicates.pop(0)
            # Chercher dans OPEN d'abord, puis MCQ
            for lst in (open_plan, mcq_plan):
                if dup_sk in lst:
                    lst[lst.index(dup_sk)] = miss_sk
                    covered.add(miss_sk)
                    break

    logger.info(
        f"[skill_assign] Distribution — mcq={mcq_plan} open={open_plan} "
        f"| eco_counts={eco_used}"
    )
    return {"mcq": mcq_plan, "open": open_plan}


# ─────────────────────────────────────────────────────────────────
# CONSTRUCTION DU PROMPT DE GÉNÉRATION
# ─────────────────────────────────────────────────────────────────

def _build_mcq_templates(mcq_skills: list[str], all_skills: list[str], seniority: str) -> str:
    def _diff(i: int) -> str:
        n = len(mcq_skills)
        if seniority == "junior":
            # Progression : easy sur les 3 premières, medium sur les 2 dernières
            # Évite le test 100% flat qui ne discrimine pas les candidats
            return "medium" if (n >= 3 and i >= n - 2) else "easy"
        if seniority == "mid":
            return "easy" if i == 0 else "medium"
        return "hard" if i == len(mcq_skills) - 1 else "medium"

    parts = []
    for i, sk in enumerate(mcq_skills):
        skill_label = sk  # toujours un skill réel (plus jamais "any")
        sep = "" if i == 0 else ","
        parts.append(f"""{sep}
    {{
      "id": {i + 1},
      "type": "mcq",
      "skill": "{skill_label}",
      "difficulty": "{_diff(i)}",
      "question": "Concrete situational question min 80 chars. NEVER start with 'What is' or 'What is the primary benefit'. Use: 'Your team...', 'A developer...', 'You notice...', 'Given this code...'. MANDATORY: include ONE specific constraint (budget/latency/team size/compliance) that makes exactly ONE answer correct and the other 3 clearly wrong.",
      "code_snippet": "ONLY include code that is REFERENCED in the question. CRITICAL: the correct answer must NEVER appear verbatim in the code_snippet — if the answer is visible in the snippet, rewrite the question to test something else about the code. Leave empty string if no code needed.",
      "options": [
        "The correct answer — clearly right ONLY given the stated constraint",
        "Plausible wrong answer 1 — reasonable in general but wrong given the constraint",
        "Plausible wrong answer 2 — reasonable in general but wrong given the constraint",
        "Plausible wrong answer 3 — clearly wrong"
      ],
      "answer": "The correct answer — clearly right ONLY given the stated constraint (must EXACTLY match one option)",
      "points": {POINTS_MCQ},
      "explanation": "Why this is correct given the constraint and why each other option fails"
    }}""")
    return "".join(parts)


def _build_open_templates(
    open_skills: list[str],
    all_skills : list[str],
    seniority  : str,
    n_mcq      : int,
) -> str:
    if not open_skills:
        return ""

    ASPECTS = [
        "tool selection with cost and scale constraints",
        "integration with existing infrastructure",
        "security and compliance requirements",
        "performance and diagnosis approach",
        "team adoption and learning curve",
        "migration from a legacy system",
        "governance and best practices",
        "troubleshooting methodology",
    ]

    def _diff(i: int, total: int) -> str:
        if seniority == "junior":
            # Progression : easy sur les premières, medium sur la dernière
            # La valeur est aussi injectée dans le hint pour que le LLM la respecte
            return "medium" if (total >= 3 and i == total - 1) else "easy"
        if seniority == "mid":
            return "hard" if (i == total - 1 and total > 1) else "medium"
        return "medium" if i == 0 else "hard"

    parts = []
    for i, sk in enumerate(open_skills):
        q_id = n_mcq + i + 1
        diff = _diff(i, len(open_skills))
        aspect = ASPECTS[i % len(ASPECTS)]

        if sk == "any":
            skill_field = "[chosen_skill]"
            skill_label = (
                f"[FREE CHOICE from: {', '.join(all_skills) if all_skills else 'role skills'}. "
                f"Must differ from other OPEN questions.]"
            )
        else:
            skill_field = sk
            skill_label = sk

        if seniority == "senior":
            q_hint = (
                f"SKILL={skill_label} ASPECT={aspect} — "
                f"Present a comparison: 'Your team evaluates [Tool A] vs [Tool B] (vs [C]) "
                f"for [specific need]. Constraint: [ONE real constraint]. Which do you recommend and why?' "
                f"Name 2-3 REAL tools. Include one hard constraint. Min 120 chars."
            )
        elif seniority == "mid":
            q_hint = (
                f"SKILL={skill_label} ASPECT={aspect} — "
                f"Present a CONCRETE DILEMMA: 'Your team must choose between [Approach A] and [Approach B] "
                f"for [specific need in the scenario]. Constraint: [ONE hard constraint — budget, deadline, "
                f"team size, compliance, or scale]. Which do you choose and why?' "
                f"Name REAL tools/approaches. Force a binary or ternary decision. Min 130 chars. "
                f"No code writing required — focus on reasoning, justification, and trade-offs."
            )
        else:
            # Varier le TYPE de problème par position pour éviter le template répétitif
            _is_last = (i == len(open_skills) - 1 and len(open_skills) >= 3)
            _JUNIOR_PROBLEM_TYPES = [
                # i=0 : Diagnostic — identifier la cause d'un symptôme
                (
                    f"SKILL={skill_label} ASPECT={aspect} — "
                    f"DIAGNOSIS question: 'You notice [concrete symptom] in your {skill_label} setup. "
                    f"Constraint: [ONE real constraint — no access to logs / limited time / no admin rights]. "
                    f"How would you identify the root cause and fix it?' "
                    f"Symptom must be specific (slow load, wrong data, connection refused…). Min 110 chars."
                ),
                # i=1 : Choix d'approche — comparer 2 options simples
                (
                    f"SKILL={skill_label} ASPECT={aspect} — "
                    f"APPROACH CHOICE question: 'You need to [accomplish specific task] using {skill_label}. "
                    f"You are considering [Approach A] or [Approach B]. "
                    f"Constraint: [ONE real constraint — deadline / limited budget / team skill level]. "
                    f"Which would you choose and why?' "
                    f"Name REAL approaches. Keep it simple for junior level. Min 110 chars."
                ),
                # i=2 : Optimisation — améliorer ce qui fonctionne déjà
                (
                    f"SKILL={skill_label} ASPECT={aspect} — "
                    f"OPTIMIZATION question: 'Your {skill_label} setup works but [specific performance issue]. "
                    f"Constraint: [ONE measurable constraint — response time / file size / memory limit]. "
                    f"What changes would you make to improve performance?' "
                    f"Issue must be concrete and measurable. Min 110 chars."
                ),
                # i=3 : Prévention — empêcher un problème futur
                (
                    f"SKILL={skill_label} ASPECT={aspect} — "
                    f"PREVENTION question: 'Your team just experienced [specific incident] with {skill_label}. "
                    f"Constraint: [ONE real constraint — no downtime allowed / budget frozen / small team]. "
                    f"What would you put in place to prevent this from happening again?' "
                    f"Incident must be realistic for junior level. Min 110 chars."
                ),
                # i=4+ : Diagnostic (cycle)
                (
                    f"SKILL={skill_label} ASPECT={aspect} — "
                    f"DIAGNOSIS question: 'A colleague reports that [concrete symptom] in the {skill_label} environment. "
                    f"Constraint: [ONE real constraint — read-only access / no restart possible / tight deadline]. "
                    f"Walk through your troubleshooting steps.' "
                    f"Be specific about the symptom. Min 110 chars."
                ),
            ]
            q_hint = _JUNIOR_PROBLEM_TYPES[i % len(_JUNIOR_PROBLEM_TYPES)]
            # Si c'est la dernière OPEN et que difficulty=medium, le signaler au LLM
            if _is_last:
                q_hint = (
                    f"[DIFFICULTY=MEDIUM — this is the final and most challenging question for this junior test] "
                    + q_hint
                    + f" This question should be slightly harder: add a second constraint or require "
                    f"the candidate to compare two realistic approaches before choosing one."
                )

        parts.append(f""",
    {{
      "id": {q_id},
      "type": "open",
      "skill": "{skill_field}",
      "difficulty": "{diff}",
      "question": "{q_hint}",
      "answer_criteria": [
        "C1 - approach relevance: the proposed approach or tool fits the described need",
        "C2 - justification: candidate explains WHY this choice is appropriate with precise reasons",
        "C3 - constraint addressed: the explicit constraint stated in the question is identified and handled",
        "C4 - tradeoff awareness: candidate mentions at least one alternative or trade-off",
        "C5 - clarity: the answer is structured, readable, and free of contradictions"
      ],
      "expected_answer": "Ideal approach for {skill_field}: describe key reasoning, approach, and trade-offs.",
      "points": {POINTS_OPEN}
    }}""")

    return "".join(parts)


def _retry_escalation_block(retry_attempt: int) -> str:
    """
    Returns an extra warning injected at the end of the prompt on retry attempts >= 1.
    Escalates the message on each retry to maximize LLM compliance.
    This solves the persistent "définition pure détectée" rejection loop by explicitly
    telling the LLM what it did wrong and enforcing scenario openers.
    """
    if retry_attempt == 0:
        return ""

    base = """

════════════════════════════════════════════════════
⚠️  RETRY INSTRUCTION — PREVIOUS ATTEMPT WAS REJECTED
════════════════════════════════════════════════════

The previous generation was REJECTED because one or more MCQ questions were flagged
as "pure definition questions". This means the question started with or was primarily
phrased as "What is X?", "Define X", or "What is the purpose of X?" — these forms
are FORBIDDEN for MCQ questions.

MANDATORY FIX — Every single MCQ question MUST:
  1. Start with a scenario opener: "Your team...", "A developer...", "You notice...",
     "Given this code...", "In the following snippet...", "A colleague reports..."
  2. Describe a concrete situation, bug, constraint, or code context FIRST.
  3. Only THEN ask what the candidate should do / what the output is / what the error is.

✅ CORRECT (scenario-first):
  "Your team deploys a Node.js API on AWS Lambda. After switching to a PostgreSQL RDS
   connection pool of 5, you notice connection timeout errors under 50 concurrent users.
   What is the most likely cause?"

❌ REJECTED (definition-first):
  "What is connection pooling in PostgreSQL?"
  "What is the purpose of AWS Lambda?"
  "What is the best practice for Node.js error handling?"

Apply this rule to EVERY MCQ question without exception."""

    if retry_attempt >= 2:
        base += """

🔴 CRITICAL — This is attempt #{attempt}. STRICTLY follow these rules or the test
will be rejected again. DO NOT start any MCQ question with "What is", "What are",
"What does", "Define", "Which of the following is true", or any variant.
EVERY MCQ must open with a real-world scenario sentence before any question mark.""".format(
            attempt=retry_attempt + 1
        )

    return base


def _build_generation_prompt(
    role             : str,
    strategy         : dict,
    seniority        : str,
    job_key          : str,
    retry_attempt    : int = 0,
    skill_assignment : dict | None = None,
) -> str:
    profile    = SENIORITY_PROFILES.get(seniority, SENIORITY_PROFILES["mid"])
    test_type  = strategy["test_type"]
    all_skills = strategy.get("all_skills", [])

    base_seed = int(job_key, 16) % 10000
    seed      = (base_seed + retry_attempt * 3571) % 10000

    # Scénario métier adapté aux skills — sélection par DOMINANCE, pas par OR simple.
    # Règle clé : docker seul ne déclenche pas un scénario CI/CD si les skills
    # dominants sont data/BI/python. Le groupe avec le plus de matches l'emporte.
    _SCENARIO_KEYWORDS = [
        ({"power bi", "sql", "ssis", "tableau", "data analyst",
          "python", "airflow", "spark", "dbt", "snowflake", "databricks"}, [0, 1, 4, 5, 9, 14]),
        ({"dynamics 365", "crm", "erp", "salesforce"},                      [8, 13]),
        ({"power automate", "sharepoint", "power apps", "m365"},             [10, 12]),
        ({"azure devops", "ci/cd", "jenkins", "github actions"},             [11]),
        ({"azure", "aws", "gcp", "cloud", "terraform", "kubernetes"},        [7, 11]),
    ]
    skill_set = {s.lower() for s in all_skills}

    best_group_idxs: list[int] = []
    best_group_count = 0
    for kws, idxs in _SCENARIO_KEYWORDS:
        count = len(skill_set & kws)
        if count > best_group_count:
            best_group_count = count
            best_group_idxs = list(idxs)
        elif count == best_group_count and count > 0:
            best_group_idxs = list(dict.fromkeys(best_group_idxs + idxs))

    # Garde-fou : si >= 2 skills data/BI présents, exclure le scénario DevOps/CI-CD (index 11)
    # pour éviter que "docker" seul contamine toutes les questions avec un contexte Azure DevOps
    _DATA_BI_SKILLS = {"python", "sql", "power bi", "airflow", "spark", "dbt",
                       "snowflake", "tableau", "ssis", "databricks"}
    if len(skill_set & _DATA_BI_SKILLS) >= 2:
        best_group_idxs = [i for i in best_group_idxs if i != 11]

    if best_group_idxs:
        scenario = BUSINESS_SCENARIOS[best_group_idxs[(base_seed + retry_attempt) % len(best_group_idxs)]]
    else:
        scenario = BUSINESS_SCENARIOS[(base_seed + retry_attempt) % 8]

    skill_assignment = skill_assignment or _assign_skills_to_questions(strategy, seniority=seniority)
    mcq_skills       = skill_assignment["mcq"]
    open_skills      = skill_assignment["open"]
    n_questions      = len(mcq_skills) + len(open_skills)

    # Structure lines pour le prompt
    def _diff_mcq(i):
        n = len(mcq_skills)
        if seniority == "junior":
            return "medium" if (n >= 4 and i == n - 1) else "easy"
        if seniority == "mid":
            return "easy" if i == 0 else "medium"
        return "hard" if i == n - 1 else "medium"

    def _diff_open(i, total):
        if seniority == "junior":
            return "easy"
        if seniority == "mid":
            return "hard" if (i == total - 1 and total > 1) else "medium"
        return "medium" if i == 0 else "hard"

    struct_lines = []
    q_id = 1
    for i, sk in enumerate(mcq_skills):
        struct_lines.append(f'  Q{q_id}: MCQ  | skill="{sk}" | points={POINTS_MCQ} | difficulty={_diff_mcq(i)}')
        q_id += 1
    for i, sk in enumerate(open_skills):
        struct_lines.append(f'  Q{q_id}: OPEN | skill="{sk}" | points={POINTS_OPEN} | difficulty={_diff_open(i, len(open_skills))}')
        q_id += 1

    mcq_templates  = _build_mcq_templates(mcq_skills, all_skills, seniority)
    open_templates = _build_open_templates(open_skills, all_skills, seniority, n_mcq=len(mcq_skills))

    # ── Template guidance (v7.0) ──────────────────────────────────
    # Sélectionner le template selon les skills pour guider le LLM
    # sur les TYPES de questions à générer (pas les questions elles-mêmes)
    template_name, template = select_template(all_skills, seniority)
    template_guidance = build_template_guidance(
        template_name=template_name,
        template=template,
        seniority=seniority,
        n_mcq=len(mcq_skills),
        n_open=len(open_skills),
    )
    logger.info(f"  [test_agent] Template sélectionné : {template_name.upper()} pour skills={all_skills}")

    return f"""You are a senior technical lead designing a REAL interview test.

TEST CONTEXT:
  Role      : {role}
  Seniority : {seniority} ({profile['description']})
  Test type : {test_type.upper()}
  Scenario  : {scenario}
  Seed      : {seed}

SKILLS TO COVER: {', '.join(all_skills)}

⚠️  SKILL INTEGRITY RULE — MOST CRITICAL RULE IN THIS PROMPT:
The "skill" field in EVERY question MUST be EXACTLY one of: {', '.join(all_skills)}

COPY-PASTE RULE: Copy the skill name CHARACTER BY CHARACTER from the list above.
DO NOT retype it from memory — you will make spelling mistakes.
DO NOT abbreviate, truncate, or paraphrase any skill name.
DO NOT use acronyms or variants (e.g. "k8s" instead of "kubernetes", "js" instead of "javascript").

❌ FORBIDDEN examples (these will cause the test to be REJECTED and regenerated):
   "pyho"       → must be "python"
   "powe bi"    → must be "power bi"
   "sharepoi"   → must be "sharepoint"
   "azue"       → must be "azure devops"
   Any spelling mistake in a skill name → REJECTED

✅ CORRECT: Copy exactly from this list → {', '.join(all_skills)}

If you cannot generate a question for a skill, reuse an existing skill from the list — NEVER create a new one.

════════════════════════════════════════════════════
MANDATORY QUESTION STRUCTURE — DO NOT CHANGE
════════════════════════════════════════════════════

{chr(10).join(struct_lines)}

Total: {n_questions} questions exactly.

{template_guidance}

════════════════════════════════════════════════════
QUESTION TYPE RULES
════════════════════════════════════════════════════

MCQ (QCM — Multiple Choice) — STRICT TECHNICAL RULES:
  ⚠️  AT LEAST 50% OF MCQ MUST include a real code snippet (non-empty "code_snippet" field)
  ⚠️  AT LEAST 30% OF MCQ MUST be a debugging or bug-detection question (candidate finds the error)
  ⚠️  Questions about which tool/library to CHOOSE are FORBIDDEN unless the choice is technically forced
  ⚠️  Pure theoretical or definition questions are FORBIDDEN
  ⚠️  LAZY OPTIONS ARE FORBIDDEN — never recycle the same 4 generic options across questions:
      ❌ BANNED option set: "Improved security" / "Faster processing" / "Simplified X" / "Reduced costs"
      ❌ BANNED: 3 or more options starting with the same generic verb (Improved / Faster / Simplified / Reduced / Better / Enhanced)
      ✅ REQUIRED: each option must be a SPECIFIC technical action, value, config, or code construct
         Good: "Set shared_buffers to 512MB" / "Create a non-clustered index on country" / "Use asyncio.gather()"
  - EXACTLY 4 answer choices — no more, no fewer
  - ✅ Only ONE option is correct — ADD A CONSTRAINT that makes exactly one correct.
  - ❌ BANNED: ambiguous questions where 2+ options are both valid best practices
  - ❌ BANNED: "What is X?" / "Define X" — pure definitions are FORBIDDEN
  - ❌ BANNED: "Which tool should you use for X?" with no technical constraint
  - ✅ REQUIRED openers: "Your team...", "A developer...", "You notice...", "Given this code..."
  - The 3 wrong options must be CLEARLY wrong given the constraints — not just "less optimal"
  - Target: {profile['mcq_target']}

  CODE SNIPPET RULE: Put code in "code_snippet" field as a plain string (no backticks).
  Leave "code_snippet": "" when no code is needed.
  NEVER embed raw code inside the "question" field.
  CRITICAL: The correct answer must NEVER appear verbatim in the code_snippet.

OPEN (Open-ended situational question) — MANDATORY STRUCTURE:
  Each OPEN question MUST follow this structure:
    Context: [real system / company size / tech stack]
    Problem: [concrete issue with at least ONE numeric constraint: 10k users, 200ms latency, 2GB file...]
    Tasks: 2-3 sub-questions the candidate must answer (approach, trade-off, justification)

  STRICT RULES FOR OPEN:
  - Must include at least ONE numeric constraint (e.g. 10,000 users, 200ms, 2GB RAM, 5 devs)
  - Must involve at least 2 different aspects of the skill (not just "how would you fix it")
  - Must require trade-offs or reasoning between named alternatives
  - No code writing required — focus on reasoning, diagnosis, and tool choice
  - Target: {profile['open_target']}
  - Good OPEN example: "{profile['open_example']}"
  {f"- {profile['forbidden']}" if profile.get('forbidden') else ""}
  {"SENIOR RULE: Present 2-3 NAMED competing tools/approaches. Candidate MUST choose and justify. Include one hard constraint." if seniority == "senior" else ""}

════════════════════════════════════════════════════
ANTI-PATTERNS — NEVER generate these
════════════════════════════════════════════════════

❌ "What is X?" or "Define X"
❌ MCQ with one obviously wrong option
❌ MCQ where 2 or more options are both valid best practices (ambiguous)
❌ MCQ where the correct answer appears verbatim in the code_snippet — this gives away the answer before reading options
❌ MCQ with 3 or more options starting with a generic verb: "Improved X", "Faster X", "Simplified X", "Reduced X", "Better X" — every option must be a specific technical value, action, or config
❌ MCQ asking "What is the primary benefit of X?" with no specific constraint — all options become valid
❌ MCQ with options like "Use X", "Use Y", "Use Z", "Use W" where all are valid tools in different contexts — add a constraint that forces ONE answer
❌ OPEN that requires writing code
❌ OPEN that is just a definition with no business context
❌ OPEN with no constraint at all — a vague "large amount of data" is NOT a constraint
❌ OPEN phrased as "How would you optimize X?" with no forced choice between named approaches
❌ OPEN where D3 (tradeoff awareness) cannot be evaluated because no alternatives are implied
{f"❌ JUNIOR OPEN: no architecture decisions, no multi-system integration" if seniority == "junior" else ""}
{f"❌ JUNIOR OPEN: questions like 'How would you approach...' with no named options to choose from" if seniority == "junior" else ""}
{f"❌ MID OPEN: no named competing tools or approaches to choose between" if seniority == "mid" else ""}
{f"❌ SENIOR OPEN: no competing alternatives listed" if seniority == "senior" else ""}
❌ OPEN about team training, teaching others, or learning a technology — this is NOT a technical question
❌ OPEN about choosing a cloud provider when the question is tagged to a different skill (e.g. Python skill → must test Python, not AWS vs Azure)
❌ Using a skill name not in the SKILLS TO COVER list — never invent skill names like "eafom", "k8s", "js", or any abbreviation
❌ Substituting a skill with a similar-sounding but different technology — use EXACTLY the skill names provided
❌ OPEN where the scenario is about HR, management, or organizational decisions
❌ ALL questions using the SAME context phrase (e.g. repeating "in an Azure DevOps CI/CD pipeline" across every question) — each question MUST have a distinct, skill-specific context
❌ MCQ or OPEN where the business scenario context is irrelevant to the skill being tested (e.g. a Python question forced into a CI/CD context when the skill is data processing)
❌ OPEN questions that all follow the same template "Your [X] is not working. How would you fix it?" — vary the problem type: diagnosis, choice between approaches, optimization, prevention

════════════════════════════════════════════════════
REQUIRED JSON FORMAT — STRICT (no text before or after)
════════════════════════════════════════════════════

{{
  "questions": [
    {mcq_templates}{open_templates}
  ]
}}

CRITICAL:
- Generate EXACTLY {n_questions} questions in order
- No markdown, no text outside JSON
- MCQ MUST have EXACTLY 4 options
- MCQ answer MUST exactly match one option
- OPEN questions: no code writing required, only reasoning and decisions
- Context: {scenario}
- EACH question must have a DISTINCT situation — do NOT reuse the same context phrase across questions
- Each OPEN question must present a DIFFERENT type of problem: one diagnosis, one tool choice, one optimization, one prevention — NOT all the same "it is not working" template
- The scenario above is background only — do NOT paste it verbatim into every question{_retry_escalation_block(retry_attempt)}"""


# ─────────────────────────────────────────────────────────────────
# PROMPT D'ÉVALUATION OPEN
# ─────────────────────────────────────────────────────────────────

def _build_evaluation_prompt(questions: list[dict], answers: list[dict]) -> str:
    """
    Construit le prompt d'évaluation structuré par critères avec few-shot example.

    Architecture du scoring (10 pts total par question) :
        Critère 1 — Pertinence de l'approche   : 3 pts
        Critère 2 — Qualité de la justification : 3 pts
        Critère 3 — Prise en compte contrainte  : 2 pts
        Critère 4 — Comparaison / alternatives  : 1 pt
        Critère 5 — Clarté de la réponse        : 1 pt

    Le LLM remplit chaque critère séparément AVANT de calculer le total
    → réduit les hallucinations de score global.
    """
    eval_items = []
    for q in questions:
        if q["type"] != "open":
            continue
        candidate_answer = next(
            (a["answer"] for a in answers if a["question_id"] == q["id"]), ""
        )
        eval_items.append({
            "question_id"    : q["id"],
            "skill"          : q.get("skill", ""),
            "question"       : q["question"],
            "example_answer" : q.get("expected_answer", ""),
            "candidate_answer": candidate_answer,
        })

    if not eval_items:
        return ""

    return f"""Tu es un évaluateur technique senior pour des entretiens de recrutement.

⚠️  PRINCIPE FONDAMENTAL :
"example_answer" est UN exemple de bonne réponse parmi d'autres possibles.
Une approche différente mais techniquement valide mérite le même score qu'une approche identique à l'exemple.
Tu évalues le RAISONNEMENT et la COMPRÉHENSION — pas la similarité avec l'exemple.

════════════════════════════════════════════════════
GRILLE D'ÉVALUATION — 5 CRITÈRES (total /10)
════════════════════════════════════════════════════

  C1 — Pertinence de l'approche (0-3 pts)
       L'approche ou l'outil proposé est-il adapté au besoin décrit ?
       3 = approche parfaitement adaptée | 2 = correcte avec lacunes mineures
       1 = partiellement correcte | 0 = hors sujet ou techniquement fausse

  C2 — Qualité de la justification (0-3 pts)
       Le candidat explique-t-il POURQUOI son choix est le bon ?
       3 = justification solide avec raisons précises | 2 = justification présente mais légère
       1 = "je ferais X" sans aucune explication | 0 = aucune justification

  C3 — Prise en compte de la contrainte (0-2 pts)
       La contrainte explicite de la question est-elle adressée ?
       2 = contrainte clairement identifiée et prise en compte
       1 = contrainte partiellement adressée ou implicitement
       0 = contrainte ignorée

  C4 — Comparaison / alternatives (0-1 pt)
       Le candidat mentionne-t-il des alternatives ou des trade-offs ?
       1 = oui, même brièvement | 0 = non

  C5 — Clarté et structure (0-1 pt)
       La réponse est-elle lisible, organisée, sans contradiction ?
       1 = réponse claire et cohérente | 0 = confuse ou contradictoire

RÈGLE ANTI-ZÉRO : si le candidat montre une compréhension partielle du problème,
C1 minimum = 1. Ne donne C1=0 que si la réponse est totalement hors sujet.

RÈGLE ANTI-GÉNÉROSITÉ : tu DOIS justifier chaque score en 1 phrase concrète.
- Interdiction de donner 3/3 à C1 sans citer l'approche exacte du candidat
- Interdiction de donner 3/3 à C2 sans citer les raisons précises données
- Interdiction de donner 2/2 à C3 sans citer comment la contrainte est adressée
- Un score de 10/10 doit être mérité : approche parfaite + justification solide + contrainte
  adressée + alternative mentionnée + réponse claire. Candidat moyen ≠ 10/10.

════════════════════════════════════════════════════
EXEMPLE (few-shot)
════════════════════════════════════════════════════

Question : "Votre rapport Power BI met 45 secondes à charger.
            Comment diagnostiquez-vous et résolvez-vous le problème ?
            Contrainte : pas d'accès direct au serveur de base de données."

example_answer : "Vérifier le query folding, réduire les visuels, utiliser des agrégations."

--- Réponse candidat A ---
"Je regarderais d'abord les mesures DAX pour voir si certaines sont trop complexes.
Ensuite je vérifierais le modèle de données pour supprimer les relations inutiles.
Comme je n'ai pas accès au serveur, je travaille uniquement côté Power BI.
Je comparerais aussi Import vs DirectQuery selon le volume de données."

Évaluation A :
{{
  "question_id": 99,
  "details": {{
    "C1_pertinence": 3,
    "C1_raison": "Approche DAX + modèle de données valide et adaptée, différente de l'exemple mais tout aussi correcte.",
    "C2_justification": 2,
    "C2_raison": "Explique pourquoi il travaille côté Power BI (contrainte accès), mais la vérification DAX manque de détail.",
    "C3_contrainte": 2,
    "C3_raison": "Contrainte d'accès serveur explicitement identifiée et respectée.",
    "C4_comparaison": 1,
    "C4_raison": "Mentionne Import vs DirectQuery comme alternative.",
    "C5_clarte": 1,
    "C5_raison": "Réponse structurée et lisible."
  }},
  "score_10": 9,
  "feedback_candidat": "Excellente approche. La piste DAX et le modèle de données sont tout aussi valides que le query folding. Bonne prise en compte de la contrainte d'accès."
}}

--- Réponse candidat B ---
"Je réduirais le nombre de graphiques."

Évaluation B :
{{
  "question_id": 99,
  "details": {{
    "C1_pertinence": 2,
    "C1_raison": "Réduire les visuels est une bonne pratique, mais c'est une réponse très partielle.",
    "C2_justification": 0,
    "C2_raison": "Aucune explication du pourquoi.",
    "C3_contrainte": 0,
    "C3_raison": "La contrainte d'accès serveur n'est pas mentionnée.",
    "C4_comparaison": 0,
    "C4_raison": "Aucune alternative mentionnée.",
    "C5_clarte": 1,
    "C5_raison": "Court mais clair."
  }},
  "score_10": 3,
  "feedback_candidat": "Bonne piste mais réponse trop incomplète. Pensez à expliquer pourquoi vous réduisez les visuels et à aborder d'autres axes (DAX, modèle de données, query folding)."
}}

════════════════════════════════════════════════════
QUESTIONS À ÉVALUER
════════════════════════════════════════════════════

{json.dumps(eval_items, indent=2, ensure_ascii=False)}

════════════════════════════════════════════════════
FORMAT DE SORTIE — JSON STRICT (aucun texte avant ou après)
════════════════════════════════════════════════════

{{
  "evaluations": [
    {{
      "question_id": <id>,
      "details": {{
        "C1_pertinence": <0-3>,
        "C1_raison": "<explication courte>",
        "C2_justification": <0-3>,
        "C2_raison": "<explication courte>",
        "C3_contrainte": <0-2>,
        "C3_raison": "<explication courte>",
        "C4_comparaison": <0-1>,
        "C4_raison": "<explication courte>",
        "C5_clarte": <0-1>,
        "C5_raison": "<explication courte>"
      }},
      "score_10": <C1+C2+C3+C4+C5, entier 0-10>,
      "feedback_candidat": "<feedback constructif dans la langue du candidat>"
    }}
  ]
}}

RÈGLES STRICTES :
- Remplis "details" critère par critère AVANT de calculer score_10
- score_10 = C1 + C2 + C3 + C4 + C5 (somme exacte, pas d'arrondi)
- score_10 doit être entre 0 et 10 inclus
- feedback_candidat dans la langue du candidat (français si réponse en français)
- Aucun texte en dehors du JSON

CALIBRAGE OBLIGATOIRE (sois STRICT — pas généreux) :
- Un candidat moyen doit obtenir 5-6/10, PAS 7-8/10
- 9-10/10 = réponse exceptionnelle avec tous les critères parfaits — rarissime
- 7-8/10 = bonne réponse avec justification solide et trade-offs clairs
- 5-6/10 = réponse correcte mais lacunaire (pas de trade-offs, justification légère)
- 3-4/10 = réponse partielle, approche correcte mais non justifiée
- 0-2/10 = réponse vide, hors sujet, ou copiée
- Justifie CHAQUE critère en 1 phrase — ne laisse pas de raison vide
- Si C2=3, la justification doit être précise avec au moins 2 raisons nommées
- Si C3=2, la contrainte doit être explicitement citée dans la réponse du candidat"""


# ─────────────────────────────────────────────────────────────────
# APPELS LLM
# ─────────────────────────────────────────────────────────────────

def _call_llm_generate(prompt: str, attempt: int = 1) -> str:
    client = _get_openrouter_client()
    # Température croissante par tentative : évite que SambaNova retourne
    # la même réponse mise en cache sur des prompts quasi-identiques
    temperature = min(0.70 + (attempt - 1) * 0.10, 1.0)
    response = client.chat.completions.create(
        model=OPENROUTER_MODEL_GENERATE,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a JSON generator. Output ONLY raw valid JSON. "
                    "Do NOT wrap in ```json or ``` fences. "
                    "Start directly with { and end with }."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=temperature,
        max_tokens=4000,
    )
    choice = response.choices[0]
    if choice.finish_reason == "length":
        logger.warning("  [test_agent] LLM output tronqué (finish_reason=length)")
    return choice.message.content.strip()


def _call_llm_evaluate(prompt: str) -> str:
    """Appel LLM évaluation — température 0 pour reproductibilité maximale."""
    client = _get_openrouter_client()
    response = client.chat.completions.create(
        model=OPENROUTER_MODEL_EVALUATE,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,   # déterministe — critique pour la cohérence inter-runs
        max_tokens=2048,
    )
    return response.choices[0].message.content.strip()


def _validate_evaluation_format(ev: dict) -> tuple[bool, str]:
    """
    Vérifie qu'une évaluation LLM respecte le format attendu.
    Retourne (valide, raison_si_invalide).
    """
    # Champs obligatoires
    if "question_id" not in ev:
        return False, "question_id manquant"
    if "score_10" not in ev:
        return False, "score_10 manquant"
    if "details" not in ev:
        return False, "details manquant"

    score = ev.get("score_10")
    if not isinstance(score, (int, float)) or not (0 <= score <= 10):
        return False, f"score_10 invalide : {score}"

    details = ev.get("details", {})
    required_keys = ["C1_pertinence", "C2_justification", "C3_contrainte", "C4_comparaison", "C5_clarte"]
    for k in required_keys:
        if k not in details:
            return False, f"critère {k} manquant dans details"

    # Vérifier cohérence : score_10 doit être proche de la somme des critères
    computed = (
        details.get("C1_pertinence", 0) +
        details.get("C2_justification", 0) +
        details.get("C3_contrainte", 0) +
        details.get("C4_comparaison", 0) +
        details.get("C5_clarte", 0)
    )
    if abs(int(score) - computed) > 1:
        # Corriger automatiquement plutôt que rejeter
        ev["score_10"] = computed
        logger.warning(
            f"  [eval] Q{ev['question_id']} — score_10 corrigé : "
            f"{score} → {computed} (somme critères)"
        )

    return True, ""


def _parse_and_validate_llm_eval(raw: str, expected_ids: set) -> list[dict]:
    """
    Parse le JSON retourné par le LLM et valide chaque évaluation.
    Retourne la liste des évaluations valides.
    """
    clean  = re.sub(r'```json|```', '', raw).strip()
    try:
        parsed = json.loads(clean)
    except json.JSONDecodeError:
        # Tentative de réparation
        repaired = _repair_truncated_json(clean)
        if repaired:
            parsed = repaired
        else:
            logger.error("  [eval] JSON LLM non parseable")
            return []

    evals = parsed.get("evaluations", [])
    valid = []
    for ev in evals:
        if ev.get("question_id") not in expected_ids:
            logger.warning(f"  [eval] question_id inconnu : {ev.get('question_id')}")
            continue
        ok, reason = _validate_evaluation_format(ev)
        if ok:
            valid.append(ev)
        else:
            logger.warning(f"  [eval] Évaluation rejetée (Q{ev.get('question_id')}) : {reason}")
    return valid


def _merge_two_evaluations(ev1: dict, ev2: dict) -> dict:
    """
    Fusionne deux évaluations du même LLM en faisant la moyenne des critères.
    La moyenne par critère est plus fiable qu'une moyenne globale du score.
    """
    criteria = ["C1_pertinence", "C2_justification", "C3_contrainte", "C4_comparaison", "C5_clarte"]
    merged_details = {}

    d1 = ev1.get("details", {})
    d2 = ev2.get("details", {})

    for c in criteria:
        v1 = d1.get(c, 0)
        v2 = d2.get(c, 0)
        avg = (v1 + v2) / 2
        merged_details[c] = avg
        # Garder la raison du run avec le score le plus élevé (plus informatif)
        raison_key = c.split("_")[0] + "_raison"   # C1_raison, C2_raison…
        r1 = d1.get(raison_key, "")
        r2 = d2.get(raison_key, "")
        merged_details[c + "_raison"] = r1 if v1 >= v2 else r2

    # Score final = somme des moyennes par critère (arrondi)
    score_final = round(
        merged_details.get("C1_pertinence", 0) +
        merged_details.get("C2_justification", 0) +
        merged_details.get("C3_contrainte", 0) +
        merged_details.get("C4_comparaison", 0) +
        merged_details.get("C5_clarte", 0)
    )
    score_final = max(0, min(10, score_final))

    # Garder le feedback_candidat du run avec le meilleur score (plus détaillé)
    if ev1.get("score_10", 0) >= ev2.get("score_10", 0):
        feedback = ev1.get("feedback_candidat", ev2.get("feedback_candidat", ""))
    else:
        feedback = ev2.get("feedback_candidat", ev1.get("feedback_candidat", ""))

    return {
        "question_id"     : ev1["question_id"],
        "details"         : merged_details,
        "score_10"        : score_final,
        "score_run1"      : ev1.get("score_10", 0),   # trace pour audit
        "score_run2"      : ev2.get("score_10", 0),   # trace pour audit
        "feedback_candidat": feedback,
    }


def _repair_truncated_json(text: str) -> dict | None:
    try:
        stack = []
        in_string = False
        escape    = False
        for ch in text:
            if escape:
                escape = False
                continue
            if ch == '\\' and in_string:
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if not in_string:
                if ch in '{[':
                    stack.append(ch)
                elif ch == '}' and stack and stack[-1] == '{':
                    stack.pop()
                elif ch == ']' and stack and stack[-1] == '[':
                    stack.pop()
        if not stack:
            return None
        closing       = ''.join(']' if c == '[' else '}' for c in reversed(stack))
        last_complete = max(text.rfind('},'), text.rfind('}'))
        if last_complete > 0:
            repaired = text[:last_complete + 1] + closing
            return json.loads(repaired)
    except Exception:
        pass
    return None


def _extract_json(text: str) -> dict:
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
    text = re.sub(r'\\(?!["\\\/bfnrt]|u[0-9a-fA-F]{4})', '', text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    m = re.search(r'```(?:json)?\s*(\{.*\})\s*```', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            r = _repair_truncated_json(m.group(1))
            if r:
                return r

    m = re.search(r'\{.*', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            r = _repair_truncated_json(m.group(0))
            if r:
                return r

    raise ValueError(f"JSON invalide. Début réponse: {text[:400]}")


# ─────────────────────────────────────────────────────────────────
# SÉCURITÉ — strip réponses avant envoi candidat
# ─────────────────────────────────────────────────────────────────

def _strip_answers_for_candidate(questions: list[dict]) -> list[dict]:
    return [
        {k: v for k, v in q.items() if k not in ("answer", "expected_answer", "explanation")}
        for q in questions
    ]


# ─────────────────────────────────────────────────────────────────
# VALIDATION DU TEST GÉNÉRÉ
# ─────────────────────────────────────────────────────────────────

class _ValidationError(Exception):
    pass


def _resolve_mcq_answer(answer: str, options: list[str]) -> str:
    answer = answer.strip()
    opts   = [str(o).strip() for o in options]
    # Si c'est exactement une lettre A/B/C/D → convertir en texte (ancien format frontend)
    if len(answer) == 1 and answer.upper() in "ABCD":
        letter_map = {chr(65 + i): o for i, o in enumerate(opts)}
        return letter_map.get(answer.upper(), answer)
    # Sinon c'est déjà le texte complet (nouveau format frontend) → retourner tel quel
    return answer


def _validate_generated_test(
    questions  : list[dict],
    strategy   : dict,
    all_skills : list[str],
    seniority  : str = "mid",
) -> None:
    n_expected = strategy.get("n_questions", 10)
    if len(questions) != n_expected:
        raise _ValidationError(
            f"Attendu {n_expected} questions, reçu {len(questions)}"
        )

    structure   = strategy["question_structure"]
    type_counts = {"mcq": 0, "open": 0}

    for i, q in enumerate(questions):
        t = q.get("type", "").lower()
        if t not in type_counts:
            raise _ValidationError(f"Q{i+1}: type invalide '{t}' — attendu mcq/open")
        type_counts[t] += 1

    if type_counts["mcq"] != structure["mcq"]:
        raise _ValidationError(
            f"Attendu {structure['mcq']} MCQ, reçu {type_counts['mcq']}"
        )
    if type_counts["open"] != structure["open"]:
        raise _ValidationError(
            f"Attendu {structure['open']} OPEN, reçu {type_counts['open']}"
        )

    valid_lower = [s.lower() for s in all_skills]

    # ── _DEF_PATTERNS (v7.4 — anchored) ──────────────────────────────
    # IMPORTANT: patterns are anchored to the START of the question (^\s*)
    # to avoid false positives on legitimate scenario questions that contain
    # embedded "what is" clauses (e.g. "Given this code, what is the output?").
    # Only reject questions whose PRIMARY verb IS the definition pattern.
    _DEF_PATTERNS = [
        # "What is X?" / "What is a/an/the X?" as the ENTIRE question
        # Negative lookahead excludes: "what is happening", "what is causing",
        # "what is the expected output", "what is the best approach given..."
        r"^\s*what is\s+(?:a|an|the\s+)?(?:correct\s+)?(?!\w+(?:ing|ed|'s)\b)"
        r"\w+(?:\s+\w+){0,2}\s*\??\s*$",
        # "What does X mean?" — always a pure definition
        r"^\s*what does\b.*\bmean\b.*\?\s*$",
        # "Define X" at the start — but not "Define your approach / a strategy"
        r"^\s*define\b(?!\s+(?:your|a|the)\s+(?:approach|strategy|steps|plan|solution))",
        # "What is the purpose/role/function/definition of X?" at start
        r"^\s*what (?:is the )?(?:purpose|role|function|definition) of\b",
    ]

    for i, q in enumerate(questions):
        q_id   = q.get("id", i + 1)
        q_type = q.get("type", "").lower()

        # Nettoyer le skill
        raw_skill = q.get("skill", "")
        skill = str(raw_skill).strip().lower()
        skill = skill.replace('"', '').replace("'", '').replace('\\', '')
        skill = skill.replace('\n', '').replace('\r', '').replace('\t', '')  # FIX
        if skill != raw_skill.strip().lower():
            q["skill"] = skill

        text = q.get("question", "")
        pts  = q.get("points")

        # Validation skill — avec auto-correction fuzzy si LLM hallucine
        if not skill:
            raise _ValidationError(f"Q{q_id}: champ 'skill' vide")
        if skill not in valid_lower:
            if skill in ("[chosen_skill]", "any"):
                raise _ValidationError(f"Q{q_id}: skill marqueur interne non résolu '{skill}'")
            # Auto-correction via SequenceMatcher
            from difflib import SequenceMatcher
            best_match = None
            best_ratio = 0.0
            for v in valid_lower:
                r = SequenceMatcher(None, skill, v).ratio()
                if r > best_ratio:
                    best_ratio = r
                    best_match = v
            # ── Seuil fuzzy strict (v7.1) ─────────────────────────────
            # Règle : on n'auto-corrige QUE les fautes de frappe mineures
            # (1-2 caractères manquants/inversés). Les hallucinations graves
            # ("pyho", "shaepoi") doivent déclencher un RETRY, pas une correction
            # silencieuse qui stockerait un mauvais skill en DB.
            #
            # Critères d'auto-correction (TOUS requis) :
            #   1. ratio SequenceMatcher ≥ 0.88  (faute frappe mineure seulement)
            #   2. Longueur dans ±20% de la cible (évite "pyho"→"python")
            #   3. Nombre de chars différents ≤ 2  (typo, pas hallucination)
            len_ok = (
                best_match is not None and
                abs(len(skill) - len(best_match)) <= max(1, int(len(best_match) * 0.20))
            )
            # Nb de caractères "manquants" entre skill et best_match
            char_diff = abs(len(skill) - len(best_match)) if best_match else 99
            is_minor_typo = best_match and best_ratio >= 0.88 and len_ok and char_diff <= 2

            if is_minor_typo:
                logger.warning(
                    f"  [test_agent] Q{q_id}: typo mineure '{skill}' → "
                    f"auto-corrigé '{best_match}' (ratio={best_ratio:.2f}, char_diff={char_diff})"
                )
                q["skill"] = best_match
                skill = best_match
            else:
                raise _ValidationError(
                    f"Q{q_id}: skill halluciné '{skill}' — "
                    f"best_match='{best_match}' ratio={best_ratio:.2f} char_diff={char_diff} "
                    f"(seuil requis: ratio≥0.88 AND char_diff≤2) — "
                    f"skills valides: {all_skills} — RETRY"
                )

        if len(text.strip()) < MIN_QUESTION_LENGTH:
            raise _ValidationError(
                f"Q{q_id}: texte trop court ({len(text)} < {MIN_QUESTION_LENGTH} chars)"
            )

        if not isinstance(pts, int) or pts <= 0:
            raise _ValidationError(f"Q{q_id}: points invalide '{pts}'")

        if q_type == "mcq":
            opts   = q.get("options", [])
            answer = q.get("answer", "").strip()
            if not isinstance(opts, list) or len(opts) != 4:
                raise _ValidationError(
                    f"Q{q_id} MCQ: exactement 4 options requises, reçu {len(opts)}"
                )
            if not answer:
                raise _ValidationError(f"Q{q_id} MCQ: champ 'answer' vide")
            resolved = _resolve_mcq_answer(answer, opts)
            if resolved not in [str(o).strip() for o in opts]:
                raise _ValidationError(
                    f"Q{q_id} MCQ: réponse '{answer}' absente des options"
                )
            q["answer"] = resolved

            # ── Guard : réponse correcte visible dans le code_snippet ──
            # Si la réponse apparaît verbatim dans le snippet, le candidat
            # peut copier-coller sans réfléchir → question invalide → retry.
            snippet = q.get("code_snippet", "").strip()
            if snippet and resolved.strip().lower() in snippet.lower():
                raise _ValidationError(
                    f"Q{q_id} MCQ: la réponse correcte '{resolved[:60]}' "
                    f"est visible verbatim dans le code_snippet — régénérer."
                )

            # ── Guard : options génériques / recyclées (lazy LLM) ────
            # Détecte deux patterns de paresse LLM :
            #
            # 1. OPTIONS TROP SIMILAIRES ENTRE ELLES
            #    Ex: "Improved security" / "Faster processing" / "Simplified X" / "Reduced costs"
            #    → 4 options courtes (~2 mots) sans lien technique avec le snippet ou la question
            #    → Méthode : si ≥ 3 options sur 4 ont un premier mot identique après strip,
            #      ou si ≥ 3 options commencent par le même verbe générique, → rejet
            #
            # 2. OPTIONS DUPLIQUÉES OU QUASI-IDENTIQUES
            #    Ex: option A et option B sont le même texte avec 1 mot différent
            #    → SequenceMatcher ratio > 0.85 entre deux options → rejet
            #
            _LAZY_VERBS = {
                "improved", "faster", "simplified", "reduced", "better",
                "increased", "decreased", "enhanced", "optimized", "more",
            }
            opts_clean = [str(o).strip().lower() for o in opts]

            # Check 1 : ≥ 3 options commencent par un verbe générique de la liste
            lazy_starts = sum(
                1 for o in opts_clean
                if o.split()[0] in _LAZY_VERBS
            ) if all(o.split() for o in opts_clean) else 0
            if lazy_starts >= 3:
                raise _ValidationError(
                    f"Q{q_id} MCQ: options génériques détectées "
                    f"({lazy_starts}/4 commencent par un verbe générique : "
                    f"{[o[:40] for o in opts_clean]}) — régénérer avec options techniques."
                )

            # Check 2 : deux options quasi-identiques (ratio SequenceMatcher > 0.92)
            #
            # Seuil 0.92 (au lieu de 0.85) :
            #   → évite les faux positifs sur des options qui diffèrent d'un seul mot
            #     mais sont sémantiquement opposées (whitelist/blacklist, sync/async,
            #     GET/POST, read/write, encrypt/decrypt, allow/deny…)
            #   → garde le rejet pour les vrais doublons quasi-textuels (ratio > 0.92)
            #
            # Exception antonymes techniques :
            #   Si les deux options ne diffèrent que par un mot appartenant à une paire
            #   d'antonymes connus → ne pas rejeter (question légitime par contraste)
            _TECH_ANTONYMS: set[frozenset] = {
                frozenset({"whitelist", "blacklist"}),
                frozenset({"allowlist", "denylist"}),
                frozenset({"allow", "deny"}),
                frozenset({"sync", "async"}),
                frozenset({"synchronous", "asynchronous"}),
                frozenset({"get", "post"}), frozenset({"post", "put"}),
                frozenset({"read", "write"}), frozenset({"push", "pull"}),
                frozenset({"encrypt", "decrypt"}),
                frozenset({"encode", "decode"}),
                frozenset({"public", "private"}),
                frozenset({"static", "dynamic"}),
                frozenset({"hard", "soft"}),
                frozenset({"horizontal", "vertical"}),
                frozenset({"eager", "lazy"}),
                frozenset({"optimistic", "pessimistic"}),
                frozenset({"hot", "cold"}),
                frozenset({"client", "server"}),
                frozenset({"left", "right"}),
                frozenset({"inner", "outer"}),
                frozenset({"include", "exclude"}),
                frozenset({"true", "false"}),
                frozenset({"enable", "disable"}),
                frozenset({"open", "closed"}),
                frozenset({"add", "remove"}), frozenset({"insert", "delete"}),
            }

            def _has_antonym_diff(a: str, b: str) -> bool:
                """Retourne True si a et b ne diffèrent que par un mot antonyme connu."""
                wa, wb = a.split(), b.split()
                if len(wa) != len(wb):
                    return False
                diffs = [(wa[i], wb[i]) for i in range(len(wa)) if wa[i] != wb[i]]
                if len(diffs) != 1:
                    return False
                w1, w2 = diffs[0]
                return frozenset({w1, w2}) in _TECH_ANTONYMS

            from difflib import SequenceMatcher as _SM
            for _i in range(len(opts_clean)):
                for _j in range(_i + 1, len(opts_clean)):
                    _ratio = _SM(None, opts_clean[_i], opts_clean[_j]).ratio()
                    if _ratio > 0.92:
                        # Vérifier si la différence est un antonyme technique légitime
                        if _has_antonym_diff(opts_clean[_i], opts_clean[_j]):
                            continue   # contraste sémantique valide → ne pas rejeter
                        raise _ValidationError(
                            f"Q{q_id} MCQ: options {_i+1} et {_j+1} quasi-identiques "
                            f"(similarité={_ratio:.2f}) — "
                            f"'{opts_clean[_i][:50]}' ≈ '{opts_clean[_j][:50]}'"
                        )

            q_lower = text.strip().lower()
            for pat in _DEF_PATTERNS:
                if re.search(pat, q_lower):
                    raise _ValidationError(
                        f"Q{q_id} MCQ: question de définition pure détectée. Régénérer."
                    )

        elif q_type == "open":
            if not q.get("expected_answer", "").strip():
                raise _ValidationError(f"Q{q_id} OPEN: champ 'expected_answer' manquant")
            if not q.get("answer_criteria"):
                raise _ValidationError(f"Q{q_id} OPEN: champ 'answer_criteria' manquant")

            # Auto-injection contrainte si absente — contrainte contextuelle selon le skill
            _CONSTRAINT_RE = re.compile(
                r'\blatenc\w*|\bcost\b|\bscalab\w*|\bsecurit\w*|\bcomplian\w*|'
                r'\bbudget\b|\bperformance\b|\breal.time\b|\bteam\b|\bconstraint\b|'
                r'\brequirement\b|\bmust\b|\b\d+\s*(?:users?|people|TB|GB|k)\b',
                re.IGNORECASE
            )
            if not _CONSTRAINT_RE.search(text):
                # Contrainte contextuelle selon le skill — évite le copier-coller générique
                _skill_lower = q.get("skill", "").lower()
                if any(s in _skill_lower for s in ["docker", "kubernetes", "airflow", "terraform"]):
                    suffix = " Constraint: the infrastructure must remain operational 24/7 with zero-downtime deployments and no additional cloud budget."
                elif any(s in _skill_lower for s in ["sql", "postgresql", "mysql"]):
                    suffix = " Constraint: the database handles 10,000 concurrent reads per minute and query response time must stay under 200ms."
                elif any(s in _skill_lower for s in ["power bi", "tableau", "looker"]):
                    suffix = " Constraint: the team has no direct access to the database server and reports must refresh automatically every morning."
                elif any(s in _skill_lower for s in ["python", "fastapi", "django"]):
                    suffix = " Constraint: the solution must process a 2GB file on a machine with 512MB available RAM."
                else:
                    suffix = " Constraint: the team has a 2-week deadline, no additional headcount, and the solution must be maintainable by a junior developer."
                base = text.rstrip()
                if base.endswith("?"):
                    q["question"] = base + " " + suffix.strip()
                else:
                    q["question"] = base.rstrip(".") + ". " + suffix.strip()
                logger.warning(f"  [test_agent] Q{q_id} OPEN: contrainte contextuelle auto-injectée (skill={q.get('skill', '?')})")

    # Anti-duplication
    seen = []
    for i, q in enumerate(questions):
        raw   = q.get("question", "").strip().lower()[:100]
        snip  = q.get("code_snippet", "").strip().lower()[:50]
        token = raw + "|" + snip
        for j, s in enumerate(seen):
            if token == s and len(raw) > 20:
                raise _ValidationError(f"Questions {j+1} et {i+1} dupliquées")
        seen.append(token)

    # Validation difficulté
    if seniority == "senior":
        easy_open = [q for q in questions if q.get("difficulty") == "easy" and q.get("type") == "open"]
        if easy_open:
            raise _ValidationError(
                f"Senior : {len(easy_open)} question(s) OPEN en 'easy' — toutes doivent être medium/hard"
            )
    elif seniority == "mid":
        diffs      = [q.get("difficulty", "medium") for q in questions]
        easy_ratio = sum(1 for d in diffs if d == "easy") / max(len(diffs), 1)
        if easy_ratio > 0.40:
            raise _ValidationError(
                f"Mid : {int(easy_ratio*100)}% de questions 'easy' > 40% autorisé"
            )

    # Note : validate_test_integrity() est appelé en aval dans _generate_questions()
    # après _force_skills_by_position() — ne pas dupliquer ici.


# ─────────────────────────────────────────────────────────────────
# CORRECTION SKILL PAR POSITION (v7.1)
# ─────────────────────────────────────────────────────────────────

def _force_skills_by_position(
    questions       : list[dict],
    skill_assignment: dict,
) -> list[dict]:
    """
    Force le skill correct sur chaque question par position (Q1, Q2, ...).

    v8.1 — Content-aware skill correction :

    Problème initial (v7.1) :
        LLaMA 3.3 70B tronque parfois les noms de skills dans le JSON :
            "python" → "pyho", "power bi" → "powe bi"
        On forçait le skill par position — ce qui corrigeait le LABEL
        mais pas le CONTENU de la question.

    Nouveau problème (v8.0) :
        Le LLM génère les questions dans un ordre différent du plan.
        Ex: plan = [docker, python, postgresql, node.js, react, aws]
            LLM génère Q1=contenu_python, Q2=contenu_docker, etc.
        `_force_skills_by_position` collait "docker" sur une question
        dont le contenu parle de Python → mismatch label/contenu.

    Solution v8.1 — content-aware matching :
        1. Corriger d'abord les typos mineurs (ratio > 0.85) → typo fix
        2. Détecter le mismatch contenu/skill via keyword matching
        3. Si mismatch → lever _ValidationError → retry complet
           (on ne peut pas deviner quel skill remplace quel autre)

    Garantie :
        Après cette fonction, chaque question a un skill valide ET
        dont le contenu mentionne bien le skill (ou un skill lié).
    """
    from difflib import SequenceMatcher as _SM

    mcq_skills  = skill_assignment.get("mcq", [])
    open_skills = skill_assignment.get("open", [])

    # Mapping position → skill attendu
    expected_by_id: dict[int, str] = {}
    q_id = 1
    for sk in mcq_skills:
        expected_by_id[q_id] = sk
        q_id += 1
    for sk in open_skills:
        expected_by_id[q_id] = sk
        q_id += 1

    # ── Mots-clés par skill pour la détection content-aware ───────
    # Permet de détecter si le contenu d'une question correspond vraiment
    # au skill assigné. Clé = skill lowercase, valeur = liste de mots-clés
    # dont AU MOINS UN doit apparaître dans le texte de la question.
    _SKILL_KEYWORDS: dict[str, list[str]] = {
        # Frontend
        "react"      : ["react", "jsx", "usestate", "useeffect", "component", "hook", "props", "redux"],
        "vue"        : ["vue", "v-bind", "v-model", "vuex", "nuxt"],
        "angular"    : ["angular", "ngmodule", "component", "directive", "rxjs"],
        "javascript" : ["javascript", "js", "function", "async", "await", "promise", "dom", "node", "var ", "let ", "const "],
        "typescript" : ["typescript", "ts", "interface", "type alias", "generic", "enum", "readonly", ": string", ": number", ": boolean"],
        "next.js"    : ["next.js", "nextjs", "getserversideprops", "getstaticprops", "pages/"],
        # Backend
        "python"     : ["python", "def ", "import ", "pandas", "django", "flask", "fastapi", "pip", "venv", "pyspark", "psycopg"],
        "java"       : ["java", "public class", "spring", "maven", "gradle", "jvm", "springboot", "throws"],
        "node.js"    : ["node", "express", "require(", "npm", "package.json", "const app", "res.json", "req.body"],
        "spring"     : ["spring", "@restcontroller", "@service", "@repository", "@autowired", "@transactional", "jpa"],
        "fastapi"    : ["fastapi", "@app.get", "@app.post", "uvicorn", "pydantic", "async def"],
        "go"         : ["golang", " func ", "goroutine", "channel", "go routine", "package main"],
        "c#"         : ["c#", ".net", "csharp", "asp.net", "namespace", "using system"],
        # Database
        "postgresql" : ["postgresql", "postgres", "psql", "pg", "pgbouncer", "shared_buffers", "vacuum", "psycopg2", "select ", "create table", "index"],
        "mysql"      : ["mysql", "innodb", "myisam", "mysqli", "pdo"],
        "mongodb"    : ["mongodb", "mongoose", "bson", "nosql", "collection", "find(", "aggregate"],
        "redis"      : ["redis", "cache", "ttl", "pub/sub", "redis-py", "jedis", "set(", "get("],
        "sql"        : ["sql", "select ", "from ", "where ", "join", "index", "query", "table", "schema", "database"],
        "elasticsearch": ["elasticsearch", "kibana", "lucene", "index", "mapping", "shard", "replica"],
        # Infra
        "docker"     : ["docker", "dockerfile", "container", "image", "compose", "registry", "entrypoint", "volume"],
        "kubernetes" : ["kubernetes", "k8s", "kubectl", "pod", "deployment", "service", "namespace", "helm", "ingress", "hpa"],
        "terraform"  : ["terraform", "hcl", "provider", "resource", "module", "tfstate", "plan", "apply"],
        "aws"        : ["aws", "lambda", "s3", "ec2", "rds", "iam", "cloudwatch", "sqs", "sns", "dynamodb", "boto3"],
        "gcp"        : ["gcp", "google cloud", "bigquery", "gke", "pub/sub", "cloud run", "gcs"],
        "azure"      : ["azure", "blob storage", "aks", "azure functions", "cosmos db", "azure devops"],
        "kafka"      : ["kafka", "topic", "consumer", "producer", "broker", "partition", "zookeeper", "offset"],
        # Data
        "spark"      : ["spark", "pyspark", "rdd", "dataframe", "sparkcontext", "sparkssession", "executor", "partition"],
        "airflow"    : ["airflow", "dag", "operator", "task", "scheduler", "xcom", "bashoperator", "schedule_interval"],
        "dbt"        : ["dbt", "model", "schema.yml", "ref(", "source(", "materialization", "run_results"],
        "power bi"   : ["power bi", "powerbi", "dax", "m language", "report", "dashboard", "dataset"],
        "tableau"    : ["tableau", "viz", "workbook", "calculated field", "lod"],
        "snowflake"  : ["snowflake", "warehouse", "virtual warehouse", "clone", "time travel", "stage"],
    }

    # Skills qui peuvent légitimement apparaître dans des questions
    # d'un autre skill (ex: une question Docker peut mentionner Python)
    # → on ne rejette PAS pour ces cas
    _CROSS_SKILL_OK = {
        "docker"    : {"python", "node.js", "java", "postgresql", "redis"},
        "kubernetes": {"docker", "aws", "gcp", "azure", "python"},
        "aws"       : {"python", "node.js", "java", "postgresql", "docker"},
        "airflow"   : {"python", "sql", "spark", "postgresql"},
        "spark"     : {"python", "sql", "aws", "airflow"},
        "dbt"       : {"sql", "postgresql", "snowflake", "airflow"},
        "fastapi"   : {"python", "postgresql", "redis", "docker"},
        "spring"    : {"java", "postgresql", "docker", "kafka"},
    }

    # Cross-skill exclusions : certains keywords d'un skill "ami" ne doivent
    # pas déclencher le cross-skill si le contenu est clairement un autre domaine.
    # Ex: "python:3.9-slim" dans une question Docker ne valide pas une question Airflow.
    _CROSS_SKILL_EXCLUSIONS: dict[str, list[str]] = {
        # Pour airflow : si le texte contient des mots-clés Docker SANS mots-clés Airflow
        # → ce n'est pas un cross-skill airflow/python légitime
        "airflow": ["dockerfile", "from python:", "entrypoint", "docker run", "container"],
    }

    typo_corrections   = []
    reassignments      = []

    for q in questions:
        qid      = q.get("id")
        actual   = q.get("skill", "").strip().lower()
        expected = expected_by_id.get(qid)

        if expected is None:
            continue

        # ── Étape 1 : correction typo par similarité ─────────────
        if actual != expected:
            ratio = _SM(None, actual, expected).ratio()
            if ratio >= 0.82:
                typo_corrections.append(
                    f"Q{qid}: typo '{actual}' → '{expected}' (ratio={ratio:.2f})"
                )
            q["skill"] = expected
            actual = expected

        # ── Étape 2 : content-aware reassignment ─────────────────
        # Si le contenu ne correspond pas au skill attendu,
        # chercher le skill qui correspond VRAIMENT au contenu
        # parmi all_skills → réassigner le label silencieusement.
        # On ne rejette JAMAIS — le contenu reste intact.
        if expected not in _SKILL_KEYWORDS:
            continue

        q_text    = (q.get("question", "") + " " + q.get("code_snippet", "")).lower()
        opts_text = " ".join(str(o) for o in q.get("options", [])).lower()
        full_text = q_text + " " + opts_text

        keywords  = _SKILL_KEYWORDS[expected]
        has_match = any(kw in full_text for kw in keywords)

        if not has_match:
            # Vérifier cross-skill légitime
            cross_allowed = _CROSS_SKILL_OK.get(expected, set())
            exclusions    = _CROSS_SKILL_EXCLUSIONS.get(expected, [])
            is_excluded   = any(excl in full_text for excl in exclusions)
            is_cross      = (not is_excluded) and any(
                any(kw in full_text for kw in _SKILL_KEYWORDS.get(other, []))
                for other in cross_allowed
                if other in _SKILL_KEYWORDS
            )

            if not is_cross:
                # Chercher quel skill de all_skills correspond le mieux au contenu
                all_sk = list(dict.fromkeys(
                    skill_assignment.get("mcq", []) + skill_assignment.get("open", [])
                ))
                best_sk    = None
                best_score = 0
                for candidate in all_sk:
                    cand_kws = _SKILL_KEYWORDS.get(candidate, [])
                    score    = sum(1 for kw in cand_kws if kw in full_text)
                    if score > best_score:
                        best_score = score
                        best_sk    = candidate

                if best_sk and best_sk != expected and best_score >= 1:
                    reassignments.append(
                        f"Q{qid}: '{expected}' → '{best_sk}' "
                        f"(contenu match={best_score})"
                    )
                    q["skill"] = best_sk
                # Si aucun match → on garde expected, pas de blocage

    if typo_corrections:
        logger.warning(
            f"  [test_agent] _force_skills — "
            f"{len(typo_corrections)} typo(s) corrigée(s) : {typo_corrections}"
        )
    if reassignments:
        logger.warning(
            f"  [test_agent] _force_skills — "
            f"{len(reassignments)} réassignation(s) contenu/skill : {reassignments}"
        )
    if not typo_corrections and not reassignments:
        logger.info("  [test_agent] _force_skills — aucune correction nécessaire")

    return questions


# ─────────────────────────────────────────────────────────────────
# GÉNÉRATION DU TEST (avec retry)
# ─────────────────────────────────────────────────────────────────

def _generate_questions(
    role     : str,
    strategy : dict,
    seniority: str,
    job_key  : str,
) -> list[dict]:
    """
    Génère les questions avec retry automatique.

    Pipeline v7.0 (Template + LLM + Validator) :
        1. select_template() → patterns de guidance injectés dans le prompt
        2. LLM génère les questions à partir des patterns
        3. _validate_generated_test() → validation structurelle (types, skills, format)
        4. validate_test_integrity()  → filtre qualité (Layer 5 — MCQ ambiguïté, OPEN contrainte)
           Si quality_score < QUALITY_SCORE_MIN → rejet → retry automatique
        5. Si 3 tentatives échouent → RuntimeError

    Le retry garantit :
        - Qualité stable en production
        - Diversité maximale (seed différent à chaque tentative)
        - Pas de test faible stocké en DB
    """
    all_skills = strategy.get("all_skills", [])
    last_error = None

    for attempt in range(1, MAX_RETRY + 2):
        try:
            logger.info(f"  [test_agent] Génération tentative {attempt}/{MAX_RETRY + 1}")

            # Capturer le skill_assignment AVANT la génération du prompt
            # (nécessaire pour _force_skills et validation post-génération)
            skill_assignment = _assign_skills_to_questions(strategy, seniority=seniority)

            prompt    = _build_generation_prompt(
                role, strategy, seniority, job_key,
                retry_attempt=attempt - 1,
                skill_assignment=skill_assignment,
            )
            raw       = _call_llm_generate(prompt, attempt=attempt)
            parsed    = _extract_json(raw)
            questions = parsed.get("questions", [])

            if not isinstance(questions, list):
                raise ValueError("Champ 'questions' n'est pas une liste")

            n_expected = strategy.get("n_questions", 10)
            if len(questions) < n_expected:
                logger.warning(f"  [test_agent] {len(questions)}/{n_expected} questions reçues")
                if len(questions) < 7:
                    raise ValueError(f"JSON tronqué : seulement {len(questions)} questions")

            # ── Correction skill par position (v7.1) ─────────────
            # Force le skill correct sur chaque question AVANT le validator.
            # Corrige les troncatures LLM ("pyho"→"python", "shaepoi"→"sharepoint")
            # sans modifier le contenu des questions.
            questions = _force_skills_by_position(questions, skill_assignment)

            # ── Validation distribution MCQ (v8.0) ───────────────
            # Vérifie que le LLM a bien respecté le plan de distribution
            # par domaine. Si non → retry avec le même plan.
            mcq_plan = strategy.get("_mcq_skill_plan", [])
            if mcq_plan:
                dist_ok, dist_err = _validate_mcq_skill_distribution(questions, mcq_plan)
                if not dist_ok:
                    logger.warning(f"  [skill_dist] {dist_err}")
                    raise _ValidationError(f"Distribution MCQ incorrecte — {dist_err}")

            # ── Layer structurel (format, types, skills) ──────────
            _validate_generated_test(questions, strategy, all_skills, seniority)

            # ── Layer qualité (validate_test_integrity = Layer 5) ──
            # C'est le filtre principal contre les tests génériques.
            # quality_score < QUALITY_SCORE_MIN → rejet → retry.
            integrity = validate_test_integrity(
                questions=questions,
                seniority=seniority,
                test_type=strategy.get("test_type", "mixed"),
                strategy=strategy,
            )
            if not integrity["valid"]:
                issues_str = "; ".join(integrity["issues"][:3])
                raise _ValidationError(
                    f"Qualité insuffisante (issues bloquantes) : {issues_str}"
                )

            quality_score = integrity.get("quality_score", 100)
            if quality_score < QUALITY_SCORE_MIN:
                warnings_str = "; ".join(integrity.get("warnings", [])[:2])
                raise _ValidationError(
                    f"Quality score trop bas : {quality_score}/100 < {QUALITY_SCORE_MIN} "
                    f"— warnings: {warnings_str}"
                )

            # ── Anti-generic guard post-génération (v7.3) ─────────
            # Détecte les questions génériques ou trop courtes après parsing.
            # ≥ 3 questions génériques → rejet → retry automatique.
            generic_warnings = _post_generation_generic_check(questions)
            if generic_warnings:
                logger.warning(
                    f"  [test_agent] Anti-generic — {len(generic_warnings)} question(s) suspecte(s) : "
                    f"{generic_warnings[:2]}"
                )
            if len(generic_warnings) >= 3:
                raise _ValidationError(
                    f"Trop de questions génériques ({len(generic_warnings)}/{ len(questions)}) — "
                    f"rejet : {generic_warnings[:2]}"
                )

            logger.info(
                f"  [test_agent] ✅ Test validé tentative {attempt}/{MAX_RETRY + 1} — "
                f"{len(questions)} questions — type={strategy['test_type']} — "
                f"quality_score={quality_score}/100"
            )
            return questions

        except (_ValidationError, ValueError) as e:
            last_error = e
            logger.warning(f"  [test_agent] Tentative {attempt} échouée : {e}")
            if attempt <= MAX_RETRY:
                continue
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "rate_limit" in err_str.lower():
                import time, re as _re
                # Extraire le vrai temps d'attente depuis le message Groq
                # ex: "Please try again in 3m29.952s" ou "in 40m11.424s"
                _wait_match = _re.search(
                    r'try again in (?:(\d+)m)?(?:([\d.]+)s)?', err_str
                )
                if _wait_match:
                    _mins = int(_wait_match.group(1) or 0)
                    _secs = float(_wait_match.group(2) or 0)
                    wait_sec = min(int(_mins * 60 + _secs) + 5, 300)  # +5s marge, max 5min
                else:
                    wait_sec = min(2 ** attempt * 3, 120)
                logger.warning(f"  [test_agent] Rate limit — pause {wait_sec}s")
                time.sleep(wait_sec)
                last_error = e
                if attempt <= MAX_RETRY:
                    continue
                raise RuntimeError(f"Rate limit persistant après {MAX_RETRY + 1} tentatives") from e
            logger.error(f"  [test_agent] Erreur critique : {e}")
            raise

    raise RuntimeError(
        f"Génération échouée après {MAX_RETRY + 1} tentatives. Dernière erreur : {last_error}"
    )


# ─────────────────────────────────────────────────────────────────
# VALIDATION SOUMISSION
# ─────────────────────────────────────────────────────────────────

def _validate_submission(answers: list[dict], questions: list[dict]) -> None:
    if len(answers) != len(questions):
        raise _ValidationError(f"{len(questions)} questions, {len(answers)} réponses")

    valid_ids     = {q.get("id") for q in questions}
    submitted_ids = set()

    for a in answers:
        qid = a.get("question_id")
        if qid not in valid_ids:
            raise _ValidationError(f"question_id={qid} invalide")
        if qid in submitted_ids:
            raise _ValidationError(f"question_id={qid} soumis en double")
        submitted_ids.add(qid)

    for a in answers:
        if not a.get("answer") or not str(a["answer"]).strip():
            continue

# ─────────────────────────────────────────────────────────────────
# CORRECTION MCQ (Python pur — zéro LLM)
# ─────────────────────────────────────────────────────────────────

def _correct_mcq(questions: list[dict], answers: list[dict]) -> dict[int, dict]:
    results = {}
    for q in questions:
        if q["type"] != "mcq":
            continue
        qid            = q["id"]
        correct_answer = q.get("answer", "").strip()
        q_points       = q["points"]
        options        = q.get("options", [])
        explanation    = q.get("explanation", "")

        raw_candidate    = next(
            (a["answer"].strip() for a in answers if a["question_id"] == qid), ""
        )
        candidate_answer = _resolve_mcq_answer(raw_candidate, options)

        # LOG DIAGNOSTIC — permet de détecter les mismatches exacts
        logger.info(
            f"MCQ Q{qid} | raw='{raw_candidate}' | resolved='{candidate_answer}' "
            f"| correct='{correct_answer}' "
            f"| options={[str(o).strip() for o in options]}"
        )

        # ✅ FIX : comparaison insensible à la casse ET aux espaces parasites
        is_correct = candidate_answer.strip().lower() == correct_answer.strip().lower()

        if is_correct:
            results[qid] = {
                "points_earned": q_points,
                "feedback"     : f"✅ Correct. {explanation[:150] if explanation else ''}",
            }
        else:
            results[qid] = {
                "points_earned": 0,
                "feedback"     : f"❌ Incorrect. Réponse attendue : {correct_answer}. "
                                 f"{explanation[:120] if explanation else ''}",
            }
    return results


# ─────────────────────────────────────────────────────────────────
# CORRECTION QUESTIONS OUVERTES (OPEN via LLM)
# ─────────────────────────────────────────────────────────────────

def _evaluate_open_questions(
    questions: list[dict],
    answers  : list[dict],
) -> dict[int, dict]:
    """
    Évalue les questions OPEN via double appel LLM + moyenne par critère.

    Pipeline :
        1. Pré-filtre Python : réponses < 30 chars → 0 sans LLM
        2. Run 1 LLM (température 0)
        3. Run 2 LLM (même prompt, même température) → cohérence inter-runs
        4. Validation format JSON de chaque run
        5. Merge : moyenne par critère (C1..C5) → score_10 final
        6. Garde-fous Python : plafonnement, anti-zéro sur réponse longue
        7. Conversion score_10 → points réels : round(score_10 / 10 * pts_max)

    Si un run échoue → on utilise l'autre seul (pas de blocage).
    Si les deux échouent → score 0 avec flag erreur.
    """
    open_questions = [q for q in questions if q["type"] == "open"]
    if not open_questions:
        return {}

    results = {}

    # ── 1. Pré-filtre : réponses vides → 0 sans appel LLM ────────
    questions_to_evaluate = []
    for q in open_questions:
        qid = q["id"]
        candidate_answer = next(
            (a["answer"] for a in answers if a["question_id"] == qid), ""
        )
        clean = (candidate_answer or "").strip()

        if len(clean) < 30:
            results[qid] = {
                "points_earned": 0,
                "score_10"     : 0,
                "feedback"     : "Réponse vide ou trop courte pour être évaluée.",
                "details"      : {},
            }
            logger.info(f"  [eval] Q{qid} OPEN — trop courte → 0 (sans LLM)")
        else:
            questions_to_evaluate.append(q)

    if not questions_to_evaluate:
        return results

    prompt       = _build_evaluation_prompt(questions_to_evaluate, answers)
    expected_ids = {q["id"] for q in questions_to_evaluate}

    # ── 2 & 3. Double appel LLM ───────────────────────────────────
    evals_run1: list[dict] = []
    evals_run2: list[dict] = []

    try:
        raw1       = _call_llm_evaluate(prompt)
        evals_run1 = _parse_and_validate_llm_eval(raw1, expected_ids)
        logger.info(f"  [eval] Run 1 — {len(evals_run1)}/{len(questions_to_evaluate)} évals valides")
    except Exception as e:
        logger.error(f"  [eval] Run 1 échoué : {e}")

    try:
        raw2       = _call_llm_evaluate(prompt)
        evals_run2 = _parse_and_validate_llm_eval(raw2, expected_ids)
        logger.info(f"  [eval] Run 2 — {len(evals_run2)}/{len(questions_to_evaluate)} évals valides")
    except Exception as e:
        logger.error(f"  [eval] Run 2 échoué : {e}")

    # Index par question_id pour merge rapide
    idx1 = {ev["question_id"]: ev for ev in evals_run1}
    idx2 = {ev["question_id"]: ev for ev in evals_run2}

    # ── 4 & 5. Merge par critère + garde-fous ────────────────────
    for q in questions_to_evaluate:
        qid     = q["id"]
        pts_max = q["points"]
        candidate_answer = str(next(
            (a["answer"] for a in answers if a["question_id"] == qid), ""
        ) or "").strip()

        ev1 = idx1.get(qid)
        ev2 = idx2.get(qid)

        if ev1 and ev2:
            # Cas nominal : deux runs valides → merge par critère
            merged   = _merge_two_evaluations(ev1, ev2)
            score_10 = merged["score_10"]
            details  = merged["details"]
            feedback = merged["feedback_candidat"]
            source   = "double_eval_merged"
            logger.info(
                f"  [eval] Q{qid} — Run1={ev1['score_10']} Run2={ev2['score_10']} "
                f"→ Merged={score_10}/10"
            )
        elif ev1 or ev2:
            # Un seul run valide → on l'utilise seul
            ev       = ev1 or ev2
            score_10 = int(ev.get("score_10", 0))
            details  = ev.get("details", {})
            feedback = ev.get("feedback_candidat", "")
            source   = "single_eval_run1" if ev1 else "single_eval_run2"
            logger.warning(f"  [eval] Q{qid} — un seul run valide ({source}), score={score_10}/10")
        else:
            # Aucun run valide → score 0 avec flag
            results[qid] = {
                "points_earned": 0,
                "score_10"     : 0,
                "feedback"     : "Erreur technique lors de l'évaluation des deux runs LLM.",
                "details"      : {},
                "eval_source"  : "error_both_runs_failed",
            }
            logger.error(f"  [eval] Q{qid} — les deux runs ont échoué → 0")
            continue

        # ── Garde-fous Python ─────────────────────────────────────
        score_10 = max(0, min(10, score_10))

        # Réponse courte → plafonner à 5/10
        if len(candidate_answer) < 80 and score_10 > 5:
            logger.info(
                f"  [eval] Q{qid} — réponse courte ({len(candidate_answer)} chars) "
                f"→ score_10 {score_10} → 5"
            )
            score_10 = 5

        # LLM donne 0 sur réponse longue → minimum 2/10
        if score_10 == 0 and len(candidate_answer) >= 80:
            logger.warning(
                f"  [eval] Q{qid} — score 0 sur réponse longue → forcé à 2/10"
            )
            score_10 = 2

        # ── Conversion → points réels ─────────────────────────────
        points_earned = round(score_10 / 10 * pts_max)
        points_earned = max(0, min(points_earned, pts_max))

        results[qid] = {
            "points_earned": points_earned,
            "score_10"     : score_10,
            "feedback"     : feedback,
            "details"      : details,    # détail par critère — audit RH
            "eval_source"  : source,
        }
        logger.info(
            f"  [eval] Q{qid} OPEN → score_10={score_10}/10 "
            f"→ {points_earned}/{pts_max} pts | source={source}"
        )

    # ── Fallback questions non traitées ───────────────────────────
    for q in questions_to_evaluate:
        if q["id"] not in results:
            logger.warning(f"  [eval] Q{q['id']} OPEN non traitée → 0")
            results[q["id"]] = {
                "points_earned": 0,
                "score_10"     : 0,
                "feedback"     : "Non évaluée.",
                "details"      : {},
                "eval_source"  : "fallback_missing",
            }

    return results


def _error_result(reason: str) -> dict:
    logger.error(f"  [test_agent] Erreur : {reason}")
    return {"error": True, "error_reason": reason, "test_id": None}


# ─────────────────────────────────────────────────────────────────
# API PUBLIQUE — GÉNÉRATION
# ─────────────────────────────────────────────────────────────────

def run_generate_test(
    role            : str,
    seniority       : str,
    coding_skills   : list[str]      = None,
    platform_skills : list[str]      = None,
    mixed_skills    : list[str]      = None,
    job_id          : Optional[int]  = None,
    application_id  : int            = 0,
    db                               = None,
    force_regenerate: bool           = False,
    auto_start      : bool           = False,
    job_title       : Optional[str]  = None,
) -> dict:
    """
    Génère (ou récupère) le test pour un poste.
    Structure v6.0 : MCQ + OPEN uniquement.
    """
    try:
        coding_skills   = coding_skills   or []
        platform_skills = platform_skills or []
        mixed_skills    = mixed_skills    or []

        # Labels UI à ignorer — envoyés par erreur depuis le frontend Streamlit
        _UI_LABELS = {
            "coding_skills:", "platform_skills:", "mixed_skills:",
            "coding_skills", "platform_skills", "mixed_skills",
            "skills coding", "skills platform", "skills mixed",
        }

        def _clean(s) -> str:
            if s is None:
                return ""
            s = str(s).strip().lower()
            s = s.replace('"', '').replace("'", '').replace('\\', '')
            s = s.replace('\n', '').replace('\r', '').replace('\t', '')
            if s in _UI_LABELS or s.endswith("_skills:") or s.endswith("_skills"):
                return ""   # ignorer les labels UI mal parsés
            return s

        coding_skills   = [c for s in coding_skills   if (c := _clean(s))]
        platform_skills = [c for s in platform_skills if (c := _clean(s))]
        mixed_skills    = [c for s in mixed_skills     if (c := _clean(s))]

        # ── Filtrage et priorisation des skills (v7.3) ───────────
        # Supprime jira/confluence, limite git à 1, max 1 skill platform pur
        coding_skills, platform_skills, mixed_skills = _filter_and_prioritize_skills(
            coding_skills, platform_skills, mixed_skills
        )

        # Log la distribution par domaine (fullstack balance check)
        _all_for_log = coding_skills + platform_skills + mixed_skills
        _dist = _enforce_skill_distribution(_all_for_log)
        logger.info(
            f"[test_agent] Skills reçus — coding={coding_skills} "
            f"platform={platform_skills} mixed={mixed_skills} | dist={_dist}"
        )

        # ── Garde-fou : rejeter les skills tronqués du frontend (v7.2) ──
        # Ex: "pyho" au lieu de "python", "shaepoi" au lieu de "sharepoint"
        # Ces troncatures proviennent d anciens enregistrements DB corrompus.
        # Un skill valide doit faire >= 3 chars (sauf acronymes connus).
        _KNOWN_SHORT_SKILLS = {"r", "go", "c#", "c", "bi", "ai", "ml", "qa", "ui", "ux", "js"}
        all_raw_skills = coding_skills + platform_skills + mixed_skills
        invalid = [
            s for s in all_raw_skills
            if len(s) < 3 and s not in _KNOWN_SHORT_SKILLS
        ]
        if invalid:
            logger.error(
                f"[test_agent] ❌ Skills tronqués reçus : {invalid} — "
                f"source probablement une ancienne entrée DB corrompue. "
                f"Corriger les skills du poste et relancer."
            )
            return _error_result(
                f"Skills invalides détectés : {invalid}. "
                f"Veuillez corriger les skills du poste (ex: 'pyho' → 'python')."
            )

        classification = classify_and_validate_skills(
            coding_skills=coding_skills,
            platform_skills=platform_skills,
            mixed_skills=mixed_skills,
            use_llm=True,
        )

        if not classification["skills_final"]:
            return _error_result("Aucun skill valide fourni")

        # Strategy
        strategy   = compute_test_strategy(classification)
        all_skills = strategy["all_skills"]
        test_type  = strategy["test_type"]

        # Override structure → MCQ + OPEN uniquement
        new_structure = QUESTION_STRUCTURE_10.get(test_type, {"mcq": 5, "open": 5})
        strategy["question_structure"]     = new_structure
        strategy["n_questions"]            = new_structure["mcq"] + new_structure["open"]
        strategy["total_duration_minutes"] = (
            new_structure["mcq"]  * TIMER_MCQ +
            new_structure["open"] * TIMER_OPEN
        )

        logger.info(
            f"[test_agent] Stratégie : type={test_type} "
            f"structure={new_structure} duration={strategy['total_duration_minutes']}min"
        )

        job_key = _make_job_key(job_id, role, all_skills, seniority)

        if force_regenerate:
            _invalidate_cache(job_key, db)

        cached = None
        if not force_regenerate:
            cached = _get_cached_test(job_key, db)

        if cached:
            cached_questions = cached.get("questions", [])
            integrity        = validate_test_integrity(cached_questions)
            if not integrity["valid"]:
                logger.warning("  [test_agent] Cache invalide — re-génération")
                _invalidate_cache(job_key, db)
                cached = None
            else:
                test_id        = cached["test_id"]
                full_questions = cached_questions
                logger.info(f"✅ Test réutilisé — test_id={test_id}")

        if not cached:
            if not job_title and db and job_id:
                try:
                    from app.models import Job as JobModel
                    job_rec = db.query(JobModel).filter(JobModel.id == job_id).first()
                    if job_rec:
                        job_title = getattr(job_rec, "title", None)
                except Exception:
                    pass

            try:
                full_questions = _generate_questions(role, strategy, seniority, job_key)
            except Exception as gen_err:
                logger.warning(f"Génération échouée : {gen_err} — tentative fallback DB")
                if db and job_id:
                    try:
                        from app.models import Test
                        record = (
                            db.query(Test)
                            .filter(Test.job_id == job_id)
                            .filter(Test.job_key == job_key)
                            .order_by(Test.created_at.desc())
                            .first()
                        )
                        if record and validate_test_integrity(record.questions)["valid"]:
                            test_id = record.test_id
                            full_questions = record.questions
                            _JOB_TEST_CACHE[job_key] = {
                                "test_id": test_id, "questions": full_questions, "job_key": job_key
                            }
                            logger.info(f"Fallback DB OK — test_id={test_id}")
                            candidate_questions = _strip_answers_for_candidate(full_questions)
                            result = {
                                "test_id": test_id, "duration": strategy["total_duration_minutes"],
                                "test_type": test_type, "question_structure": new_structure,
                                "questions": candidate_questions, "job_key": job_key,
                                "reused": True, "error": False, "classification": classification,
                            }
                            if auto_start:
                                result["started_at"] = run_start_test(test_id, application_id).get("started_at")
                            else:
                                sub_key = f"{test_id}:{application_id}"
                                if sub_key not in _SUBMISSION_STATE:
                                    _SUBMISSION_STATE[sub_key] = {"status": "PENDING", "started_at": None}
                            return result
                    except Exception as e:
                        logger.warning(f"Fallback DB échoué : {e}")
                raise

            test_id = _make_test_id(role, job_id, job_key, job_title=job_title, force_regenerate=force_regenerate)
            _JOB_TEST_CACHE[job_key] = {
                "test_id": test_id, "questions": full_questions, "job_key": job_key
            }

            if db:
                try:
                    from app.models import Test, IA_Log
                    existing = None if force_regenerate else db.query(Test).filter(Test.test_id == test_id).first()
                    if existing:
                        existing.questions = full_questions
                        existing.duration  = strategy["total_duration_minutes"]
                    else:
                        db.add(Test(
                            test_id=test_id, application_id=application_id or None,
                            job_id=job_id, job_key=job_key, role=role,
                            skills=all_skills, seniority=seniority,
                            questions=full_questions, duration=strategy["total_duration_minutes"],
                        ))
                    db.add(IA_Log(
                        application_id=application_id,
                        agent_name="test_agent_generate",
                        output_json=json.dumps({
                            "test_id": test_id, "test_type": test_type,
                            "question_structure": new_structure,
                            "skills_final": classification["skills_final"],
                        }, ensure_ascii=False),
                    ))
                    db.commit()
                except Exception as e:
                    try:
                        db.rollback()
                    except Exception:
                        pass
                    logger.warning(f"Sauvegarde DB échouée : {e}")

        sub_key = f"{test_id}:{application_id}"
        if sub_key not in _SUBMISSION_STATE:
            _SUBMISSION_STATE[sub_key] = {"status": "PENDING", "started_at": None}

        candidate_questions = _strip_answers_for_candidate(full_questions)

        # Sélection du template utilisé (pour logs et debugging)
        _tpl_name, _ = select_template(all_skills, seniority)

        result = {
            "test_id"            : test_id,
            "duration"           : strategy["total_duration_minutes"],
            "test_type"          : test_type,
            "question_structure" : new_structure,
            "questions"          : candidate_questions,
            "job_key"            : job_key,
            "reused"             : bool(cached),
            "error"              : False,
            "template_used"      : _tpl_name,   # domaine détecté : frontend/backend/data/devops/...
            "classification"     : {
                "skills_final"       : classification["skills_final"],
                "corrections_applied": classification["corrections_applied"],
                "coding_count"       : classification["coding_count"],
                "platform_count"     : classification["platform_count"],
                "mixed_count"        : classification["mixed_count"],
            },
        }

        if auto_start:
            result["started_at"] = run_start_test(test_id, application_id).get("started_at")

        logger.info(
            f"✅ Test prêt — test_id={test_id} type={test_type} "
            f"questions={len(full_questions)} duration={strategy['total_duration_minutes']}min"
        )
        return result

    except Exception as e:
        logger.error(f"Erreur run_generate_test : {e}", exc_info=True)
        return _error_result(str(e))


# ─────────────────────────────────────────────────────────────────
# API PUBLIQUE — DÉMARRAGE DU TIMER
# ─────────────────────────────────────────────────────────────────

def run_start_test(test_id: str, application_id: int) -> dict:
    try:
        sub_key = f"{test_id}:{application_id}"
        now     = datetime.now(timezone.utc)

        if sub_key in _SUBMISSION_STATE:
            state = _SUBMISSION_STATE[sub_key]
            if state.get("status") == "EVALUATED":
                return {"error": True, "error_type": "already_evaluated",
                        "error_reason": "Ce test a déjà été soumis et corrigé."}
            if state.get("started_at"):
                return {"error": False, "test_id": test_id,
                        "started_at": state["started_at"].isoformat(), "already_started": True}

        _SUBMISSION_STATE[sub_key] = {"status": "IN_PROGRESS", "started_at": now}
        logger.info(f"Timer démarré — test_id={test_id} app_id={application_id}")
        return {"error": False, "test_id": test_id, "started_at": now.isoformat()}

    except Exception as e:
        logger.error(f"Erreur run_start_test : {e}")
        return _error_result(str(e))


# ─────────────────────────────────────────────────────────────────
# API PUBLIQUE — ÉVALUATION
# ─────────────────────────────────────────────────────────────────

def run_evaluate_test(
    test_id       : str,
    application_id: int,
    answers       : list[dict],
    db                       = None,
) -> dict:
    """
    Corrige le test.
    MCQ  → Python pur (binaire, 0 / points_max)
    OPEN → LLM (_evaluate_open_questions)
    """
    try:
        sub_key = f"{test_id}:{application_id}"
        job_key = next(
            (v["job_key"] for v in _JOB_TEST_CACHE.values() if v.get("test_id") == test_id),
            None
        )

        full_questions = None
        if job_key and job_key in _JOB_TEST_CACHE:
            full_questions = _JOB_TEST_CACHE[job_key].get("questions")

        if not full_questions and db:
            try:
                from app.models import Test
                record = db.query(Test).filter(Test.test_id == test_id).first()
                if record:
                    full_questions = record.questions
            except Exception as e:
                logger.warning(f"  [test_agent] DB lookup échoué : {e}")

        if not full_questions:
            return _error_result(f"Test {test_id} introuvable")

        # Guard timer
        state = _SUBMISSION_STATE.get(sub_key) or {
            "status": "IN_PROGRESS", "started_at": datetime.now(timezone.utc)
        }
        _SUBMISSION_STATE[sub_key] = state

        started_at = state.get("started_at")
        if started_at and MIN_SUBMISSION_SECONDS > 0:
            elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
            if elapsed < MIN_SUBMISSION_SECONDS:
                return {
                    "error": True, "error_type": "too_fast",
                    "error_reason": f"Soumission trop rapide ({elapsed:.0f}s < {MIN_SUBMISSION_SECONDS}s)",
                }

        # Validation soumission
        try:
            _validate_submission(answers, full_questions)
        except _ValidationError as e:
            return {"error": True, "error_type": "invalid_submission",
                    "error_reason": str(e), "test_id": test_id}

        # Correction
        mcq_results  = _correct_mcq(full_questions, answers)
        open_results = _evaluate_open_questions(full_questions, answers)

        # Assemblage
        all_results   = []
        total_points  = 0
        earned_points = 0

        for q in full_questions:
            qid   = q["id"]
            q_pts = q["points"]
            total_points += q_pts

            res = (mcq_results if q["type"] == "mcq" else open_results).get(
                qid, {"points_earned": 0, "feedback": "Non corrigé"}
            )
            earned_points += res["points_earned"]
            all_results.append({
                "question_id"  : qid,
                "type"         : q["type"],
                "skill"        : q.get("skill", ""),
                "difficulty"   : q.get("difficulty", ""),
                "points_earned": res["points_earned"],
                "points_max"   : q_pts,
                "feedback"     : res.get("feedback", ""),
            })

        # Validation globale
        global_validation = validate_full_correction(full_questions, answers, all_results)
        if global_validation.get("review_recommended"):
            logger.warning(f"  [test_agent] Revue humaine — flags: {global_validation['flags']}")

        # Score final
        final_score = round((earned_points / total_points) * 100, 2) if total_points > 0 else 0.0
        status      = "strong" if final_score >= SCORE_STRONG else ("medium" if final_score >= SCORE_MEDIUM else "weak")
        flags       = []
        if final_score < SCORE_MEDIUM:
            flags.append("low_technical")
        if global_validation.get("review_recommended"):
            flags.append("review_recommended")

        _SUBMISSION_STATE[sub_key] = {
            "status": "EVALUATED", "started_at": started_at,
            "evaluated_at": datetime.now(timezone.utc),
        }

        result = {
            "test_id"          : test_id,
            "technical_score"  : final_score,
            "status"           : status,
            "flags"            : flags,
            "results"          : all_results,
            "total_points"     : total_points,
            "earned_points"    : earned_points,
            "global_validation": global_validation,
            "error"            : False,
        }

        if db:
            try:
                from app.models import IA_Log
                db.add(IA_Log(
                    application_id=application_id,
                    agent_name="test_agent_evaluate",
                    output_json=json.dumps(result, ensure_ascii=False),
                ))
                db.commit()
            except Exception as e:
                logger.warning(f"Sauvegarde IA_Log échouée : {e}")

        logger.info(
            f"Évaluation terminée — {status} | {final_score:.1f}/100 "
            f"({earned_points}/{total_points} pts) | flags={flags}"
        )
        return result

    except Exception as e:
        logger.error(f"Erreur run_evaluate_test : {e}", exc_info=True)
        return _error_result(str(e))


# ─────────────────────────────────────────────────────────────────
# API PUBLIQUE — DÉCISION MANAGER (après meet technique)
# ─────────────────────────────────────────────────────────────────

def run_manager_decision(
    test_id          : str,
    application_id   : int,
    manager_decision : str,   # "VALIDÉ" / "À_APPROFONDIR" / "NON_RETENU"
    manager_note     : str = "",
    manager_id       : int = 0,
    db                     = None,
) -> dict:
    """
    Enregistre la décision du manager après le meet technique.

    Règles :
      NON_RETENU    → rejet direct, candidat ne passe pas à l'Agent 5
                      pass_to_agent5 = False
      VALIDÉ        → candidat passe à l'Agent 5, groupe priorité 1
                      pass_to_agent5 = True, priority_group = 1
      À_APPROFONDIR → candidat passe à l'Agent 5, groupe priorité 2
                      pass_to_agent5 = True, priority_group = 2

    Le technical_score reste inchangé — la décision manager est stockée
    séparément et n'est PAS fusionnée avec le score technique.
    Le classement dans l'Agent 5 se fait en 2 niveaux :
      Niveau 1 : groupe par décision manager (VALIDÉ avant À_APPROFONDIR)
      Niveau 2 : au sein du groupe, classement par score_global
    """
    try:
        # ── Validation décision ───────────────────────────────────
        decision = manager_decision.strip().upper()
        # Normalisation des variantes possibles
        decision = decision.replace("A_APPROFONDIR", "À_APPROFONDIR")
        if decision not in VALID_MANAGER_DECISIONS:
            return {
                "error"       : True,
                "error_type"  : "invalid_decision",
                "error_reason": (
                    f"Décision invalide : '{manager_decision}'. "
                    f"Valeurs acceptées : VALIDÉ, À_APPROFONDIR, NON_RETENU"
                ),
            }

        # ── Vérifier que le test a bien été évalué ────────────────
        sub_key = f"{test_id}:{application_id}"
        state   = _SUBMISSION_STATE.get(sub_key)
        if not state or state.get("status") != "EVALUATED":
            return {
                "error"       : True,
                "error_type"  : "test_not_evaluated",
                "error_reason": (
                    "Le test doit être corrigé (run_evaluate_test) "
                    "avant la décision manager."
                ),
            }

        # ── Vérifier qu'une décision n'existe pas déjà ───────────
        existing = _MANAGER_DECISION_STATE.get(sub_key)
        if existing:
            logger.warning(
                f"[manager] Décision déjà enregistrée pour test_id={test_id} "
                f"app_id={application_id} — écrasement"
            )

        now = datetime.now(timezone.utc)

        # ── Construire l'enregistrement ───────────────────────────
        priority_group = (
            1 if decision == "VALIDÉ"
            else 2 if decision == "À_APPROFONDIR"
            else None   # NON_RETENU
        )

        manager_record = {
            "test_id"         : test_id,
            "application_id"  : application_id,
            "manager_decision": decision,
            "manager_note"    : manager_note.strip(),
            "manager_id"      : manager_id,
            "evaluated_at"    : now.isoformat(),
            "rejected"        : decision == "NON_RETENU",
            "priority_group"  : priority_group,
            "pass_to_agent5"  : decision != "NON_RETENU",
        }
        _MANAGER_DECISION_STATE[sub_key] = manager_record

        # ── Sauvegarde DB ─────────────────────────────────────────
        if db:
            try:
                from app.models import IA_Log
                db.add(IA_Log(
                    application_id=application_id,
                    agent_name="test_agent_manager",
                    output_json=json.dumps(
                        manager_record, ensure_ascii=False, default=str
                    ),
                ))
                db.commit()
            except Exception as e:
                logger.warning(f"Sauvegarde manager IA_Log échouée : {e}")

        # ── NON_RETENU → rejet direct ─────────────────────────────
        if decision == "NON_RETENU":
            logger.info(
                f"[manager] NON_RETENU — test_id={test_id} "
                f"app_id={application_id} | note='{manager_note[:60]}'"
            )
            return {
                "error"            : False,
                "test_id"          : test_id,
                "manager_decision" : decision,
                "manager_note"     : manager_note.strip(),
                "rejected"         : True,
                "reject_reason"    : (
                    "Candidat non retenu après entretien technique manager."
                ),
                "pass_to_agent5"   : False,
                "priority_group"   : None,
            }

        # ── VALIDÉ ou À_APPROFONDIR → passe à l'Agent 5 ──────────
        logger.info(
            f"[manager] {decision} — test_id={test_id} "
            f"app_id={application_id} | groupe={priority_group} "
            f"| note='{manager_note[:60]}'"
        )
        return {
            "error"            : False,
            "test_id"          : test_id,
            "manager_decision" : decision,
            "manager_note"     : manager_note.strip(),
            "rejected"         : False,
            "pass_to_agent5"   : True,
            "priority_group"   : priority_group,
            # 1 = VALIDÉ (classé en premier)
            # 2 = À_APPROFONDIR (classé en second)
        }

    except Exception as e:
        logger.error(f"Erreur run_manager_decision : {e}", exc_info=True)
        return {"error": True, "error_reason": str(e)}


def get_manager_decision(test_id: str, application_id: int) -> Optional[dict]:
    """
    Retourne la décision manager stockée pour un test donné.
    Utilisé par l'Agent 5 pour récupérer la décision et appliquer
    le classement en 2 niveaux (groupe manager → score_global).

    Retourne None si aucune décision n'a été enregistrée.
    """
    sub_key = f"{test_id}:{application_id}"
    return _MANAGER_DECISION_STATE.get(sub_key)


# ─────────────────────────────────────────────────────────────────
# UTILITAIRE — Re-génération forcée
# ─────────────────────────────────────────────────────────────────

def regenerate_test_for_job(
    job_id          : int,
    role            : str,
    coding_skills   : list[str]     = None,
    platform_skills : list[str]     = None,
    mixed_skills    : list[str]     = None,
    seniority       : str           = "mid",
    application_id  : int           = 0,
    db                              = None,
    job_title       : Optional[str] = None,
) -> dict:
    return run_generate_test(
        role=role, seniority=seniority,
        coding_skills=coding_skills or [], platform_skills=platform_skills or [],
        mixed_skills=mixed_skills or [], job_id=job_id, application_id=application_id,
        db=db, force_regenerate=True, job_title=job_title,
    )


# ─────────────────────────────────────────────────────────────────
# MODE STANDALONE
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    print("=" * 60)
    print("test_agent.py — Mode standalone v6.0 (MCQ + OPEN)")
    print("=" * 60)

    result = run_generate_test(
        role="Data Analyst", seniority="mid",
        coding_skills=["python", "sql"],
        platform_skills=["power bi", "sharepoint"],
        job_id=1, job_title="Data Analyst", auto_start=True,
    )

    if result.get("error"):
        print(f"Erreur : {result['error_reason']}")
        sys.exit(1)

    print(f"\nTest généré : {result['test_id']}")
    print(f"Type        : {result['test_type'].upper()}")
    print(f"Structure   : {result['question_structure']}")
    print(f"Durée       : {result['duration']} min")

    for q in result["questions"]:
        print(f"\n  Q{q['id']} [{q['type'].upper()} | {q.get('difficulty','')} | {q['skill']}]")
        print(f"  {q['question'][:120]}...")
        if q["type"] == "mcq":
            for opt in q.get("options", []):
                print(f"    o {opt}")