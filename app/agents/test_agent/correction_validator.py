"""
correction_validator.py — Validateur hybride pour la correction des tests techniques (v4.0)

Rôle dans l'architecture v4.0 :
  Ce module est le SUPERVISEUR QUALITÉ — pas le correcteur principal.

  Depuis v4.0, le pipeline d'évaluation est :
    PROBLEM Python exécutable → execution_engine (juge de paix, confidence=1.0)
    PROBLEM pseudo-code/fallback → signal_extractor → evaluation_core → decision_engine
    SCENARIO → signal_extractor → evaluation_core → decision_engine
    MCQ → Python pur (test_agent._correct_mcq)

  Ce module intervient à 2 moments précis :

  1. PRE-STORAGE (Layer 5 — validate_test_integrity) :
     Appelé pendant la GÉNÉRATION avant de stocker le test.
     Vérifie que le LLM a respecté les règles de qualité RH :
     MCQ sans ambiguïté, SCENARIO avec contrainte réelle, PROBLEM avec
     complexité suffisante, cohérence niveau/séniorité.

  2. FALLBACK LLM UNIQUEMENT (validate_candidate_answer) :
     Appelé pendant l'ÉVALUATION uniquement si le code n'est PAS exécutable
     (pseudo-code, autre langage, timeout execution_engine).
     Dans ce cas, le LLM a produit un score via signal_extractor/evaluation_core
     et ce module applique les garde-fous finaux (plafonds, flags, réconciliation).

     IMPORTANT : validate_candidate_answer N'EST PLUS APPELÉ pour les
     questions PROBLEM Python exécutables — execution_engine les gère directement.
     La vérification ast.parse() (Layer 2) reste présente pour le fallback LLM,
     mais est redondante pour l'exécution directe (execution_engine fait mieux).

Couches de validation :
  Layer 1 — Structurelle (toujours exécutée dans le fallback) :
    - Réponse vide ou trop courte → score 0 garanti
    - Réponse = copie de la question → score 0 garanti

  Layer 2 — Sémantique Python (fallback LLM uniquement) :
    - Code Python : ast.parse() → erreur de syntaxe plafonne le score
    - SQL : vérification des mots-clés requis
    - Note : pour PROBLEM exécutable, cette vérification est gérée par
      execution_engine.ast_security_check() — pas de duplication en prod.

  Layer 3 — Post-LLM (après évaluation signal_extractor/evaluation_core) :
    - Score LLM > points_max → plafonner
    - Score LLM = max ET syntaxe incorrecte → plafonner à (points_max - 1)
    - Score LLM = 0 ET overlap > 50% avec expected_answer → min = 1
    - LLM trop sévère → détecter et signaler

  Layer 4 — Cohérence globale (validate_full_correction) :
    - Vérifier que le total earned <= total max
    - Flaguer les questions à score suspicieux pour revue humaine
    - Applicable à TOUS les types (exécution + fallback LLM)

  Layer 5 — Qualité des questions générées (validate_test_integrity) :
    - MCQ : zéro ambiguïté, options valides, pas de "all of the above"
    - SCENARIO : options nommées présentes, réponse non divulguée, contrainte réelle
    - PROBLEM : longueur suffisante, indicateurs de complexité présents,
                function_name et test_cases présents (v4.0)
    - Niveau : difficulté cohérente avec la séniorité (junior/mid/senior)
"""

import ast
import re
import math
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
# CONSTANTES
# ─────────────────────────────────────────────────────────────────

# Longueur minimale d'une réponse acceptable par type
MIN_ANSWER_LENGTH = {
    # types v2.x (compatibilité)
    "debug"    : 30,
    "practical": 50,
    # types v3.0 (compatibilité)
    "problem"  : 40,
    "scenario" : 60,
    # type v6.0
    "open"     : 60,   # question ouverte — décision + justification argumentée
}

# Si l'answer est trop similaire à la question (candidate copied it) → flag
MAX_QUESTION_OVERLAP_RATIO = 0.70

# Mots-clés SQL requis selon le type d'opération demandée
SQL_KEYWORD_PATTERNS = {
    "select": ["SELECT", "FROM"],
    "insert": ["INSERT", "INTO", "VALUES"],
    "update": ["UPDATE", "SET"],
    "delete": ["DELETE", "FROM"],
    "join"  : ["JOIN"],
    "group" : ["GROUP BY"],
    "having": ["HAVING"],
    "window": ["OVER", "PARTITION"],
}

# Mots-clés Python requis par pattern d'usage
PYTHON_PATTERNS = {
    "function": ["def ", "return"],
    "class"   : ["class "],
    "decorator": ["@"],
    "context_manager": ["with "],
    "exception": ["try:", "except"],
    "list_comp": ["for ", "in "],
    "async"   : ["async def", "await"],
}


# ─────────────────────────────────────────────────────────────────
# LAYER 1 — VALIDATION STRUCTURELLE
# ─────────────────────────────────────────────────────────────────

def _check_structural(answer: str, question_type: str) -> dict:
    """
    Vérifie les conditions minimales d'une réponse valide.
    Retourne {"ok": bool, "reason": str, "force_score": int|None, "short_answer": bool}

    Distinction critique :
      - Réponse vide          → hard block (ok=False, force_score=0) — LLM jamais appelé
      - Réponse trop courte   → soft gate  (ok=True, short_answer=True) — LLM appelé,
                                score cappé à 50% en réconciliation (R1b)

    Rationale : une réponse courte peut être correcte (ex: "Use SAP Fiori Launchpad").
    Bloquer avant le LLM introduirait des faux négatifs sur des réponses concises valides.
    """
    if not answer or not answer.strip():
        return {"ok": False, "reason": "empty_answer", "force_score": 0, "short_answer": False}

    stripped = answer.strip()
    min_len  = MIN_ANSWER_LENGTH.get(question_type, 20)

    if len(stripped) < min_len:
        # Soft gate : on signale mais on ne bloque pas
        return {
            "ok"          : True,
            "reason"      : "ok",
            "force_score" : None,
            "short_answer": True,
            "short_reason": f"answer_too_short ({len(stripped)} < {min_len} chars)",
        }

    return {"ok": True, "reason": "ok", "force_score": None, "short_answer": False}


def _check_answer_not_copied(question_text: str, answer: str) -> dict:
    """
    Détecte si le candidat a simplement copié l'énoncé comme réponse.
    Comparaison par tokens communs.
    """
    if not question_text or not answer:
        return {"copied": False}

    def tokenize(text):
        return set(re.findall(r'\b\w{4,}\b', text.lower()))

    q_tokens = tokenize(question_text)
    a_tokens = tokenize(answer)

    if not q_tokens or not a_tokens:
        return {"copied": False}

    overlap = len(q_tokens & a_tokens) / max(len(q_tokens), 1)

    # Copie détectée si :
    #   - fort overlap (le candidat reprend les mots de l'énoncé)
    #   - ET la réponse n'apporte aucun vocabulaire nouveau (< 30% de mots différents)
    # Ancienne logique : len(a_tokens) < len(q_tokens) * 0.8 → ne détectait pas
    # le cas où le candidat copie l'énoncé ET ajoute du texte (réponse plus longue)
    new_tokens = a_tokens - q_tokens
    new_ratio  = len(new_tokens) / max(len(a_tokens), 1)
    copied     = overlap > MAX_QUESTION_OVERLAP_RATIO and new_ratio < 0.30

    return {"copied": copied, "overlap_ratio": round(overlap, 2), "new_vocab_ratio": round(new_ratio, 2)}


