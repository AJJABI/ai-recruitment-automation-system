"""
test_agent.py — Agent Test Technique (v4.0 - PRODUCTION READY)

NOUVEAUTÉS v4.0 (Architecture Hybride) :
══════════════════════════════════════════════════════════════════════════
1. INTÉGRATION COMPLÈTE DE L'ARCHITECTURE HYBRIDE
   - Génération : LLM + Self-Test de l'Execution Engine
     → Garantit que le LLM ne génère jamais une question impossible
   - Évaluation PROBLEM : Execution Engine (déterministe) en priorité absolue
     → Fallback sur Signal Extractor (LLM factuel) si pseudo-code/erreur
   - Évaluation SCENARIO : Signal Extractor → Evaluation Core → Decision Engine
   - Zéro hallucination de notation : le LLM ne donne plus jamais de note directement

2. NOUVEAU FORMAT JSON PROBLEM (pour Execution Engine)
   - starter_code    : squelette de fonction fourni au candidat
   - function_name   : nom exact de la fonction à implémenter
   - test_cases      : cas de test unitaires (input/expected) cachés au candidat
   - self_test_reference() : valide que la solution du LLM passe ses propres tests

3. PIPELINE D'ÉVALUATION V4.0 (_evaluate_open_questions_v4)
   - Étape A (PROBLEM) : execute_and_score() — 100% déterministe
   - Étape B (Fallback) : extract_signals() — LLM factuel (signaux, pas de note)
   - Étape C : evaluate_core() — calculette mathématique aveugle
   - Étape D : decide() — résumé RH + confidence + technical_trace

CONSERVÉ de v3.0 :
   - Système de cache mémoire + DB
   - force_regenerate=True pour re-génération
   - test_id lisible basé sur le nom du job
   - auto_start=True pour démarrage automatique du timer
   - Guard 60s configurable (TEST_AGENT_DEV_MODE)
   - Retry avec seed différent à chaque tentative
   - Fallback DB si génération échoue
   - validate_test_integrity + validate_full_correction
   - Correction MCQ : binaire Python pur (zéro LLM)
   - Profils de séniorité (junior / mid / senior)
   - Distribution de difficulté adaptée au niveau
"""

import hashlib
import json
import logging
import os
import random
import re
from collections import Counter
from datetime import datetime, timezone, date
from typing import Optional

from dotenv import load_dotenv
from groq import Groq

from app.agents.test_agent.skill_classifier import classify_and_validate_skills, compute_test_strategy
from app.agents.test_agent.correction_validator import (
    validate_candidate_answer,
    validate_test_integrity,
    validate_full_correction,
)
# Imports de la nouvelle architecture hybride (v4.0)
from app.agents.test_agent.execution_engine import execute_and_score, self_test_reference, validate_test_cases
from app.agents.test_agent.signal_extractor import extract_signals
from app.agents.test_agent.evaluation_core import evaluate as evaluate_core
from app.agents.test_agent.decision_engine import decide

load_dotenv()
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────
# CONSTANTES
# ─────────────────────────────────────────────────────────────────

GROQ_MODEL_GENERATE = "meta-llama/llama-4-scout-17b-16e-instruct"
GROQ_MODEL_EVALUATE = "llama-3.3-70b-versatile"
MAX_RETRY           = 3
MAX_SKILLS          = 5
MIN_QUESTION_LENGTH = 60

SCORE_STRONG = 70
SCORE_MEDIUM = 50

EXPECTED_MCQ       = 4  # minimum MCQ (varie selon test_type : 4-6)

# Structure des 10 questions par test_type (v4.0)
QUESTION_STRUCTURE_10 = {
    "tech"    : {"mcq": 6, "problem": 4, "scenario": 0},
    "platform": {"mcq": 5, "problem": 0, "scenario": 5},
    "mixed"   : {"mcq": 4, "problem": 2, "scenario": 4},
}
EXPECTED_PROBLEM   = None   # variable selon test_type (0, 1 ou 3)
EXPECTED_SCENARIO  = None   # variable selon test_type

# Points par type de question
POINTS_MCQ      = 1
POINTS_PROBLEM  = 4
POINTS_SCENARIO = 4

# Timer par type (minutes)
TIMER_MCQ      = 2
TIMER_PROBLEM  = 6
TIMER_SCENARIO = 5

# Guard temps configurable
_DEV_MODE = os.getenv("TEST_AGENT_DEV_MODE", "0").strip() == "1"
MIN_SUBMISSION_SECONDS = 0 if _DEV_MODE else 60

if _DEV_MODE:
    logger.warning(
        "[test_agent] ⚠️  DEV MODE actif — guard temps 60s désactivé."
    )

# ─────────────────────────────────────────────────────────────────
# CACHE JOB → TEST
# ─────────────────────────────────────────────────────────────────

_JOB_TEST_CACHE   : dict[str, dict] = {}
_SUBMISSION_STATE : dict[str, dict] = {}


def _make_job_key(
    job_id    : Optional[int],
    role      : str,
    all_skills: list[str],
    seniority : str,
) -> str:
    if job_id:
        # Inclure seniority dans la clé : un même poste peut avoir des tests
        # différents selon le niveau demandé (junior ≠ mid ≠ senior)
        raw = f"job:{job_id}:{seniority.lower()}"
    else:
        content = f"{role.lower()}:{sorted(s.lower() for s in all_skills)}:{seniority.lower()}"
        raw = content
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def _make_test_id(
    role      : str,
    job_id    : Optional[int],
    job_key   : str,
    job_title : Optional[str] = None,
) -> str:
    today      = date.today().isoformat()
    short_hash = hashlib.md5(job_key.encode()).hexdigest()[:8]

    if job_title and job_title.strip():
        slug = re.sub(r'[^A-Za-z0-9\u00C0-\u024F]+', '_', job_title.strip())
        slug = slug.strip('_').lower()[:40]
    elif job_id:
        slug = f"job_{job_id}"
    else:
        slug = re.sub(r'[^A-Za-z0-9]+', '_', role.strip()).strip('_').lower()[:30]

    return f"{slug}-{today}-{short_hash}"


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
            # Assurer rollback de la session pour éviter l'état 'InFailedSqlTransaction'
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
                logger.warning(
                    f"  [test_agent] Test {record.test_id} marqué invalide en DB"
                )
        except Exception as e:
            # Si une erreur DB survient, rollbacker la transaction pour réinitialiser
            try:
                if hasattr(db, 'rollback'):
                    db.rollback()
            except Exception:
                pass
            logger.warning(f"  [test_agent] Invalidation DB échouée : {e}")


# ─────────────────────────────────────────────────────────────────
# CLIENT GROQ
# ─────────────────────────────────────────────────────────────────

_groq_client: Optional[Groq] = None


def _get_groq_client() -> Groq:
    global _groq_client
    if _groq_client is None:
        api_key = os.getenv("GROQ_API_KEY", "")
        if not api_key:
            raise EnvironmentError("GROQ_API_KEY manquant dans .env")
        _groq_client = Groq(api_key=api_key)
    return _groq_client


# ─────────────────────────────────────────────────────────────────
# PROFILS DE SÉNIORITÉ
# ─────────────────────────────────────────────────────────────────

