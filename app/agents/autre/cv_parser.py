import os
import re
import json
import math
import logging
import unicodedata
import pdfplumber
from groq import Groq
from groq import RateLimitError as GroqRateLimitError
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError, Field
from typing import Optional
from datetime import datetime
import pytesseract
from PIL import ImageFilter, ImageEnhance
import platform as _platform, shutil as _shutil
POPPLER_PATH = os.getenv('POPPLER_PATH', r'C:\Program Files\poppler\Library\bin')


# ── Tesseract : chemin auto selon OS ─────────────────────────────────────────
# Windows : cherche dans PATH, sinon chemin par defaut
# Linux/Mac : tesseract doit etre dans le PATH (apt/brew install tesseract)
if _platform.system() == "Windows":
    _tess = os.getenv("TESSERACT_PATH") or _shutil.which("tesseract") or r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    pytesseract.pytesseract.tesseract_cmd = _tess

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

MAX_PDF_SIZE_MB = 5
MAX_TEXT_CHARS  = 12000

# ─────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

CURRENT_YEAR  = datetime.now().year
CURRENT_MONTH = datetime.now().month


# ─────────────────────────────────────────
# MODELES PYDANTIC — Validation stricte
# ─────────────────────────────────────────

class Education(BaseModel):
    degree: Optional[str] = None
    institution: Optional[str] = None
    start_year: Optional[str] = None
    end_year: Optional[str] = None


class Experience(BaseModel):
    role: Optional[str] = None
    company: Optional[str] = None
    duration: Optional[str] = None
    achievements: list[str] = Field(default_factory=list)


class Certification(BaseModel):
    name: Optional[str] = None
    issuer: Optional[str] = None
    year: Optional[str] = None


class Project(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    technologies: list[str] = Field(default_factory=list)
    link: Optional[str] = None


class Skills(BaseModel):
    technical: list[str] = Field(default_factory=list)
    soft_skills: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)


class CVData(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    skills: Optional[Skills] = None
    education: list[Education] = Field(default_factory=list)
    professional_experience: list[Experience] = Field(default_factory=list)
    internships: list[Experience] = Field(default_factory=list)
    alternance: list[Experience] = Field(default_factory=list)
    years_professional: Optional[int] = 0
    months_internships: Optional[int] = 0
    months_alternance: Optional[int] = 0
    certifications: list[Certification] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    nb_internships: Optional[int] = 0
    languages: list[str] = Field(default_factory=list)
    years_experience: Optional[int] = 0
    cv_quality_score: Optional[float] = 0.0
    classification_confidence: Optional[float] = 0.0


# ─────────────────────────────────────────
# NETTOYAGE DU TEXTE — FR + EN
# ─────────────────────────────────────────

MARKETING_PATTERNS = [
    r"Cher Internaute.*",       r"CV designer.*",
    r"Comment faire.*",         r"Exemples de CV.*",
    r"lettre de motivation.*",  r"IMPORTANT\s*:.*",
    r"Cordialement.*",          r"CVGenius.*",
    r"Supprimer les lignes.*",  r"cliquez sur.*",
    r"bouton droit.*",          r"Si vous avez des difficult.*",
    r"rassurez-vous.*",         r"Pour r.diger.*",
    r"nous avons les ressources.*",
    r"Dear.*Recruiter.*",       r"To Whom It May Concern.*",
    r"References available upon request.*",
    r"Cover letter.*",          r"Resume builder.*",
    r"Click here.*",            r"Download.*template.*",
    r"This resume was created.*",
    r"Page \d+ of \d+.*",
    r"·\s*CV\b.*",
    r"CV mis à jour.*\d{4}.*",
    r"Resume updated.*\d{4}.*",
    r"Last updated.*\d{4}.*",
]

def clean_text(text: str) -> str:
    # ── ÉTAPE 0.5 : Normaliser les bullets (cid:127) → • ─────────────────
    # pdfplumber extrait les caractères bullets comme "(cid:127)" ou "(cid:108)"
    # quand la police de caractères map ces codepoints à des glyphes décoratifs.
    # Le parser en a besoin pour détecter les achievements multi-pages.
    text = re.sub(r'\(cid:\d+\)', '•', text)

    # ── ÉTAPE 0 : Corriger les PDFs à double couche de texte ──────────
    # Certains PDFs design ont une police décorative + une couche texte
    # cachée superposée. pdfplumber lit les deux et concatène les chars :
    # "AAlliixx" au lieu de "Alix", "hheelllloo@@..." au lieu de "hello@..."
    # Détection : si une ligne a ≥3 paires de caractères identiques consécutifs
    # → prendre 1 caractère sur 2 (skip pairs).
    fixed_lines = []
    for line in text.splitlines():
        sample = re.sub(r'\s', '', line)
        if len(sample) >= 6:
            pairs_ok = sum(
                1 for i in range(0, min(len(sample) - 1, 10), 2)
                if sample[i] == sample[i + 1]
            )
            if pairs_ok >= 3:
                line = ''.join(line[i] for i in range(0, len(line), 2))
        fixed_lines.append(line)
    text = '\n'.join(fixed_lines)

    # ── ÉTAPE 1 : Recomposer les accents décomposés (LaTeX/PDF) ───────
    # NFKC d'abord : transforme "e + ´" en "é", "Aouˆt" → "Août"
    text = unicodedata.normalize('NFKC', text)

    # ── ÉTAPE 2 : Supprimer les diacritiques résiduels non recomposés ─
    # (ceux que NFKC n'a pas pu fusionner avec une lettre)
    text = re.sub(r"[`´ˆ¸˜]", "", text)

    # ── ÉTAPE 3 : Supprimer les caractères invisibles et de contrôle ─────
    # Contrôle ASCII (garde tab, newline, CR)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    # Caractères Unicode invisibles : NBSP, Zero-Width Space, Soft Hyphen,
    # Word Joiner, Zero-Width Non-Joiner — fréquents dans PDFs exportés Word
    text = re.sub(r'[\u00a0\u200b\u200c\u200d\u2060\u00ad\ufeff]', ' ', text)
    # Tirets spéciaux → tiret standard (évite problèmes de matching)
    text = re.sub(r'[\u2010-\u2015\u2212]', '-', text)
    # Guillemets typographiques → guillemets standard
    text = re.sub(r'[\u201c\u201d\u2018\u2019]', '"', text)
    # ── ÉTAPE 4 : Supprimer les \escape invalides JSON ────────────────
    # Garde \n \t \r \\ \" \/ \uXXXX — supprime \textbf \begin etc.
    text = re.sub(r'\\(?!["\\/bfnrt]|u[0-9a-fA-F]{4})', '', text)

    # ── ÉTAPE 5 : Supprimer commandes LaTeX résiduelles ───────────────
    # Cible précisément les commandes connues sans toucher %, &, <, >
    text = re.sub(
        r'\b(textbf|textit|emph|begin|end|item|hline|vspace|hspace)\b\s*\{[^}]*\}?',
        '', text
    )

    # ── ÉTAPE 6 : Nettoyage standard (URLs, marketing) ───────────────
    # NOTE : on ne supprime PAS les emails — ils sont des données de contact
    # essentielles. Sur les CVs scannés (OCR), l'email peut apparaître
    # n'importe où dans le texte (pas seulement dans les 5 premières lignes).
    # La suppression était la cause du bug email=None sur les PDFs scannés.
    text = re.sub(r"http\S+|www\.\S+|linkedin\.com\S*", "", text)
    for pattern in MARKETING_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"\b([A-Z])\s(?=[A-Z]\s)", r"\1", text)

    # ── ÉTAPE 6c : Tokens corrompus (fusion de mots par pdfplumber) ──────
    # Token corrompu = 2 mots fusionnés → maj interne anormale ex: "MaCrakmeitlilen"
    # Règle : len>12 + transition min→Maj interne + pas de tiret (Paris-Dauphine ok)
    cleaned_lines = []
    for _line in text.splitlines():
        _tokens = _line.split()
        _good = []
        for _tok in _tokens:
            _tc = re.sub(r'[^\w]', '', _tok)
            _inner = _tc[1:]
            _trans = len(re.findall(r'[a-zàâéèêïôùûü][A-ZÀÂÉÈÊÏÔÙÛÜ]', _inner))
            if len(_tc) > 12 and _trans >= 1 and '-' not in _tok:
                break
            _good.append(_tok)
        cleaned_lines.append(' '.join(_good))
    text = '\n'.join(cleaned_lines)

    # ── ÉTAPE 7 : Normaliser les espaces (sans écraser les \n) ───────
    text = re.sub(r'[ \t]{2,}', ' ', text)   # espaces multiples sur une ligne
    text = re.sub(r"\n{3,}", "\n\n", text)    # max 2 sauts de ligne consécutifs
    text = re.sub(r"[?]", "-", text)

    return text.strip()


# ─────────────────────────────────────────
# NORMALISATION ET CORRECTION DES SKILLS
# ─────────────────────────────────────────

SKILL_SYNONYMS = {
    "ml": "Machine Learning",       "dl": "Deep Learning",
    "ai": "Artificial Intelligence","nlp": "Natural Language Processing",
    "js": "JavaScript",             "ts": "TypeScript",
    "node": "Node.js",              "nodejs": "Node.js",    "node.js": "Node.js",
    "reactjs": "React",             "react.js": "React",
    "python3": "Python",            "postgres": "PostgreSQL",
    "mongo": "MongoDB",             "k8s": "Kubernetes",
    "langage sql": "SQL",           "langage python": "Python",
    "machine learning": "Machine Learning",
    "deep learning": "Deep Learning",
    "natural language processing": "Natural Language Processing",
    "apprentissage automatique": "Machine Learning",
    "intelligence artificielle": "Artificial Intelligence",
    "gestion de projet": "Project Management",
    "analyse de donnees": "Data Analysis",
    "visualisation de donnees": "Data Visualization",
    "data analysis": "Data Analysis",
    "data visualization": "Data Visualization",
    "project management": "Project Management",
}


_EMPTY_SKILL_VALUES = {"n/a", "na", "none", "aucun", "aucune", "-", "—", "néant", "neant", "/"}

GENERIC_ACHIEVEMENT_PATTERNS = [
    re.compile(r'^[Rr]ésultat\s*\d+$'),
    re.compile(r'^[Rr]esultat\s*\d+$'),
    re.compile(r'^[Aa]chievement\s*\d+$'),
    re.compile(r'^[Tt]ask\s*\d+$'),
    re.compile(r'^[Tt]âche\s*\d+$'),
    re.compile(r'^[Bb]ullet\s*\d+$'),
    re.compile(r'^[Ii]tem\s*\d+$'),
    re.compile(r'^\[\w+\]$'),               # [Action], [Résultat]
    re.compile(r'^Action\s*\d*$'),
    re.compile(r'^Responsabilité\s*\d*$'),
]

# Préfixes indiquant qu'une ligne est une entrée de section skills/certif
# et non un achievement — typique des CVs 2 colonnes où le LLM mélange les colonnes
_SKILL_SECTION_PREFIXES = re.compile(
    r'^(Langages?|Languages?|Langages de programmation|Bases de données?|'
    r'Databases?|Frameworks?|Cloud|Big Data|MLOps|BI|Viz|Outils?|Tools?|'
    r'M.thodes?|Methods?|ML/AI|Data Eng\.|Infrastructure|Conteneurs?|'
    r'Monitoring|Versioning|Web scraping|Statistics?|Stack|Compétences?|'
    r'Skills?|Expertise|Technologies?)\s*[:\-]',
    re.IGNORECASE
)

# Patterns de certifications glissées dans les achievements (CVs 2 colonnes)
_CERTIF_IN_ACHIEVEMENT = re.compile(
    r'(AWS|Azure|Google|Microsoft|Cisco|Oracle|Salesforce|PMI|ITIL|'
    r'CKA|CKS|CKAD|Kubernetes|Terraform|HashiCorp|DeepLearning(?:\.AI)?|'
    r'Coursera|Udacity|DataTalks|Databricks|Snowflake|dbt\s*Labs|NVIDIA|IBM|CompTIA)'
    r'.*?(Certified|Certificate|Professional|Associate|Practitioner|'
    r'Developer|Administrator|Architect|Engineer|Fundamentals|Basics)'
    r'.*?(?:\(\d{4}\)|\d{4})',
    re.IGNORECASE
)

# Détecte skills injectés au milieu d'un achievement (CVs 2 colonnes)
# Ex: "ETL pipelines (Python, ML/AI : Scikit-learn...) processing"
_SKILL_INJECTION_IN_TEXT = re.compile(
    r'(?:ML/AI|Langages?|Frameworks?|Cloud|Big Data|Data Eng\.|Outils?|'
    r'Bases de donn.es?|Monitoring|MLOps)\s*[:\-]\s*\w',
    re.IGNORECASE
)

def clean_achievements(experience_list: list, raw_text: str = "") -> list:
    """
    Supprime les achievements invalides générés par le LLM :
      1. Achievements génériques (Résultat 1, Achievement 2...)
      2. Lignes de skills mélangées (CVs 2 colonnes : "Langages: Python, SQL...")
      3. Certifications glissées dans les achievements ("AWS Certified... (2023)")
    """
    for exp in experience_list:
        if not isinstance(exp, dict):
            continue
        original = exp.get("achievements") or []
        cleaned  = []
        skipped  = []
        for a in original:
            if not a:
                continue
            a_strip = a.strip()
            # Filtre 1 — patterns génériques (Résultat 1, Task 2...)
            if any(p.match(a_strip) for p in GENERIC_ACHIEVEMENT_PATTERNS):
                skipped.append(f"générique: {a_strip[:40]}")
                continue
            # Filtre 2 — lignes de skills (CVs 2 colonnes)
            # Ex: "ML/AI : Scikit-learn, TensorFlow, PyTorch..."
            if _SKILL_SECTION_PREFIXES.match(a_strip):
                skipped.append(f"skill-colonne: {a_strip[:40]}")
                continue
            # Filtre 3 — certifications glissées dans achievements
            # Ex: "DeepLearning.AI TensorFlow Developer (2021)"
            if _CERTIF_IN_ACHIEVEMENT.search(a_strip):
                skipped.append(f"certif-colonne: {a_strip[:40]}")
                continue
            # Filtre 4 — skills injectés au milieu d'une phrase d'achievement
            # Ex: "ETL pipelines (Python, ML/AI : Scikit-learn, TensorFlow... Airflow) processing"
            # Ce cas arrive quand pdfplumber entrelace colonne droite dans la gauche
            if _SKILL_INJECTION_IN_TEXT.search(a_strip) and len(a_strip) > 80:
                skipped.append(f"skill-injecté: {a_strip[:40]}")
                continue
            cleaned.append(a)

        if skipped:
            logger.info(
                f"  {len(skipped)} achievement(s) filtrés (2-colonnes/génériques) : '{exp.get('role', '?')}' → "
                + " | ".join(skipped[:3])
            )
        exp["achievements"] = cleaned
    return experience_list


# Soft skills génériques que le LLM invente quand il ne trouve rien
GENERIC_SOFT_SKILLS = {
    "communication", "leadership", "teamwork", "adaptability",
    "problem solving", "critical thinking", "time management",
    "work ethic", "creativity", "collaboration", "flexibility",
}

def filter_generic_soft_skills(skills: dict, raw_text: str) -> dict:
    """Supprime les soft skills generiques hallucinés absents du texte CV."""
    soft = skills.get("soft_skills") or []
    raw_lower = raw_text.lower()
    kept, removed = [], []
    for s in soft:
        # Vérifier que le skill apparaît dans un contexte "compétence" (section skills)
        # et pas juste comme mot dans un nom d'école ou titre de poste
        if s.lower() in GENERIC_SOFT_SKILLS:
            # Chercher dans section COMPÉTENCES spécifiquement
            in_skills_section = bool(re.search(
                r'COMP.TENCES.*?' + re.escape(s),
                raw_lower, re.DOTALL | re.IGNORECASE
            ))
            if not in_skills_section:
                removed.append(s)
            else:
                kept.append(s)
        else:
            kept.append(s)
    if removed:
        logger.info(f"  {len(removed)} soft skill(s) generique(s) supprime(s) : "
                    + ", ".join(f"'{s}'" for s in removed))
    skills["soft_skills"] = kept
    return skills



SKILL_BLACKLIST_TITLES = {
    # Titres de postes glissés dans les skills
    "comptable", "ingenieur", "ingénieur", "manager", "developpeur",
    "développeur", "directeur", "chef", "responsable", "analyst",
    "consultant", "assistant", "charge", "chargé", "technicien",
    "architecte", "lead", "senior", "junior", "stagiaire",
    "alternant", "intern", "engineer", "developer",
}

# Mots trop vagues pour être des skills utiles (hallucinations LLM fréquentes)
SKILL_VAGUE_WORDS = {
    # Termes IT trop génériques
    "data", "system", "development", "management", "analysis",
    "programming", "software", "technology", "solution", "service",
    "application", "platform", "computing", "processing", "framework",
    "language", "tool", "technique", "method", "approach", "practice",
    # Termes français génériques
    "informatique", "développement", "gestion", "système", "logiciel",
    "traitement", "conception", "analyse", "programmation",
    # Termes marketing/business trop vagues
    "content", "digital", "communication", "marketing", "strategy",
    "secteurs", "disciplines", "outils", "compétences",
    # Termes IT trop génériques (sans précision)
    "cloud", "security", "architecture", "infrastructure", "backend",
    "frontend", "fullstack", "full-stack", "back-end", "front-end",
    # Termes statistiques vagues
    "régression", "regression", "tests statistiques",
    "séries temporelles", "time series",
    "statistiques avancées", "advanced statistics", "statistiques",
    # Catégories génériques (sans technologie précise)
    "langages de programmation", "bases de données", "systèmes d'exploitation",
    "résolution de problèmes", "dépannage", "languages", "databases",
    "operating systems", "problem solving", "troubleshooting",
}

