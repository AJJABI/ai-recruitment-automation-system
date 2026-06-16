"""
motivation_agent.py
===================
Agent 2 — Analyse de la lettre de motivation.

Fonctionnement :
  1. Extrait le texte de la lettre PDF
  2. Détecte la langue (FR / EN)
  3. Vérifie la longueur (< 50 mots → qualite = 20 automatique)
  4. Envoie au LLM (Groq llama-3.3-70b) avec prompt adapté FR/EN
  5. LLM retourne un JSON avec notes par critère
  6. Python calcule le score pondéré final
  7. Sauvegarde score dans Application + détail dans IA_Log

Critères et poids :
  coherence_poste  35%  — lettre cohérente avec le poste ?
  competences      25%  — compétences citées liées à l'offre ?
  experience       20%  — expérience pertinente mentionnée ?
  motivation       12%  — lettre personnalisée pour CE poste ?
  qualite           8%  — clarté, longueur, ton professionnel ?

Output retourné :
  {
    "score_motivation"  : 74,
    "pertinence_poste"  : "élevée | moyenne | faible",
    "competences_citees": ["Python", "Django"],
    "points_forts"      : ["Expérience ERP", "Technologies backend"],
    "langue"            : "fr",
    "nb_mots"           : 250,
    "detail_criteres"   : { "coherence_poste": 80, ... }
  }


"""

import os
import re
import json
import logging
import pdfplumber
from typing import Optional
from dotenv import load_dotenv
from groq import Groq

# langdetect pour détection de langue fiable (pip install langdetect)
try:
    from langdetect import detect as langdetect_detect
    from langdetect import DetectorFactory
    from langdetect.lang_detect_exception import LangDetectException
    DetectorFactory.seed = 42   # résultats reproductibles
    LANGDETECT_AVAILABLE = True
except ImportError:
    LANGDETECT_AVAILABLE = False
    logger_import = None

load_dotenv()

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────
# CLIENT LLM
# ─────────────────────────────────────────

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

LLM_MODEL    = "llama-3.3-70b-versatile"
MAX_TOKENS   = 1000
TEMPERATURE  = 0.3   # plus bas que cv_parser → résultats plus stables
MAX_ATTEMPTS = 3

# ─────────────────────────────────────────
# CONSTANTES
# ─────────────────────────────────────────

# Seuils longueur lettre
MIN_WORDS_GOOD  = 100   # > 100 mots → LLM analyse normalement
MIN_WORDS_SHORT = 50    # 50-100 mots → qualite = 50 automatique
                        # < 50 mots   → qualite = 20 automatique

# Poids des critères (total = 100)
# ─────────────────────────────────────────────────────────
# DOCUMENTATION DES RÈGLES (traçabilité pour debug)
#
# Chaque règle est référencée par son test de validation :
# R1  : plafond coherence/competences si overlap faible → T39, T44, T48
# R2  : pénalité personnalisation si générique → T40, T48
# R3  : auto_quality_score si lettre courte → T3, T15
# R4  : plafond experience si coherence<30 → T48, T52
# R5  : qualite≤40 si court+générique → T48, T52
# R6  : pénalité ×0.7 si 0skill+hors domaine → T48
# R7  : plafond spécificité 70 si spec_score<4 → T44
# R8  : double pénalité interdite (not lettre_generique) → fix bug
# R9  : phrases IA → downgrade matches → T48
# R10 : pénalité progressive junior vs senior (longueur lettre)
# ─────────────────────────────────────────────────────────
# Pondération basée sur la littérature académique :
# coherence_poste 35% [Khatri et al., IJRESM 2025 ; Xu et al., KBS 2021]
# competences     25% [ResumeGenius Survey, 2023 — 72% des RH]
# experience      20% [Padmaja et al., JETIR 2023 ; Xu et al., KBS 2021]
# personnalisation 12% [ResumeGenius Survey, 2023]
# qualite          8% [Padmaja et al., JETIR 2023]
# Calibration empirique : 18 cas de test (80% précision)
WEIGHTS = {
    "coherence_poste" : 0.35,
    "competences"     : 0.25,
    "experience"      : 0.20,
    "personnalisation": 0.12,
    "qualite"         : 0.08,
}

# Seuils pertinence_poste
SEUIL_ELEVEE      = 70
SEUIL_MOYENNE     = 40
SEUIL_TRES_FAIBLE = 20  # en dessous = "très faible"

# Longueur max texte lettre envoyé au LLM
MAX_LETTER_CHARS = 3000

# Plafonds motivation selon niveau générique
PENALITE_GENERIQUE_TOTAL   = 30   # 0 match  → motivation plafonné à 30
PENALITE_GENERIQUE_PARTIEL = 55   # 1 match  → motivation plafonné à 55
# 2+ matches → pas de pénalité


# ─────────────────────────────────────────
# EXTRACTION TEXTE PDF
# ─────────────────────────────────────────

def _extract_letter_text(letter_path: str) -> Optional[str]:
    """
    Extrait le texte brut de la lettre de motivation (PDF ou TXT).
    Retourne None si le fichier est illisible ou vide.

    FIX : Supporte maintenant les fichiers .txt en plus des .pdf
    """
    if not letter_path or not os.path.exists(letter_path):
        logger.warning(f"Lettre introuvable : '{letter_path}'")
        return None

    ext = os.path.splitext(letter_path)[1].lower()

    # ── Lecture TXT ───────────────────────────────────────────────────
    if ext == ".txt":
        try:
            with open(letter_path, "r", encoding="utf-8") as f:
                full_text = f.read().strip()
            if not full_text:
                logger.warning(f"Lettre TXT vide : '{letter_path}'")
                return None
            logger.info(f"Lettre TXT extraite : {len(full_text)} chars")
            return full_text
        except UnicodeDecodeError:
            # Essai avec latin-1 si utf-8 échoue
            try:
                with open(letter_path, "r", encoding="latin-1") as f:
                    full_text = f.read().strip()
                logger.info(f"Lettre TXT (latin-1) extraite : {len(full_text)} chars")
                return full_text if full_text else None
            except Exception as e:
                logger.error(f"Erreur lecture lettre TXT : {e}")
                return None
        except Exception as e:
            logger.error(f"Erreur lecture lettre TXT : {e}")
            return None

    # ── Lecture PDF ───────────────────────────────────────────────────
    try:
        with pdfplumber.open(letter_path) as pdf:
            pages_text = []
            for page in pdf.pages:
                text = page.extract_text() or ""
                # Normaliser les cid (artefacts PDF)
                text = re.sub(r'\(cid:\d+\)', ' ', text)
                pages_text.append(text)
            full_text = "\n".join(pages_text).strip()

        if not full_text:
            logger.warning(f"Lettre PDF vide : '{letter_path}'")
            return None

        logger.info(f"Lettre extraite : {len(full_text)} chars")
        return full_text

    except Exception as e:
        logger.error(f"Erreur lecture lettre PDF : {e}")
        return None