# ─────────────────────────────────────────────────────────────────
# LAYER 2 — VALIDATION SÉMANTIQUE PYTHON
# ─────────────────────────────────────────────────────────────────

def _extract_code_blocks(text: str) -> list[str]:
    """
    Extrait les blocs de code depuis une réponse textuelle.
    Gère 3 formats : ```python ... ```, ``` ... ```, et code inline.
    """
    blocks = []

    # Format markdown: ```python ... ``` ou ``` ... ```
    md_pattern = re.compile(r'```(?:python|py)?\s*(.*?)```', re.DOTALL | re.IGNORECASE)
    for match in md_pattern.finditer(text):
        blocks.append(match.group(1).strip())

    # Si aucun bloc markdown, traiter le texte entier comme potentiel code
    # (uniquement si ça ressemble à du code : contient def/class/import/SELECT)
    if not blocks:
        code_indicators = ['def ', 'class ', 'import ', 'SELECT ', 'INSERT ', 'UPDATE ',
                          'return ', '    ', '\n    ', 'for ', 'if ']
        if any(ind in text for ind in code_indicators):
            blocks.append(text.strip())

    return blocks


def _check_python_syntax(answer: str) -> dict:
    """
    Tente de parser le code Python avec ast.parse().
    Un code valide syntaxiquement n'est pas forcément correct, mais
    un code invalide syntaxiquement ne peut pas être la bonne solution.

    Returns:
        {"syntax_ok": bool, "has_code": bool, "error": str|None}
    """
    code_blocks = _extract_code_blocks(answer)

    if not code_blocks:
        return {"syntax_ok": True, "has_code": False, "error": None}

    for block in code_blocks:
        try:
            ast.parse(block)
        except SyntaxError as e:
            return {
                "syntax_ok": False,
                "has_code" : True,
                "error"    : f"SyntaxError ligne {e.lineno}: {e.msg}",
            }
        except Exception as e:
            return {"syntax_ok": False, "has_code": True, "error": str(e)}

    return {"syntax_ok": True, "has_code": True, "error": None}


def _check_sql_keywords(answer: str, question_text: str) -> dict:
    """
    Pour les questions SQL, vérifie que la réponse contient les mots-clés appropriés.
    Déduit le type de requête attendu depuis l'énoncé.
    """
    q_lower  = question_text.lower()
    a_upper  = answer.upper()
    required = []
    found    = []
    missing  = []

    # Déduire les mots-clés requis depuis l'énoncé
    if any(w in q_lower for w in ["select", "query", "retrieve", "find", "get", "list"]):
        required.extend(["SELECT", "FROM"])
    if any(w in q_lower for w in ["join", "relationship", "related", "combine"]):
        required.append("JOIN")
    if any(w in q_lower for w in ["group", "aggregate", "count", "sum", "avg"]):
        required.append("GROUP BY")
    if any(w in q_lower for w in ["insert", "add", "create record"]):
        required.extend(["INSERT", "INTO"])
    if any(w in q_lower for w in ["update", "modify", "change"]):
        required.extend(["UPDATE", "SET"])
    if any(w in q_lower for w in ["delete", "remove"]):
        required.extend(["DELETE", "FROM"])

    if not required:
        return {"applicable": False, "required": [], "found": [], "missing": []}

    for kw in required:
        if kw in a_upper:
            found.append(kw)
        else:
            missing.append(kw)

    return {
        "applicable": True,
        "required"  : required,
        "found"     : found,
        "missing"   : missing,
        "ratio"     : len(found) / max(len(required), 1),
    }


def _compute_keyword_overlap(answer: str, expected: str) -> float:
    """
    Calcule le ratio de mots-clés techniques en commun entre la réponse du
    candidat et la solution attendue.
    Ignore les stop words (articles, prépositions, etc.).

    Un ratio > 0.5 signifie que le candidat a évoqué la majorité des concepts
    attendus — même si la formulation diffère.
    """
    STOP_WORDS = {
        'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
        'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
        'could', 'should', 'may', 'might', 'must', 'can', 'to', 'of',
        'in', 'on', 'at', 'by', 'for', 'with', 'from', 'up', 'about',
        'this', 'that', 'it', 'its', 'we', 'you', 'they', 'or', 'and',
        'but', 'not', 'no', 'so', 'if', 'then', 'else', 'return',
    }

    def extract_keywords(text: str) -> set:
        tokens = re.findall(r'\b[a-zA-Z_]\w*\b', text.lower())
        return {t for t in tokens if len(t) > 3 and t not in STOP_WORDS}

    kw_expected = extract_keywords(expected)
    kw_answer   = extract_keywords(answer)

    if not kw_expected:
        return 0.0

    overlap = len(kw_expected & kw_answer) / len(kw_expected)
    return round(overlap, 3)


# ─────────────────────────────────────────────────────────────────
# LAYER 3 — RÉCONCILIATION LLM + PYTHON
# ─────────────────────────────────────────────────────────────────

def _reconcile(
    llm_score    : int,
    llm_feedback : str,
    points_max   : int,
    question     : dict,
    answer       : str,
    py_checks    : dict,
) -> dict:
    """
    Reconcilie le score LLM avec les contraintes Python.

    Règles de décision (par priorité décroissante) :
      R1:  Réponse vide                       → score 0 (hard block — LLM jamais appelé)
      R1b: Réponse courte (soft gate)         → cap à 50% du max (LLM a quand même jugé)
      R2:  Réponse copiée depuis la question  → score 0 (Python override)
      R3:  Syntaxe Python incorrecte          → cap à (points_max - 1)
      R4:  SQL keywords manquants             → réduire proportionnellement
      R5:  LLM score = 0 + overlap > 50%     → élever à 1 (LLM trop sévère)
      R6:  LLM score > points_max             → plafonner (ne devrait pas arriver)
      R7:  Aucun problème détecté             → conserver le score LLM

    Returns:
        {
          "points_earned"      : int,
          "feedback"           : str,
          "validation_applied" : bool,
          "python_flags"       : list[str],
          "llm_score_original" : int,
        }
    """
    flags             = py_checks.get("flags", [])
    validation_applied = False
    final_score       = llm_score
    adjustments       = []

    # R1 — Réponse structurellement invalide
    struct = py_checks.get("structural", {})
    if not struct.get("ok", True):
        reason = struct.get("reason", "invalid")
        return {
            "points_earned"      : 0,
            "feedback"           : f"Réponse invalide : {reason}",
            "validation_applied" : True,
            "python_flags"       : [f"structural:{reason}"],
            "llm_score_original" : llm_score,
        }

    # R2 — Réponse copiée
    copy_check = py_checks.get("copy_check", {})
    if copy_check.get("copied"):
        return {
            "points_earned"      : 0,
            "feedback"           : "Réponse identique à l'énoncé — aucun point accordé",
            "validation_applied" : True,
            "python_flags"       : ["answer_copied_from_question"],
            "llm_score_original" : llm_score,
        }

    # R1b — Réponse courte (soft gate) → cap à 50% du max
    # Le LLM a jugé la réponse, mais sa concision est pénalisée.
    # Une réponse courte peut être correcte, mais ne peut pas mériter le max.
    if struct.get("short_answer"):
        cap_50 = max(1, math.ceil(points_max * 0.5))
        if final_score > cap_50:
            final_score = cap_50
            validation_applied = True
            short_reason = struct.get("short_reason", "short_answer")
            adjustments.append(f"short_answer → capped to {cap_50}/{points_max} (50%)")
            flags.append(f"soft_gate:{short_reason}")

    # R3 — Syntaxe Python incorrecte plafonne le score
    syntax = py_checks.get("syntax", {})
    if syntax.get("has_code") and not syntax.get("syntax_ok"):
        syntax_error = syntax.get("error", "SyntaxError")
        cap = max(1, points_max - 1)  # peut avoir identifié le bug mais fix incorrect
        if final_score > cap:
            final_score = cap
            validation_applied = True
            adjustments.append(f"syntax_error → capped to {cap}/{points_max}")
            flags.append(f"python_syntax_error:{syntax_error[:60]}")

    # R4 — SQL keywords manquants → réduire proportionnellement
    sql = py_checks.get("sql", {})
    if sql.get("applicable") and sql.get("missing"):
        kw_ratio = sql.get("ratio", 1.0)
        if kw_ratio < 0.5:
            new_cap = math.ceil(points_max * kw_ratio)
            if final_score > new_cap:
                final_score = new_cap
                validation_applied = True
                adjustments.append(
                    f"sql_missing_keywords:{sql['missing']} → capped to {new_cap}/{points_max}"
                )
                flags.append(f"sql_keywords_missing:{','.join(sql['missing'])}")

    # R5 — LLM trop sévère : score 0 mais overlap élevé avec expected_answer
    expected = question.get("expected_answer", "")
    if llm_score == 0 and expected:
        overlap = _compute_keyword_overlap(answer, expected)
        if overlap > 0.45:
            final_score = 1
            validation_applied = True
            adjustments.append(
                f"llm_too_harsh → min=1 (overlap={overlap:.2f} with expected)"
            )
            flags.append(f"possible_llm_overly_strict:overlap={overlap:.2f}")

    # R6 — Plafond absolu
    if final_score > points_max:
        final_score = points_max
        validation_applied = True
        adjustments.append(f"capped_to_max:{points_max}")

    # Construction feedback final
    feedback_parts = [llm_feedback] if llm_feedback else []
    if adjustments:
        feedback_parts.append(f"[Validation: {' | '.join(adjustments)}]")
    feedback = " — ".join(feedback_parts) if feedback_parts else "Évalué"

    return {
        "points_earned"      : max(0, int(final_score)),
        "feedback"           : feedback,
        "validation_applied" : validation_applied,
        "python_flags"       : flags,
        "llm_score_original" : llm_score,
    }


