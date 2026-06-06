"""
skill_classifier.py — Skill Intelligence Layer (v1.2)

Rôle :
    Classer chaque skill en : coding / platform / mixed
    via un LLM — aucun hardcode, fonctionne avec n'importe quelle technologie.

Pipeline :
    1. Le RH fournit coding_skills / platform_skills / mixed_skills
    2. Ce module valide et corrige la classification via LLM
    3. Si confidence > 0.8 → correction appliquée
    4. Sinon → choix RH conservé
    5. Retourne skills_final : liste unifiée avec type validé

CORRECTIONS v1.1 :
    - Prompt LLM renforcé avec règle des 3 catégories claire + exemples MIXED explicites
    - Garde-fou MIXED : si RH déclare mixed ET LLM confidence < 0.95 → on garde mixed
    - _FALLBACK_TYPES aligné sur la règle : docker/k8s/aws/gcp = mixed (pas coding)
    - MAX_SKILLS supprimé (géré dynamiquement par compute_test_strategy)

Utilisé par :
    test_agent.py → run_generate_test() → classify_and_validate_skills()
"""

import json
import logging
import os
import re
from typing import Optional

from dotenv import load_dotenv
#from openai import OpenAI
from groq import Groq

load_dotenv()
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────
# CONSTANTES
# ─────────────────────────────────────────────────────────────────

OPENROUTER_MODEL_CLASSIFY = "llama-3.3-70b-versatile"
CONFIDENCE_THRESHOLD = 0.8    # seuil pour appliquer une correction LLM
# CORRECTION v1.1 : seuil plus haut pour corriger un skill déclaré "mixed" par le RH
# → le LLM doit être très certain (0.95) pour reclassifier un mixed en coding/platform
CONFIDENCE_THRESHOLD_MIXED_OVERRIDE = 0.95
MAX_RETRY_CLASSIFY   = 2      # retries pour l'appel LLM classification

# Types valides
VALID_TYPES = {"coding", "platform", "mixed"}


# ─────────────────────────────────────────────────────────────────
# CLIENT GROQ (partagé — singleton)
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
# PROMPT DE CLASSIFICATION — v1.1 RENFORCÉ
# ─────────────────────────────────────────────────────────────────