# ─────────────────────────────────────────
# DÉTECTION LANGUE
# ─────────────────────────────────────────

def _detect_language(text: str) -> str:
    """
    Détecte si la lettre est en français ou en anglais.
    Retourne 'fr', 'en', ou 'mixed'.

    Stratégie hybride :
    0. Marqueurs FR forts : si présents → fr immédiatement (avant langdetect)
       BUG-11 FIX : langdetect détectait "en" sur des lettres FR contenant des
       termes techniques anglais (Power Apps, SharePoint). Les marqueurs forts
       FR sont des mots grammaticaux non-ambigus → présence = lettre française.
    1. langdetect (fiable) si texte >= 20 mots
    2. Heuristique maison si texte court ou langdetect echoue
    """
    words      = text.split()
    text_lower = text.lower()

    # BUG-11 FIX : Étape 0 — marqueurs FR forts non-ambigus
    # Ces mots/expressions n'existent pas en anglais → présence = lettre FR certaine
    STRONG_FR_MARKERS = [
        "je vous ", "je suis ", "je postule", "je souhaite",
        "cordialement", "madame", "monsieur", "bonjour",
        "dans l'attente", "dans l attente", "veuillez",
        "à votre disposition", "a votre disposition",
        "mes compétences", "mes competences",
        "mon expérience", "mon experience",
        "notre entreprise",
    ]
    for marker in STRONG_FR_MARKERS:
        if marker in text_lower:
            logger.debug(f"  [lang] marqueur FR fort détecté ('{marker}') → fr")
            return "fr"

    # Etape 1 : langdetect si texte suffisamment long
    if LANGDETECT_AVAILABLE and len(words) >= 20:
        try:
            detected = langdetect_detect(text)
            if detected == "fr":
                logger.debug("  [lang] langdetect → fr")
                return "fr"
            elif detected == "en":
                logger.debug("  [lang] langdetect → en")
                return "en"
            else:
                logger.debug(f"  [lang] langdetect → {detected} (hors scope) → fallback")
        except LangDetectException:
            logger.debug("  [lang] langdetect exception → fallback heuristique")

    # Etape 2 : Heuristique maison (fallback)
    fr_signals = [
        "je", "mon", "ma", "mes", "votre", "vous", "nous",
        "experience", "competences", "poste", "entreprise",
        "candidature", "motivation", "formation", "bonjour",
        "madame", "monsieur", "cordialement",
    ]
    en_signals = [
        "i am", "my", "your", "we", "experience", "skills",
        "position", "company", "application", "motivation",
        "background", "dear", "sincerely", "regards",
        "i would", "i have", "i believe",
    ]
    fr_count = sum(1 for kw in fr_signals if re.search(
        r'\b' + re.escape(kw) + r'\b', text_lower))
    en_count = sum(1 for kw in en_signals if re.search(
        r'\b' + re.escape(kw) + r'\b', text_lower))

    logger.debug(f"  [lang] heuristique → fr={fr_count} en={en_count}")

    if en_count > fr_count + 2:
        return "en"
    elif fr_count > en_count + 2:
        return "fr"
    return "mixed"
def _count_words(text: str) -> int:
    """Compte le nombre de mots dans le texte."""
    return len(re.findall(r'\b\w+\b', text))


# ─────────────────────────────────────────
# QUALITE AUTOMATIQUE SELON LONGUEUR
# ─────────────────────────────────────────

def _normalize(text: str) -> str:
    """Normalise le texte : minuscules + supprime les accents pour comparaisons robustes."""
    import unicodedata
    text = text.lower()
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    return text


def _detect_generic_letter(
    letter_text    : str,
    job_title      : str,
    job_description: str,
    job_skills     : str,
    job_company    : str = "",
) -> dict:
    """
    Détecte si la lettre est générique (non personnalisée).

    Vérifie si la lettre mentionne :
      - Le nom de l'entreprise      (match 1)
      - Le titre du poste           (match 2)
      - Les compétences de l'offre  (match 3)

    Résultats :
      0 match → generique_total   → motivation plafonné à 30
      1 match → generique_partiel → motivation plafonné à 55
      2+ matches → personnalisee  → pas de pénalité

    Retourne :
      {
        "niveau"          : "generique_total|generique_partiel|personnalisee",
        "lettre_generique": True/False,
        "matches"         : 0-3,
        "plafond_motivation": 30 | 55 | None
      }
    """
    text_lower = _normalize(letter_text)
    matches    = 0

    # 1. Nom de l'entreprise mentionné ?
    if job_company:
        company_words = [
            w for w in _normalize(job_company).split()
            if len(w) > 3
        ]
        if any(re.search(r'\b' + re.escape(w) + r'\b', text_lower) for w in company_words):
            matches += 1
            logger.debug(f"  [generic] entreprise '{job_company}' trouvée ✅")
        else:
            logger.debug(f"  [generic] entreprise '{job_company}' absente ❌")

    # 2. Titre du poste mentionné ?
    STOPWORDS_TITLE = {
        'pour', 'avec', 'dans', 'votre', 'notre', 'cette',
        'les', 'des', 'une', 'the', 'and', 'for', 'with',
    }
    title_words = [
        w for w in re.split(r'[\s/\-]+', _normalize(job_title))
        if len(w) > 3 and w not in STOPWORDS_TITLE
    ][:3]
    if title_words and any(re.search(r'\b' + re.escape(w) + r'\b', text_lower) for w in title_words):
        matches += 1
        logger.debug(f"  [generic] poste '{job_title}' trouvé ✅")
    else:
        logger.debug(f"  [generic] poste '{job_title}' absent ❌")

    # 3. Compétences de l'offre mentionnées ?
    skill_tokens = [
        _normalize(s.strip())
        for s in re.split(r'[,;]', job_skills)
        if len(s.strip()) > 2
    ][:6]
    skills_found = [s for s in skill_tokens if re.search(r'\b' + re.escape(s) + r'\b', text_lower)]
    if skills_found:
        matches += 1
        logger.debug(f"  [generic] skills trouvés : {skills_found} ✅")
    else:
        logger.debug(f"  [generic] aucun skill de l'offre trouvé ❌")

    # Détection phrases IA/ChatGPT classiques → downgrade du score matches
    ia_phrases_fr = [
        "je suis très motivé", "votre entreprise dynamique",
        "je serais ravi de rejoindre", "contribuer à vos projets",
        "mes compétences correspondent", "je suis passionné par",
    ]
    ia_phrases_en = [
        "i am writing to apply", "i am very interested",
        "your company", "this opportunity", "i am confident",
        "i am excited", "i look forward to",
    ]
    ia_hits = sum(1 for p in ia_phrases_fr + ia_phrases_en if p in text_lower)
    if ia_hits >= 2 and matches > 0:
        matches = max(0, matches - 1)
        logger.debug(f"  [generic] Phrases IA détectées ({ia_hits}) → matches downgraded → {matches}")

    # BUG-22 FIX : détection de répétition verbatim (keyword stuffing lettre)
    # Si une séquence de 5+ mots apparaît 2+ fois → spam confirmé → plafond 35
    # Cas visé : lettres qui répètent "Power Apps, Power Automate, Power BI, ..."
    # plusieurs fois mot pour mot sans contexte
    letter_spam = False
    words_list = text_lower.split()
    if len(words_list) >= 10:
        # Extraire des n-grammes de 5 mots et compter leurs occurrences
        ngram_counts: dict = {}
        n = 5
        for i in range(len(words_list) - n + 1):
            ngram = " ".join(words_list[i:i+n])
            # Filtrer les n-grammes trop génériques (ponctuation seule, etc.)
            if len(ngram.replace(" ", "")) > 10:
                ngram_counts[ngram] = ngram_counts.get(ngram, 0) + 1
        repeated = [ng for ng, cnt in ngram_counts.items() if cnt >= 2]
        if repeated:
            letter_spam = True
            logger.warning(
                f"  [generic] BUG-22 : répétition verbatim détectée dans la lettre "
                f"({len(repeated)} n-gramme(s) répété(s)) → spam lettre confirmé"
            )

    # Décision finale
    if letter_spam:
        niveau             = "spam_verbatim"
        lettre_generique   = True
        plafond_motivation = 35   # pire que générique total (30) + bonus si skills cités
        logger.info(f"  [generic] Lettre SPAM VERBATIM → motivation ≤ {plafond_motivation}")
    elif matches == 0:
        niveau              = "generique_total"
        lettre_generique    = True
        plafond_motivation  = PENALITE_GENERIQUE_TOTAL
        logger.info(f"  [generic] Lettre GÉNÉRIQUE TOTALE (0/3) → motivation ≤ {plafond_motivation}")
    elif matches == 1:
        niveau              = "generique_partiel"
        lettre_generique    = True
        plafond_motivation  = PENALITE_GENERIQUE_PARTIEL
        logger.info(f"  [generic] Lettre semi-générique (1/3) → motivation ≤ {plafond_motivation}")
    else:
        niveau              = "personnalisee"
        lettre_generique    = False
        plafond_motivation  = None
        logger.info(f"  [generic] Lettre personnalisée ({matches}/3) → pas de pénalité")

    return {
        "niveau"            : niveau,
        "lettre_generique"  : lettre_generique,
        "matches"           : matches,
        "plafond_motivation": plafond_motivation,
    }