# ─────────────────────────────────────────────────────────────────
# ENTRY POINT PRINCIPAL
# ─────────────────────────────────────────────────────────────────

def validate_candidate_answer(
    question         : dict,
    candidate_answer : str,
    llm_result       : dict,
) -> dict:
    """
    Point d'entrée principal du validateur hybride.

    Prend le résultat LLM brut + la question + la réponse du candidat,
    et retourne une évaluation corrigée, plafonnée, et tracée.

    Args:
        question         : la question complète (avec expected_answer si disponible)
        candidate_answer : la réponse brute du candidat
        llm_result       : dict {"points_earned": int, "feedback": str}

    Returns:
        dict {
          "points_earned"      : int — score final
          "feedback"           : str — feedback enrichi
          "validation_applied" : bool — True si Python a modifié le score LLM
          "python_flags"       : list[str] — flags pour audit
          "llm_score_original" : int — score LLM avant correction
        }
    """
    # Support des nouveaux types v3.0 : problem / scenario
    # + compatibilité anciens types : debug / practical
    q_type     = question.get("type", "problem")
    q_text     = question.get("question", "")
    q_skill    = question.get("skill", "").lower()
    points_max = question.get("points", 4)
    llm_score  = max(0, min(points_max, int(llm_result.get("points_earned", 0))))
    llm_fb     = llm_result.get("feedback", "")

    py_checks = {"flags": []}

    # Layer 1 — Structurelle
    py_checks["structural"] = _check_structural(candidate_answer, q_type)

    # Arrêt anticipé uniquement si réponse vraiment vide (hard block)
    # Les réponses courtes (soft gate) continuent vers le LLM
    struct = py_checks["structural"]
    if not struct.get("ok"):
        return _reconcile(llm_score, llm_fb, points_max, question, candidate_answer, py_checks)

    # Fast semantic check pour les réponses courtes :
    # Si courte ET zéro overlap avec expected_answer → inutile d'appeler le LLM
    if struct.get("short_answer") and question.get("expected_answer"):
        overlap = _compute_keyword_overlap(candidate_answer, question["expected_answer"])
        if overlap == 0.0:
            logger.info(
                f"  [validator] fast_semantic_reject: short_answer + zero overlap "
                f"(type={q_type} skill={q_skill})"
            )
            return {
                "points_earned"      : 0,
                "feedback"           : (
                    f"Réponse trop courte et hors sujet : "
                    f"{struct.get('short_reason', 'short_answer')}"
                ),
                "validation_applied" : True,
                "python_flags"       : [
                    f"fast_semantic_reject:no_overlap",
                    f"soft_gate:{struct.get('short_reason', 'short_answer')}",
                ],
                "llm_score_original" : llm_score,
            }
        # overlap > 0 → réponse courte mais potentiellement valide → LLM juge,
        # réconciliation appliquera le cap à 50% via R1b

    # Layer 1b — Copie
    py_checks["copy_check"] = _check_answer_not_copied(q_text, candidate_answer)

    # Layer 2 — Sémantique Python
    # SCENARIO et OPEN ne nécessitent pas de code → pas de syntax check
    is_scenario = q_type in ("scenario", "open")
    if q_skill in ("python", "fastapi", "django", "flask", "backend") and not is_scenario:
        py_checks["syntax"] = _check_python_syntax(candidate_answer)
    else:
        py_checks["syntax"] = {"syntax_ok": True, "has_code": False, "error": None}

    # Layer 2b — SQL keywords
    # SCENARIO et OPEN sur SQL → on ne valide pas les keywords (réponse est textuelle)
    if q_skill in ("sql", "postgresql", "mysql", "database", "db", "t-sql") and not is_scenario:
        py_checks["sql"] = _check_sql_keywords(candidate_answer, q_text)
    else:
        py_checks["sql"] = {"applicable": False}

    # Layer 3 — Réconciliation
    result = _reconcile(llm_score, llm_fb, points_max, question, candidate_answer, py_checks)

    logger.info(
        f"  [validator] Q_type={q_type} skill={q_skill} "
        f"llm={llm_score} → final={result['points_earned']}/{points_max} "
        f"applied={result['validation_applied']} "
        f"flags={result['python_flags']}"
    )

    return result


# ─────────────────────────────────────────────────────────────────
# LAYER 5 — QUALITÉ DES QUESTIONS GÉNÉRÉES (pre-storage)
# Garantit que le LLM a respecté les règles de génération.
# Ces fonctions sont appelées dans validate_test_integrity().
# ─────────────────────────────────────────────────────────────────

# Mapping séniorité → difficultés autorisées
_ALLOWED_DIFFICULTIES: dict[str, set[str]] = {
    "junior": {"easy", "medium"},
    "mid"   : {"easy", "medium", "hard"},   # hard autorisé sur dernière Q
    "senior": {"medium", "hard"},
}