SENIORITY_PROFILES = {
    "junior": {
        "description"    : "0-2 years experience, knows fundamentals",
        "mcq_target"     : "basic syntax usage, common beginner mistakes, simple real-world patterns — NOT performance or architecture",
        "problem_target" : (
            "a SIMPLE task solvable in 10-15 lines max — "
            "e.g. filter a list, count items in a dict, check a condition on each element. "
            "NO datetime manipulation, NO multi-step business logic, NO external APIs, "
            "NO complex algorithms. The task must be completable by someone in their first month."
        ),
        "scenario_target": (
            "choose ONE tool among 2-3 obvious options for a simple, well-defined need. "
            "NO integration between multiple tools, NO architecture decisions, "
            "NO deployment strategy. Example: 'which tool to build a simple report?'"
        ),
        "expectations"   : "Correct basic logic, simple loop or condition, obvious tool choice with one-sentence justification",
        "problem_example": "Write a function that takes a list of numbers and returns only the even ones",
        "scenario_example": "Your manager wants a simple chart showing monthly sales. Which Microsoft tool do you use?",
        "forbidden"      : (
            "FORBIDDEN for junior PROBLEM: datetime, timedelta, threshold logic with multiple conditions, "
            "fraud detection, user history analysis, pagination, concurrency, decorators, async. "
            "FORBIDDEN for junior SCENARIO: tool integration, migration strategy, multi-system architecture."
        ),
    },
    "mid": {
        "description"    : "2-5 years, builds features independently",
        "mcq_target"     : "performance, security basics, architecture decisions",
        "problem_target" : "a real feature they'd build in a sprint without help",
        "scenario_target": "propose a solution with justification and trade-offs",
        "expectations"   : "Efficient solution, edge cases handled, clear reasoning",
        "problem_example": "Write a function that processes a list of orders, groups them by status, and returns a summary dict",
        "scenario_example": "A client needs a real-time dashboard for 10k daily transactions. Which tool and why?",
        "forbidden"      : "",
    },
    "senior": {
        "description"    : "5+ years, designs systems, mentors",
        "mcq_target"     : "subtle bugs, concurrency, scale issues seniors catch immediately",
        "problem_target" : (
            "a complex problem requiring system-level thinking. "
            "MUST include at least ONE of: WebSocket/polling strategy, "
            "network error handling, state management optimization, "
            "re-render performance, concurrency, or design pattern decision. "
            "Simple display/update/CRUD tasks are FORBIDDEN for senior."
        ),
        "scenario_target": "compare 2-3 competing tools or approaches, explain trade-offs, justify choice with constraints",
        "expectations"   : "Elegant, production-ready, handles edge cases, scale, and performance",
        "problem_example": "Design a WebSocket hook that reconnects automatically on failure, limits retries, and exposes connection state to the UI",
        "scenario_example": "Your team must choose between Azure DevOps, GitHub Actions, and Jenkins for CI/CD. Constraint: Azure-hosted infra, 5 devs, free tier budget. Which do you recommend and why?",
        "forbidden"      : (
            "FORBIDDEN for senior PROBLEM: "
            "simple display components (just render + update timer), "
            "basic CRUD without error handling, "
            "trivial filter/map operations without complexity, "
            "any task solvable in under 20 lines without design decisions."
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
]


# ─────────────────────────────────────────────────────────────────
# PROMPT DE GÉNÉRATION (sans templates hardcodés)
# ─────────────────────────────────────────────────────────────────

def _build_mcq_templates(mcq_skills: list[str], all_skills: list[str]) -> str:
    """
    Génère dynamiquement les exemples JSON pour toutes les MCQ du prompt.
    Adapté pour 4, 5 ou 6 MCQ selon le test_type (v4.0).
    Les slots "any" = MCQ bonus → le LLM choisit librement le skill parmi all_skills.
    """
    lines = []
    for i, sk in enumerate(mcq_skills):
        if i == 0:
            q_hint = "Concrete scenario with code snippet or real situation. Min 80 chars."
        else:
            q_hint = f"Different scenario from Q{i}. Code or concrete situation required."

        if sk == "any":
            skill_instruction = (
                f"[FREE CHOICE — pick any skill from: {', '.join(all_skills)}. "
                f"Must differ from previous MCQ skills.]"
            )
        else:
            skill_instruction = sk

        lines.append(f"""    {{
      "id": {i + 1},
      "type": "mcq",
      "category": "tech",
      "skill": "{skill_instruction}",
      "difficulty": "easy",
      "question": "{q_hint}",
      "options": [
        "The correct answer (specific)",
        "A plausible wrong answer",
        "Another plausible wrong answer"
      ],
      "answer": "The correct answer (must EXACTLY match one option)",
      "points": {POINTS_MCQ},
      "explanation": "Why this is correct and why others are wrong"
    }}""")
    return ",\n".join(lines)


def _build_generation_prompt(
    role          : str,
    strategy      : dict,
    seniority     : str,
    job_key       : str,
    retry_attempt : int = 0,
) -> str:
    """
    Construit le prompt de génération sans templates hardcodés.

    strategy = résultat de compute_test_strategy() :
        test_type, question_structure, tech_weight, platform_weight,
        skills_coding, skills_platform, skills_mixed, all_skills
    """
    profile   = SENIORITY_PROFILES.get(seniority, SENIORITY_PROFILES["mid"])
    scenario  = random.choice(BUSINESS_SCENARIOS)
    test_type = strategy["test_type"]
    structure = strategy["question_structure"]

    # Seed unique par tentative
    base_seed   = int(job_key, 16) % 10000
    retry_salt  = retry_attempt * 3571
    seed        = (base_seed + retry_salt) % 10000

    # Construire la description des skills par catégorie
    skills_coding   = strategy.get("skills_coding",   [])
    skills_platform = strategy.get("skills_platform", [])
    skills_mixed    = strategy.get("skills_mixed",    [])
    all_skills      = strategy.get("all_skills",      [])

    skills_description = []
    if skills_coding:
        skills_description.append(
            f"  CODING skills (require writing code): {', '.join(skills_coding)}"
        )
    if skills_platform:
        skills_description.append(
            f"  PLATFORM skills (tool usage, config, dashboards): {', '.join(skills_platform)}"
        )
    if skills_mixed:
        skills_description.append(
            f"  MIXED skills (coding + platform): {', '.join(skills_mixed)}"
        )

    # Construire le bloc de structure imposée
    # _assign_skills_to_questions garantit que TOUS les skills sont couverts
    skill_assignment = _assign_skills_to_questions(strategy)
    structure_lines  = []
    q_id             = 1
    mcq_skills  = skill_assignment["mcq"]
    prob_skills = skill_assignment["problem"]
    scen_skills = skill_assignment["scenario"]

    # ── Distribution de difficulté selon la séniorité ────────────
    # junior : easy / medium uniquement — 0 hard
    # mid    : easy / medium / 1 hard max (dernière question seulement)
    # senior : medium / hard — 0 easy
    def _difficulty_for(q_type: str, index: int, total: int, seniority: str) -> str:
        """
        Retourne la difficulté adaptée au niveau.
        index  : position de la question dans son groupe (0-based)
        total  : nombre total de questions dans ce groupe
        """
        if seniority == "junior":
            # Junior : jamais de hard
            # MCQ    : Q1=easy, Q2=easy
            # PROBLEM: toutes medium
            # SCENARIO: toutes easy
            if q_type == "mcq":
                return "easy"
            elif q_type == "problem":
                return "medium"
            else:  # scenario
                return "easy"

        elif seniority == "mid":
            # Mid : pas de easy sur les open questions, 1 hard max (dernière)
            if q_type == "mcq":
                return "easy" if index == 0 else "medium"
            else:
                # medium pour tout sauf la dernière question du groupe
                return "hard" if (index == total - 1 and total > 1) else "medium"

        else:  # senior
            # Senior : 0 easy, medium/hard
            if q_type == "mcq":
                return "medium"
            else:
                # Première question medium, reste hard
                return "medium" if index == 0 else "hard"

    for i, sk in enumerate(mcq_skills):
        diff = _difficulty_for("mcq", i, len(mcq_skills), seniority)
        structure_lines.append(
            f'  Q{q_id}: MCQ | skill="{sk}" | points={POINTS_MCQ} | difficulty={diff}'
        )
        q_id += 1

    for i, sk in enumerate(prob_skills):
        diff = _difficulty_for("problem", i, len(prob_skills), seniority)
        structure_lines.append(
            f'  Q{q_id}: PROBLEM | skill="{sk}" | points={POINTS_PROBLEM} | difficulty={diff}'
        )
        q_id += 1

    for i, sk in enumerate(scen_skills):
        diff = _difficulty_for("scenario", i, len(scen_skills), seniority)
        structure_lines.append(
            f'  Q{q_id}: SCENARIO | skill="{sk}" | points={POINTS_SCENARIO} | difficulty={diff}'
        )
        q_id += 1

    return f"""You are a senior technical lead designing a REAL interview test.

TEST CONTEXT:
  Role      : {role}
  Seniority : {seniority} ({profile['description']})
  Test type : {test_type.upper()}
  Scenario  : {scenario}
  Seed      : {seed}

SKILLS TO COVER:
{chr(10).join(skills_description)}

════════════════════════════════════════════════════
MANDATORY QUESTION STRUCTURE — DO NOT CHANGE
════════════════════════════════════════════════════

You MUST generate exactly these questions in this exact order:

{chr(10).join(structure_lines)}

Total: {strategy.get('n_questions', 10)} questions exactly.

════════════════════════════════════════════════════
QUESTION TYPE RULES
════════════════════════════════════════════════════

MCQ (Multiple Choice Question):
  - Must include a SHORT code snippet OR a concrete real-world scenario
  - All options must be technically plausible (no obviously wrong answers)
  - Only ONE option is correct
  - Never ask for definitions ("what is X?")
  - Target: {profile['mcq_target']}
  - Example: "Your colleague pushed this function to production. It fails on 5% of requests. Why?"

PROBLEM (Mini coding / logic):
  - Pseudo-code is ACCEPTED — focus on logic, not perfect syntax
  - Describe a specific task with clear constraints
  - Include: what to build, inputs, expected output, one edge case
  - Never ask to "design a full system" — keep it small and focused
  - Target: {profile['problem_target']}
  - Example of good PROBLEM for this level: "{profile['problem_example']}"
{f"  - {profile['forbidden']}" if profile.get('forbidden') else ""}

SCENARIO (Real platform / tool decision):
  - Based on a REAL business situation with a specific constraint
  - No code required — focus on decision and reasoning
  - Always include at least one real constraint: latency / cost / scale / security / compliance
  - Target: {profile['scenario_target']}
  - Example of good SCENARIO for this level: "{profile['scenario_example']}"
  {"TECH/MIXED SCENARIO RULE: Present 2-3 NAMED competing tools/approaches. Candidate MUST choose between them and justify. Format: Your team evaluates [Tool A] vs [Tool B] for [need]. Constraint: [real constraint]. Which do you recommend? BAD: How would you use Azure DevOps? GOOD: Your team must choose between Azure DevOps vs GitHub Actions vs Jenkins. Constraint: Azure-hosted, budget=free tier. Which and why? The assigned skill can appear as one of the options — never as the only option." if test_type in ("tech", "mixed") else "PLATFORM SCENARIO RULE: Describe a concrete business need. Ask HOW the candidate uses the assigned tool. The tool name CAN appear. Include a real constraint. BAD: What is SharePoint? GOOD: Company (500 users) needs to centralize 10TB of docs with audit trails. How would you approach this using SharePoint?"}

════════════════════════════════════════════════════
ANTI-PATTERNS — NEVER generate these
════════════════════════════════════════════════════

❌ "What is X?" or "Define X" — zero value
❌ "What does print('hello') output?" — syntax trivia
❌ "Design a complete REST API" — too vague
❌ MCQ with one obviously wrong option
❌ SCENARIO that requires writing code
❌ PROBLEM that is just a definition
{f"""
════════════════════════════════════════════════════
JUNIOR LEVEL HARD CONSTRAINTS — STRICTLY ENFORCED
════════════════════════════════════════════════════

This is a JUNIOR test. The candidate has 0-2 years of experience.
PROBLEM questions MUST be solvable in 10-15 lines of simple code.

✅ ALLOWED for PROBLEM: filter a list, count items, loop over a dict,
   check a simple condition, return a subset of data, basic string ops.

❌ STRICTLY FORBIDDEN for PROBLEM:
   - datetime / timedelta / timezone manipulation
   - fraud detection or multi-condition business rules
   - user history analysis or stateful logic
   - pagination, rate limiting, concurrency
   - decorators, async/await, generators
   - any algorithm requiring more than one loop

✅ ALLOWED for SCENARIO: pick one obvious tool for one clear need.
❌ STRICTLY FORBIDDEN for SCENARIO:
   - integrating multiple tools together
   - migration or deployment strategy
   - multi-system architecture decisions

REMEMBER: A junior in week 1 on the job. Keep it SIMPLE.
""" if seniority == "junior" else ""}

════════════════════════════════════════════════════
CORRECTION CRITERIA (include in your output)
════════════════════════════════════════════════════

For PROBLEM questions, answer_criteria must reflect:
  - "correct logic: [what the correct logic must do]"
  - "valid structure: [what clean structure looks like]"
  - "edge case handled: [specific edge case]"

For SCENARIO questions, answer_criteria must reflect:
  - "tool relevance: [why the chosen tool fits]"
  - "justification: [what a good justification contains]"
  - "coherence: [what makes the overall answer coherent]"

════════════════════════════════════════════════════
REQUIRED JSON FORMAT — STRICT (no text before or after)
════════════════════════════════════════════════════

{{
  "questions": [
    {_build_mcq_templates(mcq_skills, all_skills)}{_build_open_question_templates(prob_skills, scen_skills, seniority, n_mcq=len(mcq_skills))}
  ]
}}

CRITICAL REMINDERS:
- Generate EXACTLY {strategy.get('n_questions', 10)} questions in the order specified above
- MCQ answer MUST exactly match one of the options (same string, same case)
- PROBLEM and SCENARIO MUST have expected_answer and answer_criteria
- No markdown, no explanation outside JSON, no text before or after JSON
- Each question MUST cover its assigned skill
- Questions must be based on {scenario} context
- DIVERSITY MANDATORY: Every question must test a DIFFERENT challenge — never generate the same logic or task in different languages/tools
- If multiple PROBLEM questions exist: each must focus on a different aspect (data processing vs error handling vs performance vs security vs API design)
- If multiple SCENARIO questions exist: each must address a different business need or constraint"""


def _assign_skills_to_questions(strategy: dict) -> dict:
    """
    Distribue les skills sur les questions en garantissant que TOUS les skills
    sont couverts, même si le nombre de questions < nombre de skills.

    Principe :
      - Chaque skill doit apparaître au moins une fois.
      - Si nb_skills > nb_questions : on priorise les skills non encore couverts.
      - Si nb_skills <= nb_questions : distribution naturelle par type de question.

    Retourne :
        {
            "mcq"     : [skill1, skill2],
            "problem" : [skill3],
            "scenario": [skill4, skill5],
        }
    """
    skills_coding   = strategy.get("skills_coding",   [])
    skills_platform = strategy.get("skills_platform", [])
    skills_mixed    = strategy.get("skills_mixed",    [])
    all_skills      = strategy.get("all_skills",      [])
    structure       = strategy.get("question_structure", {})

    n_mcq      = structure.get("mcq",      0)
    n_problem  = structure.get("problem",  0)
    n_scenario = structure.get("scenario", 0)
    n_total    = n_mcq + n_problem + n_scenario

    if not all_skills:
        return {
            "mcq"     : ["general"] * n_mcq,
            "problem" : ["coding"]  * n_problem,
            "scenario": ["platform"]* n_scenario,
        }

    # ── Étape 1 : pool naturel par type de question ───────────────
    # PROBLEM  → coding + mixed en priorité
    # SCENARIO → platform + mixed en priorité
    # MCQ      → tous les skills
    pool_problem  = (skills_coding + skills_mixed)  or all_skills
    pool_scenario = (skills_platform + skills_mixed) or all_skills
    pool_mcq      = all_skills

    # ── Étape 2 : assigner en prioritisant les skills non couverts ─
    # On construit slot par slot en ordre : problem → scenario → mcq
    # et on s'assure que chaque skill est vu au moins une fois.

    assigned   : dict[str, list[str]] = {"mcq": [], "problem": [], "scenario": []}
    covered    : set[str]             = set()

    def _pick_uncovered_first(pool: list[str], covered: set) -> str:
        """Retourne le premier skill du pool pas encore couvert, sinon le premier du pool."""
        for s in pool:
            if s not in covered:
                return s
        return pool[0]

    # Remplir problem
    for _ in range(n_problem):
        sk = _pick_uncovered_first(pool_problem, covered)
        assigned["problem"].append(sk)
        covered.add(sk)

    # Remplir scenario
    for _ in range(n_scenario):
        sk = _pick_uncovered_first(pool_scenario, covered)
        assigned["scenario"].append(sk)
        covered.add(sk)

    # Remplir mcq — en priorité les skills pas encore couverts,
    # les slots bonus (au-delà des skills uniques) → "any" (LLM choisit librement)
    for _ in range(n_mcq):
        uncovered = [s for s in pool_mcq if s not in covered]
        if uncovered:
            sk = uncovered[0]
            covered.add(sk)
        else:
            # Tous les skills sont déjà couverts → slot bonus, LLM choisit librement
            sk = "any"
        assigned["mcq"].append(sk)

    # ── Étape 3 : vérifier les skills manquants et les injecter ───
    # Si après distribution certains skills ne sont toujours pas couverts,
    # on les injecte en remplaçant des doublons dans les slots disponibles.
    missing = [s for s in all_skills if s not in covered]

    if missing:
        logger.warning(
            f"[skill_assign] Skills non couverts après distribution initiale : {missing}. "
            f"Injection forcée..."
        )
        # Chercher des doublons dans les slots (skills apparus 2+ fois)
        all_assigned_flat = assigned["mcq"] + assigned["problem"] + assigned["scenario"]
        counts = Counter(all_assigned_flat)
        duplicates = [sk for sk, c in counts.items() if c > 1]

        for missing_sk in missing:
            if not duplicates:
                break
            dup_sk = duplicates.pop(0)
            # Remplacer le doublon dans l'ordre mcq → problem → scenario
            for q_type in ("mcq", "problem", "scenario"):
                if dup_sk in assigned[q_type]:
                    idx = assigned[q_type].index(dup_sk)
                    assigned[q_type][idx] = missing_sk
                    covered.add(missing_sk)
                    logger.info(
                        f"[skill_assign] '{dup_sk}' (doublon) remplacé par '{missing_sk}' "
                        f"dans slot {q_type}[{idx}]"
                    )
                    break

    logger.info(
        f"[skill_assign] Distribution finale — "
        f"mcq={assigned['mcq']} problem={assigned['problem']} scenario={assigned['scenario']} "
        f"| couverts={sorted(covered)} | total_skills={len(all_skills)}"
    )

    return assigned


def _pick_skills_for_type(
    q_type  : str,
    count   : int,
    strategy: dict,
) -> list[str]:
    """
    Wrapper de compatibilité — délègue à _assign_skills_to_questions().
    Appelé séparément pour chaque type, donc on recalcule la distribution globale.
    NOTE : Pour éviter des distributions incohérentes entre appels,
           le prompt builder appelle _assign_skills_to_questions() directement.
    """
    if count == 0:
        return []

    skills_coding   = strategy.get("skills_coding",   [])
    skills_platform = strategy.get("skills_platform", [])
    skills_mixed    = strategy.get("skills_mixed",    [])
    all_skills      = strategy.get("all_skills",      [])

    if q_type == "mcq":
        pool = all_skills[:]
    elif q_type == "problem":
        pool = (skills_coding + skills_mixed) or all_skills
    else:
        pool = (skills_platform + skills_mixed) or all_skills

    if not pool:
        return ["general"] * count

    result = []
    for i in range(count):
        result.append(pool[i % len(pool)])
    return result


def _build_open_question_templates(
    prob_skills : list[str],
    scen_skills : list[str],
    seniority   : str = "mid",
    n_mcq       : int = 4,
) -> str:
    """
    Génère les templates JSON pour les questions PROBLEM et SCENARIO.

    v4.0 — PROBLEM : nouveau format avec starter_code, function_name, test_cases
    pour l'Execution Engine. SCENARIO : format classique textuel inchangé.

    IMPORTANT : quand plusieurs PROBLEM couvrent des skills différents,
    chaque question doit tester un ASPECT DIFFÉRENT du même contexte métier.
    """
    lines = []
    q_id  = n_mcq + 1  # Les MCQ occupent Q1..Qn_mcq

    PROBLEM_ASPECTS = [
        "data processing and transformation logic",
        "error handling and validation",
        "performance optimization or algorithm efficiency",
        "authentication, authorization, or security",
        "integration or API design",
        "concurrency, async, or parallelism",
        "data structure design or schema",
        "testing, monitoring, or observability",
    ]

    SCENARIO_ASPECTS = [
        "tool selection with cost and scale constraints",
        "integration with existing infrastructure",
        "security and compliance requirements",
        "performance and latency optimization",
        "team adoption and learning curve",
        "migration from a legacy system",
    ]

    def _diff(q_type: str, index: int, total: int) -> str:
        if seniority == "junior":
            return "easy" if q_type == "scenario" else "medium"
        elif seniority == "mid":
            return "hard" if (index == total - 1 and total > 1) else "medium"
        else:  # senior
            return "medium" if index == 0 else "hard"

    # ── PROBLEM : format Execution Engine (v4.0) ──────────────────────────
    for i, sk in enumerate(prob_skills):
        difficulty = _diff("problem", i, len(prob_skills))
        aspect = PROBLEM_ASPECTS[i % len(PROBLEM_ASPECTS)]
        diversity_hint = (
            f'IMPORTANT: This question covers "{sk}". '
            f'Focus specifically on: {aspect}. '
            f'Do NOT reuse the same logic or task as other PROBLEM questions in this test — '
            f'each PROBLEM must test a DIFFERENT skill and a DIFFERENT programming challenge.'
        ) if len(prob_skills) > 1 else (
            f'This question covers "{sk}". Focus on: {aspect}.'
        )

        lines.append(f""",
    {{
      "id": {q_id},
      "type": "problem",
      "category": "tech",
      "skill": "{sk}",
      "difficulty": "{difficulty}",
      "question": "{diversity_hint} — Write the question here (min 120 chars, concrete task with clear input/output spec and at least one edge case).",
      "starter_code": "def function_name(arg1, arg2):\\n    pass",
      "function_name": "exact_function_name_here",
      "test_cases": [
        {{"id": 1, "description": "normal case — describe what it tests", "input": [[1, 2, 3]], "expected": 6}},
        {{"id": 2, "description": "empty/zero input edge case", "input": [[]], "expected": 0}},
        {{"id": 3, "description": "negative or boundary values", "input": [[-1, 0, 1]], "expected": 0}}
      ],
      "expected_answer": "def function_name(arg1):\\n    # Complete working solution in {sk}\\n    pass",
      "answer_criteria": [
        "correct logic: [describe what correct logic must achieve for {sk}]",
        "valid structure: [describe what clean structure looks like in {sk}]",
        "edge case handled: [describe the specific edge case for this task]"
      ],
      "points": {POINTS_PROBLEM}
    }}""")
        q_id += 1

    # ── SCENARIO : format classique textuel (inchangé) ───────────────────
    for i, sk in enumerate(scen_skills):
        difficulty = _diff("scenario", i, len(scen_skills))
        aspect = SCENARIO_ASPECTS[i % len(SCENARIO_ASPECTS)]
        diversity_hint = (
            f'IMPORTANT: This question covers "{sk}". '
            f'Focus on: {aspect}. '
            f'Do NOT reuse the same scenario as other SCENARIO questions in this test.'
        ) if len(scen_skills) > 1 else (
            f'This question covers "{sk}". Focus on: {aspect}.'
        )

        lines.append(f""",
    {{
      "id": {q_id},
      "type": "scenario",
      "category": "platform",
      "skill": "{sk}",
      "difficulty": "{difficulty}",
      "question": "{diversity_hint} — Write the question here (min 100 chars, real business situation, include a constraint).",
      "answer_criteria": [
        "tool relevance: [why the chosen tool/approach is appropriate for {sk}]",
        "justification: [what a strong justification includes]",
        "coherence: [what makes the overall answer coherent]"
      ],
      "expected_answer": "Reference answer using {sk}: [ideal approach + justification]",
      "points": {POINTS_SCENARIO}
    }}""")
        q_id += 1

    return "".join(lines)


# ─────────────────────────────────────────────────────────────────
# PROMPT D'ÉVALUATION (PROBLEM + SCENARIO)
# ─────────────────────────────────────────────────────────────────

def _build_evaluation_prompt(questions: list[dict], answers: list[dict]) -> str:
    eval_items = []
    for q in questions:
        if q["type"] not in ("problem", "scenario"):
            continue
        candidate_answer = next(
            (a["answer"] for a in answers if a["question_id"] == q["id"]),
            ""
        )
        eval_items.append({
            "question_id"    : q["id"],
            "type"           : q["type"],
            "skill"          : q.get("skill", ""),
            "question"       : q["question"],
            "answer_criteria": q.get("answer_criteria", []),
            "expected_answer": q.get("expected_answer", ""),
            "points_max"     : q["points"],
            "candidate_answer": candidate_answer,
        })

    if not eval_items:
        return ""

    return f"""You are a strict but fair senior evaluator for a technical interview.

Compare each candidate's answer against the expected answer and scoring criteria.
Give partial credit when the candidate shows correct understanding even if incomplete.

Questions to evaluate:
{json.dumps(eval_items, indent=2, ensure_ascii=False)}

════════════════════════════════════════════════════
SCORING RULES
════════════════════════════════════════════════════

PROBLEM question (points_max: {POINTS_PROBLEM}):
  +2 points : correct logic (main requirement is properly handled)
  +1 point  : valid structure (clean code/pseudocode, good organization)
  +1 point  : edge case handled correctly
  Give 0/{POINTS_PROBLEM} only if answer is completely wrong or empty.
  Pseudo-code is VALID — do not penalize for syntax if logic is correct.

SCENARIO question (points_max: {POINTS_SCENARIO}):
  +2 points : tool/approach relevance (correct choice for the business need)
  +1 point  : justification (explains WHY the choice is appropriate)
  +1 point  : coherence (the overall answer is consistent and practical)
  Give 0/{POINTS_SCENARIO} only if answer is completely wrong or empty.
  No code required for SCENARIO — evaluate reasoning and decision quality.

IMPORTANT:
  - Compare with expected_answer for reference — it's the model solution
  - A different but valid approach deserves full marks
  - Partial credit: give at least 1 point if approach shows understanding
  - Empty or off-topic answer = 0 points

Output format (STRICT JSON ONLY):
{{
  "evaluations": [
    {{
      "question_id": 3,
      "points_earned": 3,
      "feedback": "Correct logic for main case and clean structure. Edge case not handled."
    }}
  ]
}}

CRITICAL: points_earned MUST NOT exceed points_max for any question."""


# ─────────────────────────────────────────────────────────────────
# APPELS LLM
# ─────────────────────────────────────────────────────────────────

def _call_groq_generate(prompt: str) -> str:
    client = _get_groq_client()
    response = client.chat.completions.create(
        model       = GROQ_MODEL_GENERATE,
        messages    = [{"role": "user", "content": prompt}],
        temperature = 0.80,
        max_tokens  = 4096,
    )
    return response.choices[0].message.content.strip()


def _call_groq_evaluate(prompt: str) -> str:
    client = _get_groq_client()
    response = client.chat.completions.create(
        model       = GROQ_MODEL_EVALUATE,
        messages    = [{"role": "user", "content": prompt}],
        temperature = 0.10,
        max_tokens  = 2048,
    )
    return response.choices[0].message.content.strip()


def _extract_json(text: str) -> dict:
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
    text = re.sub(r'\\(?!["\\/bfnrt]|u[0-9a-fA-F]{4})', '', text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    m = re.search(r'\{.*\}', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass

    raise ValueError(f"JSON invalide. Début réponse: {text[:400]}")


# ─────────────────────────────────────────────────────────────────
# SÉCURITÉ — strip réponses avant envoi candidat
# ─────────────────────────────────────────────────────────────────

def _strip_answers_for_candidate(questions: list[dict]) -> list[dict]:
    safe = []
    for q in questions:
        q_clean = {
            k: v for k, v in q.items()
            if k not in ("answer", "expected_answer", "explanation")
        }
        safe.append(q_clean)
    return safe


# ─────────────────────────────────────────────────────────────────
# VALIDATION DU TEST GÉNÉRÉ
# ─────────────────────────────────────────────────────────────────

class _ValidationError(Exception):
    pass


def _validate_generated_test(
    questions   : list[dict],
    strategy    : dict,
    all_skills  : list[str],
    seniority   : str = "mid",
) -> None:
    """
    Valide le test généré selon la structure imposée par le strategy engine.

    v4.0 — Ajoute la validation technique via l'Execution Engine :
      - validate_test_cases() : vérifie le format des test_cases
      - self_test_reference()  : vérifie que la solution du LLM passe ses propres tests
        → si le self-test échoue, la question est rejetée avant d'être présentée au candidat.

    Vérifie (inchangé) :
      - Nombre de questions = strategy["n_questions"]
      - Distribution MCQ / PROBLEM / SCENARIO conforme
      - Chaque question a un skill valide
      - Texte de question suffisamment long
      - MCQ : réponse dans les options
      - PROBLEM / SCENARIO : expected_answer présent
      - Pas de duplication
    """
    if len(questions) != strategy.get("n_questions", 10):
        raise _ValidationError(
            f"Attendu {strategy.get('n_questions', 10)} questions, reçu {len(questions)}"
        )

    structure = strategy["question_structure"]
    type_counts = {"mcq": 0, "problem": 0, "scenario": 0}

    for i, q in enumerate(questions):
        t = q.get("type", "").lower()
        if t not in type_counts:
            raise _ValidationError(f"Q{i+1}: type invalide '{t}' — attendu mcq/problem/scenario")
        type_counts[t] += 1

    if type_counts["mcq"] != structure["mcq"]:
        raise _ValidationError(
            f"Attendu {structure['mcq']} MCQ, reçu {type_counts['mcq']}"
        )
    if type_counts["problem"] != structure["problem"]:
        raise _ValidationError(
            f"Attendu {structure['problem']} PROBLEM, reçu {type_counts['problem']}"
        )
    if type_counts["scenario"] != structure["scenario"]:
        raise _ValidationError(
            f"Attendu {structure['scenario']} SCENARIO, reçu {type_counts['scenario']}"
        )

    valid_lower = [s.lower() for s in all_skills]

    _DEFINITION_PATTERNS = [
        r"\bwhat is (the )?correct\b",
        r"\bwhat is (the )?(best|most efficient|most suitable|most appropriate)\b",
        r"\bwhat is\b(?! happening|\w+ doing|\w+ causing|\w+ wrong|\w+ failing)",
        r"\bwhat does\b.*\bdo\b",
        r"\bwhat does\b.*\bmean\b",
        r"\bdefine\b",
        r"\bwhich of the following (?:best )?describes\b",
        r"\bwhat (?:is the )?(?:purpose|role|function|definition) of\b",
        r"\bwhich (?:operator|keyword|syntax|method|function) (?:is used|do you use|would you use) (?:to|for)\b",
    ]

    for i, q in enumerate(questions):
        q_id   = q.get("id", i + 1)
        q_type = q.get("type", "").lower()
        skill  = q.get("skill", "").strip().lower()
        text   = q.get("question", "")
        pts    = q.get("points")

        # Skill valide
        # Les MCQ bonus (slots libres) : le LLM choisit un skill parmi all_skills librement
        # → on accepte tout skill non vide pour les MCQ si hors liste officielle
        if not skill:
            raise _ValidationError(f"Q{q_id}: champ 'skill' vide")
        if skill not in valid_lower:
            if q_type == "mcq":
                logger.warning(
                    f"  [test_agent] Q{q_id} MCQ bonus : skill '{skill}' hors liste "
                    f"officielle — accepté (slot libre LLM)"
                )
            else:
                raise _ValidationError(
                    f"Q{q_id}: skill '{skill}' absent des skills du poste {all_skills}"
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
            if not isinstance(opts, list) or len(opts) < 3:
                raise _ValidationError(f"Q{q_id} MCQ: minimum 3 options requis")
            if not answer:
                raise _ValidationError(f"Q{q_id} MCQ: champ 'answer' vide")
            resolved = _resolve_mcq_answer(answer, opts)
            if resolved not in [str(o).strip() for o in opts]:
                raise _ValidationError(
                    f"Q{q_id} MCQ: réponse '{answer}' absente des options"
                )
            q["answer"] = resolved

            question_lower = text.strip().lower()
            for pattern in _DEFINITION_PATTERNS:
                if re.search(pattern, question_lower):
                    raise _ValidationError(
                        f"Q{q_id} MCQ: question de definition pure detectee "
                        f"(pattern: '{pattern}'). Regenerer avec un scenario concret."
                    )

        elif q_type in ("problem", "scenario"):
            if not q.get("expected_answer", "").strip():
                raise _ValidationError(
                    f"Q{q_id} {q_type}: champ 'expected_answer' manquant"
                )
            if not q.get("answer_criteria"):
                raise _ValidationError(
                    f"Q{q_id} {q_type}: champ 'answer_criteria' manquant"
                )

            # ── v4.0 : Validation technique pour les PROBLEM ──────────────
            if q_type == "problem":
                # 1. Vérification du format des test_cases
                test_cases = q.get("test_cases", [])
                if not test_cases:
                    raise _ValidationError(
                        f"Q{q_id} PROBLEM: champ 'test_cases' manquant ou vide. "
                        f"Le format v4.0 exige des test_cases pour l'Execution Engine."
                    )
                tc_valid, tc_reason = validate_test_cases(test_cases)
                if not tc_valid:
                    raise _ValidationError(
                        f"Q{q_id} PROBLEM: test_cases invalides — {tc_reason}"
                    )

                # 2. Vérification du function_name
                function_name = q.get("function_name", "").strip()
                if not function_name:
                    raise _ValidationError(
                        f"Q{q_id} PROBLEM: champ 'function_name' manquant"
                    )

                # 3. Self-test : la solution du LLM doit passer ses propres tests
                logger.info(f"  [test_agent] Self-test Q{q_id} ({function_name})...")
                st = self_test_reference(
                    expected_answer=q["expected_answer"],
                    function_name=function_name,
                    test_cases=test_cases,
                )
                if not st["valid"]:
                    raise _ValidationError(
                        f"Q{q_id} PROBLEM: self-test échoué — "
                        f"la solution du LLM ne passe pas ses propres tests. "
                        f"Raison: {st['reason']}"
                    )
                logger.info(f"  [test_agent] Self-test Q{q_id} OK ✅")

    # Pas de duplication
    seen_texts = []
    for i, q in enumerate(questions):
        snippet = q.get("question", "").strip().lower()[:60]
        for j, s in enumerate(seen_texts):
            if snippet == s:
                raise _ValidationError(f"Questions {j+1} et {i+1} dupliquées")
        seen_texts.append(snippet)

    # Validation intégrité via correction_validator (Layer 5 RH)
    test_type = strategy.get("test_type", "platform")
    integrity = validate_test_integrity(
        questions,
        seniority=seniority,
        test_type=test_type,
        strategy=strategy,
    )
    if not integrity["valid"]:
        raise _ValidationError(
            f"Intégrité test échouée : {'; '.join(integrity['issues'])}"
        )
    if integrity["warnings"]:
        for w in integrity["warnings"]:
            logger.warning(f"  [test_agent] Warning intégrité : {w}")


def _resolve_mcq_answer(answer: str, options: list[str]) -> str:
    answer   = answer.strip()
    opts     = [str(o).strip() for o in options]
    letter_map = {chr(65 + i): o for i, o in enumerate(opts)}
    if answer.upper() in letter_map:
        return letter_map[answer.upper()]
    return answer


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
    Génère + valide un test technique via LLM.
    Seed différent à chaque tentative pour garantir des questions différentes.
    """
    all_skills = strategy.get("all_skills", [])
    last_error = None

    for attempt in range(1, MAX_RETRY + 2):
        try:
            logger.info(f"  [test_agent] Génération tentative {attempt}/{MAX_RETRY + 1}")

            prompt    = _build_generation_prompt(
                role, strategy, seniority, job_key,
                retry_attempt=attempt - 1
            )
            raw       = _call_groq_generate(prompt)
            parsed    = _extract_json(raw)
            questions = parsed.get("questions", [])

            if not isinstance(questions, list):
                raise ValueError("Champ 'questions' n'est pas une liste")

            _validate_generated_test(questions, strategy, all_skills, seniority)

            logger.info(
                f"  [test_agent] Test validé en {attempt} tentative(s) "
                f"— {len(questions)} questions — type={strategy['test_type']}"
            )
            return questions

        except (_ValidationError, ValueError) as e:
            last_error = e
            logger.warning(f"  [test_agent] Tentative {attempt} échouée : {e}")
            if attempt <= MAX_RETRY:
                continue
        except Exception as e:
            logger.error(f"  [test_agent] Erreur Groq critique : {e}")
            raise

    raise RuntimeError(
        f"Génération échouée après {MAX_RETRY + 1} tentatives. "
        f"Dernière erreur : {last_error}"
    )


# ─────────────────────────────────────────────────────────────────
# VALIDATION SOUMISSION
# ─────────────────────────────────────────────────────────────────

def _validate_submission(answers: list[dict], questions: list[dict]) -> None:
    if len(answers) != len(questions):
        raise _ValidationError(
            f"{len(questions)} questions, {len(answers)} réponses"
        )

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
            raise _ValidationError(
                f"Réponse vide pour question_id={a.get('question_id')}"
            )


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

        if candidate_answer.strip() == correct_answer.strip():
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
# CORRECTION QUESTIONS OUVERTES (PROBLEM + SCENARIO via LLM)
# ─────────────────────────────────────────────────────────────────

def _evaluate_open_questions_v4(
    questions: list[dict],
    answers  : list[dict],
) -> dict[int, dict]:
    """
    v4.0 — LA RÉVOLUTION ARCHITECTURALE :
    Orchestration Execution Engine → Signal Extractor → Evaluation Core → Decision Engine.

    Routing par type :
      PROBLEM  → execute_and_score() en priorité absolue (déterministe)
                 → Si échec/pseudo-code : fallback signal_extractor (LLM factuel)
      SCENARIO → signal_extractor directement (pas d'exécution possible)

    Tous les scores passent par decision_engine pour le résumé RH final.
    """
    final_results = {}

    for q in questions:
        if q["type"] not in ("problem", "scenario"):
            continue

        qid           = q["id"]
        candidate_ans = next((a["answer"] for a in answers if a["question_id"] == qid), "")
        max_pts       = q["points"]

        exec_score_result = None
        exec_trace        = None

        # ── Étape A : Exécution de code (PROBLEM uniquement) ──────────────
        if q["type"] == "problem":
            logger.info(f"  [test_agent] Q{qid} PROBLEM — Execution Engine...")
            try:
                exec_score_result, exec_trace = execute_and_score(
                    candidate_code=candidate_ans,
                    function_name=q.get("function_name", ""),
                    test_cases=q.get("test_cases", []),
                    max_pts=max_pts,
                )
            except Exception as exec_err:
                logger.warning(f"  [test_agent] Q{qid} execute_and_score erreur : {exec_err}")
                exec_score_result = None
                exec_trace        = None

            # Si l'exécution a produit un résultat décisif → by-pass LLM
            if exec_score_result and exec_score_result.get("decision") in (
                "auto_accept", "auto_reject", "auto", "review_if_borderline"
            ):
                logger.info(
                    f"  [test_agent] Q{qid} → Execution décisive "
                    f"({exec_score_result['decision']}) — LLM by-passé ✅"
                )
                pipeline_traces = [exec_trace] if exec_trace else []
                final_decision  = decide(
                    question_type="problem",
                    question=q["question"],
                    answer=candidate_ans,
                    skill=q["skill"],
                    score_result=exec_score_result,
                    signals={},
                    pipeline_traces=pipeline_traces,
                )
                final_decision["question_id"]        = qid
                final_decision["points_earned"]      = exec_score_result.get("score", 0)
                final_decision["validation_applied"] = False
                final_decision["python_flags"]       = []
                final_results[qid] = final_decision
                continue

            # Sinon (pseudo-code, SyntaxError, timeout) → fallback LLM
            logger.info(
                f"  [test_agent] Q{qid} Execution Fallback "
                f"({exec_score_result.get('reason', 'unknown') if exec_score_result else 'exception'}) "
                f"→ Signal Extractor"
            )

        # ── Étape B : Extraction des signaux (fallback PROBLEM ou SCENARIO) ─
        logger.info(f"  [test_agent] Q{qid} {q['type'].upper()} — Signal Extractor...")
        try:
            signals, trace_extract = extract_signals(
                question_type=q["type"],
                question=q["question"],
                answer=candidate_ans,
                skill=q["skill"],
            )
        except Exception as sig_err:
            logger.error(f"  [test_agent] Q{qid} extract_signals erreur : {sig_err}")
            signals       = {}
            trace_extract = {"error": str(sig_err)}

        # ── Étape C : Évaluation déterministe ─────────────────────────────
        logger.info(f"  [test_agent] Q{qid} — Evaluation Core...")
        try:
            score_result, traces_eval = evaluate_core(
                question_type=q["type"],
                question=q["question"],
                answer=candidate_ans,
                skill=q["skill"],
                signals=signals,
                max_pts=max_pts,
            )
        except Exception as eval_err:
            logger.error(f"  [test_agent] Q{qid} evaluate_core erreur : {eval_err}")
            score_result = {"score": 0, "decision": "auto_reject", "reason": str(eval_err)}
            traces_eval  = []

        # Assembler les traces dans l'ordre chronologique
        pipeline_traces = []
        if exec_trace:
            pipeline_traces.append(exec_trace)
        pipeline_traces.append(trace_extract)
        pipeline_traces.extend(traces_eval)

        # ── Étape D : Décision & Output RH ────────────────────────────────
        logger.info(f"  [test_agent] Q{qid} — Decision Engine...")
        try:
            final_decision = decide(
                question_type=q["type"],
                question=q["question"],
                answer=candidate_ans,
                skill=q["skill"],
                score_result=score_result,
                signals=signals,
                pipeline_traces=pipeline_traces,
            )
        except Exception as dec_err:
            logger.error(f"  [test_agent] Q{qid} decide() erreur : {dec_err}")
            final_decision = {
                "score"      : score_result.get("score", 0),
                "feedback"   : f"Erreur Decision Engine : {dec_err}",
                "hr_summary" : "",
            }

        final_decision["question_id"]        = qid
        final_decision["points_earned"]      = final_decision.get("score", score_result.get("score", 0))
        final_decision["validation_applied"] = False
        final_decision["python_flags"]       = []
        final_results[qid] = final_decision

    return final_results


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

    Paramètres v3.0 :
      coding_skills   : skills nécessitant du code (ex: python, sql, c#)
      platform_skills : skills orientés outils (ex: power bi, sharepoint)
      mixed_skills    : skills mixtes (ex: azure, azure devops)
      force_regenerate: True → ignore le cache et regénère
      auto_start      : True → démarre le timer automatiquement
      job_title       : pour générer un test_id lisible
    """
    try:
        coding_skills   = coding_skills   or []
        platform_skills = platform_skills or []
        mixed_skills    = mixed_skills    or []

        # ── PHASE 2 — Validation intelligente des skills ──────────
        logger.info(
            f"[test_agent] Classification skills — "
            f"coding={coding_skills} platform={platform_skills} mixed={mixed_skills}"
        )

        classification = classify_and_validate_skills(
            coding_skills   = coding_skills,
            platform_skills = platform_skills,
            mixed_skills    = mixed_skills,
            use_llm         = True,
        )

        if not classification["skills_final"]:
            return _error_result("Aucun skill valide fourni")

        # Log des corrections
        if classification["corrections_applied"]:
            for c in classification["corrections_applied"]:
                logger.info(
                    f"  [test_agent] Correction skill : "
                    f"{c['name']} {c['given']} → {c['corrected_to']} "
                    f"(confidence={c['confidence']:.2f})"
                )

        # ── PHASE 3 — Test Strategy Engine ────────────────────────
        strategy   = compute_test_strategy(classification)
        all_skills = strategy["all_skills"]

        # ── Override : forcer la structure à 10 questions (v4.0) ──────────
        test_type = strategy["test_type"]
        new_structure = QUESTION_STRUCTURE_10.get(
            test_type,
            {"mcq": 4, "problem": 2, "scenario": 4}  # fallback mixed
        )
        strategy["question_structure"] = new_structure
        strategy["n_questions"]        = 10
        # Recalculer la durée totale avec la nouvelle structure
        strategy["total_duration_minutes"] = (
            new_structure["mcq"]      * TIMER_MCQ +
            new_structure["problem"]  * TIMER_PROBLEM +
            new_structure["scenario"] * TIMER_SCENARIO
        )

        logger.info(
            f"[test_agent] Stratégie : type={strategy['test_type']} "
            f"structure={strategy['question_structure']} "
            f"duration={strategy['total_duration_minutes']}min"
        )

        # ── Cache ─────────────────────────────────────────────────
        job_key = _make_job_key(job_id, role, all_skills, seniority)

        if force_regenerate:
            _invalidate_cache(job_key, db)
            logger.info(f"  [test_agent] Régénération forcée — cache vidé")

        cached = None
        if not force_regenerate:
            cached = _get_cached_test(job_key, db)

        if cached:
            cached_questions = cached.get("questions", [])
            integrity        = validate_test_integrity(cached_questions)
            if not integrity["valid"]:
                logger.warning(f"  [test_agent] Cache invalide — re-génération forcée")
                _invalidate_cache(job_key, db)
                cached = None
            else:
                test_id        = cached["test_id"]
                full_questions = cached_questions
                logger.info(f"✅ Test existant réutilisé — test_id={test_id}")

        if not cached:
            # Récupérer job_title depuis DB si non fourni
            if not job_title and db and job_id:
                try:
                    from app.models import Job as JobModel
                    job_rec = db.query(JobModel).filter(JobModel.id == job_id).first()
                    if job_rec:
                        job_title = getattr(job_rec, "title", None)
                except Exception:
                    pass

            # ── PHASE 5 — Génération ──────────────────────────────
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
                            .order_by(Test.created_at.desc())
                            .first()
                        )
                        if record:
                            fallback_integrity = validate_test_integrity(record.questions)
                            if fallback_integrity["valid"]:
                                test_id        = record.test_id
                                full_questions = record.questions
                                _JOB_TEST_CACHE[job_key] = {
                                    "test_id"  : test_id,
                                    "questions": full_questions,
                                    "job_key"  : job_key,
                                }
                                logger.info(f"Fallback DB OK — test_id={test_id}")
                                candidate_questions = _strip_answers_for_candidate(full_questions)
                                result = {
                                    "test_id"        : test_id,
                                    "duration"       : strategy["total_duration_minutes"],
                                    "test_type"      : strategy["test_type"],
                                    "question_structure": strategy["question_structure"],
                                    "questions"      : candidate_questions,
                                    "job_key"        : job_key,
                                    "reused"         : True,
                                    "error"          : False,
                                    "classification" : classification,
                                }
                                if auto_start:
                                    start_result    = run_start_test(test_id, application_id)
                                    result["started_at"] = start_result.get("started_at")
                                else:
                                    sub_key = f"{test_id}:{application_id}"
                                    if sub_key not in _SUBMISSION_STATE:
                                        _SUBMISSION_STATE[sub_key] = {
                                            "status": "PENDING", "started_at": None
                                        }
                                return result
                    except Exception as e:
                        logger.warning(f"Fallback DB échoué : {e}")
                raise

            # test_id lisible
            test_id = _make_test_id(role, job_id, job_key, job_title=job_title)

            # Cache mémoire
            _JOB_TEST_CACHE[job_key] = {
                "test_id"  : test_id,
                "questions": full_questions,
                "job_key"  : job_key,
            }

            # Sauvegarder en DB
            if db:
                try:
                    from app.models import Test, IA_Log
                    record = Test(
                        test_id        = test_id,
                        application_id = application_id if application_id else None,
                        job_id         = job_id,
                        job_key        = job_key,
                        role           = role,
                        skills         = all_skills,
                        seniority      = seniority,
                        questions      = full_questions,
                        duration       = strategy["total_duration_minutes"],
                    )
                    db.add(record)
                    log = IA_Log(
                        application_id = application_id,
                        agent_name     = "test_agent_generate",
                        output_json    = json.dumps({
                            "test_id"           : test_id,
                            "test_type"         : strategy["test_type"],
                            "question_structure": strategy["question_structure"],
                            "skills_final"      : classification["skills_final"],
                            "corrections"       : classification["corrections_applied"],
                        }, ensure_ascii=False),
                    )
                    db.add(log)
                    db.commit()
                    logger.info(f"Test {test_id} sauvegardé en DB")
                except Exception as e:
                    logger.warning(f"Sauvegarde DB échouée : {e}")

        # État de soumission pour ce candidat
        sub_key = f"{test_id}:{application_id}"
        if sub_key not in _SUBMISSION_STATE:
            _SUBMISSION_STATE[sub_key] = {"status": "PENDING", "started_at": None}

        candidate_questions = _strip_answers_for_candidate(full_questions)

        result = {
            "test_id"            : test_id,
            "duration"           : strategy["total_duration_minutes"],
            "test_type"          : strategy["test_type"],
            "question_structure" : strategy["question_structure"],
            "questions"          : candidate_questions,
            "job_key"            : job_key,
            "reused"             : bool(cached),
            "error"              : False,
            "classification"     : {
                "skills_final"      : classification["skills_final"],
                "corrections_applied": classification["corrections_applied"],
                "coding_count"      : classification["coding_count"],
                "platform_count"    : classification["platform_count"],
                "mixed_count"       : classification["mixed_count"],
            },
        }

        if auto_start:
            start_result        = run_start_test(test_id, application_id)
            result["started_at"] = start_result.get("started_at")

        logger.info(
            f"✅ Test prêt — test_id={test_id} type={strategy['test_type']} "
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
    """Démarre le timer du test pour ce candidat."""
    try:
        sub_key = f"{test_id}:{application_id}"
        now     = datetime.now(timezone.utc)

        if sub_key in _SUBMISSION_STATE:
            state = _SUBMISSION_STATE[sub_key]
            if state.get("status") == "EVALUATED":
                return {
                    "error"       : True,
                    "error_type"  : "already_evaluated",
                    "error_reason": "Ce test a déjà été soumis et corrigé.",
                }
            if state.get("started_at"):
                return {
                    "error"       : False,
                    "test_id"     : test_id,
                    "started_at"  : state["started_at"].isoformat(),
                    "already_started": True,
                }

        _SUBMISSION_STATE[sub_key] = {
            "status"    : "IN_PROGRESS",
            "started_at": now,
        }

        logger.info(f"Timer démarré — test_id={test_id} app_id={application_id}")
        return {
            "error"     : False,
            "test_id"   : test_id,
            "started_at": now.isoformat(),
        }

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
    Corrige le test et retourne le score final.

    Scoring v4.0 :
      MCQ      : binaire (0 / points_max) — Python pur, zéro LLM
      PROBLEM  : Execution Engine (déterministe) → Fallback Signal+Core si pseudo-code
      SCENARIO : Signal Extractor → Evaluation Core → Decision Engine
    """
    try:
        # ── 1. Récupérer les questions complètes ──────────────────
        sub_key = f"{test_id}:{application_id}"
        job_key = next(
            (v["job_key"] for k, v in _JOB_TEST_CACHE.items()
             if v.get("test_id") == test_id),
            None
        )

        full_questions = None
        if job_key and job_key in _JOB_TEST_CACHE:
            full_questions = _JOB_TEST_CACHE[job_key].get("questions")

        if not full_questions and db:
            try:
                from app.models import Test
                record = (
                    db.query(Test)
                    .filter(Test.test_id == test_id)
                    .first()
                )
                if record:
                    full_questions = record.questions
            except Exception as e:
                logger.warning(f"  [test_agent] DB lookup échoué : {e}")

        if not full_questions:
            return _error_result(f"Test {test_id} introuvable")

        # ── 2. Guard timer ────────────────────────────────────────
        state = _SUBMISSION_STATE.get(sub_key)
        if not state:
            _SUBMISSION_STATE[sub_key] = {
                "status"    : "IN_PROGRESS",
                "started_at": datetime.now(timezone.utc),
            }
            state = _SUBMISSION_STATE[sub_key]
            logger.info(f"  [test_agent] Auto-démarrage timer pour {sub_key}")

        started_at = state.get("started_at")
        if started_at and MIN_SUBMISSION_SECONDS > 0:
            elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
            if elapsed < MIN_SUBMISSION_SECONDS:
                return {
                    "error"       : True,
                    "error_type"  : "too_fast",
                    "error_reason": f"Soumission trop rapide ({elapsed:.0f}s < {MIN_SUBMISSION_SECONDS}s)",
                }

        # ── 3. Validation soumission ──────────────────────────────
        try:
            _validate_submission(answers, full_questions)
        except _ValidationError as e:
            return {
                "error"       : True,
                "error_type"  : "invalid_submission",
                "error_reason": str(e),
                "test_id"     : test_id,
            }

        # ── 4. Correction MCQ (Python pur) ────────────────────────
        mcq_results  = _correct_mcq(full_questions, answers)

        # ── 5. Correction PROBLEM + SCENARIO (v4.0 — Execution Engine → Signal → Core → Decision) ──
        open_results = _evaluate_open_questions_v4(full_questions, answers)

        # ── 6. Assemblage des scores ──────────────────────────────
        all_results   = []
        total_points  = 0
        earned_points = 0

        for q in full_questions:
            qid    = q["id"]
            q_pts  = q["points"]
            q_type = q["type"]
            total_points += q_pts

            if q_type == "mcq":
                res = mcq_results.get(qid, {"points_earned": 0, "feedback": "Non corrigé"})
            else:
                res = open_results.get(qid, {"points_earned": 0, "feedback": "Non évalué"})

            earned_points += res["points_earned"]
            all_results.append({
                "question_id"       : qid,
                "type"              : q_type,
                "skill"             : q.get("skill", ""),
                "difficulty"        : q.get("difficulty", ""),
                "points_earned"     : res["points_earned"],
                "points_max"        : q_pts,
                "feedback"          : res.get("feedback", ""),
                "validation_applied": res.get("validation_applied", False),
                "python_flags"      : res.get("python_flags", []),
            })

        # ── 7. Validation globale ─────────────────────────────────
        global_validation = validate_full_correction(
            full_questions, answers, all_results
        )

        if global_validation.get("review_recommended"):
            logger.warning(
                f"  [test_agent] Revue humaine recommandée — "
                f"flags: {global_validation['flags']}"
            )

        # ── 8. Score final ────────────────────────────────────────
        final_score = (
            round((earned_points / total_points) * 100, 2)
            if total_points > 0 else 0.0
        )

        if   final_score >= SCORE_STRONG: status = "strong"
        elif final_score >= SCORE_MEDIUM: status = "medium"
        else:                             status = "weak"

        flags = []
        if final_score < SCORE_MEDIUM:
            flags.append("low_technical")
        if global_validation.get("review_recommended"):
            flags.append("review_recommended")

        # ── 9. Marquer comme évalué ───────────────────────────────
        _SUBMISSION_STATE[sub_key] = {
            "status"      : "EVALUATED",
            "started_at"  : started_at,
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

        # ── 10. Sauvegarder en DB ─────────────────────────────────
        if db:
            try:
                from app.models import IA_Log
                log = IA_Log(
                    application_id = application_id,
                    agent_name     = "test_agent_evaluate",
                    output_json    = json.dumps(result, ensure_ascii=False),
                )
                db.add(log)
                db.commit()
                logger.info(f"IA_Log évaluation sauvegardé — test_id={test_id}")
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
    """
    Force la re-génération d'un test pour un poste.
    Utile depuis l'interface admin ou un endpoint FastAPI dédié.
    """
    return run_generate_test(
        role            = role,
        seniority       = seniority,
        coding_skills   = coding_skills   or [],
        platform_skills = platform_skills or [],
        mixed_skills    = mixed_skills    or [],
        job_id          = job_id,
        application_id  = application_id,
        db              = db,
        force_regenerate= True,
        job_title       = job_title,
    )


# ─────────────────────────────────────────────────────────────────
# MODE STANDALONE
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    print("=" * 60)
    print("test_agent.py — Mode standalone v4.0")
    print("=" * 60)

    result = run_generate_test(
        role            = "Backend Developer",
        seniority       = "junior",
        coding_skills   = ["python", "sql"],
        platform_skills = ["azure devops", "power bi"],
        mixed_skills    = [],
        job_id          = 1,
        job_title       = "Backend Developer",
        auto_start      = True,
    )

    if result.get("error"):
        print(f"❌ Erreur : {result['error_reason']}")
        sys.exit(1)

    print(f"\n✅ Test généré : {result['test_id']}")
    print(f"   Type        : {result['test_type'].upper()}")
    print(f"   Structure   : {result['question_structure']}")
    print(f"   Durée       : {result['duration']} min")
    print(f"   Réutilisé   : {result['reused']}")
    print(f"   Skills final: {result['classification']['skills_final']}")

    for q in result["questions"]:
        print(f"\n  Q{q['id']} [{q['type'].upper()} | {q.get('difficulty','')} | {q['skill']}]")
        print(f"  {q['question'][:120]}...")
        if q["type"] == "mcq":
            for opt in q.get("options", []):
                print(f"    ○ {opt}")