def _check_skills_overlap(letter_text: str, job_skills: str) -> dict:
    """
    Vérification Python déterministe — compte les compétences de l'offre
    présentes dans la lettre AVANT d'appliquer les scores LLM.

    Retourne :
      {
        "matched" : int,   — compétences trouvées
        "total"   : int,   — total compétences offre
        "ratio"   : float, — ratio 0.0-1.0
        "found"   : list,  — compétences trouvées
        "plafond_coherence"   : int|None,
        "plafond_competences" : int|None,
      }

    Plafonds selon ratio :
      0%       → coherence ≤ 25, competences ≤ 15  (aucune compétence)
      < 25%    → coherence ≤ 40, competences ≤ 30  (très peu)
      < 50%    → coherence ≤ 65, competences ≤ 55  (quelques-unes)
      >= 50%   → pas de plafond                    (bon match)
    """
    text_lower = letter_text.lower()
    skills_raw = [
        s.strip().lower()
        for s in re.split(r'[,;]', job_skills)
        if s.strip()
    ]

    # Patterns négation — détecte contexte négatif autour d'un skill
    NEGATION_PATTERNS_RAW = [
        r"n['\'\']ai pas\s+.{0,40}{skill}",
        r"pas\s+(?:d['\'\'])?(?:expérience|expertise|maîtrise)?\s*.{0,20}{skill}",
        r"sans\s+(?:expérience|maîtrise|connaissance)\s+.{0,20}{skill}",
        r"peu\s+(?:d['\'\'])?(?:expérience|maîtrise)\s+.{0,20}{skill}",
        r"{skill}\s*\(notions?\)",
        r"{skill}\s*\(basique\)",
        r"notions?\s+(?:de|en|sur)?\s*{skill}",
        r"reconnais.{{0,60}}{skill}",
        r"ne\s+(?:pas\s+)?maîtrise.{{0,30}}{skill}",
        r"limite.{{0,30}}{skill}",
    ]

    def _is_negated(skill_str: str, text: str) -> bool:
        words_sk = [w for w in skill_str.split() if len(w) > 3]
        skill_re = re.escape(words_sk[0]) if words_sk else re.escape(skill_str)
        for pat_template in NEGATION_PATTERNS_RAW:
            pattern = pat_template.replace("{skill}", skill_re)
            try:
                if re.search(pattern, text, re.IGNORECASE):
                    return True
            except re.error:
                pass
        return False

    found   = []
    negated = []
    for skill in skills_raw:
        # BUG-OVERLAP FIX : le filtre len(w) > 3 excluait les skills courts comme
        # "AL" (2 chars) ou "C/AL" (4 chars avec '/').
        # Nouvelle stratégie :
        #   1. Chercher le skill complet tel quel (ex: "c/al", "al")
        #   2. Si multi-mots : chercher la phrase complète, puis les mots longs
        #   3. Fallback : tokens >= 2 chars (évite les articles "a", "i")
        matched_skill = False

        # Étape 1 : correspondance exacte du skill complet (gère "al", "c/al", etc.)
        skill_escaped = re.escape(skill.strip())
        if re.search(r'(?<![a-z0-9])' + skill_escaped + r'(?![a-z0-9])', text_lower):
            matched_skill = True

        if not matched_skill:
            # Étape 2 : tokenisation — garder tous les tokens >= 2 chars
            words = [w for w in re.split(r'[/\s]+', skill) if len(w) >= 2]
            if not words:
                continue

            if len(words) >= 2:
                # Chercher la phrase complète (ex: "azure devops", "business central saas")
                skill_phrase = r'\s+'.join(re.escape(w) for w in words[:2])
                if bool(re.search(skill_phrase, text_lower)):
                    matched_skill = True
                else:
                    # Compter les mots longs trouvés (> 3 chars)
                    long_words = [w for w in words if len(w) > 3]
                    if long_words:
                        matched_count = sum(
                            1 for w in long_words
                            if re.search(r'\b' + re.escape(w) + r'\b', text_lower)
                        )
                        if matched_count >= 2:
                            matched_skill = True
            else:
                # Skill mono-token >= 2 chars
                if re.search(r'\b' + re.escape(words[0]) + r'\b', text_lower):
                    matched_skill = True

        if matched_skill:
            if _is_negated(skill, text_lower):
                negated.append(skill)
                import logging
                logging.getLogger(__name__).info(
                    f"  [skills-overlap] '{skill}' détecté mais contexte NÉGATIF → ignoré"
                )
            else:
                found.append(skill)

    ratio = len(found) / len(skills_raw) if skills_raw else 0

    # Pénalité PROGRESSIVE (évite de tuer les bons profils juniors)
    # ratio=0 → plafond strict SEULEMENT si lettre longue (junior peut ne pas citer explicitement)
    if ratio == 0:
        if len(letter_text.split()) >= 80:
            # Lettre longue sans aucun skill → vraiment hors domaine
            plafond_coherence   = 25
            plafond_competences = 10
        else:
            # Lettre courte → junior possible, pénalité modérée
            plafond_coherence   = 35
            plafond_competences = 20
    elif ratio < 0.25:
        plafond_coherence   = 40
        plafond_competences = 30
    elif ratio < 0.5:
        plafond_coherence   = 65
        plafond_competences = 55
    else:
        plafond_coherence   = None
        plafond_competences = None

    logger.info(
        f"  [skills-overlap] {len(found)}/{len(skills_raw)} compétences trouvées "
        f"({ratio:.0%}) — plafonds: coherence={plafond_coherence}, "
        f"competences={plafond_competences}"
    )

    return {
        "matched"             : len(found),
        "total"               : len(skills_raw),
        "ratio"               : ratio,
        "found"               : found,
        "plafond_coherence"   : plafond_coherence,
        "plafond_competences" : plafond_competences,
    }