# Indicateurs de complexite attendus dans un PROBLEM serieux
_COMPLEXITY_INDICATORS = [
    "optimize", "optimiz",
    "design",
    "scalab",
    "edge case",
    "performance",
    "concurren",
    "thread", "async",
    "architect",
    "trade-off", "tradeoff",
    "constraint",
    "handle",
    "failure", "error handling",
    "pagination", "rate limit",
    # ETL / Data Integration complexity indicators
    "incremental", "delta", "upsert", "merge",
    "lookup", "reject", "error flow",
    "tmap", "subjob", "job design",
    "slowly changing", "scd",
    "cdc", "change data capture",
    "parallel", "bulk load",
    "data quality", "dedup",
    "staging", "metadata",
    "watermark", "checksum",
    "lineage", "transformation",
    "mapping", "connector",
    "restart", "recovery",
    "filter", "aggregate",
]

# Indicateurs de profondeur obligatoires pour un PROBLEM senior
# Un PROBLEM senior doit impliquer un vrai choix de design ou une problematique systeme
# IMPORTANT : liste élargie pour couvrir TOUS les domaines senior :
#   Frontend   : websocket, debounce, re-render, hook, memoize...
#   Backend    : retry, backoff, rate limit, queue, concurrency, cache...
#   DevOps/IaC : pipeline, terraform, kubernetes, deployment, scaling...
#   Data/ML    : pipeline, aggregat, transform, partition, index...
#   Security   : auth, encrypt, token, vulnerability, injection...
_SENIOR_DEPTH_INDICATORS = [
    # ── Frontend ─────────────────────────────────────────────────
    "websocket", "polling", "reconnect",
    "debounce", "throttle",
    "memoiz", "usememo", "usecallback",
    "re-render", "rerender",
    "lazy load", "code split",
    "hook", "custom hook",
    "state machine",

    # ── Backend / System ─────────────────────────────────────────
    "retry", "backoff",
    "race condition", "concurren",
    "error boundar", "fallback",
    "middleware",
    "cache", "invalidat",
    "rate limit", "queue",
    "circuit breaker",
    "transaction", "rollback", "atomic",
    "lock", "mutex", "semaphore",
    "async", "await", "thread",
    "pagination", "cursor",
    "idempoten",

    # ── DevOps / IaC / Cloud ─────────────────────────────────────
    "pipeline", "ci/cd", "cicd",
    "terraform", "infrastructure",
    "kubernetes", "container", "orchestrat",
    "deployment", "rolling update", "blue-green", "canary",
    "autoscal", "load balanc",
    "secret", "vault",
    "monitoring", "alerting", "observab",
    "replica", "failover",
    "module",                            # terraform module
    "provider",                          # terraform provider

    # ── Data / SQL / ETL ─────────────────────────────────────────
    "aggregat", "transform", "etl",
    "partition", "shard", "index",
    "window function", "cte",
    "batch", "stream",
    "schema", "migration",
    "normaliz", "denormaliz",

    # ── Security ─────────────────────────────────────────────────
    "authentif", "authoriz",
    "token", "jwt", "oauth",
    "encrypt", "hash",
    "injection", "xss", "csrf",
    "vulnerab", "sanitiz",
    "compliance", "audit",

    # ── Architecture générale ─────────────────────────────────────
    "design pattern",
    "trade-off", "tradeoff",
    "scalab", "performance",
    "fault toleran", "resilient",
    "microservice", "monolith",
    "event-driven", "message broker",
    "api gateway", "reverse proxy",

    # ── Go (golang) ───────────────────────────────────────────────
    "goroutine", "channel", "select {", "context.cancel",
    "sync.waitgroup", "sync.mutex", "errgroup",
    "defer ", "panic", "recover",
    "interface", "embed", "reflect",
    "grpc", "protobuf",

    # ── Docker / Container ────────────────────────────────────────
    "multi-stage", "multistage", "layer cach",
    "dockerfile", "entrypoint", "healthcheck",
    "volume", "network", "compose",
    "image size", "slim", "distroless",
    "registry", "push", "pull",

    # ── Java / JVM ───────────────────────────────────────────────
    "threadpool", "executorservice", "completablefuture",
    "synchronized", "volatile", "reentrantlock",
    "spring boot", "dependency injection", "bean",
    "jpa", "hibernate", "n+1",
    "garbage collect", "heap", "jvm",
    "stream api", "optional", "lambda",

    # ── Collaboration / Gestion (Jira/Confluence) ─────────────────
    "workflow", "automation rule", "webhook",
    "sprint velocity", "burndown", "epic",
    "permission scheme", "project role",
    "space permission", "template", "macro",

    # ── ETL / Data Integration (Talend, Informatica, NiFi, ADF…) ──
    # Senior ETL engineer must demonstrate advanced job design skills
    "tmap", "t_map",                             # Talend: Join/transform component
    "subjob", "sub job",                          # Talend: flow control
    "job design", "job designer",                 # Talend/Pentaho job architecture
    "lookup", "reject", "reject flow",            # ETL error routing
    "incremental load", "incremental",            # delta/CDC pattern
    "slowly changing dimension", "scd",           # data warehouse pattern
    "cdc", "change data capture",                 # real-time ingestion pattern
    "upsert", "merge",                            # idempotent write pattern
    "data quality", "dq rule",                    # data validation at scale
    "error handling", "error flow",               # robust ETL design
    "parallelism", "parallel",                    # ETL performance
    "staging", "staging area",                    # ETL architecture layer
    "metadata", "dynamic schema",                 # schema-driven ETL
    "orchestrat",                                 # workflow orchestration (already in DevOps)
    "dependency", "job chain",                    # ETL pipeline dependencies
    "delta", "watermark",                         # incremental processing patterns
    "checksum", "dedup", "deduplication",         # data integrity patterns
    "lineage", "data lineage",                    # data governance
    "mapping", "transformation rule",             # ETL logic design
    "connector", "connection pool",               # ETL connectivity
    "restart", "recovery",                        # fault-tolerant ETL
    "bulk load", "bulk insert",                   # high-volume loading
    "data vault", "dimension", "fact table",      # DWH modeling
]

# Patterns de PROBLEM trop simples pour un senior
_SENIOR_WEAK_PATTERNS = [
    r"display.*temperature",
    r"update every [0-9]+ second",
    r"simple component",
    r"show.*list of",
    r"render.*list",
    r"basic.*crud",
    r"simple.*filter",
]

# Patterns de PROBLEM triviaux interdits pour TOUS les niveaux
# Ces questions n'ont aucune valeur technique quelle que soit la séniorité
_TRIVIAL_PROBLEM_PATTERNS = [
    r"return.*greeting",
    r"greet.*patient",
    r"greet.*user",
    r"greet.*name",
    r"hello.*world",
    r"say.*hello",
    r"print.*hello",
    r"returns.*greeting.*message",
    r"greeting.*message",
    r"welcome.*message",
    r"returns a greeting",
    r"write.*function.*that.*says",
    r"function.*that.*greets",
]

# Mots-clés de contexte métier requis dans un SCENARIO
_BUSINESS_CONTEXT_KEYWORDS = [
    "company", "team", "client", "manager", "organization",
    "entreprise", "equipe", "system", "platform", "dashboard",
    "process", "workflow", "data", "report", "users", "needs",
    "want", "requires", "implement", "deploy", "build", "create",
    "design", "manage", "track", "automate", "integrate",
]

# Patterns de définition pure interdits dans un SCENARIO
_DEFINITION_PATTERNS_SCENARIO = [
    r"^what is\b",
    r"^what does\b.*\bdo\b",
    r"^define\b",
    r"^what (?:is the )?(?:purpose|role|definition) of\b",
]