def clean_skills(skills: dict) -> dict:
    """
    Étape 1 du post-traitement Python :
    - Supprime valeurs nulles (N/A, None, null)
    - Supprime doublons (insensible à la casse)
    - Supprime titres de postes glissés dans les skills
    - Supprime mots trop vagues (Data, System, Development...)
    - Filtre longueur : < 2 chars ou > 80 chars
    """
    if not isinstance(skills, dict):
        return {"technical": [], "soft_skills": [], "tools": []}
    def _clean_list(lst):
        seen, result = set(), []
        for item in (lst or []):
            if not isinstance(item, str): continue
            item = item.strip()
            # Valeurs nulles
            if not item or item.lower() in ("n/a","none","null","-","–","aucun","aucune"): continue
            # Longueur
            if len(item) < 2 or len(item) > 80: continue
            # Titres de postes
            if any(t in item.lower() for t in SKILL_BLACKLIST_TITLES): continue
            # Mots trop vagues — le LLM sort parfois "Data", "System", "Development"
            if item.lower() in SKILL_VAGUE_WORDS: continue
            # Skills tronqués — se terminent par conjonction ou contiennent fragment de phrase
            if re.search(r'\b(and|via|or|with|et|including|such as)\s*$', item, re.IGNORECASE):
                continue
            # Skills qui ressemblent à des fragments de phrase
            # Contient "via ... and" ou "via ... or" → fragment de liste tronquée
            if re.search(r'\bvia\b.+\b(and|or)\b', item, re.IGNORECASE):
                continue
            # Contient "integration via" → toujours un fragment
            if re.search(r'\bintegration\s+via\b', item, re.IGNORECASE):
                continue
            # Déduplication insensible à la casse
            if item.lower() not in seen:
                seen.add(item.lower()); result.append(item)
        return result
    return {"technical": _clean_list(skills.get("technical")),
            "soft_skills": _clean_list(skills.get("soft_skills")),
            "tools": _clean_list(skills.get("tools"))}


# ─────────────────────────────────────────────────────────────────────────────
# NORMALISATION ET CORRECTION DES SKILLS (couche Python post-LLM)
# Architecture : LLM extrait + classifie → Python corrige + normalise
# ─────────────────────────────────────────────────────────────────────────────

# Aliases de normalisation : variantes connues → forme canonique
SKILL_ALIASES = {
    # JavaScript
    "js": "JavaScript", "javascript": "JavaScript", "java script": "JavaScript",
    # TypeScript
    "ts": "TypeScript", "typescript": "TypeScript",
    # Python
    "python3": "Python", "python 3": "Python",
    # Node
    "node": "Node.js", "nodejs": "Node.js", "node.js": "Node.js",
    # React
    "reactjs": "React.js", "react js": "React.js", "react": "React.js",
    # Machine Learning
    "ml": "Machine Learning", "machine-learning": "Machine Learning",
    # Deep Learning
    "dl": "Deep Learning", "deep-learning": "Deep Learning",
    # Natural Language Processing
    "nlp": "NLP",
    # CI/CD
    "ci/cd": "CI/CD", "cicd": "CI/CD",
    # Docker/Kubernetes
    "docker": "Docker", "kubernetes": "Kubernetes", "k8s": "Kubernetes",
    # Git
    "git": "Git", "github": "GitHub", "gitlab": "GitLab",
    # Power BI
    "powerbi": "Power BI", "power bi": "Power BI",
    # Microsoft Office
    "ms excel": "Excel", "microsoft excel": "Excel",
    "ms word": "Word", "microsoft word": "Word",
    # SQL
    "sql": "SQL", "mysql": "MySQL", "postgresql": "PostgreSQL",
    "postgres": "PostgreSQL",
    # REST
    "rest": "REST API", "rest api": "REST API", "restful": "REST API",
    # TensorFlow
    "tensorflow": "TensorFlow", "tensor flow": "TensorFlow",
    # PyTorch
    "pytorch": "PyTorch", "py torch": "PyTorch",
    # Scikit-learn
    "scikit learn": "Scikit-learn", "sklearn": "Scikit-learn",
}

# Outils connus (logiciels qu'on ouvre sans coder)
KNOWN_TOOLS = {
    # BI / Dataviz
    "power bi", "tableau", "looker", "metabase", "grafana", "qlik",
    # Data / ETL tools
    "talend", "informatica", "pentaho",
    # Databases GUI
    "mysql workbench", "pgadmin", "dbeaver", "mongodb compass", "sql server management studio",
    # DevOps tools
    "docker", "kubernetes", "jenkins", "gitlab", "github", "git",
    "ansible", "terraform", "prometheus",
    # IDEs / editors
    "vscode", "vs code", "pycharm", "intellij", "eclipse", "jupyter",
    "rstudio", "spyder",
    # Design
    "figma", "adobe xd", "sketch", "canva", "photoshop", "illustrator",
    # PM / Collaboration
    "jira", "confluence", "trello", "notion", "asana", "monday", "slack", "teams",
    # Office
    "excel", "word", "powerpoint", "google sheets", "google workspace", "google docs",
    # ERP / CRM
    "sap", "salesforce", "hubspot", "odoo", "sage", "dynamics",
    # API testing
    "postman", "insomnia", "swagger",
    # Cloud platforms & consoles
    "aws console", "azure portal", "gcp console",
    "ec2", "s3", "rds", "lambda", "cloudfront", "ecs", "eks",
    "azure blob storage", "azure functions", "azure app service",
    # Messaging
    "apache kafka",
    # Mobile tools & platforms
    "firebase", "firebase cloud messaging", "fcm", "google play console", "app store connect",
    "android studio", "xcode", "expo", "fastlane", "appcenter",
    # CI/CD & monitoring
    "sonarqube", "grafana", "datadog", "sentry", "new relic",
    # Version control hosting
    "bitbucket", "azure repos",
    # Package managers
    "npm", "yarn", "pip", "maven", "gradle",
    # Containers / infra
    "docker", "kubernetes", "helm", "vagrant",
}

# Soft skills légitimes (méthodologies de travail)
# Uniquement : gestion de projet et méthodes organisationnelles
KNOWN_SOFT = {
    "agile", "scrum", "kanban", "safe", "itil",
    "merise", "design thinking", "six sigma",
}

# Compétences forcées en TECHNICAL même si le LLM les met en tools
# Règle : on CODE avec eux, on ne les "ouvre" pas comme un logiciel GUI
KNOWN_TECHNICAL_FORCED = {
    # Frameworks web / backend
    "django", "flask", "fastapi", "spring", "laravel", "symfony",
    "express", "expressjs", "rails", "asp.net", "dotnet",
    # Frameworks frontend
    "react.js", "react", "vue.js", "vue", "angular", "svelte",
    "next.js", "nuxt.js",
    # Bases de données (compétence technique, pas GUI)
    "mysql", "postgresql", "sqlite", "oracle", "sql server",
    "mongodb", "redis", "cassandra", "elasticsearch", "mariadb",
    "dynamodb", "neo4j",
    # Langages
    "python", "java", "javascript", "typescript", "c", "c++", "c#",
    "php", "ruby", "go", "rust", "kotlin", "swift", "scala", "r",
    "html", "css", "sass", "sql", "bash", "shell", "matlab",
    # ML / Data science
    "tensorflow", "pytorch", "scikit-learn", "keras", "pandas",
    "numpy", "scipy", "matplotlib", "seaborn", "spark", "hadoop",
    "machine learning", "deep learning", "nlp", "computer vision",
    "etl", "crisp-dm", "data visualization", "statistical analysis",
    # Cloud / DevOps (compétences codées)
    "google cloud", "heroku",
    "ci/cd",
    "rest api", "graphql", "grpc", "microservices",
    # Autres
    "langchain", "hugging face", "openai api", "llm",
    # Web scraping
    "beautifulsoup", "beautiful soup", "scrapy", "selenium",
    # Stacks et plateformes
    "elk stack", "elk", "mean stack", "mern stack",
    # Méthodes UX/Design
    "design thinking", "lean ux", "jobs-to-be-done", "jtbd",
    "atomic design", "double diamant", "double diamond",
    "a/b testing", "ab testing", "guerrilla testing", "usability testing",
    "user research", "design system", "wireframing", "prototypage",
    "prototyping", "motion design",
    # Patterns et méthodologies de développement logiciel
    "tdd", "bdd", "ddd", "clean architecture", "event sourcing",
    "microservices", "domain driven design", "solid", "design patterns",
    "event driven", "cqrs", "hexagonal architecture",
    # CI/CD et pratiques DevOps techniques
    "ci/cd", "code review", "pair programming", "devops",
    "infrastructure as code", "iac", "gitflow",
}


def normalize_skill(skill: str) -> str:
    """Normalise un skill : lowercase → alias lookup → capitalisation correcte."""
    s = skill.strip()
    s_lower = s.lower().replace("-", " ").replace("_", " ")
    # Lookup alias
    if s_lower in SKILL_ALIASES:
        return SKILL_ALIASES[s_lower]
    # Capitalisation par défaut : title case sauf acronymes connus
    ACRONYMS = {"sql", "css", "html", "php", "api", "rest", "etl",
                "nlp", "ml", "ai", "dl", "bi", "erp", "crm"}
    if s_lower in ACRONYMS:
        return s.upper()
    return s  # garder la casse originale si pas d'alias


def correct_skill_category(skills: dict) -> dict:
    """
    Correction déterministe post-LLM — 3 passes :
    Pass 1 : tools mal classés en technical → rester en technical si KNOWN_TECHNICAL_FORCED
    Pass 2 : skills en tools → revenir en technical si KNOWN_TECHNICAL_FORCED
    Pass 3 : soft skills connus → depuis technical ou tools vers soft_skills
    Architecture : Python corrige les erreurs prévisibles du LLM
    """
    technical  = [normalize_skill(s) for s in (skills.get("technical")  or [])]
    tools      = [normalize_skill(s) for s in (skills.get("tools")      or [])]
    soft       = [normalize_skill(s) for s in (skills.get("soft_skills") or [])]

    # Pass 0 : depuis soft_skills → technical si compétence technique forcée
    # (LLM met parfois TDD/BDD/DDD/CI-CD directement en soft_skills)
    final_soft_raw, moved_soft_to_tech = [], []
    for s in soft:
        if s.lower() in KNOWN_TECHNICAL_FORCED:
            moved_soft_to_tech.append(s)
        else:
            final_soft_raw.append(s)
    technical = technical + moved_soft_to_tech
    soft = final_soft_raw
    if moved_soft_to_tech:
        logger.info(f"  Correction soft→technical : {moved_soft_to_tech}")

    # Pass 1 : depuis technical → tools (si outil GUI connu ET pas forcé technical)
    final_tech, moved_to_tools = [], []
    for s in technical:
        if s.lower() in KNOWN_TOOLS and s.lower() not in KNOWN_TECHNICAL_FORCED:
            moved_to_tools.append(s)
        else:
            final_tech.append(s)

    # Pass 2 : depuis tools → technical (si compétence technique forcée)
    final_tools_raw, moved_to_tech = [], []
    for s in tools + moved_to_tools:
        if s.lower() in KNOWN_TECHNICAL_FORCED:
            moved_to_tech.append(s)
        else:
            final_tools_raw.append(s)
    final_tech = final_tech + moved_to_tech

    # Pass 3 : depuis technical/tools → soft_skills (méthodologies de travail)
    final_tools, moved_to_soft = [], []
    for s in final_tools_raw:
        if s.lower() in KNOWN_SOFT:
            moved_to_soft.append(s)
        else:
            final_tools.append(s)
    final_tech_clean, moved_to_soft2 = [], []
    for s in final_tech:
        if s.lower() in KNOWN_SOFT:
            moved_to_soft2.append(s)
        else:
            final_tech_clean.append(s)

    # Pass 3b : soft_skills initiaux qui ne sont PAS dans KNOWN_SOFT → garder
    # soft_skills initiaux dans KNOWN_SOFT → garder aussi (déjà bien classés)
    # Cas : Scrum arrivé directement en soft_skills → doit rester
    final_soft = soft + moved_to_soft + moved_to_soft2

    # Log corrections
    if moved_to_tools:
        logger.info(f"  Correction technical→tools : {moved_to_tools}")
    if moved_to_tech:
        logger.info(f"  Correction tools→technical : {moved_to_tech}")
    if moved_to_soft + moved_to_soft2:
        logger.info(f"  Correction →soft_skills : {moved_to_soft + moved_to_soft2}")

    # Déduplication inter-catégories (priorité : technical > tools > soft)
    seen = set()
    def dedup(lst):
        result = []
        for s in lst:
            k = s.lower()
            if k not in seen:
                seen.add(k); result.append(s)
        return result

    return {
        "technical":   dedup(final_tech_clean),
        "tools":       dedup(final_tools),
        "soft_skills": dedup(final_soft),
    }


def fix_missing_end_date(experience_list: list, raw_text: str) -> list:
    """
    Fallback Python : si duration contient seulement une date de début
    et que le texte brut du CV contient "présent/present/actuel/en cours"
    dans le même contexte → ajouter "Présent" comme date de fin.

    Problème : le LLM extrait "Juil. 2024" sans "Présent"
    quand le CV écrit "Juil. 2024 - Présent"
    """
    if not experience_list:
        return experience_list

    PRESENT_KEYWORDS = {
        "présent", "present", "actuel", "actuellement",
        "aujourd", "en cours", "en poste", "now", "current", "ongoing",
        "till date", "till now", "à ce jour", "à present", "toujours en poste"
    }
    raw_lower = raw_text.lower() if raw_text else ""

    for exp in experience_list:
        if not isinstance(exp, dict):
            continue
        duration = (exp.get("duration") or "").strip()
        if not duration:
            continue

        # Vérifier si la duration contient déjà un mot "présent"
        already_present = any(kw in duration.lower() for kw in PRESENT_KEYWORDS)
        if already_present:
            continue

        # Vérifier si la duration contient 2 dates (donc une fin explicite)
        import re as _re
        years = _re.findall(r"20\d{2}|19\d{2}", duration)
        # Si 2 années trouvées → date de fin explicite, pas besoin de corriger
        if len(years) >= 2:
            continue

        # 1 seule date → chercher dans le texte brut si c'est un poste actuel
        # Chercher le contexte autour du nom de l'entreprise ou du rôle
        company = (exp.get("company") or "").lower()[:20]
        role    = (exp.get("role")    or "").lower()[:20]

        # Fenêtre de recherche : chercher présent/actuel près du rôle ou entreprise
        context_found = False
        if company and company in raw_lower:
            idx = raw_lower.find(company)
            window = raw_lower[max(0, idx-100):idx+200]
            if any(kw in window for kw in PRESENT_KEYWORDS):
                context_found = True

        if not context_found and role and role in raw_lower:
            idx = raw_lower.find(role)
            window = raw_lower[max(0, idx-100):idx+200]
            if any(kw in window for kw in PRESENT_KEYWORDS):
                context_found = True

        if context_found:
            exp["duration"] = duration + " - Présent"
            logger.info(
                f"  [fix-end-date] '{exp.get('role')}' → duration corrigée : '{exp['duration']}'"
            )

    return experience_list



# ─────────────────────────────────────────
# CORRECTION ENTREPRISE = VILLE (Bug #19)
# ─────────────────────────────────────────

# Villes fréquentes dans les CVs FR/EN qui peuvent être prises pour entreprises
CITY_NAMES_BLACKLIST = {
    # France
    "paris", "lyon", "marseille", "toulouse", "nice", "nantes", "bordeaux",
    "lille", "rennes", "reims", "strasbourg", "grenoble", "montpellier",
    "metz", "nancy", "dijon", "clermont", "rouen", "tours", "amiens",
    "angers", "brest", "limoges", "caen", "saint-étienne", "saint etienne",
    "île-de-france", "ile-de-france", "hauts-de-seine", "val-de-marne",
    "france", "french",
    # Belgique / Suisse / Luxembourg
    "bruxelles", "brussels", "genève", "geneva", "zurich", "bâle", "lausanne",
    "luxembourg", "liège", "anvers", "antwerp",
    # UK / US / International fréquents
    "london", "paris france", "new york", "san francisco", "berlin",
    "amsterdam", "madrid", "barcelona", "rome", "milan", "munich",
    "remote", "full remote", "télétravail", "home office", "hybrid",
    # Régions / pays seuls
    "france", "belgique", "suisse", "canada", "maroc", "tunisie",
    "algérie", "sénégal", "côte d'ivoire",
}

# ─────────────────────────────────────────
# CORRECTION BÉNÉVOLAT (Bug #32)
# ─────────────────────────────────────────

# Mots-clés explicites indiquant un bénévolat
VOLUNTEER_EXPLICIT = {
    # Français
    "bénévole", "benevole", "bénévolat", "benevol",
    "pro bono", "probono",
    "volontaire", "volontariat",
    # Anglais
    "volunteer", "volunteering", "voluntary",
    "pro-bono", "community service",
}

# Mots-clés contextuels (bénévolat probable si combiné avec rôle non-sénior)
VOLUNTEER_CONTEXTUAL = {
    "association", "asso ", "ong ", "ngo ", "nonprofit", "non-profit",
    "fondation", "foundation", "charity", "charité",
    "mentorat", "mentoring", "mentor bénévole",
    "ladies of code", "club ", "collectif ", "initiative ",
}

# Signaux de postes PAYÉS dans une asso → garder comme PRO
PAID_ROLE_SIGNALS = {
    "directeur", "director", "président", "president", "ceo",
    "responsable", "manager", "chef de projet", "project manager",
    "coordinateur", "coordinator", "développeur", "developer",
    "ingénieur", "engineer", "consultant", "analyste", "analyst",
}

def fix_volunteer_experiences(result: dict) -> dict:
    """
    Détecte et retire les expériences bénévoles de professional_experience.

    Règles :
      - Si role/company contient un mot-clé VOLUNTEER_EXPLICIT → retirer
      - Si company contient un mot-clé VOLUNTEER_CONTEXTUAL ET role
        ne contient PAS de signal payé → retirer
      - Exception : poste sénior/directeur dans une asso → garder (peut être payé)

    Les expériences retirées ne sont PAS comptées dans l'expérience pro.
    Note : on ne crée pas de liste 'volunteering' dans CVData (non prévu),
    on supprime simplement pour ne pas gonfler le total pro.
    """
    import unicodedata as _ud

    def _norm(text: str) -> str:
        """Normalise : supprime accents + lowercase pour matching robuste."""
        return _ud.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii').lower()

    for key in ["professional_experience", "internships"]:
        exps = result.get(key) or []
        kept = []

        for exp in exps:
            if not isinstance(exp, dict):
                kept.append(exp)
                continue

            role    = (exp.get("role")    or "")
            company = (exp.get("company") or "")
            combined_norm = _norm(role + " " + company)
            role_norm     = _norm(role)

            # Vérifier mots-clés explicites (certitude haute)
            is_volunteer_explicit = any(_norm(kw) in combined_norm for kw in VOLUNTEER_EXPLICIT)

            if is_volunteer_explicit:
                logger.info(
                    f"  [fix-volunteer] Retiré (bénévolat explicite) : "
                    f"'{exp.get('role')}' @ '{exp.get('company')}'"
                )
                continue

            # Vérifier mots-clés contextuels + absence de signal payé
            has_volunteer_context = any(_norm(kw) in combined_norm for kw in VOLUNTEER_CONTEXTUAL)
            has_paid_signal       = any(_norm(kw) in role_norm for kw in PAID_ROLE_SIGNALS)

            if has_volunteer_context and not has_paid_signal:
                logger.info(
                    f"  [fix-volunteer] Retiré (contexte asso, rôle non-sénior) : "
                    f"'{exp.get('role')}' @ '{exp.get('company')}'"
                )
                continue

            kept.append(exp)

        if len(kept) < len(exps):
            result[key] = kept

    return result


