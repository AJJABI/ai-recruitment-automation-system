"""
cv_validator.py  v3
====================
Le validator est un contrôleur qualité, pas un nettoyeur.

Il reçoit :
  - Le JSON retourné par le parser
  - Le texte brut du PDF (source de vérité)

Il fait une seule chose : vérifier que le JSON est fidèle au PDF.

Ce qu'il vérifie :
  1. Durées       — recalcule depuis les dates brutes du PDF, corrige si écart
  2. Classification — cherche stage/alternance/CDI autour de chaque exp, corrige si besoin
  3. Skills manquants — scanne section COMPÉTENCES du PDF, ajoute ce qui manque
  4. Catégorie skills — vérifie Technical / Tools / Soft, corrige si mauvaise catégorie
  5. Expériences manquantes — compte blocs exp PDF vs JSON, signale si écart
  6. Formations manquantes  — même logique section FORMATION
  7. Certifications manquantes — même logique section CERTIFICATIONS

Ce qu'il NE fait PAS :
  ❌ Pas de nettoyage de doublons
  ❌ Pas de suppression de N/A
  ❌ Pas de normalisation de noms
  ❌ Pas de re-parsing LLM

Schéma :
  cv_parser.py    → PDF → LLM → "j'extrais ce que je vois"
  cv_validator.py → PDF + JSON → "je vérifie que ce qui est extrait est juste"

Utilisation :
  from app.agents.cv_validator import validate_and_fix
  data, report = validate_and_fix(data, pdf_path="cv.pdf")
"""

import re
import copy
import pdfplumber
from datetime import datetime
from typing import Optional, Tuple, List, Dict

CURRENT_YEAR  = datetime.now().year
CURRENT_MONTH = datetime.now().month

# ─────────────────────────────────────────────────────────────────────────────
# MAPS & CONSTANTES
# ─────────────────────────────────────────────────────────────────────────────

MONTHS_MAP: Dict[str, int] = {
    # Français complet
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4,
    "mai": 5, "juin": 6, "juillet": 7, "août": 8, "aout": 8,
    "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12,
    # Français abrégé (avec et sans point — le point est supprimé en amont)
    "jan": 1, "janv": 1,
    "fév": 2, "fev": 2, "févr": 2, "fevr": 2,
    "avr": 4,
    "juil": 7, "juill": 7,
    "aoû": 8, "aou": 8,
    "sep": 9, "sept": 9,
    "oct": 10, "nov": 11,
    "déc": 12, "dec": 12,
    # Anglais complet
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    # Anglais abrégé
    "feb": 2, "mar": 3, "apr": 4, "jun": 6,
    "jul": 7, "aug": 8,
}

# Mots-clés pour détecter la classification autour d'une expérience
STAGE_KEYWORDS    = {"stage", "stagiaire", "intern", "internship", "pfe", "pfa",
                     "trainee", "student", "étudiant"}
ALT_KEYWORDS      = {"alternance", "apprentissage", "work-study", "contrat d'alternance",
                     "alternant", "apprenti"}
PRO_KEYWORDS      = {"cdi", "cdd", "emploi", "poste", "salarié", "employé",
                     "full-time", "full time", "permanent"}

# Classification des skills — référentiel
TOOLS_SET = {
    "docker", "kubernetes", "git", "github", "gitlab", "jenkins", "jira",
    "confluence", "notion", "figma", "vscode", "vs code", "pycharm",
    "intellij", "jupyter", "power bi", "tableau", "excel", "postman",
    "insomnia", "datadog", "grafana", "prometheus", "kibana", "splunk",
    "talend", "informatica", "dbeaver", "pgadmin", "mongodb compass",
    "azure devops", "trello", "miro", "google analytics", "looker studio",
    "metabase", "qlik", "ssrs", "ssis", "ssas", "power automate",
    "power apps", "power pages", "dataverse", "al extension pack",
    "visual studio code", "argocd", "helm", "ansible", "terraform",
    "github actions", "gitlab ci", "ssms", "sql server management studio",
    "pycharm", "eclipse", "rstudio", "spyder",
    # Cloud platforms
    "aws", "gcp", "azure", "lambda", "ec2", "s3", "rds",
    "cloudfront", "ecs", "eks", "azure app service", "azure functions",
    # CSS frameworks
    "tailwind", "bootstrap", "tailwind css",
    # Mobile
    "firebase", "firebase cloud messaging", "fcm",
    "android studio", "xcode", "google play console", "app store connect",
}