# Marqueurs de présence d'options dans un SCENARIO
_SCENARIO_OPTION_MARKERS = [
    "option a", "option b", "option c",
    "a)", "b)", "c)",
    "choice a", "choice b",
    "approach a", "approach b",
    "- a:", "- b:", "- c:",
    "(a)", "(b)", "(c)",
    "vs ", "versus ",               # "X vs Y" est aussi une structure de choix
    "compare",                      # "compare these two approaches"
    "between",                      # "choose between X and Y"
    "either",                       # "either ... or ..."
]

# Mots-clés de contrainte réelle dans un SCENARIO
_CONSTRAINT_KEYWORDS = [
    "budget", "cost", "cost-",
    "performance", "latency", "throughput",
    "scale", "scalab", "load",
    "security", "compliance", "gdpr", "hipaa",
    "team", "deadline", "timeline",
    "limit", "constraint", "restrict",
    "bandwidth", "storage",
    "users", "requests per", "transactions",
    "migration", "legacy",
]


def _validate_mcq_quality(question: dict) -> list[str]:
    """
    Layer 5A — Valide la qualité d'un MCQ.

    Règles :
      - Minimum 3 options
      - Aucun "all of the above" / "none of the above"
      - Pas d'options dupliquées (même texte normalisé)
      - Options pas trop longues (> 120 chars → descriptif, pas un choix)
      - La réponse correcte est bien dans les options (redondant mais défensif)
    """
    issues  = []
    options = question.get("options", [])
    q_id    = question.get("id", "?")

    # 1. Nombre d'options — doit être exactement 4 (cohérent avec test_agent ligne 1596)
    if len(options) != 4:
        issues.append(f"Q{q_id} (MCQ): exactement 4 options requises ({len(options)} trouvées)")

    # 2. Patterns interdits
    forbidden_patterns = ["all of the above", "none of the above", "all of these", "none of these"]
    for opt in options:
        opt_lower = opt.lower().strip()
        if any(fp in opt_lower for fp in forbidden_patterns):
            issues.append(
                f"Q{q_id} (MCQ): option interdite détectée → '{opt[:60]}'"
            )

    # 3. Options dupliquées ou quasi-identiques
    normalized = [o.lower().strip() for o in options]
    if len(set(normalized)) != len(normalized):
        issues.append(f"Q{q_id} (MCQ): options dupliquées ou quasi-identiques")

    # 4. Options trop longues (descriptives, pas des choix)
    for idx, opt in enumerate(options):
        if len(opt.strip()) > 120:
            issues.append(
                f"Q{q_id} (MCQ): option {idx + 1} trop longue "
                f"({len(opt)} chars > 120) — probablement descriptive"
            )

    # 5. Réponse correcte présente dans les options (vérification défensive)
    answer = question.get("answer", "")
    if answer and options and answer not in options:
        issues.append(
            f"Q{q_id} (MCQ): réponse correcte '{answer[:50]}' absente des options"
        )

    return issues


def _validate_scenario_quality(question: dict, test_type: str = "platform") -> list[str]:
    """
    Layer 5B - Valide la qualite d'un SCENARIO.

    Le mode de validation est déterminé par le TYPE DU SKILL de la question,
    pas par le test_type global. Dans un test MIXED, une question SCENARIO
    sur un skill "platform" (ex: postgresql, jira) doit être validée en mode
    PLATFORM, pas TECH/MIXED.

    Deux modes :
      TECH/MIXED : options nommees obligatoires + contrainte reelle + pas de tool leak
                   → skill_type == "coding" ou "mixed"
      PLATFORM   : question ouverte sur l'outil - contexte metier requis + contrainte
                   → skill_type == "platform" OU test_type == "platform"
    """
    issues = []
    q_id      = question.get("id", "?")
    text      = question.get("question", "")
    text_l    = text.lower()
    skill     = question.get("skill", "").lower().strip()

    # Déterminer le mode de validation selon le type du skill individuel.
    # skill_type n'est pas injecté par le LLM — on l'infère depuis le nom du skill.
    # Règle : seuls les langages purs ET un test de type "tech" → règles comparatives strictes.
    # Tout le reste (mixed, platform, ETL, infra, slots "any", coding dans mixed test) →
    # validation ouverte (pas d'options nommées obligatoires).
    skill_type = question.get("skill_type", "").lower().strip()

    if not skill_type and skill:
        _PURE_CODING_SKILLS = {
            "python", "python3", "javascript", "typescript", "js", "ts",
            "java", "go", "golang", "ruby", "c", "c++", "c#", "csharp",
            "kotlin", "swift", "rust", "scala", "php", "r",
            "react", "angular", "vue", "node.js", "nodejs",
            "fastapi", "django", "flask", "asp.net", "asp.net core",
        }
        skill_type = "coding" if skill in _PURE_CODING_SKILLS else "mixed"

    # N'appliquer les règles TECH strictes (options nommées, tool leak) que si :
    # - skill_type == "coding" ET test_type == "tech"
    # Les tests MIXED avec skills coding génèrent des SCENARIO ouverts légitimes.
    # Les ETL/infra/platform tools doivent toujours passer en mode "platform".
    if skill_type == "coding" and test_type == "tech":
        effective_mode = "tech"
    else:
        effective_mode = "platform"

    # 1. Longueur minimale (tous types)
    if len(text.strip()) < 80:
        issues.append(
            "Q" + str(q_id) + " (SCENARIO): enonce trop court "
            "(" + str(len(text.strip())) + " chars < 80)"
        )

    # 2. Question de definition pure interdite (tous types)
    for pattern in _DEFINITION_PATTERNS_SCENARIO:
        if re.search(pattern, text_l.strip()):
            issues.append(
                "Q" + str(q_id) + " (SCENARIO): question de definition pure detectee "
                "- doit etre une situation reelle"
            )
            break

    # 3. Regles specifiques TECH/MIXED : options nommees + pas de tool leak + contrainte
    if effective_mode in ("tech", "mixed"):
        # 3a. Options nommees obligatoires
        has_options = any(marker in text_l for marker in _SCENARIO_OPTION_MARKERS)
        if not has_options:
            issues.append(
                "Q" + str(q_id) + " (SCENARIO/MIXED): options nommees manquantes "
                "- presenter 2-3 alternatives (ex: Azure DevOps vs GitHub Actions vs Jenkins)"
            )

        # 3b. Tool leak : le skill assigne ne doit pas etre le SEUL outil cite
        # (acceptable s'il apparait parmi plusieurs options)
        has_comparison = any(m in text_l for m in ["vs ", "versus ", "or ", "between", "compare"])
        skill_parts = [p for p in skill.replace("-", " ").split() if len(p) > 3]
        if skill in text_l and not has_comparison:
            issues.append(
                "Q" + str(q_id) + " (SCENARIO/MIXED): tool leak detecte ('" + skill + "') "
                "- l'outil assigne ne doit pas etre la seule option citee"
            )
        elif not has_comparison:
            for part in skill_parts:
                if part in text_l:
                    issues.append(
                        "Q" + str(q_id) + " (SCENARIO/MIXED): tool leak partiel ('" + part + "') "
                        "- ajouter des alternatives nommees"
                    )
                    break

        # 3c. Contrainte reelle obligatoire
        has_constraint = any(kw in text_l for kw in _CONSTRAINT_KEYWORDS)
        if not has_constraint:
            issues.append(
                "Q" + str(q_id) + " (SCENARIO/MIXED): contrainte reelle manquante "
                "- ajouter budget / latency / scale / security / compliance"
            )

    # 4. Regles specifiques PLATFORM : contexte metier requis
    else:  # effective_mode == "platform"
        has_context = any(kw in text_l for kw in _BUSINESS_CONTEXT_KEYWORDS)
        if not has_context:
            issues.append(
                "Q" + str(q_id) + " (SCENARIO/PLATFORM): contexte metier absent "
                "- decrire une situation reelle (company/team/users...)"
            )

    # 5. expected_answer et answer_criteria presents (tous types)
    if not question.get("expected_answer", "").strip():
        issues.append(
            "Q" + str(q_id) + " (SCENARIO): expected_answer manquant"
        )
    criteria = question.get("answer_criteria", [])
    if not criteria or all(not c.strip() for c in criteria):
        issues.append(
            "Q" + str(q_id) + " (SCENARIO): answer_criteria absent ou vide"
        )

    return issues


