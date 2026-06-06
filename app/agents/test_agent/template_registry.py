"""
template_registry.py — Template Registry pour la génération de tests (v1.0)

Rôle :
    Fournir des PATTERNS de questions (pas des questions complètes) selon
    le profil technique du candidat (domaine + séniorité).

    ❌ Pas de questions hardcodées
    ✅ Uniquement des patterns qui guident le LLM pour générer des questions NOUVELLES

Pipeline :
    skills + seniority
        ↓
    select_template()       ← choisit le template selon les skills
        ↓
    build_prompt(template)  ← injecte les patterns dans le prompt LLM
        ↓
    LLM génère les questions à partir des patterns
        ↓
    validate_test_integrity() ← filtre les tests de mauvaise qualité

Utilisé par :
    test_agent.py → _build_generation_prompt() → inject_template_patterns()
"""

# ─────────────────────────────────────────────────────────────────
# TEMPLATES PAR DOMAINE
# ─────────────────────────────────────────────────────────────────
#
# Structure de chaque template :
#   mcq_patterns   → types de MCQ attendus (thèmes, pas de texte de questions)
#   open_patterns  → types de OPEN attendus (situations, pas de texte de questions)
#   focus_areas    → points d'attention pour ce domaine
#   constraints    → contraintes réalistes à injecter dans les questions
#
# ⚠️  RÈGLE CRITIQUE :
#   Les patterns sont des GUIDES pour le LLM, pas des questions.
#   Le LLM DOIT générer des questions originales à partir de ces patterns.
#   Chaque génération doit produire des questions DIFFÉRENTES.