TECHNICAL_SET = {
    # Langages
    "python", "java", "javascript", "typescript", "c", "c++", "c#",
    "php", "ruby", "go", "rust", "kotlin", "swift", "scala", "r",
    "html", "html5", "css", "css3", "sass", "sql", "bash", "shell",
    "dart", "powershell", "matlab",
    # Frameworks
    "django", "flask", "fastapi", "spring", "laravel", "symfony",
    "express", "rails", "asp.net", "dotnet", ".net",
    "react", "react.js", "vue", "vue.js", "angular", "svelte",
    "next.js", "nuxt.js",
    # Bases de données
    "mysql", "postgresql", "sqlite", "oracle", "sql server",
    "mongodb", "redis", "cassandra", "elasticsearch", "mariadb",
    "firebase", "dynamodb", "neo4j",
    # ML / Data
    "tensorflow", "pytorch", "scikit-learn", "keras", "xgboost",
    "pandas", "numpy", "spark", "kafka", "airflow", "dbt",
    # Cloud
    "aws", "gcp", "azure", "ec2", "s3", "lambda",
    # Microsoft / Dynamics
    "business central", "dynamics 365", "dynamics 365 bc", "d365",
    "al language", "c/al", "nav", "navision", "dynamics nav",
    "dynamics crm", "erp", "crm", "job queue",
    "api rest business central", "odata", "web services",
    "azure functions", "asp.net core", "blazor",
    # DevOps pratiques
    "ci/cd", "devops", "iac", "microservices", "rest api", "graphql",
    "oauth2", "jwt",
}

SOFT_SET = {
    "agile", "scrum", "kanban", "lean", "safe",
    "design thinking", "product management", "gestion de projet",
    "project management", "sure step", "moa", "amoa",
    "conduite du changement", "change management",
    "agile scrum",
}

# Sections PDF
SKILL_SECTION_HEADERS = {
    "compétences", "competences", "skills", "technical skills",
    "technologies", "stack", "outils", "tools", "expertise",
    "core competencies", "savoir-faire",
}
EXP_SECTION_HEADERS = {
    "expériences professionnelles", "expérience", "expériences",
    "parcours professionnel", "emplois", "postes",
    "work experience", "professional experience", "employment history",
}
EDU_SECTION_HEADERS = {
    "formation", "formations", "éducation", "education",
    "diplômes", "études", "parcours académique",
    "academic background", "qualifications",
}
CERT_SECTION_HEADERS = {
    "certifications", "certification", "certificates",
    "licences", "licenses", "credentials",
}

DIPLOMA_KEYWORDS = {
    "master", "licence", "bachelor", "ingénieur", "ingenieur",
    "bts", "dut", "doctorat", "phd", "baccalauréat", "baccalaureat",
    "bac", "mba", "diplôme", "diplome",
}


# ─────────────────────────────────────────────────────────────────────────────
# EXTRACTION TEXTE BRUT
# ─────────────────────────────────────────────────────────────────────────────

def _extract_raw_text(pdf_path: str) -> str:
    """Extrait le texte brut de toutes les pages du PDF."""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            pages = []
            for page in pdf.pages:
                text = page.extract_text() or ""
                text = re.sub(r'\(cid:\d+\)', '', text)
                pages.append(text)
            return "\n".join(pages)
    except Exception:
        return ""


def _get_section(raw: str, headers: set) -> str:
    """
    Extrait le contenu d'une section PDF identifiée par ses headers.
    Retourne le texte de la section jusqu'à la prochaine section majeure.
    """
    lines = raw.splitlines()
    in_section = False
    result = []

    for line in lines:
        ll = line.lower().strip()
        # Détecter l'en-tête de section
        if any(ll == h or ll.startswith(h) for h in headers) and len(ll) < 50:
            in_section = True
            continue
        # Fin de section : ligne courte, tout en majuscule = nouvel en-tête
        if in_section and ll and len(ll) < 50 and (line.strip().isupper() or
           any(ll == h or ll.startswith(h)
               for h in SKILL_SECTION_HEADERS | EXP_SECTION_HEADERS |
                        EDU_SECTION_HEADERS | CERT_SECTION_HEADERS)):
            in_section = False
        if in_section and line.strip():
            result.append(line.strip())

    return "\n".join(result)