def _build_classification_prompt(skills_to_check: list[dict]) -> str:
    """
    Construit le prompt pour valider la classification de chaque skill.

    CORRECTION v1.1 :
    - Règle des 3 catégories réécrite avec la distinction clé :
        coding   = code pur (langage, framework, algo)
        platform = outil pur (dashboard, no-code, ERP, ticketing)
        mixed    = code + système/exécution/infrastructure
    - Exemples MIXED explicitement listés pour guider le LLM
    - Instruction STRONG : ne jamais reclassifier docker/k8s/terraform
      en coding — ils sont ALWAYS mixed
    """
    skills_json = json.dumps(skills_to_check, ensure_ascii=False)

    return f"""You are a technical classification expert for IT recruitment tests.

Your task: validate whether each skill is correctly classified as coding / platform / mixed.

════════════════════════════════════════════════════
CLASSIFICATION RULES — READ CAREFULLY
════════════════════════════════════════════════════

RULE 1 — "coding" : PURE CODE ONLY
  The skill is about writing algorithms, business logic, or application code.
  The candidate writes functions, classes, or components in a general-purpose language.
  Examples: Python, JavaScript, TypeScript, Java, Go, C#, Rust,
            HTML/CSS, React, Angular, Vue, FastAPI, Django, Flask, Node.js,
            ASP.NET, ASP.NET Core, Jest, Pytest, unit testing
  ⚠️ SQL and T-SQL are NOT coding — they are MIXED (see Rule 3)

RULE 2 — "platform" : PURE TOOL USAGE
  The skill is about using a software tool, dashboard, or platform.
  No code or scripting required — configuration, clicks, reports, workflows.
  Examples: Power BI, Power Apps, Power Automate, SharePoint, Dynamics 365,
            Microsoft Dynamics, SSIS (drag-drop ETL), Agile/Scrum methodology,
            Jira (ticket management), Confluence (documentation),
            Azure Portal (console only), Salesforce (admin/config only),
            ServiceNow (admin), Tableau (report building)

RULE 3 — "mixed" : CODE + SYSTEM / INFRASTRUCTURE / EXECUTION
  The skill requires BOTH writing configuration/code AND understanding
  how systems are packaged, deployed, orchestrated, or run at infrastructure level.
  This is NOT pure application code — it involves containers, pipelines,
  cloud infrastructure, or runtime environment management.

  ⚠️  CRITICAL MIXED SKILLS — NEVER classify these as "coding":
      docker          → mixed  (write Dockerfiles + manage containers)
      kubernetes / k8s → mixed (write manifests + orchestrate clusters)
      terraform        → mixed (write IaC + provision cloud infra)
      ansible          → mixed (write playbooks + configure systems)
      aws              → mixed (code + cloud infrastructure)
      gcp              → mixed (code + cloud infrastructure)
      azure            → mixed (code + cloud infrastructure)
      azure devops     → mixed (CI/CD pipelines + project management)
      jenkins          → mixed (write pipeline scripts + manage CI/CD)
      github actions   → mixed (write YAML workflows + CI/CD)
      gitlab ci        → mixed (write .gitlab-ci.yml + pipelines)
      helm             → mixed (write charts + deploy k8s apps)
      linux / bash     → mixed (scripting + system administration)
      elasticsearch    → mixed (query DSL + cluster management)
      kafka            → mixed (producer/consumer code + broker config)
      rabbitmq         → mixed (messaging code + broker management)
      redis            → mixed (commands/code + cache/infra management)
      sql / t-sql / tsql / plsql  → mixed (query writing + DBA/schema knowledge — NOT pure coding)
      postgresql / mysql / mongodb → mixed (SQL/queries + DBA/config)
      spark / hadoop   → mixed (code + distributed system management)
      talend           → mixed (visual job design + tMap expressions + embedded Java/code)
      informatica      → mixed (mapping designer + transformations + scripting)
      pentaho / pdi    → mixed (job designer + JavaScript steps + SQL queries)
      apache nifi      → mixed (processor config + custom scripts + data flow)
      datastage        → mixed (stage design + transformer expressions + scripts)
      matillion        → mixed (orchestration + SQL transformations + cloud config)
      mulesoft         → mixed (flow design + DataWeave scripts + connectors)
      boomi            → mixed (process design + scripting + connector config)
      azure data factory → mixed (pipeline design + expressions + linked services)
      aws glue         → mixed (visual ETL + PySpark scripts + catalog config)
      apache beam      → mixed (pipeline code + runner config + transforms)

════════════════════════════════════════════════════
DECISION LOGIC
════════════════════════════════════════════════════

Ask yourself:
  Q1: Does it require writing application code (functions, classes, algorithms)?
  Q2: Does it involve managing infrastructure, containers, pipelines, or systems?

  Q1=YES, Q2=NO  → coding
  Q1=NO,  Q2=NO  → platform
  Q1=YES, Q2=YES → mixed
  Q1=NO,  Q2=YES → mixed

════════════════════════════════════════════════════

Skills to validate:
{skills_json}

For each skill, check if the given_type is correct.
Return ONLY a JSON array. No text before or after.

Format:
[
  {{
    "name": "skill_name",
    "given": "mixed",
    "corrected": "mixed",
    "confidence": 0.97,
    "reason": "Docker requires writing Dockerfiles AND managing container infrastructure — mixed"
  }}
]

STRICT RULES:
- If given_type is correct → set corrected = given_type, confidence >= 0.85
- If given_type is wrong   → set corrected = correct_type, confidence >= 0.80
- For any skill in the CRITICAL MIXED list above → always set corrected = "mixed"
- confidence must be between 0.0 and 1.0
- reason must explain using the Q1/Q2 decision logic
- Return ALL skills, even those that are correctly classified"""


# ─────────────────────────────────────────────────────────────────
# APPEL LLM + PARSING
# ─────────────────────────────────────────────────────────────────

def _call_llm_classify(prompt: str) -> str:
    """LLM call via OpenRouter."""
    client = _get_openrouter_client()
    response = client.chat.completions.create(
        model=OPENROUTER_MODEL_CLASSIFY,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=1024,
    )
    return response.choices[0].message.content.strip()

def _extract_json_array(text: str) -> list:
    """Extrait un tableau JSON depuis la réponse LLM."""
    # Supprimer les balises <think> si présentes (certains modèles)
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()

    # Tenter parse direct
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    # Chercher un tableau JSON dans le texte
    m = re.search(r'\[.*\]', text, re.DOTALL)
    if m:
        try:
            result = json.loads(m.group(0))
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Impossible d'extraire un tableau JSON. Réponse: {text[:300]}")


# ─────────────────────────────────────────────────────────────────
# LOGIQUE DE DÉCISION — v1.1
# ─────────────────────────────────────────────────────────────────