def fix_city_as_company(result: dict) -> dict:
    """
    Corrige les cas où le LLM met une ville comme nom d'entreprise.

    Problème : le CV écrit "Développeur @ Paris" ou "Software Engineer - London"
    → le LLM extrait company = "Paris" / "London" au lieu de None.

    Règle :
      - Si company (normalisé) est dans CITY_NAMES_BLACKLIST ET
        que le company ne contient PAS d'autres mots → company = None
      - Cas ambigus gardés : "Orange Paris", "BNP Paris", "Lyon & Associés"
        (la ville est suffixe mais le nom d'entreprise précède)
    """
    for key in ["professional_experience", "internships", "alternance"]:
        for exp in (result.get(key) or []):
            if not isinstance(exp, dict):
                continue
            company = (exp.get("company") or "").strip()
            if not company:
                continue

            company_lower = company.lower().strip(" ,.-")

            # Cas 1 : company est exactement une ville seule
            if company_lower in CITY_NAMES_BLACKLIST:
                logger.info(
                    f"  [fix-city] company='{company}' → None "
                    f"('{exp.get('role')}' — ville seule détectée)"
                )
                exp["company"] = None
                continue

            # Cas 2 : company = "Ville, Pays" ou "Ville, Région"
            # ex: "Paris, France" / "Lyon, Île-de-France"
            parts = [p.strip().lower() for p in company_lower.split(",")]
            if len(parts) >= 2 and parts[0] in CITY_NAMES_BLACKLIST:
                logger.info(
                    f"  [fix-city] company='{company}' → None "
                    f"('{exp.get('role')}' — ville + région/pays)"
                )
                exp["company"] = None
                continue

            # Cas 3 : company contient une ville + "(remote)" ou "(hybrid)"
            # ex: "Paris (remote)" → None
            import re as _re
            cleaned = _re.sub(r'\s*\([^)]*\)', '', company_lower).strip(" ,.-")
            if cleaned in CITY_NAMES_BLACKLIST:
                logger.info(
                    f"  [fix-city] company='{company}' → None "
                    f"('{exp.get('role')}' — ville + parenthèse)"
                )
                exp["company"] = None
                continue

            # Cas 3 : company se termine par une ville connue
            # ex: "TechCorp Paris" → garder (Paris est suffixe, TechCorp = vrai nom)
            # ex: "Paris (remote)"  → supprimer (rien avant la ville)
            for city in CITY_NAMES_BLACKLIST:
                if company_lower.endswith(city):
                    prefix = company_lower[:-len(city)].strip(" ,.-–()")
                    if not prefix:
                        # Rien avant la ville → faux positif
                        logger.info(
                            f"  [fix-city] company='{company}' → None "
                            f"(ville en suffixe sans préfixe)"
                        )
                        exp["company"] = None
                    break

    return result


def fix_missing_company_and_dates(result: dict, raw_text: str) -> dict:
    """
    Correction Python post-LLM :
    Si une expérience a company=None ou duration="" →
    chercher dans le texte brut la ligne suivant le titre du poste
    pour récupérer l'entreprise et les dates.

    Pattern typique dans CVs 2 colonnes :
        "Développeur Back-End Junior"       ← titre
        "StartupFactory — Incubateur tech 2013 – 2015"  ← entreprise + dates
    """
    import re as _re

    for key in ["professional_experience", "internships", "alternance"]:
        for exp in (result.get(key) or []):
            if not isinstance(exp, dict):
                continue

            company  = (exp.get("company") or "").strip()
            duration = (exp.get("duration") or "").strip()
            role     = (exp.get("role") or "").strip()

            # Seulement si entreprise ou dates manquantes
            if company and company.lower() not in ("none", "null", "") and duration:
                continue

            if not role:
                continue

            # Chercher le titre dans le texte brut
            raw_lines = raw_text.splitlines()
            for i, line in enumerate(raw_lines):
                if role[:20].lower() in line.lower():
                    # Regarder les 3 lignes suivantes
                    for j in range(i+1, min(i+4, len(raw_lines))):
                        next_line = raw_lines[j].strip()
                        if not next_line:
                            continue
                        # Chercher un pattern "Entreprise YYYY – YYYY" ou "Entreprise YYYY"
                        date_match = _re.search(r'(20\d{2}|19\d{2})', next_line)
                        if date_match and len(next_line) > 5:
                            # Séparer entreprise et dates
                            date_pos = date_match.start()
                            # Trouver le début de la partie date
                            date_part_match = _re.search(
                                r'(\d{4}\s*[–-]\s*(?:\d{4}|[Pp]résent|[Pp]resent|[Aa]ctuel))',
                                next_line
                            )
                            if date_part_match:
                                company_part = next_line[:date_part_match.start()].strip(" —-–")
                                date_part    = date_part_match.group(0).strip()
                            else:
                                company_part = next_line[:date_pos].strip(" —-–")
                                date_part    = next_line[date_pos:].strip()

                            if not company or company.lower() in ("none", "null", ""):
                                if company_part:
                                    exp["company"] = company_part
                                    logger.info(
                                        f"  [fix-company] '{role[:30]}' → company='{company_part}'"
                                    )
                            if not duration and date_part:
                                exp["duration"] = date_part
                                logger.info(
                                    f"  [fix-duration] '{role[:30]}' → duration='{date_part}'"
                                )
                            break
                    break

    return result


def recover_missing_soft_skills(result: dict, raw_text: str) -> dict:
    """
    Si des méthodes KNOWN_SOFT sont dans le texte brut mais absentes
    des soft_skills extraits → les ajouter (variabilité LLM).
    """
    import re as _re
    SOFT_RECOVER = {
        "scrum": "Scrum", "agile": "Agile", "kanban": "Kanban",
        "lean": "Lean", "itil": "ITIL", "safe": "SAFe",
    }
    raw_lower = (raw_text or "").lower()
    skills = result.get("skills") or {}
    all_lower = (
        [s.lower() for s in (skills.get("technical") or [])] +
        [s.lower() for s in (skills.get("tools") or [])] +
        [s.lower() for s in (skills.get("soft_skills") or [])]
    )
    added = []
    for kw, display in SOFT_RECOVER.items():
        if _re.search(rf'\b{kw}\b', raw_lower) and kw not in all_lower:
            # Ne pas ajouter si une variante composée est déjà en technical
            # ex: "lean" ignoré si "lean ux" est déjà dans technical
            tech_lower = [s.lower() for s in (skills.get("technical") or [])]
            if any(kw in t and t != kw for t in tech_lower):
                continue
            if skills.get("soft_skills") is None:
                skills["soft_skills"] = []
            skills["soft_skills"].append(display)
            added.append(display)
    if added:
        logger.info(f"  [recover-soft] Méthodes récupérées : {added}")
        result["skills"] = skills
    return result

def fix_hallucinated_present(result: dict, raw_text: str) -> dict:
    """
    Supprime les "Présent" inventés par le LLM.
    Règle : si "Présent" est dans duration mais PAS dans le texte brut du CV
    → supprimer "Présent" et garder seulement la date de début.
    Python est la source de vérité — pas le LLM.
    """
    import re as _re

    PRESENT_WORDS = {"présent", "present", "actuel", "actuellement",
                     "en cours", "en poste", "now", "current", "ongoing",
                     "till date", "à ce jour", "toujours en poste"}

    # Vérifier si le CV contient réellement un mot "présent"
    raw_lower = (raw_text or "").lower()
    cv_has_present = any(kw in raw_lower for kw in PRESENT_WORDS)

    if cv_has_present:
        # Le CV contient "présent" → on ne touche à rien, le LLM a raison
        return result

    # Le CV ne contient PAS "présent" → supprimer tous les "- Présent" inventés
    for key in ["professional_experience", "internships", "alternance"]:
        for exp in (result.get(key) or []):
            if not isinstance(exp, dict):
                continue
            duration = exp.get("duration") or ""
            # Si "présent" dans la duration mais pas dans le CV → supprimer
            if any(kw in duration.lower() for kw in PRESENT_WORDS):
                # Garder seulement la date de début (avant le tiret)
                parts = _re.split(r"\s*[-–]\s*", duration)
                clean = parts[0].strip()
                logger.info(
                    f"  [fix-présent] '{exp.get('role')}' : "
                    f"'{duration}' → '{clean}' (Présent absent du CV)"
                )
                exp["duration"] = clean

    return result

def _fix_alternance_from_raw_text(result: dict, raw_text: str) -> dict:
    """
    Correction post-LLM : détecte les alternances que le LLM a mal classées en PRO.

    Problème : le LLM extrait role = "Développeur Web" en supprimant "— Alternance"
    du titre, donc reclassify_experiences ne voit jamais le mot-clé et classe en PRO.

    Fix : pour chaque expérience PRO, cherche le bloc correspondant dans le texte
    brut (par nom de compagnie) et vérifie si "alternance" ou "apprentissage"
    apparaît dans les 3 lignes autour du titre du poste.
    """
    if not raw_text:
        return result

    pro = result.get("professional_experience") or []
    if not pro:
        return result

    raw_lines = raw_text.splitlines()
    alternance_kws = {"alternance", "alternant", "apprentissage", "apprenti", "work-study",
                       "contrat d'alternance", "contrat alternance", "en alternance"}

    to_move_pro   = []  # indices dans pro à déplacer
    to_move_stage = []  # indices dans internships à déplacer

    # Dict pour stocker les corrections de duration trouvées dans le raw_text
    _alt_duration_fixes: dict[str, str] = {}  # role → duration corrigée

    def _check_alternance(exp_list, to_move_list):
        for idx, exp in enumerate(exp_list):
            # 1) Vérifier le champ duration directement (plus fiable)
            duration_lower = (exp.get("duration") or "").lower()
            role_lower     = (exp.get("role") or "").lower()
            if any(kw in duration_lower or kw in role_lower for kw in alternance_kws):
                to_move_list.append(idx)
                logger.info(
                    f"  [fix-alternance] '{exp.get('role')}' @ '{exp.get('company')}' "
                    f"→ reclassifié ALTERNANCE (mot-clé dans duration/role)"
                )
                continue

            # 2) Chercher dans le raw_text autour du nom de compagnie
            company = (exp.get("company") or "").lower().strip()
            if not company:
                continue
            for i, line in enumerate(raw_lines):
                if company[:15] in line.lower():
                    window_start = max(0, i - 3)
                    window_end   = min(len(raw_lines), i + 4)
                    window_text  = " ".join(raw_lines[window_start:window_end]).lower()
                    if any(kw in window_text for kw in alternance_kws):
                        to_move_list.append(idx)
                        logger.info(
                            f"  [fix-alternance] '{exp.get('role')}' @ '{exp.get('company')}' "
                            f"→ reclassifié ALTERNANCE (mot-clé trouvé dans texte brut)"
                        )
                        # Chercher la vraie duration dans les lignes suivantes
                        role_key = (exp.get("role") or "").strip()
                        for di in range(i, min(i+6, len(raw_lines))):
                            dl = raw_lines[di]
                            years = re.findall(r'\b(20\d{2}|19\d{2})\b', dl)
                            if len(years) >= 2:
                                _alt_duration_fixes[role_key] = dl.strip()
                                logger.info(f"  [alt-dur-found] '{role_key}' → '{dl.strip()}'")
                                break
                    break

    _check_alternance(pro, to_move_pro)

    # Chercher aussi dans les stages mal classifiés
    stages = result.get("internships") or []
    _check_alternance(stages, to_move_stage)

    # Déplacer les expériences détectées vers alternance
    alt = result.get("alternance") or []

    if to_move_pro:
        new_pro = []
        for idx, exp in enumerate(pro):
            if idx in to_move_pro:
                if "alternance" not in (exp.get("role") or "").lower():
                    exp["role"] = (exp.get("role") or "") + " — Alternance"
                alt.append(exp)
            else:
                new_pro.append(exp)
        result["professional_experience"] = new_pro

    if to_move_stage:
        new_stages = []
        for idx, exp in enumerate(stages):
            if idx in to_move_stage:
                if "alternance" not in (exp.get("role") or "").lower():
                    exp["role"] = (exp.get("role") or "") + " — Alternance"
                if raw_text:
                    role_words    = [w for w in (exp.get("role") or "").lower().split() if len(w) > 3][:2]
                    company_frag  = (exp.get("company") or "").lower()[:12]
                    old_dur       = exp.get("duration") or ""
                    old_sy, old_sm, old_ey, old_em = extract_period_from_duration(old_dur)
                    old_months    = (old_ey - old_sy) * 12 + (old_em - old_sm) if old_sy else 0

                    # Priorité 1 : duration trouvée lors de la détection
                    role_key = (exp.get("role") or "").strip()
                    # Le role a pu être modifié avec " — Alternance" → chercher aussi la version originale
                    role_key_clean = re.sub(r'\s*[—\-]+\s*alternance\s*$', '', role_key, flags=re.IGNORECASE).strip()
                    if role_key not in _alt_duration_fixes and role_key_clean in _alt_duration_fixes:
                        role_key = role_key_clean
                    if role_key in _alt_duration_fixes:
                        fixed_dur = _alt_duration_fixes[role_key]
                        new_sy, new_sm, new_ey, new_em = extract_period_from_duration(fixed_dur)
                        if new_sy:
                            new_months = (new_ey - new_sy) * 12 + (new_em - new_sm)
                            if new_months > old_months:
                                logger.info(f"  [fix-alternance-dur] '{old_dur}' → '{fixed_dur}' ({new_months} mois)")
                                exp["duration"] = fixed_dur

                    # Priorité 2 : recherche dans raw_text par role + company
                    elif raw_text:
                        for i, line in enumerate(raw_lines):
                            line_lower = line.lower()
                            role_match    = role_words and all(w in line_lower for w in role_words)
                            company_match = company_frag and company_frag in line_lower
                            if not (role_match or company_match):
                                continue
                            for wline in raw_lines[i:min(i+5, len(raw_lines))]:
                                years = re.findall(r'\b(20\d{2}|19\d{2})\b', wline)
                                if len(years) >= 2:
                                    new_sy, new_sm, new_ey, new_em = extract_period_from_duration(wline.strip())
                                    if new_sy is None:
                                        continue
                                    new_months = (new_ey - new_sy) * 12 + (new_em - new_sm)
                                    if new_months > old_months:
                                        logger.info(f"  [fix-alternance-dur] '{old_dur}' → '{wline.strip()}' ({new_months} mois)")
                                        exp["duration"] = wline.strip()
                                    break
                            break
                alt.append(exp)
            else:
                new_stages.append(exp)
        result["internships"] = new_stages

    if to_move_pro or to_move_stage:
        result["alternance"] = alt

    return result


def _fill_continuation_achievements(experiences: list, raw_text: str) -> list:
    """
    Complète les achievements manqués dans les blocs de continuation de page.

    Approche directe (v2) : pour chaque expérience, cherche le titre exact du
    poste dans le texte brut, puis collecte TOUS les bullets qui suivent
    jusqu'à la prochaine ligne non-bullet non-vide. On fusionne ensuite avec
    ce que le LLM a déjà extrait.

    Plus robuste que la v1 (regex CONTINUATION_BLOCK) qui traversait les
    newlines via [^(]+ et générait de faux positifs multi-lignes.
    """
    if not raw_text or not experiences:
        return experiences

    BULLET_LINE = re.compile(r'^\s*[•\-–—*■]\s*(.+)$')

    lines = raw_text.splitlines()
    logger.info(f"  [continuation-debug] appelée: {len(experiences)} exps, {len(lines)} lignes raw_text")
    for _dbg in experiences:
        logger.info(f"  [continuation-debug]  role={repr(_dbg.get('role','')[:40])} ach={len(_dbg.get('achievements') or [])}")

    for exp in experiences:
        role    = (exp.get("role")    or "").strip()
        company = (exp.get("company") or "").strip()
        if not role:
            continue

        # Chercher TOUTES les lignes du texte brut qui contiennent ce rôle
        # (peut apparaître plusieurs fois : page 1 + bloc continuation page 2)
        role_lower    = role.lower()
        company_lower = company.lower()[:15]   # matching partiel sur 15 chars

        # Collecter tous les bullets depuis CHAQUE occurrence du titre
        all_bullets: list[str] = []

        for idx, line in enumerate(lines):
            line_lower = line.lower()
            # La ligne doit contenir au moins les 2 premiers mots du rôle
            role_words = [w for w in role_lower.split() if len(w) > 2][:3]
            if not role_words or not all(w in line_lower for w in role_words):
                continue

            # Optionnel : vérifier que c'est bien lié à la bonne compagnie
            # (dans les 3 lignes suivantes ou la même ligne)
            context = " ".join(lines[idx:min(idx+4, len(lines))]).lower()
            if company_lower and company_lower not in context:
                continue

            # Collecter les bullets qui suivent immédiatement
            for j in range(idx + 1, min(idx + 25, len(lines))):
                bm = BULLET_LINE.match(lines[j])
                if bm:
                    all_bullets.append(bm.group(1).strip())
                elif lines[j].strip():
                    # Ligne non-vide non-bullet → fin du bloc d'achievements
                    # Exception : marqueurs de page (--- PAGE N ---)
                    if re.match(r'^---\s*PAGE\s*\d+\s*---$', lines[j].strip()):
                        continue
                    break

        if not all_bullets:
            continue

        # Fusionner avec les achievements existants sans doublons
        existing      = list(exp.get("achievements") or [])
        existing_lower = {a.lower().strip() for a in existing}
        added = []
        for bullet_text in all_bullets:
            key = bullet_text.lower().strip()
            if key not in existing_lower:
                existing.append(bullet_text)
                existing_lower.add(key)
                added.append(bullet_text)

        if added:
            exp["achievements"] = existing
            logger.info(
                f"  [continuation] +{len(added)} achievement(s) : "
                f"'{role}' @ '{company}'"
            )

    return experiences