def _auto_quality_score(nb_mots: int) -> Optional[int]:
    """
    Retourne un score qualité automatique si la lettre est trop courte.
    Retourne None si la longueur est normale (LLM analysera).
    """
    if nb_mots < MIN_WORDS_SHORT:
        logger.info(f"Lettre très courte ({nb_mots} mots) → qualite=20 automatique")
        return 20
    elif nb_mots < MIN_WORDS_GOOD:
        logger.info(f"Lettre courte ({nb_mots} mots) → qualite=50 automatique")
        return 50
    return None  # longueur normale → LLM décide


# ─────────────────────────────────────────
# PROMPTS LLM
# ─────────────────────────────────────────

def _build_prompt_fr(letter_text: str, job_title: str,
                     job_description: str, job_skills: str,
                     auto_qualite: Optional[int]) -> str:
    """Prompt en français pour les lettres FR/mixte."""

    qualite_instruction = (
        f"- qualite : {auto_qualite} (score fixé automatiquement — lettre trop courte)"
        if auto_qualite is not None
        else "- qualite : note de 0 à 100 (clarté, longueur adéquate, ton professionnel)"
    )

    # BUG-10 FIX : tronquer job_description à 200 chars (contexte seulement)
    # La description complète donnait trop de signal au LLM qui l'utilisait
    # pour inférer des compétences non mentionnées dans la lettre
    job_desc_context = (job_description or "")[:200].strip()
    if len(job_description or "") > 200:
        job_desc_context += "..."

    return f"""Tu es un expert RH. Analyse cette lettre de motivation par rapport à l'offre d'emploi.

OFFRE D'EMPLOI :
Titre : {job_title}
Description (contexte) : {job_desc_context}
Compétences requises : {job_skills}

LETTRE DE MOTIVATION :
{letter_text[:MAX_LETTER_CHARS]}

INSTRUCTIONS :
- Retourne UNIQUEMENT un JSON valide, sans explication ni markdown
- Note chaque critère de 0 à 100 :
  - coherence_poste : la lettre est-elle cohérente avec le domaine et le poste ?
  - competences : le candidat cite-t-il des compétences en rapport avec l'offre ?
  - experience : le candidat mentionne-t-il une expérience DIRECTEMENT PERTINENTE pour CE poste précis ?
    IMPORTANT : une expérience dans un domaine différent (ex: DevOps pour un poste ERP)
    doit recevoir un score ≤ 25, même si le candidat a beaucoup d'années d'expérience.
    Seule l'expérience dans le même domaine que le poste compte.
  - personnalisation : la lettre est-elle personnalisée pour CE poste précis ?
  {qualite_instruction}
- competences_citees : liste UNIQUEMENT les compétences/technologies EXPLICITEMENT mentionnées
  dans le texte de la lettre. NE PAS inclure des compétences inférées depuis l'offre d'emploi
  ou depuis le CV du candidat. Si une compétence n'apparaît pas mot pour mot dans la lettre,
  ne l'inclus PAS dans competences_citees. Maximum 10 éléments.
- points_forts : liste de faits courts EXTRAITS UNIQUEMENT DE LA LETTRE (max 4 éléments)
  EXEMPLE CORRECT   : ["Expérience ERP", "3 ans en développement AL", "Certification Microsoft"]
  EXEMPLE INCORRECT : ["Lettre bien rédigée", "Candidat motivé"]
  → UNIQUEMENT des faits du parcours MENTIONNÉS dans la lettre, pas des jugements

Format JSON attendu :
{{
  "coherence_poste": 80,
  "competences": 70,
  "experience": 75,
  "personnalisation": 60,
  "qualite": 85,
  "competences_citees": ["Python", "Django", "API REST"],
  "points_forts": ["Expérience ERP", "Technologies backend"]
}}"""


def _build_prompt_en(letter_text: str, job_title: str,
                     job_description: str, job_skills: str,
                     auto_qualite: Optional[int]) -> str:
    """Prompt en anglais pour les lettres EN."""

    qualite_instruction = (
        f"- qualite: {auto_qualite} (fixed automatically — letter too short)"
        if auto_qualite is not None
        else "- qualite: score 0-100 (clarity, adequate length, professional tone)"
    )

    return f"""You are an HR expert. Analyze this cover letter against the job offer.

JOB OFFER:
Title: {job_title}
Description: {job_description}
Required skills: {job_skills}

COVER LETTER:
{letter_text[:MAX_LETTER_CHARS]}

INSTRUCTIONS:
- Return ONLY a valid JSON, no explanation, no markdown
- Score each criterion from 0 to 100:
  - coherence_poste: is the letter coherent with the job domain and position?
  - competences: does the candidate mention skills relevant to the job offer?
  - experience: does the candidate mention experience DIRECTLY RELEVANT to THIS specific position?
    IMPORTANT: experience in a different domain (e.g. DevOps for an ERP position)
    must receive a score ≤ 25, even if the candidate has many years of experience.
    Only experience in the same domain as the position counts.
  - personnalisation: is the letter personalized for THIS specific position?
  {qualite_instruction}
- competences_citees: list ONLY skills/technologies EXPLICITLY mentioned in the letter text.
  DO NOT include skills inferred from the job offer or from the candidate's CV.
  If a skill does not appear word for word in the letter, do NOT include it. Maximum 10 items.
- points_forts: list of short factual items extracted ONLY FROM THE LETTER (max 4)
  CORRECT EXAMPLE   : ["3 years ERP experience", "Microsoft certification", "AL development"]
  INCORRECT EXAMPLE : ["Well-written letter", "Motivated candidate"]
  → ONLY facts from the candidate's background MENTIONED in the letter, not judgments

Expected JSON format:
{{
  "coherence_poste": 80,
  "competences": 70,
  "experience": 75,
  "personnalisation": 60,
  "qualite": 85,
  "competences_citees": ["Python", "Django", "REST API"],
  "points_forts": ["ERP experience", "Backend technologies"]
}}"""