# CORRECTION v1.1 : liste des skills qui sont TOUJOURS mixed
# Garde-fou Python indépendant du LLM — priorité absolue
_ALWAYS_MIXED: set[str] = {
    "docker", "kubernetes", "k8s", "terraform", "ansible",
    "aws", "gcp", "azure", "azure devops",
    "jenkins", "github actions", "gitlab ci", "gitlab-ci",
    "helm", "linux", "bash",
    "elasticsearch", "kafka", "rabbitmq", "redis",
    "postgresql", "mysql", "mongodb", "mariadb",
    "spark", "hadoop", "airflow", "dbt",
    # SQL skills — non exécutables comme fonctions Python.
    # test_cases input/expected non générables de façon fiable par le LLM.
    # Classifiés mixed : écriture de requêtes + connaissance DBA/schéma.
    "sql", "t-sql", "tsql", "plsql", "pl/sql",
    # Mobile cross-platform — code + déploiement plateforme (iOS/Android/store)
    "xamarin", "maui", ".net maui", "react native",
    # Salesforce — admin/config + Apex/LWC dev selon contexte → mixed par défaut
    "salesforce",
    # ETL / Data Integration tools — GUI-driven + scripting/config hybrid.
    # They involve BOTH visual job design AND scripting (tMap, tJava, expressions).
    # Classified mixed : tool usage + embedded code/expressions logic.
    "talend", "talend open studio", "talend cloud", "talend studio",
    "informatica", "informatica powercenter", "informatica cloud", "iics",
    "pentaho", "pentaho data integration", "pdi", "kettle",
    "apache nifi", "nifi",
    "datastage", "ibm datastage",
    "matillion",
    "fivetran",
    "stitch", "stitch data",
    "boomi", "dell boomi",
    "mulesoft", "anypoint",
    "azure data factory", "adf",
    "aws glue",
    "google dataflow", "dataflow",
    "apache beam", "beam",
    "snaplogic",
    # CI/CD generique — toujours mixed (pipeline + infra)
    "ci/cd", "cicd",
    # SSIS — ETL Microsoft avec scripting Script Task / Data Flow expressions
    # Bien que souvent utilisé en drag-drop, il inclut du C# / VB embedded
    "ssis", "sql server integration services",
    # Variantes composites courantes — souvent saisies ainsi par les RH
    "bash scripting", "shell scripting",   # scripting système → mixed
    "aws s3", "aws ec2", "aws lambda", "aws rds", "aws ecs", "aws eks",
    "google cloud", "google cloud platform",
    "azure blob storage", "azure functions", "azure kubernetes service", "aks",
    "ci/cd pipelines", "cicd pipelines",   # variante verbale → mixed
    "version control", "git",              # gestion de code + workflow → mixed
}