def validate_tools_against_text(skills: dict, raw_text: str) -> dict:
    """
    Valide que les outils retournés par le LLM existent vraiment dans le texte OCR.
    Supprime les outils hallucinés (Power BI, Tableau... absent du CV réel).

    Pour les CVs avec "Logiciel 01, Logiciel 02" → seuls ces outils sont gardés.
    Pour les CVs normaux → tous les outils présents dans le texte sont gardés.
    """
    if not raw_text or not skills:
        return skills

    raw_lower = raw_text.lower()
    tools     = skills.get("tools") or []

    validated_tools = []
    removed_tools   = []

    for tool in tools:
        # Vérifier si l'outil (ou un fragment significatif) est dans le texte OCR
        tool_lower = tool.lower()
        # Pour outils multi-mots (ex: "Power BI"), chercher les 2 mots principaux
        words = [w for w in tool_lower.split() if len(w) > 2]
        found = any(w in raw_lower for w in words) if words else tool_lower in raw_lower

        if found:
            validated_tools.append(tool)
        else:
            removed_tools.append(tool)

    if removed_tools:
        logger.info(
            f"  {len(removed_tools)} outil(s) halluciné(s) supprimé(s) : "
            + ", ".join(f"'{t}'" for t in removed_tools[:5])
            + (" ..." if len(removed_tools) > 5 else "")
        )

    skills["tools"] = validated_tools
    return skills


def validate_skills_against_text(skills: dict, raw_text: str) -> dict:
    """Supprime skills absents verbatim du texte (anti-hallucination).

    FIX React.js : apres normalize_skill(), "React" devient "React.js".
    La validation cherche "react.js" dans le texte mais le CV ecrit "React".
    Solution : chercher aussi la racine sans suffixe (.js) et les aliases inverses.
    """
    if not raw_text or not skills: return skills
    raw_lower = raw_text.lower()

    # Aliases inverses : forme normalisee → variantes a chercher dans le texte
    _INVERSE_ALIASES = {
        "react.js": ["react", "reactjs"],
        "vue.js":   ["vue", "vuejs"],
        "node.js":  ["node", "nodejs"],
        "next.js":  ["next", "nextjs"],
        "nuxt.js":  ["nuxt", "nuxtjs"],
    }

    def _validate(lst, cat):
        validated, removed = [], []
        for skill in (lst or []):
            skill_lower = skill.lower()
            words = [w for w in re.split(r"[\s/\-]+", skill_lower) if len(w) > 2]
            extra = _INVERSE_ALIASES.get(skill_lower, [])
            root = re.sub(r'\.(js|ts|py|rb|go)$', '', skill_lower)
            if root != skill_lower and len(root) > 2:
                extra = extra + [root]
            all_candidates = words + extra
            found = any(w in raw_lower for w in all_candidates) if all_candidates else skill_lower in raw_lower
            (validated if found else removed).append(skill)
        if removed:
            logger.info(f"  {len(removed)} {cat} absent(s) supprime(s) : " + ", ".join(f"\'{s}\'" for s in removed[:5]))
        return validated
    skills["technical"]   = _validate(skills.get("technical"),   "technique(s)")
    skills["soft_skills"] = _validate(skills.get("soft_skills"), "soft skill(s)")
    skills["tools"]       = _validate(skills.get("tools"),       "outil(s)")
    return skills

def extract_languages_from_text(raw_text: str) -> list[str]:
    """
    Extraction directe des langues depuis le texte OCR brut.
    Fallback utilisé si le LLM a raté des langues.

    Cherche des patterns FR/EN courants :
      "Français : langue maternelle" → Français
      "Anglais : niveau professionnel" → Anglais
      "Portugais : niveau débutant" → Portugais
    """
    LANG_PATTERNS = [
        # Pattern "Langue : niveau" (CV français)
        re.compile(
            r'\b(Français|Anglais|Espagnol|Allemand|Arabe|Portugais|Italien|'
            r'Chinois|Japonais|Russe|Néerlandais|Turc|Hindi|Coréen)\b',
            re.IGNORECASE
        ),
        # Pattern anglais
        re.compile(
            r'\b(French|English|Spanish|German|Arabic|Portuguese|Italian|'
            r'Chinese|Japanese|Russian|Dutch|Turkish|Hindi|Korean)\b',
            re.IGNORECASE
        ),
    ]

    # Mapping anglais → français pour uniformiser
    LANG_NORMALIZE = {
        "french": "Français", "english": "Anglais", "spanish": "Espagnol",
        "german": "Allemand", "arabic": "Arabe", "portuguese": "Portugais",
        "italian": "Italien", "chinese": "Chinois", "japanese": "Japonais",
        "russian": "Russe", "dutch": "Néerlandais", "turkish": "Turc",
        "hindi": "Hindi", "korean": "Coréen",
    }

    found = []
    seen  = set()
    for pattern in LANG_PATTERNS:
        for m in pattern.finditer(raw_text):
            lang = m.group(0)
            normalized = LANG_NORMALIZE.get(lang.lower(), lang.capitalize())
            if normalized.lower() not in seen:
                seen.add(normalized.lower())
                found.append(normalized)

    return found


# ─────────────────────────────────────────
# DETECTION PRESENT / ACTUEL
# ─────────────────────────────────────────

PRESENT_KEYWORDS = [
    "present", "présent", "actuel", "actuellement",
    "aujourd", "now", "current", "en cours", "en poste",
    "ongoing", "today", "toujours", "still",
    "till date", "à ce jour", "toujours en poste"
]

def is_present_position(text: str) -> bool:
    return any(kw in text.lower() for kw in PRESENT_KEYWORDS)


# ─────────────────────────────────────────
# MAPPING MOIS FR + EN
# ─────────────────────────────────────────

MONTHS_MAP = {
    "janvier": 1,    "février": 2,   "mars": 3,      "avril": 4,
    "mai": 5,        "juin": 6,      "juillet": 7,   "août": 8,
    "septembre": 9,  "octobre": 10,  "novembre": 11, "décembre": 12,
    "jan": 1, "fév": 2, "fev": 2, "avr": 4,
    "juil": 7,"aoû": 8, "aou": 8, "sep": 9, "sept": 9,
    "oct": 10,"nov": 11,"déc": 12,"dec": 12,
    "january": 1,    "february": 2,  "march": 3,     "april": 4,
    "may": 5,        "june": 6,      "july": 7,      "august": 8,
    "september": 9,  "october": 10,  "november": 11, "december": 12,
    "feb": 2,"mar": 3,"apr": 4,"jun": 6,"jul": 7,"aug": 8,
}


# ─────────────────────────────────────────
# EXTRACTION PERIODE AVEC MOIS — Robuste
# ─────────────────────────────────────────

def extract_period_from_duration(
    duration: str,
) -> tuple[Optional[int], Optional[int], Optional[int], Optional[int]]:
    """
    Retourne (start_year, start_month, end_year, end_month).
    Fonction unique, utilisee partout — pas de duplication de logique.

    Gere :
      "Fev. 2023 - Juin 2023"  → (2023,2, 2023,6)  = 4 mois ✅
      "Juin - Juil. 2022"      → (2022,6, 2022,7)  = 1 mois ✅
      "2020 - 2022"            → (2020,1, 2022,12) = 24 mois ✅
      "2022 - present"         → (2022,1, actuel)           ✅
      "Internship 2022"        → (2022,1, 2022,2)  = 1 mois ✅
    """
    if not duration:
        return None, None, None, None

    normalized = duration.lower()
    normalized = normalized.replace("–", " - ").replace("—", " - ").replace(".", " ")
    normalized = re.sub(r"\s+", " ", normalized).strip()

    # Fix — Années sur 2 chiffres (ex: "oct 21" → "oct 2021", "jan-22" → "jan 2022")
    # Règle : si \d{2} précédé d'un mois ou d'un tiret → compléter en 20XX
    # Fix — Format MM/YYYY (ex: "01/2022 - 03/2022") → "janvier 2022 - mars 2022"
    # Appliqué AVANT _expand_2digit_year pour éviter les conflits
    def _expand_mmyyyy(s: str) -> str:
        month_names = [
            "", "janvier", "fevrier", "mars", "avril", "mai", "juin",
            "juillet", "aout", "septembre", "octobre", "novembre", "decembre"
        ]
        def _replace(m):
            mm, yyyy = int(m.group(1)), m.group(2)
            return f"{month_names[mm]} {yyyy}" if 1 <= mm <= 12 else m.group(0)
        return re.sub(r"(?<![a-zA-Z])\b(0?[1-9]|1[0-2])/(20\d{2}|19\d{2})\b", _replace, s)
    normalized = _expand_mmyyyy(normalized)

    # Fix — Années sur 2 chiffres (ex: "oct 21" → "oct 2021", "jan-22" → "jan 2022")
    def _expand_2digit_year(s: str) -> str:
        month_abbrs = r"jan|feb|fev|mar|apr|avr|may|mai|jun|juin|jul|juil|aug|aou|sep|sept|oct|nov|dec"
        return re.sub(
            rf"\b({month_abbrs})\b[\s\-]+(\d{{2}})\b(?!\d)",
            lambda m: f"{m.group(1)} 20{m.group(2)}",
            s
        )
    normalized = _expand_2digit_year(normalized)

    present = is_present_position(duration)

    # ── Paires mois+année (ex: "décembre 2020") ───────────────────────
    pairs = []  # liste de (position, mois, année)
    for month_name, month_num in sorted(MONTHS_MAP.items(), key=lambda x: -len(x[0])):
        pattern = rf"\b{re.escape(month_name)}\b\s*(20\d{{2}}|19\d{{2}})"
        for match in re.finditer(pattern, normalized):
            pairs.append((match.start(), month_num, int(match.group(1))))
    pairs.sort(key=lambda x: x[0])

    # ── Mois isolés (sans année immédiate) — ex: "juillet" dans "Juillet - décembre 2020"
    # Positions déjà couvertes par une paire → à exclure
    paired_positions = {pos for pos, _, _ in pairs}
    isolated = []  # liste de (position, mois)
    for month_name, month_num in sorted(MONTHS_MAP.items(), key=lambda x: -len(x[0])):
        pattern_iso = rf"\b{re.escape(month_name)}\b(?!\s*(?:20|19)\d{{2}})"
        for match in re.finditer(pattern_iso, normalized):
            # Exclure si position proche d'une paire déjà trouvée
            if not any(abs(match.start() - pp) < 4 for pp in paired_positions):
                isolated.append((match.start(), month_num))
    isolated.sort(key=lambda x: x[0])

    years_found = [int(y) for y in re.findall(r"\b(20\d{2}|19\d{2})\b", normalized)]

    # ── CAS 1 : 2+ paires mois+année (cas normal) ─────────────────────
    if len(pairs) >= 2:
        _, start_month, start_year = pairs[0]
        if present:
            return start_year, start_month, CURRENT_YEAR, CURRENT_MONTH
        _, end_month, end_year = pairs[-1]
        return start_year, start_month, end_year, end_month

    # ── CAS 2 : 1 paire + mois isolé avant → "Juillet - décembre 2020" ─
    elif len(pairs) == 1:
        pair_pos, end_month, end_year = pairs[0]

        # Cherche un mois isolé AVANT la paire
        before_isolated = [(pos, m) for pos, m in isolated if pos < pair_pos]

        if before_isolated:
            # "Juillet - décembre 2020" → start=juillet, end=décembre 2020
            _, start_month = before_isolated[0]
            # Si mois début > mois fin → année précédente (ex: Nov - Jan 2023 → start=2022)
            start_year = end_year - 1 if start_month > end_month else end_year
            if present:
                return start_year, start_month, CURRENT_YEAR, CURRENT_MONTH
            return start_year, start_month, end_year, end_month

        # Mois isolé APRÈS la paire → paire=start, isolated=end (même année)
        after_isolated = [(pos, m) for pos, m in isolated if pos > pair_pos]
        if after_isolated:
            start_month, start_year = end_month, end_year
            _, end_month_iso = after_isolated[0]
            end_year_iso = end_year
            if present:
                return start_year, start_month, CURRENT_YEAR, CURRENT_MONTH
            return start_year, start_month, end_year_iso, end_month_iso

        # 1 seule paire sans mois isolé
        start_month, start_year = end_month, end_year
        if present:
            return start_year, start_month, CURRENT_YEAR, CURRENT_MONTH
        if len(years_found) >= 1:
            return start_year, start_month, years_found[-1], min(start_month + 1, 12)
        return start_year, start_month, start_year, min(start_month + 1, 12)

    # ── CAS 3 : Que des mois isolés (ex: "Juin - Juillet" sans année) ──
    elif len(isolated) >= 2 and len(years_found) >= 1:
        # "Juin - Juillet 2022" → les deux mois isolés + 1 année
        _, start_month = isolated[0]
        _, end_month   = isolated[-1]
        end_year       = years_found[-1]
        start_year     = end_year - 1 if start_month > end_month else end_year
        if present:
            return start_year, start_month, CURRENT_YEAR, CURRENT_MONTH
        return start_year, start_month, end_year, end_month

    # ── CAS 4 : Années seules (ex: "2020 - 2022") ─────────────────────
    elif len(years_found) >= 2:
        start_year = years_found[0]
        end_year   = CURRENT_YEAR if present else years_found[-1]
        return start_year, 1, end_year, 1

    # ── CAS 5 : 1 seule année ─────────────────────────────────────────
    elif len(years_found) == 1:
        start_year = years_found[0]
        if present:
            return start_year, 1, CURRENT_YEAR, CURRENT_MONTH
        return start_year, 1, start_year, 2

    return None, None, None, None


def duration_to_months(duration, exp: dict = None) -> int:
    """
    Convertit une chaine de duree en nombre de mois.
    Accepte aussi un dict experience — utilise _explicit_months si présent.
    Priorité : _explicit_months > parenthèses "(3 months)" > calcul dates.
    """
    # 0) _explicit_months stocké par le validator (source la plus fiable)
    if isinstance(duration, dict):
        exp = duration
        duration = exp.get("duration") or ""
    if exp and exp.get("_explicit_months"):
        return int(exp["_explicit_months"])
    if not duration:
        return 0
    # 1) Durée explicite entre parenthèses : "(3 months)" / "(16 mois)" / "(2 ans 1 mois)"
    m = re.search(r'\((\d+)\s*(month|mois|months)\)', duration, re.IGNORECASE)
    if m:
        return int(m.group(1))
    m2 = re.search(r'\((\d+)\s*(an|ans|year|years)[\s,]*(\d+)?\s*(mois|month|months?)?\)', duration, re.IGNORECASE)
    if m2:
        years = int(m2.group(1))
        months = int(m2.group(3)) if m2.group(3) else 0
        return years * 12 + months
    # 2) Fallback : calcul par dates
    sy, sm, ey, em = extract_period_from_duration(duration)
    if sy is None:
        return 0
    return max((ey - sy) * 12 + (em - sm), 0)


# ─────────────────────────────────────────
# CALCUL DUREES — UNE SEULE PASSE (Bug 2 fix)
#
# FIX : calculate_total_months() loggue les details.
#       classify_experience_weighted() appelle extract_period_from_duration()
#       DIRECTEMENT sans passer par calculate_total_months()
#       → elimine le double-calcul et le double-log.
# ─────────────────────────────────────────

def calculate_total_months(experience_list: list, log_details: bool = True) -> int:
    """
    Calcule le total en mois pour une liste d'experiences.

    FIX chevauchements : si 2 postes se chevauchent (ex: consultant 2019-présent
    ET lead dev 2020-2022), on ne compte pas la période en double.
    Algorithme : convertir en intervalles absolus → trier → fusionner → sommer.

    Exemple Thomas Girard :
      2019-2026 + 2020-2022 → fusionné en 2019-2026 (pas de double comptage)
      Résultat correct : 13 ans au lieu de 15 ans

    log_details=True  → affiche le detail de chaque experience
    log_details=False → silencieux (usage interne classification)
    """
    if not experience_list:
        return 0

    # ── Étape 1 : collecter tous les intervalles valides ─────────────
    intervals = []
    for exp in experience_list:
        duration = exp.get("duration", "") if isinstance(exp, dict) else (exp.duration or "")
        duration = duration or ""
        # Durée explicite extraite depuis raw_text (ex: "(3 months)" dans le CV)
        explicit_months = exp.get("_explicit_months") if isinstance(exp, dict) else None
        sy, sm, ey, em = extract_period_from_duration(duration)
        if sy is None:
            if log_details:
                logger.warning(f"  Dates non detectees : '{duration}'")
            continue
        start_abs = sy * 12 + sm
        end_abs   = ey * 12 + em
        if explicit_months:
            # Utiliser la durée explicite du CV — recalculer end_abs
            end_abs = start_abs + explicit_months
        if end_abs <= start_abs:
            if log_details:
                logger.warning(f"  Duree nulle/negative ignoree : '{duration}'")
            continue
        intervals.append((start_abs, end_abs, sm, sy, em, ey))
        if log_details:
            months_raw = end_abs - start_abs
            src = f" (explicit)" if explicit_months else ""
            logger.info(f"  {sm}/{sy} → {em}/{ey} = {months_raw} mois{src}")

    if not intervals:
        return 0

    # ── Étape 2 : fusionner les chevauchements ────────────────────────
    intervals_sorted = sorted(intervals, key=lambda x: x[0])
    merged = [(intervals_sorted[0][0], intervals_sorted[0][1])]
    nb_overlaps = 0
    for start, end, *_ in intervals_sorted[1:]:
        last_start, last_end = merged[-1]
        if start < last_end:          # chevauchement détecté
            nb_overlaps += 1
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))

    if nb_overlaps and log_details:
        logger.info(f"  {nb_overlaps} chevauchement(s) détecté(s) — double-comptage corrigé")

    total = sum(end - start for start, end in merged)
    return total


def calculate_years_experience(experience_list: list) -> int:
    return max(math.floor(calculate_total_months(experience_list) / 12), 0)


# ─────────────────────────────────────────
# CLASSIFICATION HYBRIDE — Système expert
#
# Architecture :
#   PRIORITÉ 1 — Mots-clés explicites (certitude 0.95)
#   PRIORITÉ 2 — Score pondéré multi-critères
#   PRIORITÉ 3 — Fallback → professional_experience
#
# Système expert hybride : Rules + LLM + Weighted Scoring
# ─────────────────────────────────────────

INTERNSHIP_EXPLICIT = [
    "stage", "stagiaire", "intern", "internship",
    "pfe", "pfa", "stage de fin", "projet de fin"
]

ALTERNANCE_EXPLICIT = [
    "alternance", "alternant", "apprentissage",
    "apprenti", "contrat d'apprentissage", "work-study"
]

INTERNSHIP_WEIGHTED = [
    ("stage", 0.70),     ("stagiaire", 0.70),  ("intern", 0.70),
    ("pfe", 0.70),       ("pfa", 0.70),
    ("junior", 0.10),    ("débutant", 0.10),   ("debutant", 0.10),
    ("assistant", 0.20), ("étudiant", 0.15),   ("etudiant", 0.15),
]

PROFESSIONAL_SIGNALS = [
    ("cdi", -0.50),   ("cdd", -0.40),   ("freelance", -0.50),
    ("senior", -0.30),("lead", -0.30),  ("manager", -0.30),
    ("consultant", -0.20), ("architect", -0.30), ("ingenieur", -0.10),
]