# ─────────────────────────────────────────
# CALCUL SCORE PONDÉRÉ
# ─────────────────────────────────────────

def _calculate_score(criteres: dict) -> int:
    """
    Calcule le score final pondéré depuis les critères LLM.

    score = coherence(35%) + competences(25%) + experience(20%)
          + motivation(12%) + qualite(8%)
    """
    score = 0.0
    for critere, poids in WEIGHTS.items():
        valeur = criteres.get(critere, 0)
        # Sécurité : s'assurer que la valeur est dans [0, 100]
        valeur = max(0, min(100, int(valeur)))
        score += valeur * poids

    return round(score)


# ─────────────────────────────────────────
# PERTINENCE POSTE
# ─────────────────────────────────────────

def _get_pertinence(score: int) -> str:
    """Convertit le score numérique en label qualitatif.
    
    Niveaux :
      élevée     : score ≥ 70  → candidat pertinent
      moyenne    : score ≥ 40  → candidat partiellement pertinent
      faible     : score ≥ 20  → candidat peu pertinent
      très faible: score <  20 → candidat hors sujet (total mismatch)
    """
    if score >= SEUIL_ELEVEE:
        return "élevée"
    elif score >= SEUIL_MOYENNE:
        return "moyenne"
    elif score >= SEUIL_TRES_FAIBLE:
        return "faible"
    return "très faible"


# ─────────────────────────────────────────
# APPEL LLM
# ─────────────────────────────────────────

def _call_llm(prompt: str) -> Optional[dict]:
    """
    Appelle le LLM Groq avec 3 tentatives.
    Retourne le dict JSON parsé ou None si échec.
    """
    for attempt in range(MAX_ATTEMPTS):
        try:
            logger.info(f"Appel LLM motivation — tentative {attempt + 1}/{MAX_ATTEMPTS}")

            response = client.chat.completions.create(
                model=LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=TEMPERATURE,
                max_tokens=MAX_TOKENS,
                timeout=60,
            )

            raw = response.choices[0].message.content.strip()

            # Supprimer balises think (DeepSeek R1)
            raw = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()

            # Supprimer markdown code blocks
            if "```" in raw:
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]

            # Nettoyer les escapes invalides
            raw = re.sub(r'\\(?!["\\/bfnrt]|u[0-9a-fA-F]{4})', '', raw)

            parsed = json.loads(raw)
            logger.info("JSON LLM motivation valide reçu")
            return parsed

        except json.JSONDecodeError:
            logger.warning(f"JSON invalide — tentative {attempt + 1}/{MAX_ATTEMPTS}")
            if attempt == MAX_ATTEMPTS - 1:
                logger.error("LLM a retourné un JSON invalide après 3 tentatives")
            continue

        except Exception as e:
            err = str(e)
            # Rate limit Groq
            if "429" in err or "rate_limit" in err:
                logger.error(f"Rate limit Groq : {err}")
                return None
            logger.error(f"Erreur LLM : {err}")
            if attempt == MAX_ATTEMPTS - 1:
                return None
            continue

    return None


# ─────────────────────────────────────────
# VALIDATION RÉSULTAT LLM
# ─────────────────────────────────────────

def _validate_llm_result(data: dict, auto_qualite: Optional[int]) -> dict:
    """
    Valide et nettoie le résultat LLM.
    - S'assure que tous les critères sont présents [0-100]
    - Applique auto_qualite si défini
    - Nettoie competences_citees et points_forts
    """
    criteres = {}
    for critere in WEIGHTS.keys():
        val = data.get(critere)
        try:
            val = max(0, min(100, int(val)))
        except (TypeError, ValueError):
            val = 50  # valeur par défaut si manquant
        criteres[critere] = val

    # Appliquer qualite automatique si lettre courte
    if auto_qualite is not None:
        criteres["qualite"] = auto_qualite

    # Nettoyer competences_citees
    competences = data.get("competences_citees") or []
    if isinstance(competences, list):
        competences = [str(c).strip() for c in competences if c and str(c).strip()][:10]
    else:
        competences = []

    # Nettoyer points_forts
    points_forts = data.get("points_forts") or []
    if isinstance(points_forts, list):
        points_forts = [str(p).strip() for p in points_forts if p and str(p).strip()][:4]
    else:
        points_forts = []

    return {
        "criteres"        : criteres,
        "competences_citees": competences,
        "points_forts"    : points_forts,
    }


# ─────────────────────────────────────────
# FONCTION PRINCIPALE
# ─────────────────────────────────────────

def _build_justification(
    criteres       : dict,
    skills_overlap : dict,
    generic_info   : dict,
    nb_mots        : int,
    langue         : str,
) -> list:
    """Génère des justifications factuelles sans LLM."""
    justifications = []
    matched = skills_overlap.get("matched", 0)
    total   = skills_overlap.get("total", 0)
    if matched == 0 and total > 0:
        justifications.append(
            f"Aucune compétence de l'offre trouvée dans la lettre ({total} requises)"
        )
    elif matched > 0:
        pct = int(matched / total * 100) if total else 0
        justifications.append(
            f"{matched}/{total} compétences de l'offre mentionnées ({pct}%)"
        )
    niveau = generic_info.get("niveau", "")
    if niveau == "generique_total":
        justifications.append(
            "Lettre générique — ni l'entreprise, ni le poste, ni les compétences cités"
        )
    elif niveau == "generique_partiel":
        justifications.append("Lettre semi-personnalisée — entreprise ou poste non mentionné")
    else:
        justifications.append("Lettre personnalisée — entreprise et poste identifiés")
    if nb_mots < 50:
        justifications.append(f"Lettre très courte ({nb_mots} mots) — analyse limitée")
    elif nb_mots < 100:
        justifications.append(f"Lettre courte ({nb_mots} mots)")
    else:
        justifications.append(f"Lettre de longueur adéquate ({nb_mots} mots)")
    coherence = criteres.get("coherence_poste", 0)
    if coherence <= 25:
        justifications.append("Domaine de la lettre éloigné du poste demandé")
    elif coherence <= 50:
        justifications.append("Domaine de la lettre partiellement lié au poste")
    else:
        justifications.append("Domaine de la lettre cohérent avec le poste")
    if langue == "en":
        justifications.append("Lettre rédigée en anglais")
    elif langue == "fr":
        justifications.append("Lettre rédigée en français")
    else:
        justifications.append("Langue de la lettre mixte ou indéterminée")
    return justifications