def _apply_correction(item: dict, given_type_original: str) -> dict:
    """
    Applique la règle de décision avec garde-fous v1.1.

    Règles par priorité :
      P0 — Si le skill est dans _ALWAYS_MIXED → forcer "mixed", ignorer le LLM
      P1 — Si given_type = "mixed" ET confidence LLM < 0.95 → garder "mixed"
           (le LLM doit être très certain pour reclassifier un infra skill)
      P2 — Si confidence >= 0.8 ET correction différente → appliquer correction
      P3 — Sinon → garder given_type

    Retourne :
        {
            "name"       : str,
            "type"       : str,   # type final retenu
            "corrected"  : bool,  # True si correction appliquée vs given_type_original
            "confidence" : float,
            "reason"     : str,
        }
    """
    name       = str(item.get("name", "")).strip().lower()
    given      = str(item.get("given", given_type_original)).strip().lower()
    corrected  = str(item.get("corrected", given)).strip().lower()
    confidence = float(item.get("confidence", 0.5))
    reason     = str(item.get("reason", ""))

    # Sécurité : types invalides → fallback coding
    if given not in VALID_TYPES:
        given = "coding"
    if corrected not in VALID_TYPES:
        corrected = given

    # ── P0 : Garde-fou ALWAYS_MIXED — priorité absolue ────────────
    # Indépendant du LLM — ces skills sont toujours mixed
    if name in _ALWAYS_MIXED:
        final_type    = "mixed"
        was_corrected = (given_type_original != "mixed")

        # Raison précise selon la famille de skill — évite le message trompeur
        # "infrastructure/cloud" pour des skills comme SQL ou ETL tools
        _SQL_SKILLS  = {"sql", "t-sql", "tsql", "plsql", "pl/sql"}
        _DB_SKILLS   = {"postgresql", "mysql", "mongodb", "mariadb", "elasticsearch", "redis"}
        _ETL_SKILLS  = {
            "talend", "talend open studio", "talend cloud", "talend studio",
            "informatica", "informatica powercenter", "informatica cloud", "iics",
            "pentaho", "pentaho data integration", "pdi", "kettle",
            "apache nifi", "nifi", "datastage", "ibm datastage", "matillion",
            "fivetran", "stitch", "stitch data", "boomi", "dell boomi",
            "mulesoft", "anypoint", "azure data factory", "adf",
            "aws glue", "google dataflow", "dataflow", "apache beam", "beam",
            "snaplogic", "ssis", "sql server integration services",
        }
        _MOBILE_SKILLS = {"xamarin", "maui", ".net maui", "react native"}

        if name in _SQL_SKILLS:
            p0_reason = "SQL skill — query writing + DBA/schema knowledge — always mixed (P0 guard)"
        elif name in _DB_SKILLS:
            p0_reason = "Database skill — query/code + server config/admin — always mixed (P0 guard)"
        elif name in _ETL_SKILLS:
            p0_reason = "ETL/Integration tool — visual design + embedded scripting — always mixed (P0 guard)"
        elif name in _MOBILE_SKILLS:
            p0_reason = "Cross-platform mobile skill — code + platform deployment — always mixed (P0 guard)"
        elif name in {"salesforce"}:
            p0_reason = "Salesforce — admin/config + Apex/LWC dev depending on context — always mixed (P0 guard)"
        else:
            p0_reason = "Infrastructure/container/cloud/CI-CD skill — always mixed (P0 guard)"

        if was_corrected:
            logger.info(
                f"  [classifier] '{name}' : {given_type_original} → mixed "
                f"(garde-fou ALWAYS_MIXED — {p0_reason.split(' — ')[0]})"
            )
        else:
            logger.info(f"  [classifier] '{name}' : mixed ✓ (ALWAYS_MIXED confirmé)")
        return {
            "name"      : name,
            "type"      : "mixed",
            "corrected" : was_corrected,
            "confidence": 1.0,
            "reason"    : p0_reason,
        }

    # ── P1 : Garde-fou MIXED — seuil renforcé ────────────────────
    # Si le RH a déclaré "mixed" et que le LLM veut changer en coding/platform
    # → exiger une confidence très haute (0.95) pour accepter la correction
    if given_type_original == "mixed" and corrected != "mixed":
        if confidence < CONFIDENCE_THRESHOLD_MIXED_OVERRIDE:
            logger.info(
                f"  [classifier] '{name}' : correction LLM ({given} → {corrected}, "
                f"confidence={confidence:.2f}) refusée — "
                f"seuil mixed={CONFIDENCE_THRESHOLD_MIXED_OVERRIDE} non atteint → RH conservé (mixed)"
            )
            return {
                "name"      : name,
                "type"      : "mixed",
                "corrected" : False,
                "confidence": confidence,
                "reason"    : reason,
            }

    # ── P2 : Correction LLM standard ─────────────────────────────
    if confidence >= CONFIDENCE_THRESHOLD and corrected != given:
        final_type    = corrected
        was_corrected = (given_type_original != corrected)
        logger.info(
            f"  [classifier] '{name}' : {given} → {corrected} "
            f"(confidence={confidence:.2f}) — CORRIGÉ"
        )
    else:
        # ── P3 : Garder le choix RH ───────────────────────────────
        final_type    = given
        was_corrected = False
        if corrected != given:
            logger.info(
                f"  [classifier] '{name}' : correction {corrected} ignorée "
                f"(confidence={confidence:.2f} < {CONFIDENCE_THRESHOLD}) — RH conservé"
            )

    return {
        "name"      : name,
        "type"      : final_type,
        "corrected" : was_corrected,
        "confidence": confidence,
        "reason"    : reason,
    }


# ─────────────────────────────────────────────────────────────────
# FALLBACK — sans LLM (si Groq indisponible)
# ─────────────────────────────────────────────────────────────────