def get_education_years(education_list: list) -> tuple[int, int]:
    start_years, end_years = [], []
    for edu in education_list:
        try:
            if edu.get("start_year"):
                start_years.append(int(edu["start_year"]))
            ey = edu.get("end_year")
            if ey and str(ey).isdigit():
                end_years.append(int(ey))
        except (ValueError, TypeError):
            continue
    return (
        min(start_years) if start_years else 0,
        max(end_years)   if end_years   else CURRENT_YEAR
    )


def classify_experience_weighted(
    exp: dict,
    education_list: list
) -> tuple[str, float]:
    """
    Classifie avec score de confiance.
    FIX Bug 2 : calcule la duree en interne via extract_period_from_duration()
    directement — ne passe PAS par calculate_total_months() pour eviter
    le double-log lors du calcul final.
    """
    role         = (exp.get("role") or "").lower()
    duration_str = (exp.get("duration") or "").lower()
    combined     = role + " " + duration_str

    # ── P1 : mots-clés explicites ──────────────────────────────
    for kw in INTERNSHIP_EXPLICIT:
        if kw in combined:
            logger.info(f"  → STAGE  [P1 conf=0.95] '{kw}' : '{exp.get('role')}'")
            return "internships", 0.95

    for kw in ALTERNANCE_EXPLICIT:
        if kw in combined:
            logger.info(f"  → ALTERN [P1 conf=0.95] '{kw}' : '{exp.get('role')}'")
            return "alternance", 0.95

    # ── P2 : scoring pondéré ────────────────────────────────────
    internship_score = 0.0

    # Signal A : mots-clés ponderes
    for kw, weight in INTERNSHIP_WEIGHTED:
        if kw in combined:
            internship_score += weight

    # Signal B : duree courte — calcul DIRECT (pas de log ici, Bug 2 fix)
    sy, sm, ey, em = extract_period_from_duration(exp.get("duration", ""))
    duration_months = 0
    if sy is not None:
        duration_months = max((ey - sy) * 12 + (em - sm), 0)
        if duration_months <= 6:
            internship_score += 0.30
        elif duration_months <= 12:
            internship_score += 0.10

    # Signal C : pendant les etudes
    edu_start, edu_end = get_education_years(education_list)
    if sy is not None and edu_start <= sy <= edu_end:
        internship_score += 0.30

    # Signaux negatifs
    for kw, penalty in PROFESSIONAL_SIGNALS:
        if kw in combined:
            internship_score += penalty

    internship_score = max(internship_score, 0.0)

    if internship_score >= 0.50:
        confidence = min(0.50 + internship_score * 0.30, 0.92)
        logger.info(
            f"  → STAGE  [P2 conf={confidence:.2f} score={internship_score:.2f}] : '{exp.get('role')}'"
        )
        return "internships", round(confidence, 2)

    # ── P3 : fallback professionnel ─────────────────────────────
    fallback_confidence = 0.60
    if duration_months > 12:
        fallback_confidence = min(fallback_confidence + 0.15, 0.85)
    for kw, penalty in PROFESSIONAL_SIGNALS:
        if kw in combined and abs(penalty) > 0.2:
            fallback_confidence = min(fallback_confidence + 0.10, 0.90)

    logger.info(f"  → PRO    [P3 conf={fallback_confidence:.2f}] : '{exp.get('role')}'")
    return "professional_experience", round(fallback_confidence, 2)


def make_exp_hash(exp: dict) -> str:
    return "|".join([
        (exp.get("role")     or "").strip().lower(),
        (exp.get("company")  or "").strip().lower(),
        (exp.get("duration") or "").strip().lower(),
    ])


def reclassify_experiences(parsed: dict) -> tuple[dict, float]:
    """Reclassifie + deduplique. Retourne (parsed, confidence_globale)."""
    education_list = parsed.get("education", [])

    all_raw = []
    for key in ["experience", "professional_experience", "internships", "alternance"]:
        all_raw.extend(parsed.get(key) or [])

    parsed["professional_experience"] = []
    parsed["internships"]             = []
    parsed["alternance"]              = []

    seen_hashes = set()
    confidences = []

    for exp in all_raw:
        exp_dict = exp if isinstance(exp, dict) else exp.model_dump()
        h = make_exp_hash(exp_dict)

        if h in seen_hashes:
            logger.warning(
                f"  Doublon ignore : '{exp_dict.get('role')}' @ '{exp_dict.get('company')}'"
            )
            continue

        seen_hashes.add(h)
        category, confidence = classify_experience_weighted(exp_dict, education_list)
        exp_dict["_confidence"] = confidence
        parsed[category].append(exp_dict)
        confidences.append(confidence)

    parsed.pop("experience", None)

    global_confidence = round(sum(confidences) / len(confidences), 2) if confidences else 0.0
    logger.info(f"Confiance globale classification : {global_confidence:.2f}")

    for key in ["professional_experience", "internships", "alternance"]:
        for entry in parsed.get(key, []):
            entry.pop("_confidence", None)

    return parsed, global_confidence


# ─────────────────────────────────────────
# CORRECTION END_YEAR EDUCATION
# ─────────────────────────────────────────

def fix_education_end_years(education_list: list) -> list:
    """
    Corrige les dates de formation incohérentes après parsing LLM/OCR.
    1. end_year manquant            → CURRENT_YEAR
    2. end_year < start_year        → inverser
    3. end_year > CURRENT_YEAR + 1  → CURRENT_YEAR
    4. institution = "N/A" ou vide  → None (nettoyé)
    """
    _NA_VALUES = {"n/a", "na", "none", "null", "-", "—", "n.a.", "unknown", "inconnu"}
    for edu in education_list:
        # Fix 4 — institution N/A → None
        inst = (edu.get("institution") or "").strip()
        if inst.lower() in _NA_VALUES:
            edu["institution"] = None
            logger.info(f"  Education institution N/A nettoyée : {edu.get('degree')}")
        start = edu.get("start_year")
        end   = edu.get("end_year")
        if end is None and start is not None:
            edu["end_year"] = str(CURRENT_YEAR)
            logger.info(f"  Education end_year manquant → {CURRENT_YEAR} : {edu.get('degree')}")
            continue
        try:
            start_int = int(start) if start else None
            end_int   = int(end)   if end   else None
        except (ValueError, TypeError):
            continue
        if start_int is None or end_int is None:
            continue
        if end_int < start_int:
            edu["start_year"] = str(end_int)
            edu["end_year"]   = str(start_int)
            logger.info(f"  Education dates inversées : {end_int}-{start_int} → {start_int}-{end_int} : {edu.get('degree')}")
        elif end_int > CURRENT_YEAR + 5:
            edu["end_year"] = str(CURRENT_YEAR)
            logger.info(f"  Education end_year aberrant : {end_int} → {CURRENT_YEAR} : {edu.get('degree')}")
    return education_list


def fix_education_dates_ocr_collision(
    education_list: list,
    pro_exp_list: list,
    raw_text: str = ""
) -> list:
    """
    Corrige les dates de formation "volées" depuis la colonne EXPÉRIENCE (CVs 2 colonnes scannés).
    Stratégie : extraire toutes les paires d'années du texte OCR brut,
    identifier celles des expériences, attribuer les paires libres aux formations en collision.
    """
    if not education_list or not pro_exp_list:
        return education_list

    pro_year_pairs = set()
    pro_years_all  = set()
    for exp in pro_exp_list:
        duration = exp.get("duration") or ""
        years = re.findall(r'\b(20\d{2}|19\d{2})\b', duration)
        if len(years) >= 2:
            pro_year_pairs.add((int(years[0]), int(years[-1])))
        for y in years:
            pro_years_all.add(int(y))

    first_pro_year = min(pro_years_all) if pro_years_all else CURRENT_YEAR

    # Extraire toutes les paires d'années du texte OCR brut
    raw_pairs: list[tuple[int, int]] = []
    if raw_text:
        for m in re.finditer(r'\b(20\d{2}|19\d{2})\b\s*[-–—]\s*\b(20\d{2}|19\d{2})\b', raw_text):
            y1, y2 = int(m.group(1)), int(m.group(2))
            raw_pairs.append((min(y1, y2), max(y1, y2)))

    # Paires libres = présentes dans OCR, non utilisées par l'expérience pro, durée ≤ 6 ans
    free_pairs = sorted(
        {(y1, y2) for (y1, y2) in raw_pairs
         if (y1, y2) not in pro_year_pairs
         and y2 <= first_pro_year + 2
         and (y2 - y1) <= 6},
        key=lambda p: -p[1]  # plus récentes en premier
    )

    assigned: set[tuple[int, int]] = set()
    for edu in education_list:
        try:
            sy = int(edu.get("start_year") or 0)
            ey = int(edu.get("end_year")   or 0)
        except (ValueError, TypeError):
            continue
        if (sy, ey) not in pro_year_pairs:
            assigned.add((sy, ey))

    for edu in education_list:
        try:
            sy = int(edu.get("start_year") or 0)
            ey = int(edu.get("end_year")   or 0)
        except (ValueError, TypeError):
            continue
        if (sy, ey) not in pro_year_pairs:
            continue
        logger.warning(f"  Collision OCR : '{edu.get('degree')}' a les dates {sy}-{ey} d'une expérience pro")
        best = next((p for p in free_pairs if p not in assigned and p != (sy, ey)), None)
        if best:
            edu["start_year"] = str(best[0])
            edu["end_year"]   = str(best[1])
            assigned.add(best)
            logger.info(f"  Correction OCR : {sy}-{ey} → {best[0]}-{best[1]} : {edu.get('degree')}")
        else:
            logger.warning(f"  Aucune paire libre pour '{edu.get('degree')}'")

    return education_list


# ─────────────────────────────────────────
# CALCUL SCORE QUALITE CV
#
# FIX Bug 3 : bonus profil etudiant avance
#   Un etudiant avec 3 diplomes + certifs + stages
#   ne doit pas etre penalise par l'absence de CDI.
#   → Si years_professional = 0 mais stages >= 4 mois
#     et diplomes >= 2 → bonus compensatoire
# ─────────────────────────────────────────

def count_quantified_achievements(experience_list: list) -> int:
    count   = 0
    pattern = re.compile(
        r"\d+\s*(%|modele|model|algorithme|algorithm|projet|project|an|year|fois|time|k€|€|\$)"
    )
    for exp in experience_list:
        achievements = exp.get("achievements") or [] if isinstance(exp, dict) else []
        for a in achievements:
            if pattern.search(a.lower()):
                count += 1
    return count


def calculate_cv_quality_score(data: dict) -> float:
    score = 0.0

    skills = data.get("skills") or {}
    if isinstance(skills, dict):
        technical  = skills.get("technical") or []
        soft       = skills.get("soft_skills") or []
        tools      = skills.get("tools") or []
        all_skills = technical + soft + tools
    else:
        technical, soft, tools, all_skills = [], [], [], []

    # ── Competences (20%) ────────────────────────────────────────
    if len(all_skills) >= 8:    score += 0.20
    elif len(all_skills) >= 5:  score += 0.12
    elif len(all_skills) >= 2:  score += 0.07
    # Bonus : profil expérimenté qui liste peu de skills (CV minimaliste)
    # Ne pas trop pénaliser les seniors qui décrivent leurs compétences en prose
    elif len(all_skills) == 0 and (data.get("years_professional", 0) or 0) >= 5:
        score += 0.05

    # ── Diversite technique (5%) ─────────────────────────────────
    if len(technical) > 0 and len(tools) > 0 and len(soft) > 0:
        score += 0.05

    # ── Bonus stack technique riche (5%) ────────────────────────
    if len(technical) >= 15:   score += 0.05
    elif len(technical) >= 10: score += 0.03

    # ── Experience pro en annees (20%) ───────────────────────
    yp = data.get("years_professional", 0) or 0
    if yp >= 10:   score += 0.20   # profil senior
    elif yp >= 5:  score += 0.16   # profil confirmé
    elif yp >= 3:  score += 0.12
    elif yp >= 1:  score += 0.08

    # ── Stages + Alternance (10%) ────────────────────────────────
    stage_m = data.get("months_internships", 0) or 0
    alt_m   = data.get("months_alternance", 0) or 0
    if stage_m + alt_m >= 6:    score += 0.10
    elif stage_m + alt_m >= 3:  score += 0.06
    elif stage_m + alt_m >= 1:  score += 0.03

    # ── FIX Bug 3 : Bonus profil etudiant avance (5%) ────────────
    # Un profil etudiant avec bonne formation + stages + certifs
    # merite un bonus meme sans CDI.
    education = data.get("education") or []
    certifications = data.get("certifications") or []
    if yp == 0 and (stage_m + alt_m) >= 3 and len(education) >= 2:
        score += 0.05
        logger.info("  Bonus profil etudiant avance : +0.05")

    # ── Formation (15%) ──────────────────────────────────────────
    if len(education) >= 3:    score += 0.15
    elif len(education) >= 2:  score += 0.12
    elif len(education) == 1:  score += 0.07

    # ── Nombre entrees experience (10%) ─────────────────────────
    all_exp = (
        (data.get("professional_experience") or []) +
        (data.get("internships") or []) +
        (data.get("alternance") or [])
    )
    if len(all_exp) >= 3:   score += 0.10
    elif len(all_exp) >= 1: score += 0.05

    # ── Achievements quantifies (8%) ────────────────────────────
    nb_q = count_quantified_achievements(all_exp)
    if nb_q >= 3:   score += 0.08
    elif nb_q >= 1: score += 0.04

    # ── Certifications (10%) ────────────────────────────────────
    cert_score = min(len(certifications) * 0.04, 0.10)
    score += cert_score

    # ── Completude profil (4%) ───────────────────────────────────
    if data.get("full_name"): score += 0.02
    if data.get("email"):     score += 0.01
    if data.get("phone"):     score += 0.01

    return round(min(score, 1.0), 2)


# ─────────────────────────────────────────
# EXTRACTION TEXTE PDF + OCR FALLBACK
#
# Responsabilite de ce module :
#   → Toujours recevoir un .pdf (garanti par applications.py)
#   → PDF normal    : pdfplumber (texte natif, rapide)
#   → PDF scanne    : OCR automatique page par page
#                     via pdf2image (Poppler) + Tesseract
#   → PDF corrompu  : erreur claire pour le candidat
#
# Tesseract langues : francais + anglais + arabe (RTL)
# DPI OCR : 300 (qualite optimale pour CV)
# ─────────────────────────────────────────

# Langues Tesseract — FR + EN + Arabe
TESSERACT_LANGS = "fra+eng"

# Seuil : si une page a moins de X chars → consideree scannee
MIN_NATIVE_CHARS = 30


def _ocr_page(pdf_path: str, page_num: int) -> str:
    """
    OCR page scannee — strategie split colonnes.

    Probleme : PSM11 sur la page entiere entrelace les 2 colonnes
    ligne par ligne, melange Formation et Experience, lit la photo
    comme du texte arabe. Solution : decouper l image en zones.

    Zones :
      En-tete  (0-22% hauteur)   : PSM11 fr+en -> email, tel, nom
      Col. gauche (0-47% largeur): PSM6        -> Formation, Competences, Langues
      Col. droite (47-100% larg) : PSM6        -> Experience professionnelle
    """
    try:
        from pdf2image import convert_from_path
        images = convert_from_path(
            pdf_path,
            first_page=page_num,
            last_page=page_num,
            dpi=300,
            poppler_path=POPPLER_PATH
        )
        if not images:
            return ""

        img = images[0]
        w, h = img.size

        img = img.convert("L")
        img = ImageEnhance.Contrast(img).enhance(1.5)
        img = img.filter(ImageFilter.SHARPEN)

        # ── En-tete : PSM11 fr+en uniquement (pas ara -> evite lecture photo) ──
        HEADER_H  = int(h * 0.22)
        BODY_TOP  = HEADER_H
        COL_SPLIT = int(w * 0.40)   # 47% evite de couper la 1ere lettre des noms

        img_header = img.crop((0, 0, w, HEADER_H))
        raw_header = pytesseract.image_to_string(
            img_header, config="--psm 11 -l fra+eng"
        )
        header_lines = [l.strip() for l in raw_header.splitlines() if l.strip()]

        # Email + telephone depuis en-tete
        email_val, phone_val = "", ""
        for line in header_lines:
            if not email_val:
                m = re.search(r'[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}', line)
                if m:
                    email_val = m.group(0)
            if not phone_val:
                m = re.search(r'[\+\d][\d\s\-\(\)]{7,}', line)
                if m:
                    cand = m.group(0).strip()
                    if len(re.sub(r'\D', '', cand)) >= 8:
                        phone_val = cand

        # Fallback : PSM11 sur toute la page si email/tel manquants
        if not email_val or not phone_val:
            raw_full = pytesseract.image_to_string(img, config="--psm 11 -l fra+eng")
            for line in raw_full.splitlines():
                line = line.strip()
                if not email_val:
                    m = re.search(r'[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}', line)
                    if m: email_val = m.group(0)
                if not phone_val:
                    m = re.search(r'[\+\d][\d\s\-\(\)]{7,}', line)
                    if m:
                        cand = m.group(0).strip()
                        if len(re.sub(r'\D', '', cand)) >= 8:
                            phone_val = cand

        # Nom depuis en-tete : lignes MAJUSCULES consecutives
        SECTION_KEYWORDS = {
            "PROFIL", "FORMATION", "EXPERIENCE", "EXPÉRIENCE",
            "COMPETENCES", "COMPÉTENCES", "LANGUES", "EXPERTISE",
            "REFERENCES", "RÉFÉRENCE", "CONTACT", "CERTIFICATIONS"
        }
        JOB_WORDS = {
            "EXPERT", "COMPTABLE", "DIRECTEUR", "MANAGER",
            "INGENIEUR", "INGÉNIEUR", "ANALYSTE", "CONSULTANT",
            "DEVELOPPEUR", "DÉVELOPPEUR", "CHEF", "RESPONSABLE"
        }

        def is_name_line(s: str) -> bool:
            if len(s) < 2 or len(s) > 40:            return False
            if sum(c.isalpha() for c in s) / max(len(s), 1) < 0.70: return False
            if any(c in s for c in "@0123456789+/\\|"): return False
            if s in SECTION_KEYWORDS or s in JOB_WORDS:  return False
            return s == s.upper()

        # Collecte toutes les lignes-nom dans les 25 premieres lignes de l en-tete
        # Tolerant aux artefacts courts (C, », ~~) entre DOMINIQUE et MARCHET
        name_parts = []
        for line in header_lines[:25]:
            if line in SECTION_KEYWORDS:
                break
            if is_name_line(line):
                name_parts.append(line)
                if len(name_parts) >= 3:
                    break
        # Max 2 parties : prenom + nom (evite "DOMINIQUE MARCHET EXPERT COMPTABLE")
        name_val = " ".join(name_parts[:2])

        if email_val:  logger.info(f"  PSM11 -> email : {email_val}")
        if phone_val:  logger.info(f"  PSM11 -> tel   : {phone_val}")
        if name_val:   logger.info(f"  PSM11 -> nom   : {name_val}")
        else:          logger.warning("  PSM11 -> nom non detecte (LLM extraira)")

        # ── Corps : split gauche / droite ──────────────────────────────────────
        img_left  = img.crop((0,         BODY_TOP, COL_SPLIT, h))
        img_right = img.crop((COL_SPLIT, BODY_TOP, w,         h))

        cfg6 = f"--psm 6 -l {TESSERACT_LANGS}"
        text_left  = pytesseract.image_to_string(img_left,  config=cfg6)
        text_right = pytesseract.image_to_string(img_right, config=cfg6)

        # ── Assemblage : contacts + col. gauche + col. droite ─────────────────
        contact_lines = []
        if name_val:   contact_lines.append(f"Nom: {name_val}")
        if email_val:  contact_lines.append(f"Email: {email_val}")
        if phone_val:  contact_lines.append(f"Tel: {phone_val}")

        parts = [p for p in [
            "\n".join(contact_lines),
            text_left.strip(),
            text_right.strip(),
        ] if p]
        text = "\n\n".join(parts)

        nb_char = len(text.strip())
        if nb_char:
            logger.info(f"  OCR page {page_num} : {nb_char} chars extraits (split-col)")
        else:
            logger.warning(f"  OCR page {page_num} : aucun texte detecte")
        return text

    except ImportError:
        logger.error("pdf2image non installe -- pip install pdf2image")
        return ""
    except Exception as e:
        logger.warning(f"  OCR page {page_num} echoue : {e}")
        return ""