TEMPLATES: dict[str, dict] = {

    # ─────────────────────────────────────────────────────────────
    # FRONTEND (React, Vue, Angular, TypeScript, CSS)
    # ─────────────────────────────────────────────────────────────
    "frontend": {
        "mcq_patterns": [
            "React hooks behavior in edge case (stale closure, dependency array mistake)",
            "TypeScript typing error or strict mode behavior",
            "Component re-render cause and prevention strategy",
            "State management decision (local state vs context vs external store)",
            "Performance optimization pattern (memo, lazy, suspense, virtualization)",
            "Event handling or async state update bug",
            "CSS layout or specificity conflict in real scenario",
        ],
        "open_patterns": [
            "Diagnose performance issue in a slow React component with real metrics constraint",
            "Choose between two state management approaches with team size and scale constraint",
            "Design frontend architecture for a feature with accessibility and performance constraint",
            "Debug a rendering or hydration issue in a production app",
        ],
        "focus_areas": [
            "hooks correctness", "rendering optimization", "TypeScript strict typing",
            "component composition", "async state management",
        ],
        "constraints": [
            "the page must load under 2 seconds on 3G",
            "the team has no backend access",
            "bundle size must stay under 200KB",
            "the component is shared across 5 different apps",
            "no additional libraries allowed",
        ],
    },

    # ─────────────────────────────────────────────────────────────
    # BACKEND (Node.js, Python, FastAPI, Django, Java, Go)
    # ─────────────────────────────────────────────────────────────
    "backend": {
        "mcq_patterns": [
            "API design decision (REST vs RPC, versioning, status codes)",
            "Async behavior or event loop misconception",
            "Authentication or authorization edge case (JWT expiry, RBAC)",
            "Error handling strategy in production code",
            "Database connection pooling or transaction isolation issue",
            "Caching strategy decision with TTL or invalidation constraint",
            "Rate limiting or concurrency bug in a real scenario",
        ],
        "open_patterns": [
            "Design a scalable API endpoint with latency and concurrency constraint",
            "Diagnose a backend performance degradation with real metrics",
            "Handle a race condition or data consistency problem in production",
            "Choose between two architectural patterns for a service with cost constraint",
        ],
        "focus_areas": [
            "API design quality", "async correctness", "error handling",
            "authentication security", "database interaction patterns",
        ],
        "constraints": [
            "the API must handle 10,000 requests per second",
            "no downtime during migration",
            "response time must stay under 100ms at p99",
            "the service is called by 3 external partners",
            "no breaking changes to existing clients",
        ],
    },

    # ─────────────────────────────────────────────────────────────
    # DATA / ANALYTICS (Python, SQL, Power BI, Tableau, dbt)
    # ─────────────────────────────────────────────────────────────
    "data": {
        "mcq_patterns": [
            "SQL aggregation or window function behavior in edge case",
            "Python pandas performance issue with large DataFrame",
            "Power BI DAX measure calculation error or ambiguity",
            "Data model design decision (star vs snowflake schema)",
            "ETL pipeline failure cause and recovery strategy",
            "Query optimization for slow analytical query",
            "Data type or encoding issue causing silent data corruption",
        ],
        "open_patterns": [
            "Diagnose a slow Power BI report with no direct DB access constraint",
            "Design a data pipeline for 5 heterogeneous sources with freshness constraint",
            "Choose between two data modeling approaches with storage and query speed constraint",
            "Handle a data quality issue discovered in production with SLA constraint",
        ],
        "focus_areas": [
            "SQL correctness", "DAX/MDX formulas", "pipeline reliability",
            "data model quality", "query performance optimization",
        ],
        "constraints": [
            "no direct database access",
            "data must refresh every 15 minutes",
            "the pipeline processes 50GB per day",
            "used by non-technical business stakeholders",
            "no additional infrastructure budget",
        ],
    },

    # ─────────────────────────────────────────────────────────────
    # DEVOPS / INFRASTRUCTURE (Docker, Kubernetes, Terraform, CI/CD)
    # ─────────────────────────────────────────────────────────────
    "devops": {
        "mcq_patterns": [
            "Docker layer caching behavior or image size issue",
            "Kubernetes pod failure cause (OOMKilled, CrashLoopBackOff, Pending)",
            "CI/CD pipeline design decision with security constraint",
            "Terraform state management problem or conflict",
            "Container networking or service discovery issue",
            "Secret management decision in a cloud-native context",
            "Rolling vs blue-green vs canary deployment trade-off",
        ],
        "open_patterns": [
            "Design a zero-downtime deployment strategy with infrastructure cost constraint",
            "Diagnose a Kubernetes pod that keeps restarting with no budget for new nodes",
            "Choose between two CI/CD tools for an Azure-hosted project with team size constraint",
            "Handle a production incident caused by a bad deployment with rollback constraint",
        ],
        "focus_areas": [
            "container orchestration", "CI/CD pipeline design", "infrastructure as code",
            "security hardening", "incident response and rollback",
        ],
        "constraints": [
            "zero downtime required",
            "no additional cloud budget",
            "the team has 2 junior DevOps engineers",
            "deployment must complete in under 5 minutes",
            "the system runs 24/7 for a financial client",
        ],
    },

    # ─────────────────────────────────────────────────────────────
    # PLATFORM / MICROSOFT 365 (Power BI, Power Automate, SharePoint, Dynamics)
    # ─────────────────────────────────────────────────────────────
    "platform": {
        "mcq_patterns": [
            "Power Automate flow failure or trigger misconfiguration",
            "SharePoint permission inheritance or content type issue",
            "Dynamics 365 entity relationship or workflow configuration error",
            "Power BI report sharing and row-level security decision",
            "Power Apps formula or delegation issue with large dataset",
            "Microsoft 365 license or feature availability constraint",
            "Azure AD conditional access or SSO misconfiguration",
        ],
        "open_patterns": [
            "Design a Power Automate approval workflow for 5 departments with exception handling",
            "Diagnose a Power BI report that returns wrong numbers for one department",
            "Choose between Power Apps and a custom solution with license cost constraint",
            "Handle a SharePoint migration with zero-downtime and data integrity constraint",
        ],
        "focus_areas": [
            "platform configuration accuracy", "license and governance constraints",
            "no-code/low-code tool selection", "data governance", "user adoption",
        ],
        "constraints": [
            "no developer resources available",
            "Microsoft 365 E3 license only",
            "500 concurrent users",
            "must comply with GDPR data residency",
            "go-live in 3 weeks",
        ],
    },

    # ─────────────────────────────────────────────────────────────
    # FULLSTACK (React + Node / Django / FastAPI + SQL)
    # ─────────────────────────────────────────────────────────────
    "fullstack": {
        "mcq_patterns": [
            "Frontend-backend contract issue (CORS, auth header, payload mismatch)",
            "API response design decision affecting frontend state management",
            "Database query performance issue triggered by frontend user action",
            "Session or token management bug crossing frontend and backend",
            "Monorepo vs multi-repo trade-off for a growing fullstack team",
            "Caching strategy decision (client vs server vs CDN) with real constraint",
            "Error propagation from backend to frontend UX",
        ],
        "open_patterns": [
            "Diagnose a full-stack feature that is slow end-to-end with profiling constraint",
            "Design an authentication flow across frontend and backend with security constraint",
            "Choose between SSR, CSR, and SSG for a new feature with SEO and performance constraint",
            "Handle a data synchronization problem between frontend optimistic update and backend truth",
        ],
        "focus_areas": [
            "frontend-backend integration", "end-to-end data flow",
            "authentication across layers", "performance at both layers",
            "API contract design",
        ],
        "constraints": [
            "the mobile app and web app share the same API",
            "SEO is critical for the marketing team",
            "authentication must work offline",
            "the backend team and frontend team are different squads",
            "response time must be under 500ms including DB query",
        ],
    },

    # ─────────────────────────────────────────────────────────────
    # DEFAULT — fallback générique si aucun domaine détecté
    # ─────────────────────────────────────────────────────────────
    "default": {
        "mcq_patterns": [
            "Technical decision with a specific constraint that makes one answer clearly correct",
            "Real-world bug or error that a developer would encounter",
            "Performance or security trade-off in a production scenario",
            "Tool or approach selection with cost, scale, or team size constraint",
            "Edge case behavior of a common technology pattern",
        ],
        "open_patterns": [
            "Diagnose a production issue with real metrics and access constraints",
            "Choose between two technical approaches with concrete constraints",
            "Design a solution for a real business problem with technical and organizational constraints",
        ],
        "focus_areas": [
            "practical problem solving", "constraint awareness",
            "trade-off reasoning", "production-readiness",
        ],
        "constraints": [
            "limited time and budget",
            "must be maintainable by a junior developer",
            "no additional infrastructure",
            "3-week deadline",
            "must not break existing functionality",
        ],
    },
}