# ─────────────────────────────────────────────────────────────────────────────
# CALCUL DE DURÉE DEPUIS DATES BRUTES
# ─────────────────────────────────────────────────────────────────────────────

def _parse_date_pairs(text: str) -> List[Tuple[int, int]]:
    """
    Extrait toutes les paires (mois, année) trouvées dans un texte.
    Retourne une liste triée par position d'apparition.
    """
    norm = text.lower()
    norm = norm.replace("–", " - ").replace("—", " - ").replace(".", " ")
    norm = re.sub(r'\s+', ' ', norm).strip()

    pairs = []  # (position, mois, année)
    for month_name, month_num in sorted(MONTHS_MAP.items(), key=lambda x: -len(x[0])):
        pattern = rf"\b{re.escape(month_name)}\b\s*(20\d{{2}}|19\d{{2}})"
        for m in re.finditer(pattern, norm):
            pairs.append((m.start(), month_num, int(m.group(1))))

    pairs.sort(key=lambda x: x[0])
    return [(m, y) for _, m, y in pairs]


def _is_present(text: str) -> bool:
    return bool(re.search(
        r'\b(présent|present|actuel|actuellement|aujourd|en cours|en poste|'
        r'now|current|ongoing|till date|à ce jour)\b',
        text, re.IGNORECASE
    ))