def _detect_column_split(page) -> float | None:
    """
    Détecte automatiquement le point de séparation entre 2 colonnes
    en cherchant le plus grand gap horizontal entre les mots.
    Retourne la position x du split, ou None si pas de 2 colonnes détectées.
    """
    try:
        words = page.extract_words()
        if len(words) < 10:
            return None
        x0_page, _, x1_page, _ = page.bbox
        width = x1_page - x0_page

        # Collecter toutes les positions X gauche des mots
        x_lefts = sorted(set(round(w['x0'] - x0_page) for w in words))
        if len(x_lefts) < 4:
            return None

        # Trouver le plus grand gap entre positions X consécutives
        # dans la zone centrale de la page (20%-80%)
        zone_min = width * 0.15
        zone_max = width * 0.80
        best_gap, best_x = 0, None
        for i in range(len(x_lefts) - 1):
            if zone_min <= x_lefts[i] <= zone_max:
                gap = x_lefts[i+1] - x_lefts[i]
                if gap > best_gap:
                    best_gap = gap
                    best_x = x0_page + (x_lefts[i] + x_lefts[i+1]) / 2

        # Gap significatif = au moins 15% de la largeur de page (seuil relevé de 8% → 15%)
        if best_gap >= width * 0.15 and best_x is not None:
            # Vérification supplémentaire : au moins 18% des mots doivent être à droite du split
            # Évite les faux positifs sur CVs 1 colonne avec quelques mots débordants
            words_right = sum(1 for w in words if w['x0'] > best_x)
            ratio_right = words_right / len(words) if words else 0
            if ratio_right >= 0.18:
                return best_x
    except Exception:
        pass
    return None


def _extract_native_page(page) -> str:
    """
    Extrait le texte natif d'une page pdfplumber.
    Détecte automatiquement les PDFs 2 colonnes (texte entrelacé)
    et utilise within_bbox pour séparer les colonnes proprement.

    Détection de texte doublé : si >30% des lignes non-vides ont
    chaque caractère répété 2x (AAlliixx) → PDF double couche.
    Dans ce cas on crop gauche/droite pour éviter l'entrelacement.
    """
    full_text = page.extract_text() or ""
    if not full_text.strip():
        return ""

    # ── Détecter PDF double couche ────────────────────────────────────
    lines = [l for l in full_text.splitlines() if l.strip()]
    doubled = 0
    for line in lines[:15]:
        sample = re.sub(r'\s', '', line)
        if len(sample) >= 6:
            pairs = sum(1 for i in range(0, min(len(sample)-1, 10), 2)
                       if sample[i] == sample[i+1])
            if pairs >= 3:
                doubled += 1

    if doubled >= 2:
        # PDF 2 colonnes avec double couche texte → split via bbox
        x0, y0, x1, y1 = page.bbox
        split_x = x0 + (x1 - x0) * 0.35
        try:
            left_text  = page.within_bbox((x0, y0, split_x, y1)).extract_text() or ""
            right_text = page.within_bbox((split_x, y0, x1, y1)).extract_text() or ""
            logger.info("  Détection PDF 2 colonnes double couche → split bbox")
            return left_text + "\n" + right_text
        except Exception:
            pass  # fallback sur texte plein

    # ── Détecter 2 colonnes normales par gap horizontal ──────────────
    split_x = _detect_column_split(page)
    if split_x is not None:
        x0, y0, x1, y1 = page.bbox
        try:
            left_text  = page.within_bbox((x0, y0, split_x, y1)).extract_text() or ""
            right_text = page.within_bbox((split_x, y0, x1, y1)).extract_text() or ""
            right_lines = [l.strip() for l in right_text.splitlines() if l.strip()]
            if right_lines and len(right_lines) > 3:
                logger.info(f"  Détection 2 colonnes → split à x={split_x:.0f}")
                # Si la colonne gauche est une sidebar (stack/compétences/méthodes)
                # → ne garder QUE la colonne droite pour éviter le mélange
                LEFT_SIDEBAR_KEYWORDS = {
                    "stack technique", "stack", "méthodes", "methods",
                    "back-end", "front-end", "devops", "outils", "tools",
                    "compétences", "skills", "certifications", "langues"
                }
                left_lower = left_text.lower()
                left_header_lines = [l.strip().lower() for l in left_text.splitlines()[:6] if l.strip()]
                is_sidebar = sum(
                    1 for kw in LEFT_SIDEBAR_KEYWORDS
                    if any(kw in line for line in left_header_lines)
                ) >= 2
                if is_sidebar:
                    # Sidebar : passer gauche EN PREMIER (skills) puis droite (expériences)
                    # Séparateur clair pour que le LLM comprenne la structure
                    logger.info("  Colonne gauche = sidebar → gauche (skills) + droite (exp)")
                    return left_text + "\n--- EXPÉRIENCES SUITE ---\n" + right_text
                return left_text + "\n" + right_text
        except Exception:
            pass

    return full_text