# ─────────────────────────────────────────────────────────────────
# SÉLECTION DE TEMPLATE
# ─────────────────────────────────────────────────────────────────

def select_template(skills: list[str], seniority: str = "mid") -> tuple[str, dict]:
    """
    Sélectionne le template approprié en fonction des skills du candidat.

    Retourne :
        (template_name, template_dict)

    Logique de sélection (par priorité) :
        1. Fullstack si skills frontend ET backend présents
        2. Frontend si React/Vue/Angular/TypeScript présents
        3. Backend si Node/Python/Java/Go + API présents
        4. Data si SQL/Power BI/Python data présents
        5. DevOps si Docker/Kubernetes/Terraform présents
        6. Platform si Power Automate/SharePoint/Dynamics présents
        7. Default si aucun match
    """
    skills_lower = {s.lower().strip() for s in skills}

    # ── Détection par groupe de skills ───────────────────────────
    _FRONTEND_SKILLS = {
        "react", "vue", "angular", "typescript", "javascript",
        "html", "css", "next.js", "nextjs", "svelte", "nuxt",
    }
    _BACKEND_SKILLS = {
        "node", "node.js", "nodejs", "python", "fastapi", "django",
        "flask", "java", "spring", "go", "golang", "c#", "asp.net",
        ".net", "ruby", "rails", "express", "nestjs",
    }
    _DATA_SKILLS = {
        "sql", "postgresql", "mysql", "t-sql", "tsql", "power bi",
        "tableau", "dbt", "airflow", "spark", "databricks", "snowflake",
        "pandas", "numpy", "data", "analytics", "bi",
    }
    _DEVOPS_SKILLS = {
        "docker", "kubernetes", "k8s", "terraform", "ansible",
        "jenkins", "github actions", "gitlab ci", "helm", "linux",
        "bash", "ci/cd", "devops", "aws", "gcp", "azure devops",
    }
    _PLATFORM_SKILLS = {
        "power automate", "power apps", "sharepoint", "dynamics 365",
        "dynamics", "microsoft 365", "office 365", "teams", "ssis",
        "azure data factory", "power platform", "servicenow",
    }
    _API_SIGNALS = {"api", "rest", "graphql", "grpc", "microservices", "backend"}

    has_frontend = bool(skills_lower & _FRONTEND_SKILLS)
    has_backend  = bool(skills_lower & _BACKEND_SKILLS) or bool(skills_lower & _API_SIGNALS)
    has_data     = bool(skills_lower & _DATA_SKILLS)
    has_devops   = bool(skills_lower & _DEVOPS_SKILLS)
    has_platform = bool(skills_lower & _PLATFORM_SKILLS)

    # ── Priorité 1 : Fullstack (frontend + backend) ───────────────
    if has_frontend and has_backend:
        return "fullstack", TEMPLATES["fullstack"]

    # ── Priorité 2 : Frontend pur ─────────────────────────────────
    if has_frontend:
        return "frontend", TEMPLATES["frontend"]

    # ── Priorité 3 : Backend pur ──────────────────────────────────
    if has_backend:
        return "backend", TEMPLATES["backend"]

    # ── Priorité 4 : Data / Analytics ────────────────────────────
    if has_data:
        return "data", TEMPLATES["data"]

    # ── Priorité 5 : DevOps / Infrastructure ─────────────────────
    if has_devops:
        return "devops", TEMPLATES["devops"]

    # ── Priorité 6 : Platform / Microsoft 365 ────────────────────
    if has_platform:
        return "platform", TEMPLATES["platform"]

    # ── Fallback ──────────────────────────────────────────────────
    return "default", TEMPLATES["default"]