def _validate_problem_quality(question: dict, seniority: str = "mid") -> list[str]:
    """
    Layer 5C - Valide la qualite d'un PROBLEM.

    Regles :
      - Texte minimum 100 chars
      - Indicateurs de complexite requis (sauf junior easy)
      - Pour senior : indicateurs de profondeur obligatoires + patterns faibles interdits
      - expected_answer et answer_criteria presents
    """
    issues    = []
    q_id      = question.get("id", "?")
    text      = question.get("question", "")
    text_l    = text.lower()
    difficulty = question.get("difficulty", "medium")

    # 1. Longueur minimale
    if len(text.strip()) < 100:
        issues.append(
            "Q" + str(q_id) + " (PROBLEM): enonce trop court "
            "(" + str(len(text.strip())) + " chars < 100)"
        )

    # 2. Patterns triviaux interdits pour TOUS les niveaux (greeting, hello, welcome…)
    for pattern in _TRIVIAL_PROBLEM_PATTERNS:
        if re.search(pattern, text_l):
            issues.append(
                "Q" + str(q_id) + " (PROBLEM): question triviale detectee "
                "- pattern interdit: '" + pattern + "'. "
                "La question doit etre ancree dans le contexte metier du poste. "
                "REJETE: greeting/hello/welcome. "
                "ATTENDU: filtrer des donnees, compter des elements, traiter une liste metier."
            )
            break

    # 3. Indicateurs de complexite (pas requis pour junior easy)
    is_easy_junior = (seniority == "junior" and difficulty == "easy")
    if not is_easy_junior:
        has_complexity = any(ind in text_l for ind in _COMPLEXITY_INDICATORS)
        if not has_complexity:
            issues.append(
                "Q" + str(q_id) + " (PROBLEM): aucun indicateur de complexite detecte "
                "- ajouter edge case / performance / design / error handling"
            )

    # 3. Validation profondeur senior : patterns faibles interdits
    if seniority == "senior":
        for pattern in _SENIOR_WEAK_PATTERNS:
            if re.search(pattern, text_l):
                issues.append(
                    "Q" + str(q_id) + " (PROBLEM/SENIOR): question trop simple pour senior "
                    "- pattern faible detecte: '" + pattern + "'. "
                    "Ajouter WebSocket/retry/memoization/state management/design decision."
                )
                break

        has_depth = any(ind in text_l for ind in _SENIOR_DEPTH_INDICATORS)

        # Si la question elle-même ne contient pas d'indicateur,
        # vérifier aussi expected_answer et answer_criteria (souvent plus riches)
        if not has_depth:
            expected_l = question.get("expected_answer", "").lower()
            criteria_l = " ".join(question.get("answer_criteria", [])).lower()
            has_depth = (
                any(ind in expected_l for ind in _SENIOR_DEPTH_INDICATORS)
                or any(ind in criteria_l for ind in _SENIOR_DEPTH_INDICATORS)
            )

        if not has_depth:
            issues.append(
                "Q" + str(q_id) + " (PROBLEM/SENIOR): profondeur insuffisante "
                "- aucun indicateur senior detecte. "
                "Requis selon le domaine — Backend: retry/cache/concurrency/transaction/rate-limit | "
                "DevOps: pipeline/terraform/kubernetes/deployment/scaling | "
                "Frontend: websocket/debounce/memoize/re-render/design-pattern | "
                "Data: aggregat/partition/etl/index/schema | "
                "Security: auth/encrypt/token/compliance/audit"
            )

    # 4. expected_answer present
    if not question.get("expected_answer", "").strip():
        issues.append(
            "Q" + str(q_id) + " (PROBLEM): expected_answer manquant"
        )

    # 5. answer_criteria present
    criteria = question.get("answer_criteria", [])
    if not criteria or all(not c.strip() for c in criteria):
        issues.append(
            "Q" + str(q_id) + " (PROBLEM): answer_criteria absent ou vide"
        )

    return issues


def _validate_level_consistency(question: dict, seniority: str) -> list[str]:
    """
    Layer 5D — Vérifie la cohérence difficulté ↔ séniorité.

    Règles :
      - junior  : easy ou medium uniquement (jamais hard)
      - mid     : easy, medium ou hard (hard acceptable sur dernière Q)
      - senior  : medium ou hard uniquement (jamais easy)

    Note : 'mid' accepte formellement hard ici car le code de génération
    l'autorise sur la dernière question d'un groupe. On ne surbloque pas,
    mais on avertit si easy apparaît sur une question ouverte senior.
    """
    issues     = []
    q_id       = question.get("id", "?")
    q_type     = question.get("type", "")
    difficulty = question.get("difficulty", "")

    allowed = _ALLOWED_DIFFICULTIES.get(seniority, {"easy", "medium", "hard"})

    if difficulty and difficulty not in allowed:
        issues.append(
            f"Q{q_id} ({q_type.upper()}): difficulté '{difficulty}' "
            f"incompatible avec séniorité '{seniority}' "
            f"— attendu : {sorted(allowed)}"
        )

    # Avertissement spécifique : senior avec easy sur question ouverte
    if seniority == "senior" and difficulty == "easy" and q_type in ("problem", "scenario"):
        issues.append(
            f"Q{q_id} ({q_type.upper()}): easy sur question ouverte senior "
            f"— niveau insuffisant pour filtrer les candidats"
        )

    return issues