def analyze_motivation_letter(
    letter_path    : str,
    job_title      : str,
    job_description: str,
    job_skills     : str,
    job_company    : str = "",
    job_lang       : str = "",   # BUG-LANG FIX : langue du job depuis DB (évite recalcul sur titre EN)
) -> Optional[dict]:
    """
    Analyse la lettre de motivation et retourne un score structuré.

    Args:
        letter_path     : chemin vers le PDF de la lettre
        job_title       : titre du poste (Job.title)
        job_description : description du poste (Job.description)
        job_skills      : compétences requises (Job.skills_required)

    Returns:
        dict avec score et détails, ou None si lettre illisible

    Exemple :
        result = analyze_motivation_letter(
            letter_path     = "uploads/lettre.pdf",
            job_title       = "Développeur Business Central",
            job_description = "Développement extensions AL...",
            job_skills      = "AL Language, SQL Server, API REST",
        )
        # result = {
        #   "score_motivation"  : 74,
        #   "pertinence_poste"  : "élevée",
        #   "competences_citees": ["AL Language", "SQL"],
        #   "points_forts"      : ["Expérience ERP", "3 ans BC"],
        #   "langue"            : "fr",
        #   "nb_mots"           : 250,
        #   "detail_criteres"   : { ... }
        # }
    """
    # ── Nettoyage paramètres (Point 6) ── AVANT toute utilisation ──────
    job_title       = (job_title       or "").strip()
    job_description = (job_description or "").strip()
    job_skills      = (job_skills      or "").strip()
    job_company     = (job_company     or "").strip()

    logger.info(f"Analyse lettre motivation : '{letter_path}'")
    logger.info(f"Poste : '{job_title}'")

    # ── Étape 1 : Extraction texte PDF ───────────────────────────────
    letter_text = _extract_letter_text(letter_path)
    if not letter_text:
        logger.warning("Lettre illisible → score_motivation = None")
        return None

    # ── Étape 2 : Comptage mots ───────────────────────────────────────
    nb_mots = _count_words(letter_text)
    logger.info(f"Lettre : {nb_mots} mots")

    # ── Étape 3 : Détection langue ────────────────────────────────────
    langue = _detect_language(letter_text)
    logger.info(f"Langue détectée : {langue}")

    # ── Étape 4 : Score qualité automatique si courte ────────────────
    auto_qualite = _auto_quality_score(nb_mots)

    # ── Étape 4b : Détection lettre générique ────────────────────────
    generic_info = _detect_generic_letter(
        letter_text    = letter_text,
        job_title      = job_title,
        job_description= job_description,
        job_skills     = job_skills,
        job_company    = job_company,
    )

    # ── Étape 4c : Vérification Python déterministe des compétences ────────
    skills_overlap = _check_skills_overlap(letter_text, job_skills)

    # ── Étape 5 : Construction prompt ────────────────────────────────
    job_title       = (job_title       or "").strip()
    job_description = (job_description or "").strip()
    job_skills      = (job_skills      or "").strip()

    if langue == "en":
        prompt = _build_prompt_en(
            letter_text, job_title, job_description, job_skills, auto_qualite
        )
        logger.info("Prompt sélectionné : ANGLAIS")
    else:
        prompt = _build_prompt_fr(
            letter_text, job_title, job_description, job_skills, auto_qualite
        )
        logger.info("Prompt sélectionné : FRANÇAIS")

    # ── Étape 6 : Appel LLM ──────────────────────────────────────────
    llm_result = _call_llm(prompt)
    if llm_result is None:
        logger.error("LLM a échoué après 3 tentatives → None")
        return None

    # ── Étape 7 : Validation et nettoyage ────────────────────────────
    validated = _validate_llm_result(llm_result, auto_qualite)
    criteres        = validated["criteres"]
    competences     = validated["competences_citees"]
    # Filtrer phrases génériques dans points_forts
    _GENERIC_TERMS = [
        "managed", "experience", "knowledge", "skills", "ability",
        "worked", "used", "good", "strong", "excellent",
        "géré", "expérience", "connaissance", "compétences",
        "travaillé", "utilisé", "bonne", "forte",
    ]
    def _is_generic_phrase(p: str) -> bool:
        pl = p.lower()
        # Phrase générique si : < 5 mots OU contient termes creux
        if len(pl.split()) < 4:
            return True
        return any(t in pl for t in _GENERIC_TERMS)

    points_forts = list(dict.fromkeys(
        p for p in validated["points_forts"]
        if not _is_generic_phrase(p)
    )) or validated["points_forts"][:2]  # fallback si tout filtré

    # ── Étape 7a : Appliquer plafonds skills overlap (déterministe) ─────
    p_coh = skills_overlap.get("plafond_coherence")
    p_com = skills_overlap.get("plafond_competences")
    if p_coh is not None and criteres.get("coherence_poste", 0) > p_coh:
        old_val = criteres["coherence_poste"]
        criteres["coherence_poste"] = p_coh
        logger.info(
            f"  [skills-overlap] Plafond coherence : {old_val} → {p_coh} "
            f"({skills_overlap['matched']}/{skills_overlap['total']} skills)"
        )
    if p_com is not None and criteres.get("competences", 0) > p_com:
        old_val = criteres["competences"]
        criteres["competences"] = p_com
        logger.info(
            f"  [skills-overlap] Plafond competences : {old_val} → {p_com}"
        )

    # ── Étape 7b : Appliquer pénalité lettre générique ──────────────
    plafond = generic_info.get("plafond_motivation")
    if plafond is not None:
        old_motivation = criteres.get("personnalisation", 0)
        if old_motivation > plafond:
            criteres["personnalisation"] = plafond
            logger.info(
                f"  [generic] Pénalité appliquée : "
                f"personnalisation {old_motivation} → {plafond} "
                f"(niveau: {generic_info['niveau']})"
            )

    # ── Étape 7b2 : Détection profil junior (flag uniquement) ──────────
    # Le plafond sera appliqué APRÈS _calculate_score (étape 8b)
    junior_signals = [
        "stage", "stagiaire", "étudiant", "pfe",
        "fin d'études", "licence", "master 1", "bachelor",
        "intern", "student", "internship", "graduate", "entry level",
        "first experience", "première expérience",
    ]
    is_junior_letter = any(sig in letter_text.lower() for sig in junior_signals)
    if is_junior_letter:
        logger.debug("  [seniority] Profil junior détecté dans la lettre")

    # ── Étape 7c : Plafond experience si domaine incohérent ──────────
    coherence = criteres.get("coherence_poste", 0)
    if coherence < 30:
        old_exp = criteres.get("experience", 0)
        if old_exp > 30:
            criteres["experience"] = 30
            logger.info(
                f"  [domain] Plafond experience : {old_exp} → 30 "
                f"(coherence={coherence} < 30 → domaine incohérent)"
            )

    # ── Étape 7d : Pénalité qualité si lettre courte + générique ──────
    if nb_mots < 80 and generic_info.get("lettre_generique"):
        old_qual = criteres.get("qualite", 0)
        if old_qual > 40:
            criteres["qualite"] = 40
            logger.info(
                f"  [quality] Pénalité qualité : {old_qual} → 40 "
                f"(lettre courte {nb_mots} mots + générique)"
            )

    # ── Étape 7d2 : Pénalité légère si langue lettre ≠ langue job ──────
    # La langue du job est inférée depuis job_title et job_description
    # BUG-LANG FIX : utiliser job_lang depuis DB si fourni, sinon détecter depuis texte
    langue_job = job_lang if job_lang in ("fr", "en") else _detect_language(job_title + " " + job_description)
    if langue in ("fr", "en") and langue_job in ("fr", "en") and langue != langue_job:
        old_perso = criteres.get("personnalisation", 0)
        if old_perso > 55:
            criteres["personnalisation"] = max(55, old_perso - 10)
            logger.info(
                f"  [langue] Mismatch langue : lettre={langue} ≠ job={langue_job} "
                f"→ personnalisation {old_perso} → {criteres['personnalisation']}"
            )

    # ── Étape 7e : Flag pénalité globale si 0 compétence + hors domaine
    penalite_globale = (
        skills_overlap.get("matched", 0) == 0
        and criteres.get("coherence_poste", 0) < 25
    )
    if penalite_globale:
        logger.info(
            "  [penalty] Pénalité globale activée : "
            "0 compétence + coherence < 25"
        )

    # ── Étape 7f : Spécificité avancée (protection lettres IA/génériques) ──
    # Combine 3 signaux pour mesurer la profondeur réelle de la lettre
    spec_score = 0

    # Signal 1 : chiffres concrets (3 ans, 5 clients, 12 objets AL...)
    spec_score += len(re.findall(r'\b\d+\b', letter_text))

    # Signal 2 : phrases longues = explication réelle (> 10 mots)
    spec_score += sum(
        1 for s in letter_text.split('.')
        if len(s.split()) > 10
    )

    # Signal 3 : verbes d'action = expérience concrète
    action_verbs_fr = [
        "développé", "implémenté", "intégré", "conçu", "déployé",
        "migré", "créé", "géré", "optimisé", "configuré",
    ]
    action_verbs_en = [
        "developed", "implemented", "integrated", "designed", "deployed",
        "migrated", "created", "managed", "optimized", "configured",
    ]
    all_verbs = action_verbs_fr + action_verbs_en
    spec_score += sum(1 for v in all_verbs if v in letter_text.lower())

    logger.info(f"  [specificity] score={spec_score} (chiffres/phrases/verbes)")

    # Pénalité si lettre FAUSSEMENT personnalisée (superficielle mais matches≥2)
    # Ne s'applique PAS si déjà pénalisée comme générique (évite double pénalité)
    if (
        generic_info.get("matches", 0) >= 2
        and spec_score < 3
        and not generic_info.get("lettre_generique", False)
    ):
        old_perso = criteres.get("personnalisation", 0)
        if old_perso > 40:
            criteres["personnalisation"] = 40
            logger.info(
                f"  [specificity] personnalisation pénalisée : "
                f"{old_perso} → 40 (faussement personnalisée, superficielle)"
            )

    # ── Étape 8 : Calcul score final ─────────────────────────────────
    score_final = _calculate_score(criteres)

    # Plafond global si très peu de contenu concret (après calcul !)
    if spec_score < 4 and score_final > 70:
        old_score = score_final
        score_final = 70
        logger.info(
            f"  [specificity] Score plafonné : {old_score} → 70 "
            f"(spécificité={spec_score} < 4 — lettre peu concrète)"
        )

    # ── Étape 8b : Seniority cap APRÈS calcul ────────────────────────
    if is_junior_letter and score_final > 65:
        score_avant_junior = score_final
        score_final = min(score_final, 65)
        logger.info(
            f"  [seniority] Profil junior → score plafonné : "
            f"{score_avant_junior} → {score_final}"
        )

    # Appliquer pénalité globale × 0.7 si 0 skill + domaine hors sujet
    if penalite_globale and score_final > 15:
        score_avant = score_final
        score_final = round(score_final * 0.7)
        logger.info(
            f"  [penalty] Score pénalisé : {score_avant} × 0.7 = {score_final}"
        )
    # ── Hard gate métier (comportement RH réel) ─────────────────────────
    # Si hors domaine total ET 0 compétence → cap à 20 comme un RH le ferait
    # Référence dataset : D13 frontend=31 (RH=12), D14 cloud=35 (RH=15)
    if (criteres.get("coherence_poste", 0) < 25
            and skills_overlap.get("matched", 0) == 0
            and score_final > 20):
        score_avant_gate = score_final
        score_final = 20
        logger.info(
            f"  [hard-gate] Score plafonné : {score_avant_gate} → 20 "
            f"(coherence<25 + 0 skill → rejet métier)"
        )

    pertinence  = _get_pertinence(score_final)

    logger.info(
        f"Score motivation : {score_final}/100 — pertinence : {pertinence} "
        f"| détail : {criteres}"
    )

    # ── Résultat final ────────────────────────────────────────────────
    justifications = _build_justification(
        criteres=criteres, skills_overlap=skills_overlap,
        generic_info=generic_info, nb_mots=nb_mots, langue=langue,
    )
    # Signal exploitable par le matching_agent
    if score_final >= 70:
        signal_motivation = "strong"
    elif score_final >= 40:
        signal_motivation = "medium"
    else:
        signal_motivation = "weak"

    result = {
        "score_motivation"  : score_final,
        "signal_motivation" : signal_motivation,
        "pertinence_poste"  : pertinence,
        "lettre_generique"  : generic_info["lettre_generique"],
        "competences_citees": competences,
        "points_forts"      : points_forts,
        "justification"     : justifications,
        "langue"            : langue,
        "nb_mots"           : nb_mots,
        "detail_criteres"   : criteres,
    }

    return result