# CORRECTION v1.1 : docker/k8s/aws/gcp/postgresql = mixed (pas coding)
# Dictionnaire de fallback minimal pour les skills très courants
# NE PAS AJOUTER ICI — c'est uniquement un filet de sécurité d'urgence
_FALLBACK_TYPES: dict[str, str] = {
    # coding — langages et frameworks purs
    "python"       : "coding", "javascript"  : "coding", "typescript": "coding",
    "c#"           : "coding", "java"        : "coding", "go"        : "coding",
    "rust"         : "coding",
    "html"         : "coding", "css"         : "coding", "react"     : "coding",
    "angular"      : "coding", "vue"         : "coding", "asp.net"   : "coding",
    "asp.net core" : "coding", "fastapi"     : "coding", "django"    : "coding",
    "flask"        : "coding", "node.js"     : "coding", "nodejs"    : "coding",
    "unit testing" : "coding", "jest"        : "coding", "pytest"    : "coding",
    "kotlin"       : "coding", "swift"       : "coding", "scala"     : "coding",
    "php"          : "coding", "ruby"        : "coding", "r"         : "coding",
    "graphql"      : "coding", "rest api"    : "coding", "grpc"      : "coding",
    # Variantes société — langages web
    "html5"        : "coding", "css3"        : "coding",
    "c# .net"      : "coding", "dotnet"      : "coding", ".net"      : "coding",

    # platform — outils purs sans code
    "power bi"          : "platform", "power apps"        : "platform",
    "power automate"    : "platform", "sharepoint"        : "platform",
    "dynamics 365"      : "platform", "microsoft dynamics": "platform",
    "erp"               : "platform", "crm"               : "platform",
    "dynamics 365 erp"  : "platform", "dynamics 365 crm"  : "platform",
    "power platform"    : "platform",
    "agile"             : "platform", "scrum"             : "platform",
    "agile/scrum"       : "platform", "méthodes agiles"   : "platform",
    "jira"              : "platform", "confluence"        : "platform",
    "tableau"           : "platform", "servicenow"        : "platform",
    "salesforce admin"  : "platform", "azure portal"      : "platform",
    "trello"            : "platform", "notion"            : "platform",
    "monday"            : "platform",
    # Outils Microsoft 365 / collaboration
    "microsoft 365"     : "platform", "office 365"        : "platform",
    "teams"             : "platform", "excel"             : "platform",
    "word"              : "platform", "powerpoint"        : "platform",

    # mixed — infra + code ou outil + scripting
    # CORRECTION v1.1 : docker, k8s, cloud providers → mixed (pas coding)
    # CORRECTION v1.2 : ssis, ci/cd → mixed ; sync complète avec _ALWAYS_MIXED
    "docker"         : "mixed", "kubernetes"    : "mixed", "k8s"           : "mixed",
    "terraform"      : "mixed", "ansible"       : "mixed", "azure"         : "mixed",
    "azure devops"   : "mixed", "aws"           : "mixed", "gcp"           : "mixed",
    "jenkins"        : "mixed", "github actions": "mixed", "gitlab ci"     : "mixed",
    "gitlab-ci"      : "mixed",
    "helm"           : "mixed", "linux"         : "mixed", "bash"          : "mixed",
    "elasticsearch"  : "mixed", "kafka"         : "mixed", "rabbitmq"      : "mixed",
    "redis"          : "mixed", "postgresql"    : "mixed", "mysql"         : "mixed",
    "mongodb"        : "mixed", "mariadb"       : "mixed",
    "spark"          : "mixed", "hadoop"        : "mixed",
    "airflow"        : "mixed", "dbt"           : "mixed",
    "sql"            : "mixed", "t-sql"         : "mixed", "tsql"          : "mixed",
    "plsql"          : "mixed", "pl/sql"        : "mixed",
    # Mobile cross-platform
    "xamarin"        : "mixed", "maui"          : "mixed", ".net maui"     : "mixed",
    "react native"   : "mixed",
    # Salesforce — mixed par défaut (admin + Apex/LWC dev)
    "salesforce"     : "mixed",
    # ETL / Data Integration — mixed (GUI + embedded scripting/expressions)
    "talend"         : "mixed", "talend open studio": "mixed", "talend cloud": "mixed",
    "talend studio"  : "mixed",
    "informatica"    : "mixed", "informatica powercenter": "mixed",
    "informatica cloud": "mixed", "iics"        : "mixed",
    "pentaho"        : "mixed", "pentaho data integration": "mixed",
    "pdi"            : "mixed", "kettle"        : "mixed",
    "apache nifi"    : "mixed", "nifi"          : "mixed",
    "datastage"      : "mixed", "ibm datastage" : "mixed",
    "matillion"      : "mixed", "fivetran"      : "mixed",
    "stitch"         : "mixed", "stitch data"   : "mixed",
    "boomi"          : "mixed", "dell boomi"    : "mixed",
    "mulesoft"       : "mixed", "anypoint"      : "mixed",
    "azure data factory": "mixed", "adf"        : "mixed",
    "aws glue"       : "mixed", "google dataflow": "mixed",
    "dataflow"       : "mixed", "apache beam"   : "mixed",
    "beam"           : "mixed", "snaplogic"     : "mixed",
    # v1.2 : ssis et ci/cd → mixed (scripting embedded + pipeline infra)
    "ssis"           : "mixed", "sql server integration services": "mixed",
    "ci/cd"              : "mixed", "cicd"              : "mixed",
    # Variantes composites
    "bash scripting"     : "mixed", "shell scripting"   : "mixed",
    "aws s3"             : "mixed", "aws ec2"           : "mixed",
    "aws lambda"         : "mixed", "aws rds"           : "mixed",
    "google cloud"       : "mixed", "azure blob storage": "mixed",
    "ci/cd pipelines"    : "mixed", "git"               : "mixed",
}