def validate_test_integrity(
    questions : list[dict],
    seniority : str = "mid",
    test_type : str = "platform",
    strategy  : dict = None,
) -> dict:
    """
    Valide l'intégrité ET la qualité des questions générées par le LLM
    avant de les stocker en base.

    Layers exécutés :
      - Layer existant : structure JSON, réponse dans options, points cohérents
      - Layer 5A : qualité MCQ (options, ambiguïté, longueur)
      - Layer 5B : qualité SCENARIO (options nommées, réponse non divulguée, contrainte)
                   → utilise le type du skill individuel (coding/platform/mixed)
                   → un skill "platform" dans un test MIXED → règles PLATFORM
      - Layer 5C : qualité PROBLEM (longueur, complexité, expected_answer)
      - Layer 5D : cohérence difficulté ↔ séniorité

    Args:
        questions : liste des questions générées par le LLM
        seniority : "junior" | "mid" | "senior" — niveau attendu du test
        test_type : "tech" | "platform" | "mixed"
        strategy  : résultat de compute_test_strategy() — optionnel mais recommandé
                    Permet d'injecter le type de chaque skill dans les questions
                    pour que _validate_scenario_quality() applique les bonnes règles.

    Returns:
        {
          "valid"          : bool — False si au moins une issue critique
          "issues"         : list[str] — bloquants (test rejeté)
          "warnings"       : list[str] — non bloquants (stocké mais signalé)
          "quality_score"  : int — 0-100, score de qualité des questions
          "quality_details": dict — détail par type de question
        }
    """
    issues   = []
    warnings = []

    # ── Construire un index skill → type depuis la stratégie ──────
    # Permet à _validate_scenario_quality de connaître le type de chaque skill
    # et d'appliquer les bonnes règles (PLATFORM vs TECH/MIXED) par question,
    # indépendamment du test_type global.
    skill_type_map: dict[str, str] = {}
    if strategy:
        for sk in strategy.get("skills_coding",   []):
            skill_type_map[sk.lower()] = "coding"
        for sk in strategy.get("skills_platform", []):
            skill_type_map[sk.lower()] = "platform"
        for sk in strategy.get("skills_mixed",    []):
            skill_type_map[sk.lower()] = "mixed"

    # Injecter skill_type dans chaque question pour que les validators l'utilisent
    for q in questions:
        sk = q.get("skill", "").lower().strip()
        if sk in skill_type_map:
            q["skill_type"] = skill_type_map[sk]

    # ── Cohérence des points ──────────────────────────────────────
    # Structure 10 questions : 5 MCQ×1 + 2 PROBLEM×4 + 3 SCENARIO×4 = 25 pts
    # Structure minimale      : 5 MCQ×1 + 0 PROBLEM + 5 SCENARIO×4 = 25 pts
    # Plage valide : 10 (tout MCQ×1) → 40 (tout PROBLEM/SCENARIO×4)
    total_pts = sum(q.get("points", 0) for q in questions)
    if total_pts < 10 or total_pts > 40:
        warnings.append(
            f"Total points = {total_pts} — attendu entre 10 et 40 "
            f"(ex: 5 MCQ×1 + 2 PROBLEM×4 + 3 SCENARIO×4 = 25)"
        )

    # ── Compteurs qualité ─────────────────────────────────────────
    quality_issues_by_type: dict[str, list[str]] = {
        "mcq": [], "scenario": [], "problem": [], "open": [], "level": []
    }

    for i, q in enumerate(questions):
        q_type  = q.get("type", "")
        q_id    = q.get("id", i + 1)
        q_pts   = q.get("points", 0)
        q_text  = q.get("question", "")

        # ── Vérification texte minimal ────────────────────────────
        if len(q_text.strip()) < 30:
            issues.append(f"Q{q_id}: texte trop court ({len(q_text)} chars)")

        # ── Layer existant : MCQ answer in options ────────────────
        if q_type == "mcq":
            opts   = q.get("options", [])
            answer = q.get("answer", "")
            if answer not in opts:
                issues.append(
                    f"Q{q_id} (MCQ): réponse correcte '{answer[:40]}' absente des options"
                )
            if q.get("expected_answer"):
                warnings.append(
                    f"Q{q_id} (MCQ): champ 'expected_answer' inutile dans une MCQ"
                )
            opts_lower = [o.lower().strip() for o in opts]
            if len(set(opts_lower)) < len(opts_lower):
                issues.append(f"Q{q_id} (MCQ): options dupliquées (Layer existant)")

        elif q_type in ("debug", "problem"):
            code_indicators = ['def ', 'class ', 'SELECT ', 'function ', '()', '=>', '    ']
            has_code = any(ind in q_text for ind in code_indicators)
            if q_type == "debug" and not has_code:
                warnings.append(f"Q{q_id} (debug): aucun code détecté dans l'énoncé")
            if not q.get("expected_answer", "").strip():
                warnings.append(
                    f"Q{q_id} ({q_type}): expected_answer vide — correction LLM moins fiable"
                )
            if not q.get("answer_criteria"):
                warnings.append(f"Q{q_id} ({q_type}): answer_criteria absent")

            # v4.0 — Vérification des champs execution_engine (PROBLEM uniquement)
            if q_type == "problem":
                eval_mode = q.get("evaluation_mode", "")
                is_llm_eval = (eval_mode == "llm")

                if not is_llm_eval and not q.get("function_name", "").strip():
                    issues.append(
                        f"Q{q_id} (problem): champ 'function_name' manquant — "
                        f"execution_engine ne peut pas s'exécuter"
                    )
                # starter_code : warning uniquement pour skills exécutables (Python)
                # Les LLM-skills (Java, Talend, Docker…) n'ont pas de starter_code — normal
                if not is_llm_eval and not q.get("starter_code", "").strip():
                    warnings.append(
                        f"Q{q_id} (problem): champ 'starter_code' manquant — "
                        f"le candidat ne verra pas la signature"
                    )
                if not is_llm_eval:
                    test_cases = q.get("test_cases", [])
                    if not test_cases or len(test_cases) < 3:
                        issues.append(
                            f"Q{q_id} (problem): 'test_cases' insuffisants "
                            f"({len(test_cases)} fournis, minimum 3 requis)"
                        )
                    else:
                        # Vérifier structure minimale de chaque test case
                        for i, tc in enumerate(test_cases):
                            if not isinstance(tc.get("input"), list):
                                issues.append(
                                    f"Q{q_id} (problem): test_case {i+1} — "
                                    f"'input' doit être une liste"
                                )
                            if "expected" not in tc:
                                issues.append(
                                    f"Q{q_id} (problem): test_case {i+1} — "
                                    f"champ 'expected' manquant"
                                )

        elif q_type in ("practical", "scenario"):
            if not q.get("expected_answer", "").strip():
                warnings.append(
                    f"Q{q_id} ({q_type}): expected_answer vide — correction LLM moins fiable"
                )
            if not q.get("answer_criteria"):
                warnings.append(f"Q{q_id} ({q_type}): answer_criteria absent")
            if q_pts < 3:
                warnings.append(
                    f"Q{q_id} ({q_type}): seulement {q_pts} pts — attendu >= 3"
                )

        elif q_type == "open":
            # v7.2 — expected_answer : WARNING uniquement (pas bloquant)
            # En v6.0+, les OPEN utilisent answer_criteria (C1-C5) comme référence.
            # expected_answer est optionnel — un placeholder générique est généré
            # dans le prompt. S'il est absent ou générique, c'est un warning,
            # pas un blocage : le LLM d'évaluation se base sur les critères.
            exp_ans = q.get("expected_answer", "").strip()
            if not exp_ans:
                warnings.append(
                    f"Q{q_id} (open): expected_answer absent — "
                    f"le LLM se base sur answer_criteria uniquement (acceptable)"
                )
            elif exp_ans.startswith("Ideal approach for"):
                # Placeholder générique — acceptable mais signalé
                warnings.append(
                    f"Q{q_id} (open): expected_answer est un placeholder générique — "
                    f"l'évaluation reposera sur answer_criteria"
                )
            # answer_criteria : bloquant uniquement si complètement absent
            if not q.get("answer_criteria"):
                issues.append(
                    f"Q{q_id} (open): answer_criteria absent — BLOQUANT "
                    f"(le LLM d'évaluation ne peut pas noter sans critères C1-C5)"
                )
            if q_pts < 3:
                warnings.append(
                    f"Q{q_id} (open): seulement {q_pts} pts — attendu >= 3"
                )

        # ── Layer 5 : validateurs qualité ────────────────────────
        if q_type == "mcq":
            mcq_issues = _validate_mcq_quality(q)
            quality_issues_by_type["mcq"].extend(mcq_issues)
            # "absente des options" → bloquant (layer 5 only)
            # "dupliqué"           → SKIP ici : déjà ajouté à issues par le layer
            #                        existant (ligne ~1037). Double-reporter crée 2
            #                        issues bloquantes pour le même défaut et gonfle
            #                        artificiel le compteur de rejets.
            # Tout le reste        → warning non bloquant.
            for iss in mcq_issues:
                if "absente des options" in iss:
                    issues.append(iss)          # bloquant — non couvert par layer existant
                elif "dupliqué" in iss:
                    pass                        # déjà dans issues via layer existant
                elif "option interdite" in iss:
                    issues.append(iss)          # bloquant — "All of the above" interdit
                else:
                    warnings.append(iss)        # non bloquant

        elif q_type == "scenario":
            scen_issues = _validate_scenario_quality(q, test_type)
            quality_issues_by_type["scenario"].extend(scen_issues)
            for iss in scen_issues:
                is_blocking = any(kw in iss for kw in [
                    "definition pure", "options nommees manquantes",
                    "tool leak", "contrainte reelle manquante",
                    "contexte metier absent",
                ])
                if is_blocking:
                    issues.append(iss)
                else:
                    warnings.append(iss)

        elif q_type == "open":
            # OPEN : validation v7.1 — vérification contrainte réelle + pas de définition pure
            open_issues: list[str] = []
            q_lower = q.get("question", "").lower()

            # 1. Définition pure → bloquant
            _DEF_PATTERNS_SIMPLE = [
                r"\bwhat is\b\s+(?:(?:a|an|the)\s+)?\w+\s*\?$",
                r"\bdefine\b\s+\w+",
            ]
            for pat in _DEF_PATTERNS_SIMPLE:
                if re.search(pat, q_lower) and len(q_lower) < 80:
                    open_issues.append(
                        f"Q{q_id} (open): definition_pure détectée — BLOQUANT "
                        f"(les questions OPEN doivent être situationnelles avec contrainte)"
                    )

            # 2. Contrainte réelle absente → bloquant (v7.1)
            # Une OPEN sans contrainte explicite génère des réponses vagues et non évaluables
            _OPEN_CONSTRAINT_RE = re.compile(
                r"\blatenc\w*|\bcost\b|\bscalab\w*|\bsecurit\w*|\bcomplian\w*|"
                r"\bbudget\b|\bperformance\b|\breal.time\b|\bteam\b|"
                r"\bconstraint\b|\brequirement\b|\bmust\b|\bdeadline\b|"
                r"\b\d+\s*(?:users?|people|TB|GB|k|ms|sec|min)\b|"
                r"\bno\s+(?:access|budget|downtime|additional)\b|"
                r"\blimited\b",
                re.IGNORECASE,
            )
            if not _OPEN_CONSTRAINT_RE.search(q.get("question", "")):
                open_issues.append(
                    f"Q{q_id} (open): contrainte_reelle_absente — BLOQUANT "
                    f"(toute question OPEN doit avoir une contrainte explicite : "
                    f"budget, délai, accès limité, performance, scale...)"
                )

            quality_issues_by_type["open"].extend(open_issues)
            for iss in open_issues:
                # Bloquant si définition pure OU contrainte absente
                if "BLOQUANT" in iss:
                    issues.append(iss)
                else:
                    warnings.append(iss)

        elif q_type in ("problem", "debug"):
            prob_issues = _validate_problem_quality(q, seniority)
            quality_issues_by_type["problem"].extend(prob_issues)
            for iss in prob_issues:
                is_blocking = any(kw in iss for kw in [
                    "trop court", "answer_criteria absent ou vide",
                    "trop simple pour senior", "profondeur insuffisante",
                    "question triviale detectee",   # greeting/hello/welcome — tous niveaux
                ])
                if is_blocking:
                    issues.append(iss)
                else:
                    warnings.append(iss)

        # Layer 5D — cohérence niveau (toujours en warning, jamais bloquant)
        level_issues = _validate_level_consistency(q, seniority)
        quality_issues_by_type["level"].extend(level_issues)
        warnings.extend(level_issues)

    # ── Score qualité 0-100 ───────────────────────────────────────
    total_q = max(len(questions), 1)
    total_quality_issues = sum(
        len(v) for v in quality_issues_by_type.values()
    )
    # Chaque issue de qualité coûte ~10 points, plafonné à 0
    quality_score = max(0, 100 - (total_quality_issues * 10))

    logger.info(
        f"[validator] validate_test_integrity — "
        f"seniority={seniority} valid={len(issues)==0} "
        f"issues={len(issues)} warnings={len(warnings)} "
        f"quality_score={quality_score}"
    )

    return {
        "valid"          : len(issues) == 0,
        "issues"         : issues,
        "warnings"       : warnings,
        "quality_score"  : quality_score,
        "quality_details": quality_issues_by_type,
    }