# ─────────────────────────────────────────
# INTÉGRATION FASTAPI — helper
# ─────────────────────────────────────────

def run_motivation_agent(
    letter_path    : str,
    job_title      : str,
    job_description: str,
    job_skills     : str,
    job_company    : str = "",
    job_lang       : str = "",   # BUG-LANG FIX : passer job.lang depuis applications.py
    application_id : int = 0,
    db             = None,
) -> dict:
    """
    Wrapper pour l'intégration FastAPI/applications.py.

    Appelle analyze_motivation_letter() puis :
    - Sauvegarde score dans Application.score_motivation
    - Sauvegarde détail complet dans IA_Log

    BUG-2 FIX : retourne toujours un dict — jamais None.
      analyze_motivation_letter() peut retourner None si :
        - PDF illisible / introuvable
        - LLM échoue après 3 tentatives (Groq timeout / quota)
      Avant : result["score_motivation"] → TypeError si result=None
      Après : fallback_result utilisé → score=50, signal=medium
              Application.status conservé EN_ATTENTE, revue manuelle

    Args:
        letter_path, job_title, job_description, job_skills : données
        application_id : ID de la candidature en BDD
        db             : session SQLAlchemy (Depends(get_db))

    Returns:
        dict résultat — toujours non-None
    """
    from app.models import Application, IA_Log
    import json as _json

    # ── Fallback result si analyze_motivation_letter retourne None ────────
    # Causes possibles : PDF illisible, LLM timeout, quota Groq épuisé
    FALLBACK_RESULT = {
        "score_motivation"  : 50,          # score neutre → pas de pénalité injuste
        "signal_motivation" : "medium",
        "pertinence_poste"  : "moyenne",
        "lettre_generique"  : False,
        "competences_citees": [],
        "points_forts"      : [],
        "justification"     : {
            "warning": "Analyse lettre indisponible — LLM inaccessible ou PDF illisible.",
        },
        "langue"            : "inconnu",
        "nb_mots"           : 0,
        "detail_criteres"   : {},
        "error"             : True,
        "error_reason"      : "analyze_motivation_letter a retourné None",
    }

    try:
        result = analyze_motivation_letter(
            letter_path     = letter_path,
            job_title       = job_title,
            job_description = job_description,
            job_skills      = job_skills,
            job_company     = job_company,
            job_lang        = job_lang,   # BUG-LANG FIX
        )
    except Exception as e:
        logger.error(
            f"  [motivation] Exception inattendue application_id={application_id} : {e}",
            exc_info=True,
        )
        result = None

    # BUG-2 FIX : utiliser le fallback si None
    if result is None:
        logger.warning(
            f"  [motivation] analyze_motivation_letter a retourné None "
            f"(application_id={application_id}) → fallback score=50 utilisé"
        )
        result = FALLBACK_RESULT

    # ── Sauvegarder dans Application ──────────────────────────────────────
    if db:
        application = db.query(Application).filter(
            Application.id == application_id
        ).first()

        if application:
            application.score_motivation = float(result["score_motivation"])
            db.commit()
            logger.info(
                f"Application {application_id} : "
                f"score_motivation = {application.score_motivation}"
                + (" [FALLBACK]" if result.get("error") else "")
            )
        else:
            logger.warning(
                f"  [motivation] Application {application_id} introuvable "
                f"— score_motivation non sauvegardé"
            )

        # ── Sauvegarder dans IA_Log ────────────────────────────────────────
        log = IA_Log(
            application_id = application_id,
            agent_name     = "motivation_agent",
            output_json    = _json.dumps(result, ensure_ascii=False),
        )
        db.add(log)
        db.commit()
        logger.info(f"IA_Log sauvegardé — agent: motivation_agent, app: {application_id}")

    return result