def _fallback_classify(name: str, given_type: str) -> str:
    """
    Fallback si le LLM est indisponible.
    Applique aussi le garde-fou ALWAYS_MIXED avant de consulter le dictionnaire.
    """
    key = name.strip().lower()
    # Garde-fou P0 même en mode fallback
    if key in _ALWAYS_MIXED:
        return "mixed"
    return _FALLBACK_TYPES.get(key, given_type)


# ─────────────────────────────────────────────────────────────────
# FONCTION PRINCIPALE
# ─────────────────────────────────────────────────────────────────

def classify_and_validate_skills(
    coding_skills   : list[str],
    platform_skills : list[str],
    mixed_skills    : list[str],
    use_llm         : bool = True,
) -> dict:
    """
    Point d'entrée principal du Skill Intelligence Layer.

    Paramètres :
        coding_skills   : skills déclarés coding par le RH
        platform_skills : skills déclarés platform par le RH
        mixed_skills    : skills déclarés mixed par le RH
        use_llm         : True (défaut) → valider via LLM
                          False → utiliser uniquement le fallback dict

    Retourne :
        {
            "skills_final": [
                {"name": "python",   "type": "coding"},
                {"name": "power bi", "type": "platform"},
                {"name": "docker",   "type": "mixed"},   ← TOUJOURS mixed
            ],
            "corrections_applied": [
                {"name": "docker", "given": "coding", "corrected_to": "mixed", ...}
            ],
            "total": 3,
            "coding_count":   1,
            "platform_count": 1,
            "mixed_count":    1,
            "error": None,
        }
    """
    # ── 1. Construire la liste unifiée avec type déclaré ──────────
    all_skills: list[dict] = []

    for s in coding_skills:
        if s is None:
            continue
        s = str(s).strip()
        if s:
            all_skills.append({"name": s.lower(), "given_type": "coding"})

    for s in platform_skills:
        if s is None:
            continue
        s = str(s).strip()
        if s:
            all_skills.append({"name": s.lower(), "given_type": "platform"})

    for s in mixed_skills:
        if s is None:
            continue
        s = str(s).strip()
        if s:
            all_skills.append({"name": s.lower(), "given_type": "mixed"})

    # ── Fusionner les skills composites connus ────────────────────
    # Si "azure" et "devops" sont déclarés séparément → "azure devops"
    COMPOSITE_SKILLS = {
        ("azure", "devops"): "azure devops",
    }
    names_in_order = [sk["name"] for sk in all_skills]
    for (a, b), merged in COMPOSITE_SKILLS.items():
        if a in names_in_order and b in names_in_order:
            for sk in all_skills:
                if sk["name"] == a:
                    sk["name"] = merged
                    break
            all_skills = [sk for sk in all_skills if sk["name"] != b]
            logger.info(
                f"[classifier] Skills composites fusionnés : '{a}' + '{b}' → '{merged}'"
            )

    # Dédupliquer (garder le premier)
    seen = set()
    unique_skills = []
    for sk in all_skills:
        if sk["name"] not in seen:
            seen.add(sk["name"])
            unique_skills.append(sk)

    # NOTE v4.0 : MAX_SKILLS supprimé — le total est fixé à 10 questions
    # dans compute_test_strategy() selon la structure tech/platform/mixed

    if not unique_skills:
        logger.warning("[classifier] Aucun skill fourni")
        return {
            "skills_final"       : [],
            "corrections_applied": [],
            "total"              : 0,
            "coding_count"       : 0,
            "platform_count"     : 0,
            "mixed_count"        : 0,
            "error"              : "Aucun skill fourni",
        }

    logger.info(
        f"[classifier] Classification de {len(unique_skills)} skills : "
        f"{[s['name'] for s in unique_skills]}"
    )

    # ── 2. Validation via LLM ─────────────────────────────────────
    skills_final       : list[dict] = []
    corrections_applied: list[dict] = []
    llm_error          : Optional[str] = None

    if use_llm:
        skills_to_check = [
            {"name": s["name"], "given_type": s["given_type"]}
            for s in unique_skills
        ]
        prompt = _build_classification_prompt(skills_to_check)

        for attempt in range(1, MAX_RETRY_CLASSIFY + 2):
            try:
                logger.info(f"  [classifier] Tentative LLM {attempt}")
                raw     = _call_llm_classify(prompt)
                results = _extract_json_array(raw)

                # Vérifier qu'on a bien tous les skills
                result_names = {r.get("name", "").strip().lower() for r in results}
                input_names  = {s["name"] for s in unique_skills}
                missing      = input_names - result_names

                if missing:
                    raise ValueError(f"Skills manquants dans la réponse LLM : {missing}")

                # Appliquer les corrections
                result_map = {r["name"].strip().lower(): r for r in results}

                for sk in unique_skills:
                    name             = sk["name"]
                    given_type_rh    = sk["given_type"]  # type déclaré par le RH

                    if name in result_map:
                        item = result_map[name]
                        # Injecter le given_type RH si absent de la réponse LLM
                        if "given" not in item:
                            item["given"] = given_type_rh
                        # CORRECTION v1.1 : passer given_type_original séparément
                        decision = _apply_correction(item, given_type_original=given_type_rh)
                    else:
                        # Skill absent de la réponse LLM → appliquer garde-fou quand même
                        decision = _apply_correction(
                            {"name": name, "given": given_type_rh, "corrected": given_type_rh,
                             "confidence": 0.0, "reason": "absent de la réponse LLM"},
                            given_type_original=given_type_rh,
                        )

                    # FIX : utiliser sk["name"] (nom RH original) et non decision["name"]
                    # (le LLM peut retourner "bash" au lieu de "bash scripting")
                    skills_final.append({
                        "name": sk["name"],
                        "type": decision["type"],
                    })

                    if decision["corrected"]:
                        corrections_applied.append({
                            "name"        : name,
                            "given"       : given_type_rh,
                            "corrected_to": decision["type"],
                            "confidence"  : decision["confidence"],
                            "reason"      : decision["reason"],
                        })

                logger.info(
                    f"[classifier] Classification OK — "
                    f"{len(corrections_applied)} correction(s) appliquée(s)"
                )
                break  # succès

            except Exception as e:
                llm_error = str(e)
                logger.warning(f"  [classifier] Tentative {attempt} échouée : {e}")
                if attempt <= MAX_RETRY_CLASSIFY:
                    continue
                # Tous les retries épuisés → fallback
                logger.warning(
                    f"[classifier] LLM indisponible après {MAX_RETRY_CLASSIFY + 1} "
                    f"tentatives — fallback dictionnaire activé"
                )
                skills_final = []
                for sk in unique_skills:
                    final_type = _fallback_classify(sk["name"], sk["given_type"])
                    skills_final.append({"name": sk["name"], "type": final_type})
                corrections_applied = []
    else:
        # Mode sans LLM — fallback direct (avec garde-fous P0)
        logger.info("[classifier] Mode sans LLM — fallback dictionnaire")
        for sk in unique_skills:
            final_type = _fallback_classify(sk["name"], sk["given_type"])
            skills_final.append({"name": sk["name"], "type": final_type})

    # ── 3. Comptage final ─────────────────────────────────────────
    coding_count   = sum(1 for s in skills_final if s["type"] == "coding")
    platform_count = sum(1 for s in skills_final if s["type"] == "platform")
    mixed_count    = sum(1 for s in skills_final if s["type"] == "mixed")

    logger.info(
        f"[classifier] Résultat final : "
        f"coding={coding_count} platform={platform_count} mixed={mixed_count} "
        f"| skills={[s['name'] for s in skills_final]}"
    )

    return {
        "skills_final"       : skills_final,
        "corrections_applied": corrections_applied,
        "total"              : len(skills_final),
        "coding_count"       : coding_count,
        "platform_count"     : platform_count,
        "mixed_count"        : mixed_count,
        "error"              : llm_error if not skills_final else None,
    }