def build_template_guidance(
    template_name: str,
    template     : dict,
    seniority    : str,
    n_mcq        : int,
    n_open       : int,
) -> str:
    """
    Construit le bloc de guidance à injecter dans le prompt de génération.

    Ce bloc guide le LLM sur :
        - Les types de MCQ attendus (patterns, pas de texte)
        - Les types de OPEN attendus (situations, pas de texte)
        - Les contraintes réalistes à utiliser
        - Les focus areas du domaine

    ⚠️  Le LLM DOIT générer des questions ORIGINALES.
        Il ne doit pas copier les patterns — ce sont des THÈMES, pas des questions.
    """
    mcq_patterns  = template.get("mcq_patterns", [])
    open_patterns = template.get("open_patterns", [])
    constraints   = template.get("constraints", [])
    focus_areas   = template.get("focus_areas", [])

    # Sélectionner les patterns pertinents selon le nombre de questions
    selected_mcq_patterns  = mcq_patterns[:min(n_mcq + 2, len(mcq_patterns))]
    selected_open_patterns = open_patterns[:min(n_open + 2, len(open_patterns))]

    # Ajuster la profondeur selon la séniorité
    seniority_guidance = {
        "junior": (
            "MCQ must test COMMON MISTAKES and BASIC USAGE patterns. "
            "OPEN must present a single well-defined problem with a clear correct approach."
        ),
        "mid": (
            "MCQ must test REAL-WORLD DECISIONS under constraints. "
            "OPEN must require structured reasoning and tool/approach justification."
        ),
        "senior": (
            "MCQ must test SUBTLE BUGS, EDGE CASES, and SCALE issues that seniors catch immediately. "
            "OPEN MUST present 2-3 NAMED competing approaches — candidate must choose and justify."
        ),
    }.get(seniority, "")

    lines = [
        f"",
        f"════════════════════════════════════════════════════",
        f"DOMAIN TEMPLATE GUIDANCE — {template_name.upper()}",
        f"════════════════════════════════════════════════════",
        f"",
        f"⚠️  CRITICAL: These are QUESTION TYPES (patterns), NOT actual questions.",
        f"    Generate ORIGINAL questions INSPIRED by these patterns.",
        f"    NEVER copy a pattern as a question. Each question must be unique.",
        f"",
        f"MCQ QUESTION TYPES to cover ({n_mcq} MCQ total):",
    ]
    for i, p in enumerate(selected_mcq_patterns[:n_mcq + 2], 1):
        lines.append(f"  MCQ-{i}: {p}")

    lines += [
        f"",
        f"OPEN QUESTION TYPES to cover ({n_open} OPEN total):",
    ]
    for i, p in enumerate(selected_open_patterns[:n_open + 1], 1):
        lines.append(f"  OPEN-{i}: {p}")

    lines += [
        f"",
        f"REALISTIC CONSTRAINTS to use in questions (pick the most fitting):",
    ]
    for c in constraints[:4]:
        lines.append(f"  • {c}")

    lines += [
        f"",
        f"DOMAIN FOCUS AREAS (what the evaluator will check):",
        f"  {', '.join(focus_areas)}",
        f"",
        f"SENIORITY CALIBRATION ({seniority.upper()}):",
        f"  {seniority_guidance}",
        f"",
        f"════════════════════════════════════════════════════",
    ]

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────
# MODE STANDALONE — test rapide
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json

    print("=" * 60)
    print("template_registry.py — Mode standalone v1.0")
    print("=" * 60)

    test_cases = [
        (["React", "TypeScript", "Node.js"], "mid"),
        (["Python", "SQL", "Power BI"], "senior"),
        (["Docker", "Kubernetes", "Terraform"], "mid"),
        (["Power Automate", "SharePoint", "Dynamics 365"], "junior"),
        (["React", "CSS"], "junior"),
        (["Java", "Spring", "PostgreSQL"], "senior"),
    ]

    for skills, seniority in test_cases:
        name, template = select_template(skills, seniority)
        guidance = build_template_guidance(name, template, seniority, n_mcq=6, n_open=4)
        print(f"\n▶  Skills: {skills} | Seniority: {seniority}")
        print(f"   → Template sélectionné : {name.upper()}")
        print(f"   → MCQ patterns disponibles : {len(template['mcq_patterns'])}")
        print(f"   → OPEN patterns disponibles : {len(template['open_patterns'])}")
        print(guidance[:300] + "...")