# ─────────────────────────────────────────
# MAIN — test standalone
# ─────────────────────────────────────────

if __name__ == "__main__":
    import sys

    # Test avec fichier réel si fourni
    if len(sys.argv) >= 2:
        path = sys.argv[1]
    else:
        # Test avec texte simulé (sans PDF)
        print("Usage : python motivation_agent.py <lettre.pdf>")
        print("\nTest avec données simulées...\n")

        # Simuler une extraction de texte
        fake_letter = """
        Madame, Monsieur,

        Je vous adresse ma candidature pour le poste de Développeur Business Central AL
        au sein de votre entreprise.

        Titulaire d'une Licence en Génie Logiciel, j'ai acquis une solide expérience
        de 3 ans en développement AL sur Microsoft Dynamics 365 Business Central.
        J'ai notamment développé des extensions AL pour des clients dans les secteurs
        distribution et retail, en utilisant les technologies API REST Business Central,
        SQL Server et Azure DevOps.

        Mon expérience chez Novelis IT m'a permis de maîtriser le cycle complet de
        développement BC, de la conception à la mise en production.

        Je suis convaincu que mon profil correspond aux besoins de votre équipe.

        Cordialement,
        Amine Slimani
        """

        # Test direct sans PDF
        nb_mots    = _count_words(fake_letter)
        langue     = _detect_language(fake_letter)
        auto_q     = _auto_quality_score(nb_mots)

        print(f"Nb mots    : {nb_mots}")
        print(f"Langue     : {langue}")
        print(f"Auto qualite: {auto_q}")

        prompt = _build_prompt_fr(
            fake_letter,
            "Développeur Business Central AL",
            "Développement d'extensions AL sur Dynamics 365 BC pour clients B2B.",
            "AL Language, SQL Server, API REST, Azure DevOps",
            auto_q,
        )

        print("\nAppel LLM...")
        llm_result = _call_llm(prompt)

        if llm_result:
            validated   = _validate_llm_result(llm_result, auto_q)
            score_final = _calculate_score(validated["criteres"])
            pertinence  = _get_pertinence(score_final)

            result = {
                "score_motivation"  : score_final,
                "pertinence_poste"  : pertinence,
                "competences_citees": validated["competences_citees"],
                "points_forts"      : validated["points_forts"],
                "langue"            : langue,
                "nb_mots"           : nb_mots,
                "detail_criteres"   : validated["criteres"],
            }

            print("\n" + "="*50)
            print("RÉSULTAT ANALYSE LETTRE MOTIVATION")
            print("="*50)
            print(f"Score         : {result['score_motivation']} / 100")
            print(f"Pertinence    : {result['pertinence_poste']}")
            print(f"Langue        : {result['langue']}")
            print(f"Nb mots       : {result['nb_mots']}")
            print(f"Compétences   : {result['competences_citees']}")
            print(f"Points forts  : {result['points_forts']}")
            print(f"Détail        : {result['detail_criteres']}")
            print("="*50)
        else:
            print("❌ LLM a échoué")