def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Extraction PDF avec OCR automatique sur les pages scannees.

    Algorithme page par page :
      1. pdfplumber → texte natif
      2. Si texte < MIN_NATIVE_CHARS → page scannee → OCR Tesseract
      3. Si tout le PDF est vide apres OCR → erreur claire

    Ce module ne gere que du .pdf.
    PNG/JPG : rejetes par applications.py (HTTP 422)
    DOCX    : converti en PDF par applications.py avant d'arriver ici
    """
    pdf_path = pdf_path.strip()
    if not pdf_path.lower().endswith(".pdf"):
        raise ValueError(
            "Le parser n'accepte que des fichiers PDF. "
            "PNG/JPG sont rejetes au niveau upload. "
            "DOCX est converti en PDF par l'API avant parsing."
        )

    size_mb = os.path.getsize(pdf_path) / (1024 * 1024)
    if size_mb > MAX_PDF_SIZE_MB:
        raise ValueError(f"PDF trop grand : {size_mb:.1f}MB (max {MAX_PDF_SIZE_MB}MB)")

    logger.info(f"Extraction PDF : {pdf_path} ({size_mb:.2f}MB)")
    text      = ""
    ocr_pages = 0

    try:
        with pdfplumber.open(pdf_path) as pdf:
            nb_pages = len(pdf.pages)
            logger.info(f"PDF ouvert : {nb_pages} page(s)")

            for i, page in enumerate(pdf.pages):
                native = _extract_native_page(page)

                # Marqueur de page pour aider le LLM à situer les blocs
                page_marker = f"\n--- PAGE {i+1} ---\n" if nb_pages > 1 else ""

                if len(native.strip()) >= MIN_NATIVE_CHARS:
                    # Texte natif suffisant
                    text += page_marker + native + "\n"
                    logger.info(f"  Page {i+1} : texte natif ({len(native.strip())} chars)")
                else:
                    # Page scannee → OCR automatique
                    logger.info(f"  Page {i+1} : scannee → OCR...")
                    ocr_text = _ocr_page(pdf_path, page_num=i + 1)
                    if ocr_text.strip():
                        text += page_marker + ocr_text + "\n"
                        ocr_pages += 1
                    else:
                        logger.warning(f"  Page {i+1} : non recuperee")

    except Exception as e:
        logger.error(f"Erreur lecture PDF : {e}")
        raise ValueError(f"Impossible d'ouvrir le PDF : {e}")

    if ocr_pages:
        logger.info(f"OCR Tesseract applique sur {ocr_pages} page(s) scannee(s)")

    if not text.strip():
        raise ValueError(
            "CV illisible : aucun texte extractible dans ce PDF. \n"
            "Causes possibles : PDF protege, corrompu, ou image sans texte. \n"
            "Conseil : verifiez que le texte est selectionnable dans votre PDF."
        )

    cleaned = clean_text(text)

    # Supprimer les en-têtes de continuation de page (ex : "Sophie Laurent — suite")
    # avant d'envoyer au LLM pour éviter les faux blocs d'expérience
    cleaned = strip_continuation_headers(cleaned)
    logger.info(f"Texte final : {len(cleaned)} caracteres")

    if len(cleaned) > MAX_TEXT_CHARS:
        cleaned = smart_truncate(cleaned, MAX_TEXT_CHARS)

    # On retourne aussi le texte brut (avant nettoyage) pour le fallback email.
    # Normalise les codes (cid:N) en • pour que _fill_continuation_achievements
    # et _fix_alternance_from_raw_text puissent parser les bullets correctement.
    raw_normalized = re.sub(r'\(cid:\d+\)', '•', text)
    return cleaned, raw_normalized


# ─────────────────────────────────────────
# NETTOYAGE CONTACT — Post-parsing
# ─────────────────────────────────────────

def sanitize_contact_fields(data: dict, raw_text: str = "") -> dict:
    """
    Nettoie email et téléphone après parsing LLM.
    Nécessaire pour les CVs scannés où l'OCR génère des artefacts
    autour des icônes (✉ → 'ER C', 📞 → 'C', etc.)

    Email   : extrait uniquement la partie valide (contient @ et domaine)
              Fallback : recherche regex directement dans raw_text si LLM a raté
    Téléphone : garde uniquement chiffres, +, -, espaces, ()
                minimum 8 chiffres pour être valide
    """
    # ── Email ──────────────────────────────────────────────────────────
    email = data.get("email") or ""
    email_match = re.search(r'[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}', email)
    data["email"] = email_match.group(0) if email_match else None
    if email and not data["email"]:
        logger.warning(f"Email invalide ignoré : '{email}'")

    # ── Fallback : regex sur raw_text si le LLM a raté l'email ────────
    # Cas typique : CV scanné avec icônes → OCR fusionne les champs →
    # le LLM reçoit "ER C +123-456-7890" au lieu de "hello@example.com"
    if not data["email"] and raw_text:
        fallback = re.search(r'[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}', raw_text)
        if fallback:
            data["email"] = fallback.group(0)
            logger.info(f"Email récupéré via fallback regex : '{data['email']}'")

    # ── Téléphone ──────────────────────────────────────────────────────
    phone = data.get("phone") or ""

    # Étape 1 : extraire le premier pattern téléphone valide depuis la valeur LLM
    phone_match = re.search(
        r'[\+\d][\d\s\.\-\(\)/]{6,}',   # au moins 6 chars après le début
        phone
    )
    phone = phone_match.group(0).strip() if phone_match else ""

    # Étape 2 : normalisation
    # "+33 (0) 6 12 34" → "+33 6 12 34" (supprimer le (0) français)
    phone = re.sub(r'\(\s*0\s*\)', '', phone).strip()
    # "06.12.34.56.78" → "06 12 34 56 78" (points → espaces)
    phone = phone.replace('.', ' ')
    # Espaces multiples → simple
    phone = re.sub(r'\s{2,}', ' ', phone).strip()
    # Garder uniquement : chiffres, +, -, espaces, ()
    phone_clean = re.sub(r'[^\d\+\-\s\(\)]', '', phone).strip()

    digits_only = re.sub(r'\D', '', phone_clean)
    if 8 <= len(digits_only) <= 15:
        data["phone"] = phone_clean
    else:
        if data.get("phone"):
            logger.warning(f"Téléphone invalide ignoré : '{data.get('phone')}'")
        data["phone"] = None

    # Étape 3 : fallback regex sur raw_text si LLM a raté le tel
    if not data["phone"] and raw_text:
        # Pattern international large : +XX XXX XXX XXX ou 0X XX XX XX XX
        tel_fallback = re.search(
            r'(?<!\d)'                           # pas précédé d'un chiffre
            r'(\+\d{1,3}[\s\-\.]?\(?\d{1,4}\)?'  # préfixe international
            r'[\s\-\.]?\d{2,4}'
            r'(?:[\s\-\.]\d{2,4}){1,4})'         # groupes de chiffres
            r'(?!\d)',                             # pas suivi d'un chiffre
            raw_text
        )
        if tel_fallback:
            cand = tel_fallback.group(0).strip()
            digits_cand = re.sub(r'\D', '', cand)
            if 8 <= len(digits_cand) <= 15:
                data["phone"] = cand
                logger.info(f"Téléphone récupéré via fallback regex : '{cand}'")

    return data


# ─────────────────────────────────────────
# MULTI-PAGES — Nettoyage et fusion
# ─────────────────────────────────────────

# Patterns des en-têtes de continuation (page 2, 3...)
# Ex : "Sophie Laurent — suite", "— 2 / 3 —", "Resume (continued)"
_CONTINUATION_PATTERNS = [
    # "Prénom Nom — suite" ou "Prénom Nom (suite)"
    re.compile(r'^.{2,50}\s*[—\-–]\s*(suite|continued?|suite\s*\.\.\.|cont\.?)\s*$',
               re.IGNORECASE | re.MULTILINE),
    # Titres de poste seuls répétés en haut de page : "UX Designer Senior — suite"
    re.compile(r'^.{5,80}\s*[—\-–]\s*suite\s*$', re.IGNORECASE | re.MULTILINE),
    # Numéros de page déjà filtrés par MARKETING_PATTERNS mais variante FR
    re.compile(r'^[—\-–]+\s*\d+\s*/\s*\d+\s*[—\-–]+\s*$', re.MULTILINE),
    # "Page 2 sur 3" / "Page 2/3"
    re.compile(r'^Page\s+\d+\s*(sur|of|/)\s*\d+\s*$', re.IGNORECASE | re.MULTILINE),
    # En-tête répétitif : nom seul sur une ligne au début d'une page
    # (détecté uniquement si précédé du marqueur --- PAGE N ---)
    re.compile(r'(?<=--- PAGE \d ---\n)[^\n]{3,60}\n(?=\n)', re.IGNORECASE),
]


def strip_continuation_headers(text: str, candidate_name: str = "") -> str:
    """
    Supprime les en-têtes de continuation de page qui polluent le texte LLM.

    Ces en-têtes (ex : "Sophie Laurent — suite", "— 2/3 —") n'apportent
    aucune info au LLM mais peuvent le faire croire à un nouveau bloc
    d'expérience ou casser la lecture d'un bloc commencé en page précédente.

    Si candidate_name fourni, supprime aussi les lignes contenant uniquement
    ce nom (répétition de l'en-tête du CV en haut de chaque page).
    """
    for pattern in _CONTINUATION_PATTERNS:
        text = pattern.sub("", text)

    # Supprimer la répétition du nom seul en tête de page suivante
    if candidate_name and len(candidate_name.split()) >= 2:
        # Échappe le nom pour regex, tolère majuscules/minuscules
        escaped = re.escape(candidate_name.strip())
        text = re.sub(
            r'(?m)^' + escaped + r'\s*$\n?',
            '',
            text,
            flags=re.IGNORECASE
        )

    # Nettoyer les lignes vides en excès laissées par les suppressions
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def merge_split_experiences(experiences: list[dict]) -> list[dict]:
    """
    Fusionne les entrées d'expérience dupliquées créées par un saut de page.

    Symptôme : le LLM crée deux entrées pour la même expérience car le bloc
    est coupé par un saut de page — la 2e entrée a le même role+company
    mais des achievements différents (la suite).

    Algorithme :
      • Normalise role + company en clé de déduplication
      • Si deux entrées ont la même clé → fusionne les achievements
        et conserve la duration de la première entrée (plus complète)
    """
    if not experiences:
        return experiences

    def _key(exp: dict) -> str:
        role    = (exp.get("role")    or "").lower().strip()
        company = (exp.get("company") or "").lower().strip()
        # Retire les suffixes communs de continuation dans le titre
        role = re.sub(r'\s*[—\-–]\s*(suite|cont\.?|continued?)$', '', role, flags=re.IGNORECASE)
        return f"{role}|{company}"

    merged: dict[str, dict] = {}
    order: list[str] = []

    for exp in experiences:
        key = _key(exp)
        if key in merged:
            # Fusionner les achievements sans doublons
            existing_ach = merged[key].get("achievements") or []
            new_ach      = exp.get("achievements") or []
            seen_ach     = {a.lower().strip() for a in existing_ach}
            for a in new_ach:
                if a.lower().strip() not in seen_ach:
                    existing_ach.append(a)
                    seen_ach.add(a.lower().strip())
            merged[key]["achievements"] = existing_ach
            logger.info(
                f"  [multi-page] Fusion expérience : '{exp.get('role')}' @ '{exp.get('company')}'"
            )
        else:
            merged[key] = dict(exp)  # copie pour éviter mutation
            order.append(key)

    return [merged[k] for k in order]


def smart_truncate(text: str, max_chars: int = 12000) -> str:
    """
    Troncature intelligente qui préserve les blocs d'expérience complets.

    Au lieu de couper brutalement à max_chars (ce qui peut tronquer un
    bloc d'expérience en plein milieu), cherche le dernier saut de section
    (ligne vide + majuscules) avant la limite et coupe là.

    Ajoute une note "[TEXTE TRONQUÉ — pages suivantes non incluses]" pour
    avertir le LLM qu'il manque potentiellement des données.
    """
    if len(text) <= max_chars:
        return text

    # Chercher la dernière ligne vide dans les 500 derniers chars autorisés
    # pour couper proprement entre deux blocs
    window = text[:max_chars]
    last_blank = window.rfind('\n\n', max_chars - 600, max_chars)
    if last_blank != -1:
        cut = last_blank
    else:
        # Fallback : couper à la dernière newline
        last_nl = window.rfind('\n', max_chars - 200, max_chars)
        cut = last_nl if last_nl != -1 else max_chars

    truncated = text[:cut].rstrip()
    logger.warning(
        f"Texte tronqué intelligemment : {len(text)} → {len(truncated)} chars "
        f"(coupure propre entre blocs)"
    )
    return truncated + "\n\n[TEXTE TRONQUÉ — certaines expériences/sections de fin de CV peuvent manquer]"


# ─────────────────────────────────────────
# APPEL LLM + VALIDATION
# ─────────────────────────────────────────

def detect_cv_language(raw_text: str) -> str:
    """
    Détecte si le CV est principalement en anglais, français ou mixte.
    Retourne 'en', 'fr', ou 'mixed'.
    Utilisé pour sélectionner dynamiquement le prompt LLM adapté.
    """
    text_lower = raw_text.lower()
    fr_signals = ["expérience", "formation", "compétences", "langues",
                  "poste", "entreprise", "diplôme", "stage", "présent"]
    en_signals = ["experience", "education", "skills", "languages",
                  "position", "company", "degree", "internship", "present",
                  "work experience", "summary", "objective"]
    fr_count = sum(1 for kw in fr_signals if kw in text_lower)
    en_count = sum(1 for kw in en_signals if kw in text_lower)
    if en_count > fr_count + 2:   return "en"
    elif fr_count > en_count + 2: return "fr"
    return "mixed"


def parse_cv_with_llm(raw_text: str, raw_ocr_text: str = "") -> dict:

    # ── Détection dynamique de la langue du CV ────────────────────────
    cv_lang = detect_cv_language(raw_ocr_text or raw_text)
    logger.info(f"Langue détectée : {cv_lang}")

    # ── Template JSON universel (FR + EN) ─────────────────────────────
    json_template = f"""
{{
  "full_name": "First Last",
  "email": "email@example.com",
  "phone": "+33600000000",
  "skills": {{
    "technical": ["Skill A", "Skill B"],
    "soft_skills": ["Method A"],
    "tools": ["Tool A", "Tool B"]
  }},
  "education": [
    {{
      "degree": "Degree title",
      "institution": "School name",
      "start_year": "2018",
      "end_year": "{CURRENT_YEAR}"
    }}
  ],
  "professional_experience": [
    {{
      "role": "Job title",
      "company": "Company name",
      "duration": "2021 - 2022",
      "achievements": ["Achievement 1", "Achievement 2"]
    }}
  ],
  "internships": [
    {{
      "role": "Internship title",
      "company": "Company name",
      "duration": "June 2020 - August 2020",
      "achievements": ["Task 1", "Task 2"]
    }}
  ],
  "alternance": [],
  "certifications": [
    {{
      "name": "Certification name",
      "issuer": "Issuing organization",
      "year": "2023"
    }}
  ],
  "projects": [
    {{
      "name": "Project name",
      "description": "Short project description",
      "technologies": ["Python", "FastAPI"],
      "link": "https://github.com/example/project"
    }}
  ],
  "nb_internships": 1,
  "languages": ["French", "English"],
  "years_experience": 1
}}
"""

    # ══════════════════════════════════════════════════════════════════
    # PROMPT FRANÇAIS — CV en français ou mixte
    # ══════════════════════════════════════════════════════════════════
    prompt_fr = (
        "Tu es un expert en analyse de CV. Le CV peut être en français, en anglais ou les deux.\n\n"
        "TEXTE DU CV (peut contenir des marqueurs --- PAGE N --- pour les CV multi-pages) :\n\n"
        + raw_text +
        "\n\nINSTRUCTIONS IMPORTANTES :\n"
        "- Retourne UNIQUEMENT un JSON valide, sans explication ni markdown\n"
        "- Pour les noms de compétences : utilise l'anglais\n"
        "- Pour les intitulés de diplômes et de postes : garde la langue originale du CV\n"
        "- NE JAMAIS écrire de valeurs bilingues comme 'Autonomie / Autonomy' — choisis l'anglais\n"
        "- Pour la durée : copie EXACTEMENT ce qui est écrit dans le CV — ne pas ajouter ni inventer\n"
        "  Si le CV dit 'Juil. 2024' uniquement → écrire 'Juil. 2024' — rien d'autre\n"
        "  Si le CV dit '2021 - Présent' → écrire '2021 - Présent'\n"
        "  NE JAMAIS écrire Présent si le mot n'est pas littéralement dans le texte du CV\n"
        "- NE JAMAIS inventer des expériences — extraire UNIQUEMENT ce qui est dans le texte\n"
        "- Si un champ est manquant, retourner null ou []\n"
        "- NE JAMAIS mettre N/A, None, '-' dans les listes — utiliser [] à la place\n"
        "- soft_skills : UNIQUEMENT les méthodes/frameworks EXPLICITEMENT écrits dans le CV\n"
        "  NE JAMAIS inventer des soft_skills comme 'Agile' si le mot est absent du CV\n"

        "\n=== RÈGLES CV MULTI-PAGES ===\n"
        "- Le texte peut contenir des marqueurs --- PAGE 2 ---, --- PAGE 3 ---\n"
        "- Ce sont des délimiteurs de page, PAS des titres de section\n"
        "- Un bloc d'expérience PEUT s'étaler sur 2 pages — traiter comme UNE SEULE entrée\n"
        "- Un en-tête 'Jean Dupont — suite' en haut de page = EN-TÊTE DE CONTINUATION, l'ignorer\n"
        "- SCANNER TOUTES LES PAGES pour les expériences, compétences, certifications\n"
        "- Si le texte se termine par '[TEXTE TRONQUÉ...]' → extraire ce qui est disponible avant\n"

        "\n=== FORMAT EN-TÊTE OCR ===\n"
        "Le texte peut commencer par des champs pré-extraits :\n"
        "  Email: hello@example.com\n"
        "  Tel: +123-456-7890\n"
        "  Nom: JEAN DUPONT\n"
        "→ Utiliser ces valeurs directement pour full_name, email, phone.\n"

        "\n=== SECTIONS EN ANGLAIS ===\n"
        "Si le CV est en anglais, reconnaître ces titres de sections :\n"
        "  WORK EXPERIENCE / EXPERIENCE                     → professional_experience\n"
        "  EDUCATION / ACADEMIC BACKGROUND / QUALIFICATIONS → education\n"
        "  SKILLS / TECHNICAL SKILLS / CORE COMPETENCIES   → skills\n"
        "  CERTIFICATIONS / LICENSES / CREDENTIALS          → certifications\n"
        "  LANGUAGES / LANGUAGE SKILLS                      → languages\n"
        "  INTERNSHIP / PLACEMENT / TRAINEE / CO-OP         → internships\n"
        "  VOLUNTEERING / VOLUNTEER EXPERIENCE              → IGNORER\n"
        "Diplômes anglais : Bachelor's = Licence, Master's = Master, PhD = Doctorat\n"
        "'Present' / 'Current' / 'Now' en anglais = poste actuel\n"

        "\n=== RÈGLES COMPÉTENCES ===\n"
        "- Extraire depuis DEUX sources :\n"
        "  1. Sections dédiées (COMPÉTENCES, SKILLS, STACK, TECHNOLOGIES, EXPERTISE...)\n"
        "     Ces sections ont souvent des SOUS-CATÉGORIES — extraire TOUTES :\n"
        "     ex: 'Langages: Python, Go' ET 'Frameworks: Django, FastAPI' ET 'Cloud: AWS'\n"
        "     → Python, Go, Django, FastAPI, AWS — TOUTES les sous-catégories, pas seulement la 1ère\n"
        "     Les labels (Langages, Frameworks, Cloud) sont des EN-TÊTES, pas des compétences\n"
        "  2. Lignes 'Technologies :' dans les blocs d'expérience\n"
        "- Extraire sous-compétences entre parenthèses :\n"
        "  'Python (Pandas, NumPy)' → Python + Pandas + NumPy\n"
        "- NE JAMAIS inventer ni déduire depuis les descriptions de postes\n"

        "\n=== CLASSIFICATION DES COMPÉTENCES ===\n"
        "Pour chaque compétence : Peut-on l'ouvrir comme un logiciel standalone ?\n"
        "  OUI → tools     (Docker, Git, Figma, Jira, VSCode, Excel, Postman, Power BI)\n"
        "  NON → code ou méthode ?\n"
        "         OUI → technical   (Python, SQL, TensorFlow, REST API, CI/CD, AWS)\n"
        "         NON → soft_skills (Agile, Scrum, Kanban — UNIQUEMENT si écrit verbatim)\n"

        "\n=== CLASSIFICATION DES EXPÉRIENCES ===\n"
        "  professional_experience → CDI, CDD, emploi long terme\n"
        "  internships             → stage, PFE, PFA, internship, < 6 mois\n"
        "  alternance              → alternance, apprentissage, work-study\n"
        "  Si incertain → mettre dans professional_experience\n"
        "BÉNÉVOLAT → NE PAS inclure dans les listes ci-dessus :\n"
        "  Si role/company contient : bénévole, volunteer, pro bono, mentorat bénévole\n"
        "  → Ne pas extraire cette expérience (ou la mettre dans professional_experience\n"
        "    UNIQUEMENT si c'est un poste payé senior : directeur, responsable, développeur...)\n"

        "\n=== EXTRACTION DU NOM ===\n"
        "- full_name = PRÉNOM + NOM (minimum 2 mots)\n"
        "- Si sur 2 lignes (OCR) : concaténer → 'JEAN' + 'DUPONT' = 'JEAN DUPONT'\n"
        "- Si le texte commence par 'Nom: X Y' → utiliser cette valeur directement\n"

        "\n=== CERTIFICATION vs FORMATION vs EXPÉRIENCE vs PROJETS ===\n"
        "  certifications[] : certificats nommés avec émetteur/année optionnels\n"
        "  education[]      : UNIQUEMENT diplômes officiels (Master, Licence, BTS, DUT, PhD)\n"
        "  professional_experience[] : UNIQUEMENT vrais emplois avec entreprise + dates\n"
        "  projects[]       : projets personnels / académiques / GitHub explicitement décrits comme projets\n"
        "                   avec nom, description courte, technologies et lien si présent\n"
        "  Tests de langue (TOEIC, TOEFL, IELTS) → certifications[], PAS languages[]\n"

        "\n=== RÈGLE RÉALISATIONS ===\n"
        "- Copier le texte EXACT du CV pour les réalisations\n"
        "- NE JAMAIS écrire 'Résultat 1', 'Achievement 1', 'Task 1'\n"
        "- Si aucune réalisation → retourner []\n"

        "\n=== NOM D'ENTREPRISE ===\n"
        "- company = NOM DE L'ENTREPRISE uniquement — JAMAIS une ville, région ou pays\n"
        "  ❌ FAUX : company='Paris', company='Lyon', company='France', company='Remote'\n"
        "  ✅ JUSTE : company='TechCorp', company='Accenture France', company=null si inconnu\n"
        "  Si le CV dit 'Développeur @ Paris' → company=null (Paris est une ville, pas une entreprise)\n"
        "  Si le CV dit 'Consultant - Lyon, France' → company=null\n"
        "  Suffixe ville OK : 'BNP Paris', 'Google Paris' → garder (vrai nom + ville suffixe)\n"

        "\n=== AUTRES RÈGLES ===\n"
        f"- end_year formation : si en cours (present, en cours, actuel, current) → '{CURRENT_YEAR}'\n"
        "- Classes préparatoires (CPGE, MPSI/MP/PC/PSI) = entrée education valide\n"
        "- Un 'Parcours' dans un diplôme n'est PAS une entrée séparée\n"
        "- Certifications : extraire TOUTE certif — émetteur et année sont OPTIONNELS\n"
        "- Tests de langue = certifications : TOEIC, TOEFL, IELTS, DELF, DALF, HSK\n"
        "- year manquant → year=null (ne jamais sauter une certif)\n"
        "- Langues : UNIQUEMENT si section LANGUES explicite\n"
        "- Respecter EXACTEMENT ce format :\n"
        + json_template
    )

    # ══════════════════════════════════════════════════════════════════
    # PROMPT ANGLAIS — CV purement en anglais
    # ══════════════════════════════════════════════════════════════════
    prompt_en = (
        "You are an expert CV/Resume analyzer. Parse the following CV and extract all information.\n\n"
        "CV TEXT (may contain --- PAGE N --- markers for multi-page CVs):\n\n"
        + raw_text +
        "\n\nCRITICAL INSTRUCTIONS:\n"
        "- Return ONLY a valid JSON object — no explanation, no markdown, no code blocks\n"
        "- For skill names: use English\n"
        "- For degree names and job titles: keep the ORIGINAL language from the CV\n"
        "- NEVER write bilingual values — pick one language (prefer English)\n"
        "- For duration: copy EXACTLY what is written in the CV — do NOT invent end dates\n"
        "  If CV says 'Jul 2024' only → write 'Jul 2024' — nothing else\n"
        "  If CV says 'Jan 2021 - Present' → write 'Jan 2021 - Present'\n"
        "  NEVER write Present/Current unless the word is literally in the CV text\n"
        "- NEVER invent experiences — extract ONLY what is in the CV TEXT above\n"
        "- If a field is missing → return null or []\n"
        "- NEVER use N/A, None, '-' in lists — use [] instead\n"
        "- soft_skills: ONLY methods/frameworks EXPLICITLY written in the CV — NEVER invent\n"

        "\n=== SECTION RECOGNITION ===\n"
        "Map these section headers to the correct JSON fields:\n"
        "  WORK EXPERIENCE / EXPERIENCE / PROFESSIONAL EXPERIENCE  → professional_experience\n"
        "  EMPLOYMENT HISTORY / CAREER HISTORY / POSITIONS HELD    → professional_experience\n"
        "  EDUCATION / ACADEMIC BACKGROUND / QUALIFICATIONS        → education\n"
        "  SKILLS / TECHNICAL SKILLS / CORE COMPETENCIES           → skills\n"
        "  KEY SKILLS / AREAS OF EXPERTISE / PROFICIENCIES         → skills\n"
        "  CERTIFICATIONS / LICENSES / CREDENTIALS / AWARDS        → certifications\n"
        "  LANGUAGES / LANGUAGE SKILLS / LINGUISTIC SKILLS         → languages\n"
        "  INTERNSHIP / PLACEMENT / TRAINEE PROGRAM / CO-OP        → internships\n"
        "  VOLUNTEERING / COMMUNITY SERVICE / PRO BONO             → IGNORE (not pro experience)\n"
        "  PROJECTS / SIDE PROJECTS / PERSONAL PROJECTS            → IGNORE unless paid role\n"

        "\n=== DEGREE MAPPING ===\n"
        "  Bachelor's / B.Sc / B.A / B.Eng / Undergraduate → Licence\n"
        "  Master's / M.Sc / M.A / M.Eng / MBA / MSc       → Master\n"
        "  PhD / Doctorate / DPhil                          → Doctorat\n"
        "  Associate's Degree / HND / HNC                  → BTS/DUT\n"
        "  High School Diploma / A-Levels / GCSEs           → Baccalauréat\n"

        "\n=== DATE & DURATION RULES ===\n"
        "  'Present' / 'Current' / 'Now' / 'Ongoing' / 'Till date' → current position\n"
        "  'Since 2020'        → current position, write '2020 - Present'\n"
        "  'Jan 2021 - Present' → write exactly as is\n"
        "  '2019 - 2022'        → write exactly as is\n"
        "  'Q1 2021 - Q3 2022' → write '2021 - 2022'\n"

        "\n=== MULTI-PAGE CV RULES ===\n"
        "- --- PAGE 2 ---, --- PAGE 3 --- markers are page boundaries, NOT section headers\n"
        "- An experience block CAN span two pages → treat as ONE single entry\n"
        "- 'John Doe — continued' at top of a page = CONTINUATION HEADER, ignore it\n"
        "- SCAN ALL PAGES for experiences, skills, certifications\n"
        "- If text ends with '[TRUNCATED...]' → extract everything available before it\n"

        "\n=== OCR HEADER FORMAT ===\n"
        "The text may start with pre-extracted contact fields:\n"
        "  Email: hello@example.com\n"
        "  Tel: +1-555-123-4567\n"
        "  Nom: JOHN DOE\n"
        "→ Use these values directly for full_name, email, phone.\n"

        "\n=== SKILLS EXTRACTION ===\n"
        "- Extract from BOTH: dedicated skill sections AND inline 'Tech:' / 'Stack:' lines\n"
        "- Skill sections often have SUB-CATEGORIES — extract ALL of them:\n"
        "  e.g. 'Languages: Python, Go' AND 'Frameworks: Django, FastAPI' AND 'Cloud: AWS'\n"
        "  → Extract Python, Go, Django, FastAPI, AWS — ALL sub-categories, not just first\n"
        "  Sub-category labels (Languages, Frameworks, Cloud, Databases) are HEADERS not skills\n"
        "- Extract sub-skills in parentheses: 'Python (Pandas, NumPy)' → Python + Pandas + NumPy\n"
        "- NEVER infer skills from job description prose\n"

        "\n=== SKILL CLASSIFICATION ===\n"
        "For each skill, ask: Can I open/launch it as a standalone app?\n"
        "  YES → tools     (Docker, Git, Figma, Jira, VSCode, Excel, Postman, Power BI)\n"
        "  NO  → Can I write code with it, or use it as a methodology?\n"
        "         YES → technical   (Python, SQL, TensorFlow, REST API, CI/CD, AWS)\n"
        "         NO  → soft_skills (Agile, Scrum, Kanban — ONLY if explicitly written)\n"
        "  RULE: the CV section label does NOT decide the category\n"

        "\n=== EXPERIENCE CLASSIFICATION ===\n"
        "  professional_experience → full-time, permanent, contract, long-term roles\n"
        "  internships             → internship, placement, trainee, co-op, < 6 months\n"
        "  alternance              → apprenticeship, work-study, sandwich course\n"
        "  If unsure → put in professional_experience\n"
        "VOLUNTEERING → Do NOT include in any of the above lists:\n"
        "  If role/company contains: volunteer, pro bono, nonprofit, NGO, charity, mentoring\n"
        "  → Do NOT extract (or only include if it is a PAID senior role:\n"
        "    director, manager, developer, engineer, consultant...)\n"

        "\n=== COMPANY EXTRACTION ===\n"
        "- company = COMPANY NAME only — NEVER a city, region, or country\n"
        "  ❌ WRONG: company='Paris', company='London', company='Remote', company='France'\n"
        "  ✅ RIGHT: company='TechCorp', company='Accenture UK', company=null if unknown\n"
        "  If CV says 'Software Engineer - London' → company=null (London is a city, not a company)\n"
        "  If CV says 'Developer @ Paris (remote)' → company=null\n"
        "  City suffixes are OK: 'BNP Paris', 'Google London' → keep (real company + city)\n"

        "\n=== NAME EXTRACTION ===\n"
        "- full_name = FIRST NAME + LAST NAME (minimum 2 words)\n"
        "- If name is on 2 lines (OCR): concatenate → 'JOHN' + 'DOE' = 'JOHN DOE'\n"
        "- NEVER return a single word as full_name\n"

        "\n=== CERTIFICATION vs EDUCATION vs EXPERIENCE ===\n"
        "  certifications[]:          named certificates with optional issuer/year\n"
        "  education[]:               ONLY official degrees (Bachelor, Master, PhD, etc.)\n"
        "  professional_experience[]: ONLY paid jobs with company + dates\n"
        "  Language tests (TOEIC, TOEFL, IELTS) → certifications[], NOT languages[]\n"
        "    e.g. 'TOEIC 970' → {\"name\": \"TOEIC 970\", \"issuer\": \"ETS\", \"year\": null}\n"

        "\n=== ACHIEVEMENTS RULE ===\n"
        "- Copy the EXACT text from the CV — never paraphrase or summarize\n"
        "- NEVER write 'Achievement 1', 'Task 1', 'Result 1'\n"
        "- If no achievement text found → return []\n"

        "\n=== PROJECTS RULES ===\n"
        "- Extract projects ONLY if the CV explicitly contains a projects/personal projects/academic projects/GitHub/portfolio section\n"
        "- Do NOT convert normal job missions into projects[]\n"
        "- A project embedded in an internship/professional experience achievement should stay in achievements unless it is clearly listed as a standalone project entry\n"
        "- technologies = only technologies explicitly mentioned for that project\n"
        "- link = GitHub/portfolio/demo URL if explicitly present, else null\n"
        "\n=== OTHER RULES ===\n"
        f"- Education end_year: if currently enrolled (present/current/ongoing) → set to '{CURRENT_YEAR}'\n"
        "- A 'Major' or 'Specialization' within a degree is NOT a separate education entry\n"
        "- Certifications: year missing → year=null (never skip the certification)\n"
        "- Languages field: ONLY if an explicit LANGUAGES section exists in the CV\n"
        "- Respond EXACTLY in this JSON format:\n"
        + json_template
    )

    # ── Sélection dynamique du prompt ────────────────────────────────
    if cv_lang == "en":
        prompt = prompt_en
        logger.info("Prompt sélectionné : ANGLAIS")
    else:
        prompt = prompt_fr
        logger.info("Prompt sélectionné : FRANÇAIS (CV fr ou mixte)")

    for attempt in range(3):
        try:
            logger.info(f"Appel LLM — tentative {attempt + 1}/3")

            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.6,
                max_tokens=4000,
                timeout=60
            )

            raw_response = response.choices[0].message.content.strip()

            # ── Supprimer le bloc <think>...</think> de DeepSeek R1 ────
            # Le modèle raisonne avant de répondre — on garde uniquement le JSON
            import re as _re
            raw_response = _re.sub(r'<think>.*?</think>', '', raw_response,
                                   flags=_re.DOTALL).strip()

            if "```" in raw_response:
                raw_response = raw_response.split("```")[1]
                if raw_response.startswith("json"):
                    raw_response = raw_response[4:]

            # ── Nettoyage défensif de la réponse LLM ───────────────
            # Certains CVs (LaTeX, encodage corrompu) génèrent des
            # séquences \escape invalides dans le JSON du LLM
            raw_response = re.sub(
                r'\\(?!["\\/bfnrt]|u[0-9a-fA-F]{4})',
                '',
                raw_response
            )

            parsed = json.loads(raw_response)
            logger.info("JSON valide recu du LLM")
            if parsed.get("skills"):
                # Étape 1 : nettoyage (None, doublons, titres de postes)
                parsed["skills"] = clean_skills(parsed["skills"])
                logger.info("  Skills nettoyés")
                # Étape 2 : normalisation + correction catégories (Python déterministe)
                parsed["skills"] = correct_skill_category(parsed["skills"])
                logger.info("  Skills normalisés et catégories corrigées")
                # Étape 3 : validation (supprimer skills absents du texte CV)
                parsed["skills"] = validate_skills_against_text(parsed["skills"], raw_ocr_text)
                # Étape 4 : supprimer soft skills génériques hallucinés
                parsed["skills"] = filter_generic_soft_skills(parsed["skills"], raw_ocr_text)

            # Reclassification hybride
            logger.info("Classification hybride des experiences...")
            parsed, global_confidence = reclassify_experiences(parsed)

            # Fusion des expériences dupliquées par saut de page
            for key in ["professional_experience", "internships", "alternance"]:
                if parsed.get(key):
                    before = len(parsed[key])
                    parsed[key] = merge_split_experiences(parsed[key])
                    after = len(parsed[key])
                    if after < before:
                        logger.info(
                            f"  [multi-page] {before - after} doublon(s) fusionné(s) dans '{key}'"
                        )

            # Fix alternance mal classée en PRO par le LLM
            # (LLM supprime "— Alternance" du titre → reclassify ne voit pas le mot-clé)

            # Supprimer les "Présent" inventés par le LLM (Python = source de vérité)
            # Fix entreprise/dates manquantes (CVs 2 colonnes entrelacées)
            parsed = fix_missing_company_and_dates(parsed, raw_ocr_text)
            parsed = fix_city_as_company(parsed)
            parsed = fix_volunteer_experiences(parsed)
            parsed = recover_missing_soft_skills(parsed, raw_ocr_text)
            parsed = fix_hallucinated_present(parsed, raw_ocr_text)

            parsed = _fix_alternance_from_raw_text(parsed, raw_ocr_text)

            # Valider avec Pydantic
            validated = CVData(**parsed)
            result = validated.model_dump()

            # Re-appliquer fix alternance sur result (post-Pydantic) pour que
            # les corrections de duration soient conservées dans le dict final
            result = _fix_alternance_from_raw_text(result, raw_ocr_text)

            # ── Nettoyage email/téléphone (artefacts OCR) ─────────────
            result = sanitize_contact_fields(result, raw_text=raw_ocr_text)

            # ── Validation anti-hallucination ──────────────────────────

            # Fix 1 : Supprimer achievements génériques (Résultat 1, Tâche 2...)
            for key in ["professional_experience", "internships", "alternance"]:
                if result.get(key):
                    result[key] = clean_achievements(result[key], raw_ocr_text)

            # Fix 1b : Compléter les achievements coupés par saut de page
            # Opère sur result (post-Pydantic) — les modifications sont garanties conservées.
            for key in ["professional_experience", "internships", "alternance"]:
                if result.get(key):
                    _fill_continuation_achievements(result[key], raw_ocr_text)

            # Fix 1c : Re-appliquer clean_achievements après continuation
            # car _fill_continuation_achievements peut réinjecter des certifs/skills
            # depuis le raw_text (ex: "DeepLearning.AI TensorFlow Developer (2021)")
            for key in ["professional_experience", "internships", "alternance"]:
                if result.get(key):
                    result[key] = clean_achievements(result[key], raw_ocr_text)

            # Fix 2 : Valider outils contre texte OCR (supprimer outils hallucinés)
            if result.get("skills") and raw_ocr_text:
                result["skills"] = validate_tools_against_text(result["skills"], raw_ocr_text)

            # Fix 2b : Supprimer soft skills génériques hallucinés
            if result.get("skills") and raw_ocr_text:
                result["skills"] = filter_generic_soft_skills(result["skills"], raw_ocr_text)


            # Fix 3 : Langues — fallback extraction directe si LLM en a raté
            # FIX doublons FR/EN : normaliser les 2 côtés en français avant fusion
            # Ex: LLM retourne "French" + OCR retourne "Français" → même langue
            if raw_ocr_text:
                _LANG_EN_TO_FR = {
                    "french": "Français", "english": "Anglais", "spanish": "Espagnol",
                    "german": "Allemand", "arabic": "Arabe", "portuguese": "Portugais",
                    "italian": "Italien", "chinese": "Chinois", "japanese": "Japonais",
                    "russian": "Russe", "dutch": "Néerlandais", "turkish": "Turc",
                    "hindi": "Hindi", "korean": "Coréen",
                }
                def _normalize_lang(lang: str) -> str:
                    return _LANG_EN_TO_FR.get(lang.lower(), lang.capitalize())

                langs_llm = result.get("languages") or []
                langs_ocr = extract_languages_from_text(raw_ocr_text)

                seen_norm = set()
                normalized_llm = []
                for lang in langs_llm:
                    norm = _normalize_lang(lang)
                    if norm.lower() not in seen_norm:
                        seen_norm.add(norm.lower())
                        normalized_llm.append(norm)

                added = []
                for lang in langs_ocr:
                    norm = _normalize_lang(lang)
                    if norm.lower() not in seen_norm:
                        seen_norm.add(norm.lower())
                        normalized_llm.append(norm)
                        added.append(norm)

                if added:
                    logger.info(f"  Langues ajoutées depuis OCR : {', '.join(added)}")
                result["languages"] = normalized_llm

            # Corriger end_year education
            if result.get("education"):
                result["education"] = fix_education_end_years(result["education"])
                result["education"] = fix_education_dates_ocr_collision(
                    result["education"],
                    result.get("professional_experience") or [],
                    raw_text=raw_ocr_text
                )

            # ── Calcul des metriques — UNE SEULE PASSE (Bug 2 fix) ──
            # calculate_total_months() est appele ici UNE SEULE FOIS
            # avec log_details=True pour afficher les details proprement
            pro_exp = result.get("professional_experience") or []
            intern  = result.get("internships") or []
            alt     = result.get("alternance") or []

            # Fix duration — chercher la durée explicite "(N mois)" ou "(N months)" dans raw_text
            # Couvre : alternance mal calculée ET stages avec durée explicite dans le CV
            # Ex: "Jun 2023 – Aug 2023 (3 months — Internship)" → 3 mois (au lieu de 2 par diff)
            def _fix_duration_from_raw(exp_list, raw_lines):
                for exp in exp_list:
                    old_dur = exp.get("duration") or ""
                    old_sy, old_sm, old_ey, old_em = extract_period_from_duration(old_dur)
                    old_months = (old_ey - old_sy) * 12 + (old_em - old_sm) if old_sy else 0
                    stopwords_dur = {"alternance", "intern", "stage", "stagiaire",
                                     "developer", "developpeur", "ingenieur", "engineer",
                                     "senior", "junior", "frontend", "backend"}
                    role_words = [w for w in (exp.get("role") or "").lower().split()
                                  if len(w) > 3 and w not in stopwords_dur][:2]
                    company_frag = (exp.get("company") or "").lower()[:12]
                    # Priorite : ligne avec role ET entreprise > entreprise seule > role seul
                    best_i, best_score = None, 0
                    for i, line in enumerate(raw_lines):
                        ll = line.lower()
                        rm = bool(role_words and all(w in ll for w in role_words))
                        cm = bool(company_frag and company_frag in ll)
                        s  = (2 if rm and cm else 1 if cm else 0)
                        if s > best_score:
                            best_score, best_i = s, i
                        if best_score == 2:
                            break
                    if best_i is not None:
                        for wline in raw_lines[best_i:min(best_i+4, len(raw_lines))]:
                            m_explicit = re.search(
                                r"\((\d+)\s*(mois|months?)\b", wline, re.IGNORECASE
                            )
                            if m_explicit:
                                explicit_months = int(m_explicit.group(1))
                                if explicit_months != old_months:
                                    logger.info(f"  [fix-dur-explicit] '{exp.get('role')}' "
                                                f"{old_months}m -> {explicit_months}m")
                                    # Nettoyer la ligne PDF : garder seulement "MMM YYYY – MMM YYYY"
                                    clean_dur = re.split(r'\s*[\|•]\s*', wline)[0]
                                    clean_dur = re.sub(r'\s*\(.*', '', clean_dur).strip()
                                    ny, nm, ney, nem = extract_period_from_duration(clean_dur)
                                    if ny:
                                        exp["duration"] = clean_dur
                                    exp["_explicit_months"] = explicit_months
                                break

            if raw_ocr_text:
                raw_lines_fix = raw_ocr_text.splitlines()
                _fix_duration_from_raw(alt, raw_lines_fix)
                _fix_duration_from_raw(intern, raw_lines_fix)

            logger.info("Calcul durees — EXPERIENCE PRO :")
            years_pro    = calculate_years_experience(pro_exp)

            logger.info("Calcul durees — STAGES :")
            months_int   = calculate_total_months(intern, log_details=True)

            logger.info("Calcul durees — ALTERNANCE :")
            months_alt   = calculate_total_months(alt, log_details=True)

            total_months = calculate_total_months(
                pro_exp + intern + alt, log_details=False   # pas de re-log du total
            )

            result["years_professional"]       = years_pro
            result["months_internships"]        = months_int
            result["months_alternance"]         = months_alt
            result["nb_internships"]            = len(intern)
            result["years_experience"]          = max(math.floor(total_months / 12), 0)
            result["classification_confidence"] = global_confidence

            # Score qualite
            result["cv_quality_score"] = calculate_cv_quality_score(result)

            logger.info(
                f"CV parse — score: {result['cv_quality_score']} | "
                f"confiance: {global_confidence} | "
                f"Pro: {years_pro} ans | "
                f"Stages: {months_int} mois | "
                f"Alt: {months_alt} mois"
            )

            # ── skills_all : index global pour le job matching agent ──────
            # Combine technical + tools en une liste plate dédupliquée
            # Utilisé par les agents suivants pour comparer CV ↔ offre
            skills = result.get("skills") or {}
            all_skills = (
                (skills.get("technical") or []) +
                (skills.get("tools")     or []) +
                (skills.get("soft_skills") or [])
            )
            # Dédupliquer en conservant l'ordre
            seen_all = set()
            result["skills_all"] = [
                s for s in all_skills
                if s.lower() not in seen_all and not seen_all.add(s.lower())
            ]

            return result

        except json.JSONDecodeError:
            logger.warning(f"JSON invalide — tentative {attempt + 1}/3")
            if attempt == 2:
                logger.error("LLM a retourne un JSON invalide apres 3 tentatives")
                raise ValueError("LLM returned invalid JSON after 3 attempts")
            continue

        except ValidationError as e:
            logger.error(f"Validation Pydantic echouee : {str(e)}")
            raise ValueError(f"Pydantic validation failed: {str(e)}")

        except Exception as e:
            # Détecter RateLimitError Groq (429) — stopper immédiatement sans retry
            err_str = str(e)
            if "429" in err_str or "rate_limit_exceeded" in err_str or "tokens per day" in err_str.lower():
                import re as _re2
                wait_match = _re2.search(r"try again in ([\w.]+)", err_str)
                wait_time = wait_match.group(1) if wait_match else "environ 1 heure"
                msg = (
                    f"Limite journaliere API Groq atteinte (100 000 tokens/jour). "
                    f"Reessayez dans {wait_time}. "
                    f"Plus d'infos : https://console.groq.com/settings/billing"
                )
                logger.error(f"Rate limit Groq : {msg}")
                raise ValueError(msg)
            logger.error(f"Erreur inattendue LLM : {err_str}")
            if attempt == 2:
                raise ValueError(f"Erreur LLM apres 3 tentatives : {err_str}")
            continue


# ─────────────────────────────────────────
# FONCTION PRINCIPALE
# ─────────────────────────────────────────

def run_cv_parser(pdf_path: str, use_cache: bool = True) -> dict:
    """
    Parse un CV PDF et retourne les données structurées.

    Cache MD5 PostgreSQL (30 jours) :
      - Calcule le MD5 du fichier PDF
      - Si déjà en cache → retourne immédiatement (0 token Groq)
      - Si nouveau       → parse + sauvegarde en cache

    Paramètres :
      pdf_path  : chemin vers le fichier PDF
      use_cache : False pour forcer un re-parsing (ignorer le cache)
    """
    logger.info(f"Debut analyse CV : {pdf_path}")

    if not os.path.exists(pdf_path):
        logger.error(f"Fichier introuvable : {pdf_path}")
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    # ── Cache MD5 PostgreSQL ──────────────────────────────────────────
    md5_hash = None
    if use_cache:
        try:
            from app.agents.cv_agent.cv_cache  import compute_md5, get_cached_result, save_to_cache
            md5_hash = compute_md5(pdf_path)

            # Vérifier si le résultat est déjà en cache
            cached = get_cached_result(md5_hash)
            if cached is not None:
                logger.info(
                    f"Cache HIT — parsing ignoré pour : {pdf_path} "
                    f"(candidat: {cached.get('full_name', 'inconnu')})"
                )
                return cached

        except Exception as e:
            # Erreur cache (DB indisponible, psycopg2 non installé...)
            # → on continue le parsing normalement sans bloquer
            logger.warning(f"Cache indisponible — parsing normal : {e}")
            md5_hash = None

    # ── Parsing normal (cache MISS ou cache désactivé) ────────────────
    cleaned_text, raw_ocr_text = extract_text_from_pdf(pdf_path)
    parsed_data = parse_cv_with_llm(cleaned_text, raw_ocr_text=raw_ocr_text)
    parsed_data["raw_text"] = cleaned_text

    # ── Sauvegarder dans le cache ─────────────────────────────────────
    if use_cache and md5_hash:
        try:
            from app.agents.cv_agent.cv_cache  import save_to_cache
            save_to_cache(md5_hash, parsed_data)
        except Exception as e:
            logger.warning(f"Impossible de sauvegarder dans le cache : {e}")

    logger.info(f"Analyse terminee — candidat: {parsed_data.get('full_name')}")

    # ── Validation automatique post-parsing ──────────────────────────
    # Lance tous les checks de cohérence (durées, skills, achievements...)
    # et attache le rapport au résultat. N'interrompt jamais le pipeline.
    try:
        from app.agents.cv_agent.cv_cache  import validate_and_fix
        parsed_data, val_report = validate_and_fix(parsed_data, pdf_path=pdf_path)
        parsed_data["_validation"] = val_report
        if val_report["fixed"]:
            logger.info(
                f"Validation : {len(val_report['fixed'])} correction(s) — "
                + " | ".join(val_report["fixed"][:2])
            )
        if val_report["warnings"]:
            logger.warning(
                f"Validation : {len(val_report['warnings'])} avertissement(s) — "
                + " | ".join(val_report["warnings"][:2])
            )
        if not val_report["fixed"] and not val_report["warnings"]:
            logger.info(f"Validation OK — {val_report['summary']}")
    except Exception as e:
        logger.warning(f"Validation CV indisponible : {e}")

    return parsed_data