# ─────────────────────────────────────────────────────────────────
# VALIDATION GLOBALE D'UNE CORRECTION COMPLÈTE
# ─────────────────────────────────────────────────────────────────

def validate_full_correction(
    questions   : list[dict],
    answers     : list[dict],
    corrections : list[dict],
) -> dict:
    """
    Validation finale de l'ensemble d'une correction.

    Vérifie la cohérence globale :
      - Chaque question a bien une correction
      - Aucun score ne dépasse le max de sa question
      - Le total earned est plausible (ni 0/11 ni 11/11 sur n=1)
      - Détecte les patterns suspects (ex: tous les open à 0)

    Returns:
        {"ok": bool, "flags": list[str], "review_recommended": bool}
    """
    flags              = []
    review_recommended = False

    q_map = {q["id"]: q for q in questions}
    c_map = {c["question_id"]: c for c in corrections}

    total_max    = 0
    total_earned = 0
    open_earned  = 0
    open_max     = 0

    for qid, q in q_map.items():
        pts_max = q.get("points", 0)
        total_max += pts_max

        if qid not in c_map:
            flags.append(f"Q{qid}: non corrigée")
            continue

        corr   = c_map[qid]
        earned = corr.get("points_earned", 0)
        total_earned += earned

        # Dépassement du max
        if earned > pts_max:
            flags.append(f"Q{qid}: {earned}>{pts_max} pts — impossible, plafonné")
            corr["points_earned"] = pts_max
            earned = pts_max

        if q.get("type") in ("debug", "practical", "problem", "scenario", "open"):
            open_earned += earned
            open_max    += pts_max

    # Questions ouvertes toutes à 0 → suspicieux si candidat a répondu
    if open_max > 0 and open_earned == 0:
        all_open_answered = all(
            len(str(a.get("answer", "")).strip()) > 20
            for a in answers
            if any(q["id"] == a["question_id"] and q["type"] in ("debug", "practical", "problem", "scenario", "open")
                   for q in questions)
        )
        if all_open_answered:
            flags.append(
                "all_open_questions_scored_0 despite non-empty answers — review recommended"
            )
            review_recommended = True

    # Score total = 0 mais toutes les réponses non vides → suspicieux
    if total_earned == 0 and all(len(str(a.get("answer", "")).strip()) > 10 for a in answers):
        flags.append("total_score=0 with all questions answered — possible LLM error")
        review_recommended = True

    # Score parfait → flag pour vérification
    if total_max > 0 and total_earned == total_max:
        flags.append("perfect_score — verification recommended")

    logger.info(
        f"  [validator] Correction globale : {total_earned}/{total_max} "
        f"flags={flags} review={review_recommended}"
    )

    return {
        "ok"                 : len([f for f in flags if "impossible" in f or "error" in f]) == 0,
        "flags"              : flags,
        "review_recommended" : review_recommended,
        "total_earned"       : total_earned,
        "total_max"          : total_max,
    }