def _extract_explicit_months(text: str) -> Optional[int]:
    """
    Extrait la durée explicite entre parenthèses :
    (3 mois), (16 months), (2 ans 2 mois), (1 an 8 mois), (6 ans)
    """
    # (N mois) ou (N months)
    m = re.search(r'\((\d+)\s*(mois|months?)\b', text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    # (N ans N mois) ou (N years N months)
    m2 = re.search(
        r'\((\d+)\s*(ans?|years?)\s*(\d+)?\s*(mois|months?)?\b',
        text, re.IGNORECASE
    )
    if m2:
        years  = int(m2.group(1))
        months = int(m2.group(3)) if m2.group(3) else 0
        return years * 12 + months
    # (N ans) seul
    m3 = re.search(r'\((\d+)\s*(ans?|years?)\)', text, re.IGNORECASE)
    if m3:
        return int(m3.group(1)) * 12
    return None


def _calc_months_from_dates(duration: str) -> Optional[int]:
    """
    Calcule la durée en mois depuis une string de dates brutes du PDF.
    Priorité : durée explicite (N mois/ans) > calcul depuis les dates.
    Retourne None si poste actuel.
    """
    if not duration:
        return 0

    if _is_present(duration):
        # Chercher start date + calculer depuis maintenant
        pairs = _parse_date_pairs(duration)
        if pairs:
            sm, sy = pairs[0]
            return (CURRENT_YEAR - sy) * 12 + (CURRENT_MONTH - sm)
        return None

    # Priorité 1 : durée explicite entre parenthèses
    explicit = _extract_explicit_months(duration)
    if explicit is not None:
        return explicit

    # Priorité 2 : calcul depuis les dates
    pairs = _parse_date_pairs(duration)
    if len(pairs) >= 2:
        sm, sy = pairs[0]
        em, ey = pairs[-1]
        return max((ey - sy) * 12 + (em - sm), 0)

    # Fallback : années seules
    years = [int(y) for y in re.findall(r'\b(20\d{2}|19\d{2})\b', duration)]
    if len(years) >= 2:
        return max((years[-1] - years[0]) * 12, 0)

    return 0


# ─────────────────────────────────────────────────────────────────────────────
# VÉRIFICATION 1 — DURÉES
# ─────────────────────────────────────────────────────────────────────────────

def _check_durations(data: dict, raw: str, fixed: list, warnings: list) -> None:
    """
    Pour chaque expérience : cherche la ligne complète dans le PDF brut
    (qui contient les parenthèses ex-plicites), recalcule la durée,
    et compare avec _explicit_months du parser.
    Si écart → corrige. Si cohérent → ne touche pas.
    """
    raw_lines = raw.splitlines() if raw else []

    for category in ["professional_experience", "internships", "alternance"]:
        for exp in (data.get(category) or []):
            duration = exp.get("duration") or ""
            if not duration:
                continue

            parser_months = exp.get("_explicit_months") or 0

            # Chercher la ligne PDF complète (avec parenthèses) autour de cette exp
            role    = exp.get("role") or ""
            company = exp.get("company") or ""
            ctx     = _find_context_lines(raw, role, company, window=5)

            # Chercher une ligne contenant la duration ET des parenthèses
            pdf_line = duration  # fallback : utiliser la duration nettoyée
            for line in raw_lines:
                if (re.search(r'(20\d{2}|19\d{2})', line) and
                        re.search(r'[-–—]', line) and
                        re.search(r'\(', line)):
                    # Vérifier que cette ligne correspond à cette expérience
                    line_norm = line.lower()
                    dur_norm  = duration.lower()[:15]
                    if dur_norm and dur_norm in line_norm:
                        pdf_line = line
                        break

            validator_months = _calc_months_from_dates(pdf_line)
            if validator_months is None:
                continue  # poste actuel

            if parser_months and validator_months == parser_months:
                continue  # cohérent — ne pas toucher

            if parser_months and abs(validator_months - parser_months) <= 1:
                continue  # tolérance 1 mois

            # Si parser n'a pas stocké _explicit_months (= 0) pour une exp PRO
            # → la durée est calculée par dates dans cv_parser, ne pas interférer
            if not parser_months:
                continue

            if validator_months != parser_months:
                old_m = parser_months
                exp["_explicit_months"] = validator_months
                fixed.append(
                    f"[durée][{category}] '{(exp.get('role') or '')[:35]}' : "
                    f"{old_m}m → {validator_months}m "
                    f"(PDF: '{pdf_line.strip()[:50]}')"
                )


# ─────────────────────────────────────────────────────────────────────────────
# VÉRIFICATION 2 — CLASSIFICATION
# ─────────────────────────────────────────────────────────────────────────────

def _find_context_lines(raw: str, role: str, company: str, window: int = 4) -> str:
    """
    Trouve les lignes du PDF autour d'une expérience donnée.
    Retourne un bloc de texte de `window` lignes autour de la meilleure correspondance.
    """
    lines = raw.splitlines()
    role_words = [w for w in role.lower().split()
                  if len(w) > 3 and w not in {
                      "développeur", "developer", "consultant", "ingénieur",
                      "engineer", "senior", "junior", "stage", "stagiaire"
                  }][:3]
    company_frag = (company or "").lower()[:12]

    best_i, best_score = 0, 0
    for i, line in enumerate(lines):
        ll = line.lower()
        rm = bool(role_words and any(w in ll for w in role_words))
        cm = bool(company_frag and company_frag in ll)
        s  = 2 if (rm and cm) else (1 if cm else (1 if rm else 0))
        if s > best_score:
            best_score, best_i = s, i
        if best_score == 2:
            break

    start = max(0, best_i - 1)
    end   = min(len(lines), best_i + window)
    return " ".join(lines[start:end]).lower()


def _check_classification(data: dict, raw: str, fixed: list, warnings: list) -> None:
    """
    Vérifie la classification de chaque expérience en cherchant les mots-clés
    stage/alternance/CDI dans le texte PDF autour de cette expérience.
    """
    # Vérifier les PRO → sont-ils vraiment des stages ou alternances ?
    pro   = data.get("professional_experience") or []
    inter = data.get("internships") or []
    alt   = data.get("alternance") or []

    # PRO → STAGE ?
    to_stage, keep_pro = [], []
    for exp in pro:
        ctx = _find_context_lines(raw, exp.get("role",""), exp.get("company",""))
        role_low = (exp.get("role") or "").lower()
        if any(kw in role_low or kw in ctx for kw in STAGE_KEYWORDS):
            to_stage.append(exp)
            fixed.append(
                f"[classification] '{(exp.get('role') or '')[:40]}' PRO → STAGE "
                f"(mot-clé stage détecté dans PDF)"
            )
        else:
            keep_pro.append(exp)
    if to_stage:
        data["professional_experience"] = keep_pro
        data["internships"] = inter + to_stage

    # STAGE → ALTERNANCE ?
    inter = data.get("internships") or []
    to_alt, keep_inter = [], []
    for exp in inter:
        ctx = _find_context_lines(raw, exp.get("role",""), exp.get("company",""))
        dur_low = (exp.get("duration") or "").lower()
        if any(kw in dur_low or kw in ctx for kw in ALT_KEYWORDS):
            to_alt.append(exp)
            fixed.append(
                f"[classification] '{(exp.get('role') or '')[:40]}' STAGE → ALTERNANCE "
                f"(mot-clé alternance détecté dans PDF)"
            )
        else:
            keep_inter.append(exp)
    if to_alt:
        data["internships"] = keep_inter
        data["alternance"] = (data.get("alternance") or []) + to_alt


# ─────────────────────────────────────────────────────────────────────────────
# VÉRIFICATION 3 — SKILLS MANQUANTS + MAUVAISES CATÉGORIES
# ─────────────────────────────────────────────────────────────────────────────

def _classify_skill(skill: str) -> Optional[str]:
    """Classifie un skill selon le référentiel. Retourne None si inconnu."""
    k = skill.lower().strip().rstrip('.')
    k = re.sub(r'\s+', ' ', k)

    if k in TOOLS_SET:
        return "tools"
    if k in TECHNICAL_SET:
        return "technical"
    if k in SOFT_SET:
        return "soft_skills"

    # Heuristiques Microsoft / Dynamics
    if any(x in k for x in ["business central", "dynamics", "al language", "erp", "crm",
                              "d365", "navision", "job queue", "odata", "azure function"]):
        return "technical"
    if any(x in k for x in ["power bi", "power apps", "power automate", "ssrs", "ssis",
                              "ssas", "grafana", "kibana", "tableau", "azure devops",
                              "al extension", "visual studio"]):
        return "tools"
    if any(x in k for x in ["agile", "scrum", "kanban", "sure step", "moa", "amoa",
                              "conduite du changement"]):
        return "soft_skills"
    return None


def _parse_skills_from_section(section_text: str) -> List[str]:
    """
    Extrait les tokens skills depuis le texte d'une section COMPÉTENCES.
    Gère les formats :
      - "Catégorie : skill1, skill2"
      - "• skill1 • skill2"
      - "skill1, skill2, skill3"
    """
    found = []
    for line in section_text.splitlines():
        # Ignorer les lignes très courtes ou les en-têtes
        if len(line.strip()) < 3:
            continue
        # Format "Catégorie : items"
        if ':' in line:
            parts = line.split(':', 1)
            items = re.split(r'[,;|•·/]', parts[1])
        else:
            items = re.split(r'[,;|•·/]', line)

        for item in items:
            item = item.strip().strip('•-–()').strip()
            item = re.sub(r'\(.*?\)', '', item).strip()  # supprimer précisions entre ()
            if 2 < len(item) < 60:
                # Rejeter les tokens qui ressemblent à des titres de poste ou entreprises
                # Ex: "Business Central — Dynamix Services", "Stage PFE", etc.
                if re.search(r'—|stagiaire|stage|intern|entreprise|services|agency|group', item, re.IGNORECASE):
                    continue
                # Rejeter si contient un chiffre suivi d'un mois/année (date)
                if re.search(r'\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|janv|févr|mars|avr|mai|juin|juil|août|sept|2020|2021|2022|2023|2024|2025|2026)\b', item, re.IGNORECASE):
                    continue
                found.append(item)

    return found


def _check_skills(data: dict, raw: str, fixed: list, warnings: list) -> None:
    """
    1. Vérifie que chaque skill est dans la bonne catégorie → corrige si besoin.
    2. Scanne la section COMPÉTENCES du PDF → ajoute les skills manquants.
    """
    skills = data.get("skills")
    if not skills:
        return

    # ── Étape 1 : corriger les mauvaises catégories ──────────────────────────
    all_skills_by_cat = {
        "technical":  list(skills.get("technical",   []) or []),
        "tools":      list(skills.get("tools",       []) or []),
        "soft_skills": list(skills.get("soft_skills", []) or []),
    }

    to_move = []  # (skill, old_cat, new_cat)
    for cat, skill_list in all_skills_by_cat.items():
        for skill in skill_list:
            correct = _classify_skill(skill)
            if correct and correct != cat:
                to_move.append((skill, cat, correct))

    for skill, old_cat, new_cat in to_move:
        if skill in skills.get(old_cat, []):
            skills[old_cat].remove(skill)
        if skill not in skills.get(new_cat, []):
            skills.setdefault(new_cat, []).append(skill)
        fixed.append(f"[skill-cat] '{skill}' : {old_cat} → {new_cat}")

    # ── Étape 2 : skills manquants depuis PDF ────────────────────────────────
    if not raw:
        return

    section = _get_section(raw, SKILL_SECTION_HEADERS)
    if not section:
        # Fallback : chercher partout si section non trouvée
        section = raw

    pdf_skills = _parse_skills_from_section(section)

    # Index de tous les skills déjà extraits (normalisés)
    extracted_norm = set()
    for cat in ["technical", "tools", "soft_skills"]:
        for s in (skills.get(cat) or []):
            extracted_norm.add(re.sub(r'\s+', ' ', s.lower().strip()))

    added = []
    for ps in pdf_skills:
        ps_norm = re.sub(r'\s+', ' ', ps.lower().strip())
        # Vérifier si déjà présent (match exact ou inclusion)
        # Alias pour éviter les doublons (vue.js ↔ vue 3, react.js ↔ react, etc.)
        ALIASES = [
            {"vue", "vue.js", "vue 3", "vue3"},
            {"react", "react.js"},
            {"node", "node.js"},
            {"express", "express.js"},
            {"tailwind", "tailwind css"},
            {"bootstrap"},
            {"aws", "amazon web services"},
            {"gcp", "google cloud"},
        ]
        def _is_alias(a, b):
            a, b = a.lower(), b.lower()
            for group in ALIASES:
                if a in group and b in group:
                    return True
            return False

        already = any(
            ps_norm == en or ps_norm in en or en in ps_norm or _is_alias(ps_norm, en)
            for en in extracted_norm
            if len(en) > 2
        )
        if not already:
            # Rejeter les phrases déguisées en skills
            if len(ps) > 60: continue  # trop long = phrase
            if re.search(r'[.!?]$', ps): continue  # se termine par ponctuation
            if re.search(r'(to|scaled|serving|using|with|from|by|and|building)', ps, re.IGNORECASE): continue
            cat = _classify_skill(ps)
            if cat:
                skills.setdefault(cat, []).append(ps)
                extracted_norm.add(ps_norm)
                added.append(f"'{ps}' → {cat}")

    if added:
        fixed.append(
            f"[skills-manquants] {len(added)} skill(s) présent(s) dans PDF mais absents du JSON : "
            + ", ".join(added[:6])
            + (f" (+{len(added)-6} autres)" if len(added) > 6 else "")
        )


# ─────────────────────────────────────────────────────────────────────────────
# VÉRIFICATION 4 — EXPÉRIENCES MANQUANTES
# ─────────────────────────────────────────────────────────────────────────────

def _check_missing_experiences(data: dict, raw: str, warnings: list) -> None:
    """
    Compte les blocs d'expérience dans le PDF (lignes avec année + tiret)
    et compare avec le nombre dans le JSON.
    Signale si le PDF semble en avoir plus.
    """
    if not raw:
        return

    # Compter les blocs dans le JSON
    total_json = (
        len(data.get("professional_experience") or []) +
        len(data.get("internships") or []) +
        len(data.get("alternance") or [])
    )

    # Repérer les lignes "durée" dans la section expérience du PDF
    section = _get_section(raw, EXP_SECTION_HEADERS)
    if not section:
        return

    # Une ligne de durée : contient une année ET un séparateur -/–
    duration_lines = [
        line for line in section.splitlines()
        if re.search(r'\b(20\d{2}|19\d{2})\b', line)
        and re.search(r'[-–—]', line)
        and len(line.strip()) > 5
    ]
    pdf_exp_count = len(duration_lines)

    if pdf_exp_count > total_json + 1:
        # Recueillir les intitulés de poste potentiellement manquants
        missing_roles = []
        lines = section.splitlines()
        for i, line in enumerate(lines):
            if (re.search(r'\b(20\d{2}|19\d{2})\b', line) and
                    re.search(r'[-–—]', line)):
                # Ligne précédente = probable intitulé de poste
                if i > 0 and lines[i-1].strip() and len(lines[i-1].strip()) > 5:
                    missing_roles.append(lines[i-1].strip())

        # Filtrer ceux déjà dans le JSON
        json_roles = set()
        for cat in ["professional_experience", "internships", "alternance"]:
            for exp in (data.get(cat) or []):
                json_roles.add((exp.get("role") or "").lower()[:20])

        truly_missing = [
            r for r in missing_roles
            if not any(r.lower()[:20] in jr or jr in r.lower()[:20]
                       for jr in json_roles)
        ]

        if truly_missing:
            warnings.append(
                f"[exp-manquantes] PDF contient ~{pdf_exp_count} expérience(s), "
                f"JSON en a {total_json}. "
                f"Rôles potentiellement manquants : {truly_missing[:3]}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# VÉRIFICATION 5 — FORMATIONS MANQUANTES
# ─────────────────────────────────────────────────────────────────────────────

def _check_missing_education(data: dict, raw: str, warnings: list) -> None:
    """
    Compte les diplômes dans le PDF et compare avec le JSON.
    """
    if not raw:
        return

    section = _get_section(raw, EDU_SECTION_HEADERS)
    if not section:
        return

    # Compter les lignes contenant un mot-clé diplôme
    pdf_count = sum(
        1 for line in section.splitlines()
        if any(kw in line.lower() for kw in DIPLOMA_KEYWORDS)
    )
    json_count = len(data.get("education") or [])

    if pdf_count > json_count + 1:
        warnings.append(
            f"[formation-manquante] PDF contient ~{pdf_count} diplôme(s), "
            f"JSON en a {json_count} — vérifier si extraction incomplète"
        )


# ─────────────────────────────────────────────────────────────────────────────
# VÉRIFICATION 6 — CERTIFICATIONS MANQUANTES
# ─────────────────────────────────────────────────────────────────────────────

def _check_missing_certifications(data: dict, raw: str, fixed: list, warnings: list) -> None:
    """
    Scanne la section CERTIFICATIONS du PDF.
    Ajoute les certifications présentes dans le PDF mais absentes du JSON.
    """
    if not raw:
        return

    section = _get_section(raw, CERT_SECTION_HEADERS)
    if not section:
        return

    # Index des certifications déjà extraites
    existing = data.get("certifications") or []
    existing_norm = set()
    for c in existing:
        name = (c.get("name") or "").lower()
        if name:
            existing_norm.add(name[:35])

    added = []
    for line in section.splitlines():
        line = line.strip().lstrip('•-–').strip()
        if len(line) < 8:
            continue

        line_norm = line.lower()[:35]
        already = any(
            line_norm in en or en in line_norm
            for en in existing_norm
        )
        if not already:
            # Parser nom + émetteur + année
            year_m = re.search(r'\b(20\d{2})\b', line)
            year   = int(year_m.group(1)) if year_m else None
            name   = re.sub(r'\b20\d{2}\b', '', line).strip()
            # Supprimer séparateurs fin de ligne
            name   = name.rstrip('|·—-–').strip()
            if '|' in name:
                parts  = name.split('|')
                name   = parts[0].strip()
                issuer = parts[1].strip() if len(parts) > 1 else None
            elif '—' in name or '–' in name:
                parts  = re.split(r'[—–]', name)
                name   = parts[0].strip()
                issuer = parts[1].strip() if len(parts) > 1 else None
            else:
                issuer = None

            if len(name) > 5:
                new_cert = {"name": name}
                if issuer:
                    new_cert["issuer"] = issuer
                if year:
                    new_cert["year"] = str(year)
                existing.append(new_cert)
                existing_norm.add(line_norm)
                added.append(name[:45])

    if added:
        data["certifications"] = existing
        fixed.append(
            f"[certif-manquantes] {len(added)} certification(s) absentes du JSON, "
            f"récupérées depuis PDF : {added[:3]}"
            + (f" (+{len(added)-3} autres)" if len(added) > 3 else "")
        )


# ─────────────────────────────────────────────────────────────────────────────
# SCORE FIDÉLITÉ (PDF ↔ JSON)
# ─────────────────────────────────────────────────────────────────────────────

def _compute_fidelity_score(fixed: list, warnings: list) -> float:
    """
    Score de fidélité du JSON par rapport au PDF.
    100% = JSON parfaitement fidèle au PDF.
    Chaque correction et warning réduit le score.
    """
    score = 1.0
    score -= len(fixed)    * 0.05   # -5% par correction
    score -= len(warnings) * 0.02   # -2% par warning
    return round(max(0.0, min(1.0, score)), 2)


# ─────────────────────────────────────────────────────────────────────────────
# FONCTION PRINCIPALE
# ─────────────────────────────────────────────────────────────────────────────

def validate_and_fix(
    data: dict,
    pdf_path: str = "",
) -> Tuple[dict, dict]:
    """
    Valide et corrige le JSON du parser en le comparant au PDF (source de vérité).

    Args:
        data:     JSON retourné par run_cv_parser()
        pdf_path: chemin vers le PDF original

    Returns:
        (data_corrigé, rapport)
        rapport = {
            "is_valid":    bool,
            "fidelity":    float,   ← score fidélité JSON/PDF (0-1)
            "fixed":       list[str],
            "warnings":    list[str],
            "summary":     str,
            "pdf_stats":   dict,    ← ce que le validator a trouvé dans le PDF
        }
    """
    data = copy.deepcopy(data)

    fixed:    List[str] = []
    warnings: List[str] = []

    # Extraire texte brut du PDF
    raw = _extract_raw_text(pdf_path) if pdf_path else ""

    # ── 6 vérifications ──────────────────────────────────────────────────────
    _check_durations(data, raw, fixed, warnings)
    _check_classification(data, raw, fixed, warnings)
    _check_skills(data, raw, fixed, warnings)
    _check_missing_experiences(data, raw, warnings)
    _check_missing_education(data, raw, warnings)
    _check_missing_certifications(data, raw, fixed, warnings)

    # ── Stats PDF ─────────────────────────────────────────────────────────────
    all_skills = (
        (data.get("skills") or {}).get("technical",   []) +
        (data.get("skills") or {}).get("tools",       []) +
        (data.get("skills") or {}).get("soft_skills", [])
    )
    pdf_stats = {
        "pdf_available":       bool(raw),
        "skills_apres_fix":    len(all_skills),
        "exp_total":           (len(data.get("professional_experience") or []) +
                                len(data.get("internships") or []) +
                                len(data.get("alternance") or [])),
        "education_total":     len(data.get("education") or []),
        "certifications_total": len(data.get("certifications") or []),
    }

    # ── Score fidélité & résumé ───────────────────────────────────────────────
    fidelity = _compute_fidelity_score(fixed, warnings)
    is_valid  = len(fixed) == 0 and len(warnings) == 0
    name      = data.get("full_name") or "?"

    if is_valid:
        summary = f"✅ JSON fidèle au PDF — score {fidelity:.0%} | {name}"
    elif fixed and not warnings:
        summary = f"🔧 {len(fixed)} correction(s) appliquée(s) — score {fidelity:.0%} | {name}"
    elif fixed and warnings:
        summary = (f"🔧 {len(fixed)} correction(s) + "
                   f"⚠️  {len(warnings)} avertissement(s) — score {fidelity:.0%} | {name}")
    else:
        summary = f"⚠️  {len(warnings)} avertissement(s) — score {fidelity:.0%} | {name}"

    report = {
        "is_valid":  is_valid,
        "fidelity":  fidelity,
        "fixed":     fixed,
        "warnings":  warnings,
        "summary":   summary,
        "pdf_stats": pdf_stats,
    }

    return data, report


# ─────────────────────────────────────────────────────────────────────────────
# AFFICHAGE
# ─────────────────────────────────────────────────────────────────────────────

def print_report(report: dict) -> None:
    """Affiche le rapport de validation de façon lisible."""
    W = 62
    print("\n" + "═" * W)
    print("  RAPPORT VALIDATION — PDF ↔ JSON")
    print("═" * W)
    print(f"\n  {report['summary']}\n")

    stats = report.get("pdf_stats", {})
    print(f"  Skills   : {stats.get('skills_apres_fix', 0)} au total après fix")
    print(f"  Expér.   : {stats.get('exp_total', 0)}")
    print(f"  Formation: {stats.get('education_total', 0)}")
    print(f"  Certifs  : {stats.get('certifications_total', 0)}")
    print()

    if report["fixed"]:
        print("── ✅ CORRECTIONS APPLIQUÉES " + "─" * (W - 29))
        for f in report["fixed"]:
            print(f"  ✅  {f}")
        print()

    if report["warnings"]:
        print("── ⚠️  AVERTISSEMENTS " + "─" * (W - 22))
        for w in report["warnings"]:
            print(f"  ⚠️   {w}")
        print()

    if not report["fixed"] and not report["warnings"]:
        print("  Aucun écart détecté entre le PDF et le JSON.\n")

    print("═" * W + "\n")