# ─────────────────────────────────────────────────────────────────
# TEST STRATEGY ENGINE
# ─────────────────────────────────────────────────────────────────

def compute_test_strategy(classification_result: dict) -> dict:
    """
    Détermine le type de test et la structure des questions
    à partir du résultat de classify_and_validate_skills().

    Retourne :
        {
            "test_type"             : "tech" | "platform" | "mixed",
            "n_questions"           : int,
            "tech_weight"           : float,
            "platform_weight"       : float,
            "question_structure"    : {"mcq": int, "open": int},
            "total_duration_minutes": int,
            "skills_coding"         : list[str],
            "skills_platform"       : list[str],
            "skills_mixed"          : list[str],
            "all_skills"            : list[str],
        }
    """
    coding_count   = classification_result.get("coding_count",   0)
    platform_count = classification_result.get("platform_count", 0)
    mixed_count    = classification_result.get("mixed_count",    0)
    skills_final   = classification_result.get("skills_final",   [])

    total = coding_count + platform_count + mixed_count
    if total == 0:
        total = 1  # éviter division par zéro

    # ── Décision du type de test ──────────────────────────────────
    #
    # Règles par priorité :
    # R1 — Majorité coding (>= 3) → TECH
    # R2 — Majorité platform (>= 3) → PLATFORM
    # R3 — Que des skills coding (0 platform, 0 mixed) → TECH
    # R4 — Que des skills platform (0 coding, 0 mixed) → PLATFORM
    # R5 — Tous les autres cas (mixed présents, ou combinaison) → MIXED
    #
    # NOTE : mixed skills = coding + infra → contribuent au test MIXED
    #        et génèrent des PROBLEM (pas des SCENARIO)

    if coding_count >= 3:
        test_type = "tech"
    elif platform_count >= 3:
        test_type = "platform"
    elif coding_count > 0 and platform_count == 0 and mixed_count == 0:
        test_type = "tech"
    elif platform_count > 0 and coding_count == 0 and mixed_count == 0:
        test_type = "platform"
    else:
        # R5 : mix de catégories (ou que du mixed) → MIXED
        test_type = "mixed"

    # ── Pondération dynamique ─────────────────────────────────────
    tech_weight     = round((coding_count + 0.5 * mixed_count) / total, 2)
    platform_weight = round((platform_count + 0.5 * mixed_count) / total, 2)

    # ── Nombre de questions : toujours 10 (v4.0) ─────────────────
    all_skill_names = [s["name"] for s in skills_final]
    n_questions = 10

    # ── Structure des questions (v6.0) ──────────────────────────────────
    # tech     → 7 MCQ + 3 OPEN
    # platform → 5 MCQ + 5 OPEN
    # mixed    → 5 MCQ + 5 OPEN
    if test_type == "tech":
        question_structure = {"mcq": 7, "open": 3}
        duration = 7 * 3 + 3 * 8   # 21 + 24 = 45 min
    elif test_type == "platform":
        question_structure = {"mcq": 5, "open": 5}
        duration = 5 * 3 + 5 * 8   # 15 + 40 = 55 min
    else:  # mixed
        question_structure = {"mcq": 5, "open": 5}
        duration = 5 * 3 + 5 * 8   # 15 + 40 = 55 min

    # ── Séparer les skills par catégorie ─────────────────────────
    skills_coding   = [s["name"] for s in skills_final if s["type"] == "coding"]
    skills_platform = [s["name"] for s in skills_final if s["type"] == "platform"]
    skills_mixed    = [s["name"] for s in skills_final if s["type"] == "mixed"]

    logger.info(
        f"[classifier] Stratégie : test_type={test_type} "
        f"n_questions={n_questions} structure={question_structure} duration={duration}min "
        f"weights=tech:{tech_weight}/platform:{platform_weight}"
    )

    return {
        "test_type"             : test_type,
        "n_questions"           : n_questions,
        "tech_weight"           : tech_weight,
        "platform_weight"       : platform_weight,
        "question_structure"    : question_structure,
        "total_duration_minutes": duration,
        "skills_coding"         : skills_coding,
        "skills_platform"       : skills_platform,
        "skills_mixed"          : skills_mixed,
        "all_skills"            : all_skill_names,
    }


# ─────────────────────────────────────────────────────────────────
# MODE STANDALONE — test rapide
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    print("=" * 60)
    print("skill_classifier.py — Mode standalone v1.1")
    print("=" * 60)

    # Cas de test : docker déclaré en mixed (correct), doit rester mixed
    result = classify_and_validate_skills(
        coding_skills   = ["python", "java", "go"],
        platform_skills = ["jira", "confluence"],
        mixed_skills    = ["docker"],
        use_llm         = True,
    )

    print("\n📊 Résultat classification :")
    for s in result["skills_final"]:
        marker = "✅" if s["type"] == _FALLBACK_TYPES.get(s["name"], s["type"]) else "⚠️"
        print(f"  {marker} {s['name']:<20} → {s['type']}")

    if result["corrections_applied"]:
        print("\n⚠️  Corrections appliquées :")
        for c in result["corrections_applied"]:
            print(
                f"  {c['name']}: {c['given']} → {c['corrected_to']} "
                f"(confidence={c['confidence']:.2f})"
            )
            print(f"  Raison : {c['reason']}")

    strategy = compute_test_strategy(result)
    print(f"\n🎯 Type de test   : {strategy['test_type'].upper()}")
    print(f"   Nb questions   : {strategy['n_questions']}")
    print(f"   Structure      : {strategy['question_structure']}")
    print(f"   Durée          : {strategy['total_duration_minutes']} min")
    print(f"   Skills coding  : {strategy['skills_coding']}")
    print(f"   Skills platform: {strategy['skills_platform']}")
    print(f"   Skills mixed   : {strategy['skills_mixed']}")