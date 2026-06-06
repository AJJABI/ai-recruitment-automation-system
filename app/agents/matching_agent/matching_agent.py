"""
matching_agent.py — Agent 3 : Matching CV ↔ Offre

Pipeline :
  1.  Construction textes CV décorrélés (sémantique / skills)
  2.  Construction texte offre sémantique
  3.  Embedding sémantique (sentence-transformers) + fallback TF-IDF
  4.  Cosine similarity CV ↔ offre
  5.  Skills match déterministe avec synonymes + densité
  6.  Expérience match graduée (années + domaine)
  7.  Score matching (0.5×skills + 0.3×sim + 0.2×exp)
  8.  Overrides absolus (avant fusion)
  9.  Score final (0.6×matching + 0.4×motivation)
 10.  Ajustements score (hard rules plafond/plancher)
 11.  Décision finale (ENTRETIEN / EN_ATTENTE / REJETÉ)
 12.  Signal final combiné (strong / medium / weak / risk)
 13.  Justification structurée + confidence_score
 14.  Logging complet IA_Log
"""
import re
import json
import logging
import unicodedata
from typing import Optional

from sklearn.metrics.pairwise import cosine_similarity as sklearn_cosine

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────
# CONSTANTES CONFIGURABLES
# ─────────────────────────────────────────────────────────────────

SEUIL_ENTRETIEN = 70
SEUIL_ATTENTE   = 40

# Pondération score matching
# FIX-2/10 : skills > sim, textes décorrélés → pas de double comptage
POIDS_SKILLS     = 0.50
POIDS_SEMANTIQUE = 0.30
POIDS_EXPERIENCE = 0.20

# Pondération fusion finale
POIDS_MATCHING   = 0.60
POIDS_MOTIVATION = 0.40

MODELE_EMBEDDING = "paraphrase-multilingual-mpnet-base-v2"

# FIX-19 : seuil densité — nb occurrences pour considérer un skill "pratiqué"
SKILL_DENSITY_THRESHOLD = 3

# FIX-22 : dénominateur pondération fréquence skills dans le score
# score_skill_i = min(1.0, occurrences_i / SKILL_WEIGHTED_DENOM)
# 1 mention → 0.33  |  2 mentions → 0.67  |  3+ mentions → 1.0
SKILL_WEIGHTED_DENOM = 3.0

# FIX-E : seuil détection keyword stuffing
# Si total_skill_mentions / total_words > ce seuil → spam suspect
# Seuil empirique — à recalibrer sur dataset réel
KEYWORD_STUFFING_THRESHOLD = 0.15

# ─────────────────────────────────────────────────────────────────
# SYNONYMES SKILLS
# ─────────────────────────────────────────────────────────────────

SKILL_SYNONYMS: dict[str, list[str]] = {
    "sql server"                 : ["t-sql", "tsql", "ssms", "mssql"],
    "al language"                : ["al lang", "business central al"],
    "appsource"                  : ["app source", "ms appsource"],
    "api rest business central"  : ["api rest bc", "rest api bc", "bc api", "odata bc"],
    "azure devops"               : ["devops", "azure pipelines", "ado"],
    "business central"           : ["d365 bc", "ms bc"],                   # FIX-B : "dynamics 365 bc" retiré (faux positif — "dynamics"+"365" trop ambigus séparément)
    "c/al"                       : ["cal", "classic al", "c-al"],
    "dynamics nav"               : ["nav", "navision"],
    "odata"                      : ["odata v4", "odata services"],
    "t-sql"                      : ["tsql", "stored procedures"],
    "power bi"                   : ["powerbi", "power-bi"],
    "machine learning"           : ["ml", "apprentissage automatique"],
    "deep learning"              : ["dl", "reseau neuronal", "neural network"],
    "natural language processing": ["nlp", "traitement du langage"],
}

# ─────────────────────────────────────────────────────────────────
# SINGLETON EMBEDDING + CACHE JOB (FIX-14)
# ─────────────────────────────────────────────────────────────────

_embedding_model                    = None
_fallback_mode                      = False
_job_embed_cache: dict[int, object] = {}


def _load_embedding_model():
    """
    Charge sentence-transformers une seule fois (singleton).
    Fallback TF-IDF transparent si modèle indisponible.
    Système ne tombe jamais.
    """
    global _embedding_model, _fallback_mode

    if _embedding_model is not None:
        return _embedding_model

    try:
        from sentence_transformers import SentenceTransformer
        _embedding_model = SentenceTransformer(MODELE_EMBEDDING)
        _fallback_mode   = False
        logger.info(f"Modèle embedding chargé : {MODELE_EMBEDDING}")
    except Exception as e:
        logger.warning(
            f"sentence-transformers non disponible ({e}) → fallback TF-IDF activé"
        )
        _embedding_model = "tfidf"
        _fallback_mode   = True

    return _embedding_model


# ─────────────────────────────────────────────────────────────────
# NORMALISATION TEXTE
# ─────────────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """Minuscules, sans accents, espaces normalisés."""
    text = text.lower().strip()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"\s+", " ", text)
    return text


# ─────────────────────────────────────────────────────────────────
# CONSTRUCTION TEXTES DÉCORRÉLÉS (FIX-10)
#
# Deux textes CV distincts :
#   _build_cv_text_semantic → embedding (expériences, certifs, formation)
#                             SANS liste brute skills
#   _build_cv_text_skills   → matching skills (liste + achievements)
#                             SANS descriptions narratives
#   _build_job_text_semantic → embedding (titre + description)
#                              SANS skills_required
#
# Raison : évite que skills soit compté deux fois (biais CV verbeux)
# ─────────────────────────────────────────────────────────────────

def _build_cv_text_semantic(cv_profile: dict) -> str:
    """
    Texte CV pour embedding : parcours, certifs, formation. Pas de liste skills.
    FIX-C : intègre le champ projects[] structuré (nom + description).
            Les projets personnels enrichissent le signal sémantique sans
            biaiser le matching skills (texte séparé).
    """
    parts = []

    for exp in (cv_profile.get("professional_experience", []) or []):
        if exp.get("role"):    parts.append(exp["role"])
        if exp.get("company"): parts.append(exp["company"])
        for ach in (exp.get("achievements", []) or []):
            if ach: parts.append(str(ach))

    for intern in (cv_profile.get("internships", []) or []):
        if intern.get("role"): parts.append(intern["role"])
        for ach in (intern.get("achievements", []) or []):
            if ach: parts.append(str(ach))

    for alt in (cv_profile.get("alternance", []) or []):
        if alt.get("role"): parts.append(alt["role"])
        for ach in (alt.get("achievements", []) or []):
            if ach: parts.append(str(ach))

    for cert in (cv_profile.get("certifications", []) or []):
        if cert.get("name"): parts.append(cert["name"])

    for edu in (cv_profile.get("education", []) or []):
        if edu.get("degree"): parts.append(edu["degree"])

    # FIX-C : projets structurés → signal sémantique (nom + description)
    # Pas les technologies (évite double comptage avec cv_text_skills)
    for proj in (cv_profile.get("projects", []) or []):
        if not isinstance(proj, dict):
            continue
        if proj.get("name"):        parts.append(proj["name"])
        if proj.get("description"): parts.append(proj["description"])

    years = cv_profile.get("years_experience", 0) or 0
    if years:
        parts.append(f"{years} ans experience")

    text = " ".join(p for p in parts if p.strip())
    logger.debug(f"  [matching] CV semantic text ({len(text)} chars)")
    return text


def _build_cv_text_skills(cv_profile: dict) -> str:
    """
    Texte CV pour matching skills : liste skills + achievements. Pas de descriptions.
    FIX-C : intègre les technologies des projets structurés.
            Un projet "Stock Manager" avec technologies=["Python","Flask","SQL Server"]
            contribue au matching skills exactement comme un achievement d'expérience.
    """
    parts = []

    skills    = cv_profile.get("skills", {}) or {}
    technical = skills.get("technical", []) or []
    tools     = skills.get("tools", [])     or []

    parts.extend(str(s) for s in technical if s)
    parts.extend(str(t) for t in tools     if t)

    for exp in (cv_profile.get("professional_experience", []) or []):
        for ach in (exp.get("achievements", []) or []):
            if ach: parts.append(str(ach))

    for intern in (cv_profile.get("internships", []) or []):
        for ach in (intern.get("achievements", []) or []):
            if ach: parts.append(str(ach))

    for alt in (cv_profile.get("alternance", []) or []):
        for ach in (alt.get("achievements", []) or []):
            if ach: parts.append(str(ach))

    # FIX-C : technologies des projets structurés → matching skills
    # Pas le nom/description (évite double comptage avec cv_text_semantic)
    for proj in (cv_profile.get("projects", []) or []):
        if not isinstance(proj, dict):
            continue
        for tech in (proj.get("technologies", []) or []):
            if tech: parts.append(str(tech))
        # Les achievements projet (ex: "Développé une API REST BC") contribuent aussi
        for ach in (proj.get("achievements", []) or []):
            if ach: parts.append(str(ach))

    return _normalize(" ".join(p for p in parts if p.strip()))


def _build_job_text_semantic(job: dict) -> str:
    """Texte offre pour embedding : titre + description. Pas de skills_required."""
    parts = []
    for key in ("title", "description", "company"):
        val = job.get(key, "") or ""
        if val.strip():
            parts.append(val)
    text = " ".join(parts)
    logger.debug(f"  [matching] Job semantic text ({len(text)} chars)")
    return text


# ─────────────────────────────────────────────────────────────────
# SIMILARITÉ SÉMANTIQUE
# ─────────────────────────────────────────────────────────────────

def _compute_similarity(
    cv_text : str,
    job_text: str,
    job_id  : int = 0,
) -> tuple[float, bool]:
    """
    Similarité cosine sur textes décorrélés.
    FIX-14 : cache embedding job par job_id.

    Returns : (similarity 0.0-1.0, fallback_used bool)
    """
    model = _load_embedding_model()

    if model == "tfidf":
        return _tfidf_similarity(cv_text, job_text)

    try:
        cv_vec = model.encode(cv_text)

        if job_id and job_id in _job_embed_cache:
            job_vec = _job_embed_cache[job_id]
            logger.debug(f"  [matching] Cache hit embedding job_id={job_id}")
        else:
            job_vec = model.encode(job_text)
            if job_id:
                _job_embed_cache[job_id] = job_vec

        sim = float(sklearn_cosine([cv_vec], [job_vec])[0][0])
        logger.info(f"  [matching] Embedding similarity : {sim:.3f}")
        return sim, False

    except Exception as e:
        logger.error(f"  [matching] Embedding échoué ({e}) → TF-IDF fallback")
        return _tfidf_similarity(cv_text, job_text)


def _tfidf_similarity(cv_text: str, job_text: str) -> tuple[float, bool]:
    """
    Fallback TF-IDF.
    ⚠ Limites connues : pas de compréhension contextuelle, dépend du
    vocabulaire exact, biais linguistique important.
    "Business Central" vs "ERP Microsoft BC" → peut rater.
    Scores TF-IDF non comparables aux scores embedding.
    """
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        vec   = TfidfVectorizer(ngram_range=(1, 2), max_features=5000)
        tfidf = vec.fit_transform([cv_text, job_text])
        sim   = float(sklearn_cosine(tfidf[0], tfidf[1])[0][0])
        logger.info(f"  [matching] TF-IDF similarity : {sim:.3f}")
        return sim, True
    except Exception as e:
        logger.error(f"  [matching] TF-IDF échoué aussi ({e}) → similarity=0.0")
        return 0.0, True


# ─────────────────────────────────────────────────────────────────
# SKILLS MATCH + DENSITÉ (FIX-9, FIX-19)
# ─────────────────────────────────────────────────────────────────

def _expand_with_synonyms(skill: str) -> list[str]:
    """Retourne le skill + tous ses synonymes connus."""
    skill_lower = skill.lower().strip()
    variants    = [skill_lower]
    for canonical, synonyms in SKILL_SYNONYMS.items():
        if skill_lower == canonical or skill_lower in synonyms:
            variants.append(canonical)
            variants.extend(synonyms)
    return list(set(variants))


def _skill_present(skill: str, text_lower: str) -> bool:
    """
    Vérifie si un skill est présent dans le texte.
    FIX-4  : filtre mots ≤ 2 chars sur tous les variants.
    FIX-9  : teste toutes les paires consécutives de mots.
    FIX-B  : filtre tokens purement numériques (ex: "365" dans "dynamics 365 bc")
             → empêche "dynamics"+"365" de matcher "Microsoft Dynamics"+"Office 365"
    FIX-B  : fallback >= 2 → >= len(words) — exige TOUS les mots filtrés
             Avant : 2 mots sur N suffisaient → faux positifs sur variants longs
             Après : tous les mots significatifs doivent être présents
    """
    for variant in _expand_with_synonyms(skill):
        # FIX-B : exclure mots ≤ 2 chars ET tokens purement numériques
        words = [w for w in variant.split() if len(w) > 2 and not re.match(r'^\d+$', w)]
        if not words:
            continue

        if len(words) == 1:
            if re.search(r"\b" + re.escape(words[0]) + r"\b", text_lower):
                return True
        else:
            # FIX-9 : toutes les paires consécutives
            for i in range(len(words) - 1):
                phrase = (
                    r"\b" + re.escape(words[i])
                    + r"\s+" + re.escape(words[i + 1]) + r"\b"
                )
                if re.search(phrase, text_lower):
                    return True
            # FIX-B : Fallback — TOUS les mots doivent être présents (>= len(words))
            # Avant : >= 2 permettait des faux positifs sur variants à 3+ mots
            if sum(
                1 for w in words
                if re.search(r"\b" + re.escape(w) + r"\b", text_lower)
            ) >= len(words):
                return True

    return False


def _skill_density(skill: str, text_lower: str) -> int:
    """
    FIX-19 : compte le nombre d'occurrences d'un skill dans le texte.

    Principe :
      presence binaire (présent/absent) = biais "SQL mentionné 1 fois = SQL expert"
      La densité est un signal supplémentaire :
        count = 1     → mentionné (peut être copié/collé)
        count = 2     → probablement utilisé
        count ≥ 3     → probablement pratiqué régulièrement

    IMPORTANT : la densité n'est PAS intégrée dans le score (V2).
    Elle est utilisée uniquement dans la justification pour alerter le RH.
    Raison : intégrer la densité dans le score sans validation empirique
    risque de créer un biais "CV verbeux" incontrôlé.
    """
    count = 0
    for variant in _expand_with_synonyms(skill):
        # FIX-B : même filtre que _skill_present — numérique + longueur
        words = [w for w in variant.split() if len(w) > 2 and not re.match(r'^\d+$', w)]
        if not words:
            continue
        if len(words) == 1:
            count += len(re.findall(r"\b" + re.escape(words[0]) + r"\b", text_lower))
        else:
            for i in range(len(words) - 1):
                phrase = (
                    r"\b" + re.escape(words[i])
                    + r"\s+" + re.escape(words[i + 1]) + r"\b"
                )
                count += len(re.findall(phrase, text_lower))
    return count


def _check_skills_match(cv_text_skills: str, job_skills_str: str) -> dict:
    """
    Compare les skills du CV avec les skills requis du job.
    FIX-13 : skills_ratio = 0.5 si job sans skills (neutre).
    FIX-19 : calcule la densité de chaque skill matchée.
    FIX-22 : skills_weighted_ratio — pondère chaque skill par sa fréquence.
             score_skill_i = min(1.0, occurrences_i / 3.0)
             Réduit le biais "SQL mentionné 1 fois = SQL expert".
             C'est skills_weighted_ratio qui est utilisé dans le score matching
             à la place de skills_ratio (binaire).

    Returns:
        skills_matched        : list[str]
        skills_missing        : list[str]
        skills_ratio          : float — ratio binaire (présent/absent)
        skills_weighted_ratio : float — ratio pondéré par fréquence
        skills_high_density   : list[str] — ≥ 3 mentions
        skills_low_density    : list[str] — 1 mention seulement
    """
    job_skills = [
        s.strip().lower()
        for s in re.split(r"[,;\n]", job_skills_str)
        if s.strip() and len(s.strip()) > 1
    ]

    # FIX-13 : neutre à 0.5
    if not job_skills:
        logger.info("  [matching] Aucun skill requis → skills_ratio = 0.5 (neutre)")
        return {
            "skills_matched"            : [],
            "skills_missing"            : [],
            "skills_ratio"              : 0.5,
            "skills_weighted_ratio"     : 0.5,
            "skills_high_density"       : [],
            "skills_low_density"        : [],
            "keyword_stuffing_suspected": False,  # BUG-FIX : absent du return anticipé
        }

    matched      = []
    missing      = []
    high_density = []
    low_density  = []
    weighted_sum = 0.0   # FIX-22

    for skill in job_skills:
        if _skill_present(skill, cv_text_skills):
            matched.append(skill)
            density = _skill_density(skill, cv_text_skills)
            # FIX-22 : contribution pondérée par fréquence
            weighted_sum += min(1.0, density / SKILL_WEIGHTED_DENOM)
            if density >= SKILL_DENSITY_THRESHOLD:
                high_density.append(skill)
            else:
                low_density.append(skill)
        else:
            missing.append(skill)
            # skill absent → contribution 0 au weighted_sum

    ratio          = len(matched) / len(job_skills)
    weighted_ratio = weighted_sum  / len(job_skills)   # FIX-22

    # FIX-E (v2) : détection keyword stuffing améliorée
    #
    # PROBLÈME ORIGINAL : pénalité flat -20% s'appliquait à TOUS les profils avec
    # densité élevée, y compris les seniors légitimes avec 6 ans d'expérience.
    # En même temps, les vrais stuffers (ratio=0.96) tombaient à 0.77 → ENTRETIEN quand même.
    #
    # CORRECTIONS :
    # 1. Exemption profil légitime : skills_ratio=1.0 ET nb_certifications >= 1 → pas de pénalité
    # 2. Pénalité progressive selon ratio de stuffing (au lieu de -20% flat)
    # 3. Si stuffing confirmé ET weighted_ratio reste > 0.70 → plafonner à 0.70
    #    (empêche les vrais stuffers de passer en ENTRETIEN)
    keyword_stuffing_suspected = False
    total_words = len(cv_text_skills.split())
    if total_words > 0:
        total_skill_mentions = sum(
            _skill_density(s, cv_text_skills) for s in matched
        )
        stuffing_ratio = total_skill_mentions / total_words
        if stuffing_ratio > KEYWORD_STUFFING_THRESHOLD:
            # Vérifier si c'est un profil légitime (ne pas pénaliser les seniors)
            # Critères : tous les skills matchés ET densité justifiée par nb skills
            # Un CV de N skills peut légitimement avoir N×3 mentions (skills section + 2 exp)
            max_legitimate_ratio = (len(matched) * 3) / max(total_words, 1)
            is_legitimate_rich_profile = (
                # ratio == 1.0 and                        # tous les skills présents
                stuffing_ratio <= max_legitimate_ratio  # densité proportionnelle aux skills
            )

            if is_legitimate_rich_profile:
                # Profil riche légitime → pas de pénalité, juste signaler
                keyword_stuffing_suspected = False
                logger.info(
                    f"  [matching] Densité élevée MAIS profil légitime détecté "
                    f"(ratio={stuffing_ratio:.2f}, skills={len(matched)}/{len(matched)+len(missing)}, "
                    f"max_legitime={max_legitimate_ratio:.2f}) → pas de pénalité"
                )
            else:
                # Vrai stuffing suspect → pénalité progressive
                keyword_stuffing_suspected = True
                old_weighted = weighted_ratio
                # Pénalité progressive : plus le ratio est élevé, plus la pénalité est forte
                # stuffing_ratio 0.15-0.20 → -15% | 0.20-0.30 → -25% | > 0.30 → -40%
                if stuffing_ratio > 0.30:
                    penalty = 0.60
                elif stuffing_ratio > 0.20:
                    penalty = 0.75
                else:
                    penalty = 0.85
                weighted_ratio = weighted_ratio * penalty
                # Plafond absolu : un vrai stuffer ne peut pas dépasser 0.60 de weighted_ratio
                # Empêche les stuffers de passer ENTRETIEN même avec 7/7 skills
                weighted_ratio = min(weighted_ratio, 0.60)
                logger.warning(
                    f"  [matching] FIX-E keyword stuffing confirmé : "
                    f"{total_skill_mentions} mentions / {total_words} mots "
                    f"= {stuffing_ratio:.2f} > {KEYWORD_STUFFING_THRESHOLD} "
                    f"(max_légitime={max_legitimate_ratio:.2f}) "
                    f"→ weighted_ratio {old_weighted:.2f} → {weighted_ratio:.2f} "
                    f"(pénalité {int((1-penalty)*100)}%)"
                )

    logger.info(
        f"  [matching] Skills : {len(matched)}/{len(job_skills)} "
        f"ratio={ratio:.0%} weighted={weighted_ratio:.2f} "
        f"stuffing={keyword_stuffing_suspected} "
        f"— high={high_density[:3]} low={low_density[:3]}"
    )

    return {
        "skills_matched"            : matched,
        "skills_missing"            : missing,
        "skills_ratio"              : ratio,
        "skills_weighted_ratio"     : weighted_ratio,
        "skills_high_density"       : high_density,
        "skills_low_density"        : low_density,
        "keyword_stuffing_suspected": keyword_stuffing_suspected,
    }


# ─────────────────────────────────────────────────────────────────
# EXPÉRIENCE MATCH GRADUÉE
# ─────────────────────────────────────────────────────────────────

def _extract_years_required(desc: str) -> int:
    """
    Extrait les années requises depuis la description.
    FIX-7/11 : capte "3 ans", "3+ ans", "minimum 5 ans",
               "3-5 ans", "entre 2 et 4 ans", "junior (0-2 ans)".
    Prend le MAX. Plafond à 20.
    """
    desc_lower = desc.lower()
    candidates = []

    for m in re.finditer(r"(\d+)\+?\s*(?:ans?|years?)", desc_lower):
        candidates.append(int(m.group(1)))

    for m in re.finditer(
        r"(\d+)\s*(?:[-àa]|et)\s*(\d+)\s*(?:ans?|years?)",
        desc_lower
    ):
        candidates.append(int(m.group(1)))
        candidates.append(int(m.group(2)))

    if not candidates:
        return 0
    val = max(candidates)
    return val if val <= 20 else 0


def _extract_roles_from_cv(cv_profile: dict) -> list[str]:
    """
    FIX-23 : extrait tous les titres de postes du CV pour comparaison domaine.
    Sources : professional_experience + internships + alternance.
    """
    roles = []
    for section in ("professional_experience", "internships", "alternance"):
        for exp in (cv_profile.get(section, []) or []):
            role = (exp.get("role", "") or "").strip().lower()
            if role:
                roles.append(role)
    return roles


def _title_domain_overlap(cv_roles: list[str], job_title: str) -> float:
    """
    FIX-23 : calcule le chevauchement de mots entre les titres CV et le titre du job.
    Retourne un score 0.0-1.0.

    Principe : words in common / max(len(job_words), 1)
    Exemple :
      CV : "data analyst" | job : "data scientist"
      mots communs : {"data"} → 1/2 = 0.5 (partiel, pas identique)
      CV : "développeur business central" | job : "business central developer"
      mots communs : {"business", "central"} → 2/3 = 0.67

    Ce score est utilisé comme signal SUPPLÉMENTAIRE dans dim_domain,
    pas comme remplacement de la similarity.
    """
    if not cv_roles or not job_title:
        return 0.0

    # Mots du titre job (filtrés : > 2 chars)
    job_words = set(
        w for w in _normalize(job_title).split()
        if len(w) > 2
    )
    if not job_words:
        return 0.0

    best_overlap = 0.0
    for role in cv_roles:
        role_words = set(
            w for w in _normalize(role).split()
            if len(w) > 2
        )
        if not role_words:
            continue
        common  = len(job_words & role_words)
        overlap = common / max(len(job_words), 1)
        best_overlap = max(best_overlap, overlap)

    return best_overlap


def _compute_experience_score(
    cv_profile  : dict,
    job         : dict,
    similarity  : float,
    skills_ratio: float = 0.5,
) -> dict:
    """
    Score expérience en 2 dimensions :
      Dimension 1 — Années (60 pts max)
      Dimension 2 — Domaine (40 pts max)

    FIX-21 : dim_domain découplé de similarity.
      Avant : similarity > 0.7 → 40pts
             → similarity comptée une 2e fois (déjà dans score_matching)
             → poids effectif similarity > 30% déclaré
      Après : basé sur skills_ratio (source indépendante)
             skills_ratio > 0.5 → 40pts  (bon overlap skills = bon domaine)
             skills_ratio > 0.2 → 25pts  (overlap partiel)
             sinon              → 10pts  (hors domaine)

    FIX-23 : title_overlap comme bonus domaine
      Si les titres de postes CV correspondent au titre job → +5 pts bonus
      (corrige partiellement les faux matches sémantiques)
      domain_ok utilise maintenant title_overlap en signal supplémentaire.
    """
    years_cv       = cv_profile.get("years_experience", 0) or 0
    # BUG-16 FIX : utiliser years_professional pour la vérification d'éligibilité
    # years_experience inclut stages + pro → trompe la règle minimum requis
    # Le job demande X ans d'expérience PROFESSIONNELLE, pas de stages
    years_pro_cv   = cv_profile.get("years_professional", 0) or 0
    years_required = _extract_years_required(job.get("description", "") or "")

    # Dimension 1 — Années (60 pts max)
    # BUG-16 FIX : comparer years_pro_cv (expérience professionnelle réelle)
    # et non years_cv (qui inclut les stages)
    if years_required == 0:
        dim_years = 50
    elif years_pro_cv >= years_required:
        dim_years = 60
    elif years_pro_cv >= years_required * 0.5:
        dim_years = 40
    else:
        dim_years = 20

    # FIX-21 : dim_domain basé sur skills_ratio (découplé de similarity)
    if skills_ratio > 0.5:
        dim_domain = 40
    elif skills_ratio > 0.2:
        dim_domain = 25
    else:
        dim_domain = 10

    # FIX-23 : bonus titres (max +5 pts, plafonné à 40)
    cv_roles      = _extract_roles_from_cv(cv_profile)
    job_title     = job.get("title", "") or ""
    title_overlap = _title_domain_overlap(cv_roles, job_title)
    if title_overlap > 0.5:
        dim_domain = min(40, dim_domain + 5)

    experience_score = min(100, dim_years + dim_domain)

    # domain_ok : skills bien matchés OU titre proche
    domain_ok = (skills_ratio > 0.3) or (title_overlap > 0.4)

    logger.info(
        f"  [matching] Expérience : score={experience_score} "
        f"(années={dim_years}pts domaine={dim_domain}pts) "
        f"years_cv={years_cv} years_req={years_required} "
        f"skills_ratio={skills_ratio:.2f} title_overlap={title_overlap:.2f}"
    )

    return {
        "experience_score": experience_score,
        "years_ok"        : (years_pro_cv >= years_required) or (years_required == 0),
        "domain_ok"       : domain_ok,
        "years_cv"        : years_cv,
        "years_pro_cv"    : years_pro_cv,
        "years_required"  : years_required,
        "title_overlap"   : round(title_overlap, 3),
    }


# ─────────────────────────────────────────────────────────────────
# SCORE MATCHING
# ─────────────────────────────────────────────────────────────────

def _calculate_matching_score(
    similarity            : float,
    skills_weighted_ratio : float,
    experience_score      : int,
) -> int:
    """
    score_matching = 0.5×skills_weighted + 0.3×sim + 0.2×exp

    FIX-22 : utilise skills_weighted_ratio à la place de skills_ratio binaire.
    skills_weighted_ratio pondère chaque skill par sa fréquence d'apparition
    → réduit le biais "SQL mentionné 1 fois = SQL expert".
    """
    score = (
        POIDS_SKILLS     * skills_weighted_ratio * 100 +
        POIDS_SEMANTIQUE * similarity            * 100 +
        POIDS_EXPERIENCE * experience_score
    )
    score = max(0, min(100, round(score)))
    logger.info(
        f"  [matching] score_matching={score} "
        f"(skills_w={skills_weighted_ratio:.2f}×50 + "
        f"sim={similarity:.2f}×30 + exp={experience_score}×20)"
    )
    return score


# ─────────────────────────────────────────────────────────────────
# OVERRIDES ABSOLUS
# ─────────────────────────────────────────────────────────────────

def _has_personal_projects(cv_profile: dict) -> bool:
    """
    FIX-24 : détecte les projets personnels dans le CV.
    Sources :
      1. Nouveau champ projects[] parsé explicitement
      2. Fallback historique via achievements / rôles

    Utilisé pour protéger les juniors en reconversion contre l'override R1.
    """
    PROJECT_KEYWORDS = {
        "projet", "project", "github", "portfolio",
        "kaggle", "personnel", "perso", "open source",
        "opensource", "side project", "hackathon",
    }
    # BUG-09/23 FIX : faux positifs sur "github actions" et achievements SAP/enterprise
    # "github actions" est un outil CI/CD, pas un lien de portfolio
    # → on exclut les cas où "github" est suivi de "actions"
    FALSE_POSITIVE_PHRASES = {
        "github actions", "github action",
        "gitlab ci", "gitlab ci/cd",
    }

    # Source 1 — champ projects[] explicite
    projects = cv_profile.get("projects", []) or []
    if len(projects) > 0:
        return True

    # Source 2 — fallback historique dans expériences / achievements
    for section in ("professional_experience", "internships", "alternance"):
        for exp in (cv_profile.get(section, []) or []):
            role = (exp.get("role", "") or "").lower()
            if any(kw in role for kw in PROJECT_KEYWORDS):
                # BUG-09/23 FIX : vérifier que ce n'est pas un faux positif
                if not any(fp in role for fp in FALSE_POSITIVE_PHRASES):
                    return True
            for ach in (exp.get("achievements", []) or []):
                ach_lower = str(ach).lower()
                if any(kw in ach_lower for kw in PROJECT_KEYWORDS):
                    # BUG-09/23 FIX : exclure "github actions", "gitlab ci/cd" etc.
                    if not any(fp in ach_lower for fp in FALSE_POSITIVE_PHRASES):
                        return True
    return False


def _check_overrides(
    similarity      : float,
    skills_ratio    : float,
    score_motivation: int,
    cv_quality_score: float = 0.0,
    cv_profile      : dict  = None,
) -> Optional[str]:
    """
    Retourne "REJETÉ" si cas absolu détecté. None sinon.
    Exécuté AVANT le calcul du score final.

    FIX-3  : R1 ajoute AND skills_ratio < 0.2
    FIX-12 : R2 ajoute AND score_motivation < 60
    FIX-20 : R1 ajoute AND cv_quality_score < 0.4
    FIX-24 : R1 protégé si projets personnels détectés (autodidacte)
    FIX-25 : R1 protégé si years_experience == 0
             (junior complet sans expérience pro = possible reconversion/étudiant)
             Combiné avec FIX-24 : si junior ET projets → jamais d'override R1
    """
    if cv_profile is None:
        cv_profile = {}

    years_cv    = cv_profile.get("years_experience", 0) or 0
    has_projects = _has_personal_projects(cv_profile)

    # R1 — Lettre parfaite + CV hors domaine + quasi 0 skills + CV faible qualité
    # FIX-24/25 : ne pas override si junior avec projets (signal autodidacte)
    r1_candidate = (
        similarity       < 0.3  and
        score_motivation > 70   and
        skills_ratio     < 0.2  and
        cv_quality_score < 0.4
    )
    if r1_candidate:
        # FIX-25 : junior (0 ans) → peut être reconversion ou étudiant
        if years_cv == 0:
            logger.info(
                f"  [override] R1 candidat MAIS years_experience=0 → "
                f"protection junior → pas d'override"
            )
        # FIX-24 : projets perso détectés → signal autodidacte → pas d'override
        elif has_projects:
            logger.info(
                f"  [override] R1 candidat MAIS projets perso détectés → "
                f"protection autodidacte → pas d'override"
            )
        else:
            logger.info(
                f"  [override] R1 : sim={similarity:.2f}<0.3, "
                f"motivation={score_motivation}>70, "
                f"skills_ratio={skills_ratio:.2f}<0.2, "
                f"cv_quality={cv_quality_score:.2f}<0.4 → REJETÉ direct"
            )
            return "REJETÉ"

    # R2 — Double zéro absolu + lettre faible
    if skills_ratio == 0.0 and similarity < 0.2 and score_motivation < 60:
        logger.info(
            f"  [override] R2 : skills_ratio=0, "
            f"sim={similarity:.2f}<0.2, "
            f"motivation={score_motivation}<60 → REJETÉ direct"
        )
        return "REJETÉ"

    return None


# ─────────────────────────────────────────────────────────────────
# SCORE FINAL FUSIONNÉ
# ─────────────────────────────────────────────────────────────────

def _calculate_final_score(score_matching: int, score_motivation: int) -> int:
    """score_final = 0.6×matching + 0.4×motivation"""
    score = POIDS_MATCHING * score_matching + POIDS_MOTIVATION * score_motivation
    return max(0, min(100, round(score)))


# ─────────────────────────────────────────────────────────────────
# AJUSTEMENTS SCORE
# ─────────────────────────────────────────────────────────────────

def _apply_adjustments(
    score_final           : int,
    similarity            : float,
    skills_ratio          : float,
    score_motivation      : int,
    signal_motivation     : str,
    signal_matching       : str,
    cv_quality_score      : float = 0.0,
    keyword_stuffing      : bool  = False,
) -> tuple[int, list[str]]:
    """Ajustements plafond/plancher après fusion."""
    rules_triggered = []

    # BUG-19 FIX : keyword stuffing confirmé → plafonner score_final à 69
    # (EN_ATTENTE max, jamais ENTRETIEN automatique)
    # Un vrai stuffer ne doit pas bénéficier de la fusion avec le score motivation
    # pour passer le seuil ENTRETIEN. La pénalité sur weighted_ratio seule
    # ne suffit pas car score_motivation peut compenser.
    # Condition : stuffing détecté ET densité vraiment anormale (>max_legit)
    if keyword_stuffing and score_final >= SEUIL_ENTRETIEN:
        old = score_final
        score_final = SEUIL_ENTRETIEN - 1   # 69 → EN_ATTENTE
        rules_triggered.append(f"BUG19:keyword_stuffing_plafond:{old}→{score_final}")
        logger.warning(
            f"  [adjust] BUG19 : keyword stuffing confirmé "
            f"→ score_final plafonné {old}→{score_final} "
            f"(EN_ATTENTE max — revue humaine obligatoire)"
        )

    # A1 — Hors domaine + 0 skill → plafond 40
    if similarity < 0.3 and skills_ratio == 0.0:
        old = score_final
        score_final = min(score_final, 40)
        if score_final != old:
            rules_triggered.append(f"A1:hors_domaine_0skill:{old}→{score_final}")

    # BUG-07 FIX : skills_ratio=0 ET domain_ok=False → REJETÉ automatique
    # Indépendamment du score motivation — un candidat sans aucun skill requis
    # ne doit pas passer en EN_ATTENTE parce qu'il a bien rédigé sa lettre.
    # Exception : si FIX-F déjà appliqué (CV mal parsé) → laisser EN_ATTENTE
    if skills_ratio == 0.0 and similarity < 0.5 and score_final >= SEUIL_ATTENTE:
        old = score_final
        score_final = SEUIL_ATTENTE - 1   # 39 → REJETÉ
        rules_triggered.append(f"BUG07:zero_skills_hors_domaine:{old}→{score_final}")
        logger.info(
            f"  [adjust] BUG07 : skills_ratio=0.0 + similarity={similarity:.2f}<0.5 "
            f"→ REJETÉ forcé ({old}→{score_final}) — aucune compétence requise présente"
        )

    # A1b — Domaine différent partiel → force sous seuil rejet
    # Conditions : CV sémantiquement loin (sim < 0.45) ET < 40% skills requis
    # → peu importe le score motivation, on force le REJETÉ
    if similarity < 0.45 and skills_ratio < 0.4 and score_final > 40:
        old = score_final
        score_final = min(score_final, 39)
        rules_triggered.append(f"A1b:domaine_different_partiel:{old}→{score_final}")
        logger.info(
            f"  [adjust] A1b : domaine différent détecté "
            f"(similarity={similarity:.2f} < 0.45, skills_ratio={skills_ratio:.2f} < 0.40) "
            f"→ score {old} → {score_final} (force REJETÉ)"
        )

    # A2 — Bon profil + lettre quasi vide → plancher 50
    # FIX-26 : utilise _is_bon_profil() au lieu de similarity > 0.75 seule
    # Raison : un reconverti avec skills_ratio=0.80 mais similarity=0.50
    # (wording ≠ mais compétences OK) doit aussi bénéficier du plancher
    if _is_bon_profil(similarity, skills_ratio) and score_motivation < 20:
        old = score_final
        score_final = max(score_final, 50)
        if score_final != old:
            rules_triggered.append(f"A2:bon_profil_lettre_vide:{old}→{score_final}")

    # A3 — Double signal faible → plafond 35
    if signal_matching == "weak" and signal_motivation == "weak":
        old = score_final
        score_final = min(score_final, 35)
        if score_final != old:
            rules_triggered.append(f"A3:double_weak:{old}→{score_final}")

    # FIX-F : CV mal parsé → forcer EN_ATTENTE si décision serait REJETÉ
    # EXCEPTION 1 : si A1b déjà déclenché (domaine différent) → on laisse le REJETÉ
    # EXCEPTION 2 (BUG-05 FIX) : si skills_ratio < 0.2 → ne pas protéger
    #   Un candidat avec 0-1 skill n'est pas protégé par un mauvais formatage CV
    #   La protection FIX-F est pour les CVs mal parsés avec des compétences réelles,
    #   pas pour les profils objectivement disqualifiés
    domain_mismatch = similarity < 0.45 and skills_ratio < 0.4
    fixf_applicable = (
        cv_quality_score < 0.5 and
        score_final < SEUIL_ATTENTE and
        not domain_mismatch and
        skills_ratio >= 0.2   # BUG-05 FIX : au moins 1-2 skills présents avant de protéger
    )
    if fixf_applicable:
        old = score_final
        score_final = SEUIL_ATTENTE   # 40 = plancher EN_ATTENTE
        rules_triggered.append(
            f"FIX-F:cv_qualite_faible({cv_quality_score:.2f}):REJETÉ→EN_ATTENTE"
        )
        logger.warning(
            f"  [adjust] FIX-F : cv_quality_score={cv_quality_score:.2f} < 0.5 "
            f"ET score={old} < {SEUIL_ATTENTE} ET skills_ratio={skills_ratio:.2f}>=0.2 "
            f"→ forcer EN_ATTENTE (CV mal parsé — profil incomplet, revue manuelle)"
        )
    elif cv_quality_score < 0.5 and score_final < SEUIL_ATTENTE and not domain_mismatch and skills_ratio < 0.2:
        logger.info(
            f"  [adjust] FIX-F ignoré : skills_ratio={skills_ratio:.2f}<0.2 "
            f"(profil objectivement disqualifié, pas de protection CV mal parsé) "
            f"→ REJETÉ maintenu"
        )
    elif cv_quality_score < 0.5 and score_final < SEUIL_ATTENTE and domain_mismatch:
        logger.info(
            f"  [adjust] FIX-F ignoré : A1b domaine différent déjà appliqué "
            f"(similarity={similarity:.2f}, skills_ratio={skills_ratio:.2f}) "
            f"→ REJETÉ maintenu"
        )

    return max(0, min(100, score_final)), rules_triggered


# ─────────────────────────────────────────────────────────────────
# DÉCISION + SIGNAL COMBINÉ (FIX-16)
# ─────────────────────────────────────────────────────────────────

def _compute_decision(score_final: int) -> str:
    if score_final >= SEUIL_ENTRETIEN: return "ENTRETIEN"
    if score_final >= SEUIL_ATTENTE:   return "EN_ATTENTE"
    return "REJETÉ"


def _compute_signal(
    score_final     : int,
    score_matching  : int,
    score_motivation: int,
) -> str:
    """
    FIX-16 : signal combiné — "risk" pour les anomalies.
      CV fort + lettre vide → candidat potentiel non investi
      CV creux + lettre parfaite → probable lettre générée
    FIX-28 : cast int() explicite pour éviter les comparaisons float/int instables.
    """
    # FIX-28 : normalisation des types pour comparaisons stables
    score_final      = int(score_final)
    score_matching   = int(score_matching)
    score_motivation = int(score_motivation)

    if score_matching > 70 and score_motivation < 30:
        return "risk"
    if score_matching < 35 and score_motivation > 75:
        return "risk"
    if score_final >= SEUIL_ENTRETIEN: return "strong"
    if score_final >= SEUIL_ATTENTE:   return "medium"
    return "weak"


# ─────────────────────────────────────────────────────────────────
# CONFIDENCE SCORE (FIX-18)
# ─────────────────────────────────────────────────────────────────

def _compute_confidence(
    fallback_used        : bool,
    cv_quality_score     : float,
    skills_ratio         : float,
    skills_weighted_ratio: float,
    similarity           : float,
    job_skills_empty     : bool,
) -> dict:
    """
    FIX-18 : confidence_score — indique au RH quand faire confiance au score.
    FIX-A  : échelle graduée skills + ajout skills_weighted_ratio.

    Problème que ça résout :
      "documenter la limite" ≠ solution.
      Le RH doit savoir QUAND le score est fiable et quand il ne l'est pas.
      Sans confidence_score, tous les scores semblent également fiables.

    FIX-A — Problème découvert sur cas test réel :
      skills_ratio=0.333, skills_weighted=0.167 → confidence=100 (FAUX)
      Cause : seuil skills_ratio < 0.2 trop bas, skills_weighted non utilisé
      Correction : échelle graduée basée sur les deux signaux

    Calcul :
      Base 100, déductions pour chaque facteur de risque.

    Interprétation :
      ≥ 80 → score fiable — décision automatique acceptable
      60-79 → score moyen — revue humaine recommandée
      < 60  → score faible — revue humaine obligatoire

    Facteurs de déduction :
      -30 : fallback TF-IDF actif (sim non fiable contextuellement)
      -20 : cv_quality_score < 0.4 (CV pauvre → profil incomplet)
      -15 : job_skills_empty (pas de skills requis → skills_ratio non informatif)
      -15 : skills_ratio < 0.5 (moins de la moitié des skills requis matchés)
      -10 : skills_weighted_ratio < 0.25 (skills présents mais peu représentés)
      -10 : similarity < 0.3 (profil très éloigné — peu de signal)
    """
    score = 100

    if fallback_used:
        score -= 30   # TF-IDF = dégradation majeure de la similarité

    if cv_quality_score < 0.4:
        score -= 20   # CV pauvre → profil incomplet → matching moins fiable

    if job_skills_empty:
        score -= 15   # pas de skills requis → skills_ratio toujours 0.5

    # FIX-A : remplace l'ancien "skills_ratio < 0.2 → -10" trop permissif
    if skills_ratio < 0.5:
        score -= 15   # moins de la moitié des skills requis → couverture insuffisante

    if skills_weighted_ratio < 0.25:
        score -= 10   # skills présents mais peu représentés dans le CV (faible densité)

    if similarity < 0.3:
        score -= 10   # profil très éloigné → peu de signal sémantique

    score = max(0, min(100, score))

    if score >= 80:
        level             = "high"
        message           = "Score fiable — décision automatique acceptable."
        score_is_indicative = False
    elif score >= 60:
        level             = "medium"
        message           = "Score moyen — revue humaine recommandée."
        score_is_indicative = True
    else:
        level             = "low"
        message           = "Score peu fiable — revue humaine obligatoire."
        score_is_indicative = True

    return {
        "score"             : score,
        "level"             : level,
        "message"           : message,
        # FIX-D : flag explicite pour le frontend
        # True = afficher bandeau "⚠ Score indicatif" dans le dashboard
        "score_is_indicative": score_is_indicative,
    }


# ─────────────────────────────────────────────────────────────────
# HELPERS SIGNAL DOMAINE COMBINÉ (FIX-26)
#
# Problème résolu :
#   similarity seule crée deux types d'erreurs silencieuses :
#   - Faux négatifs : reconversion avec bons skills mais wording CV ≠ wording offre
#     Ex: CV "ingénieur ERP" candidat à "développeur Business Central"
#     → similarity = 0.28, skills_ratio = 0.75 → hors domaine ? NON
#   - Faux positifs : CV générique avec bon wording mais 0 compétence
#     → similarity = 0.72, skills_ratio = 0.0 → bon profil ? NON
#
# Solution : deux helpers combinant les deux signaux indépendants
# ─────────────────────────────────────────────────────────────────

def _is_hors_domaine(similarity: float, skills_ratio: float) -> bool:
    """
    FIX-26 : profil vraiment hors domaine = sim faible ET skills faibles.

    Remplace les seuils `similarity < 0.3` seuls dans les ajustements
    et la justification.

    Seuils :
      similarity < 0.3  : wording éloigné de l'offre
      skills_ratio < 0.25 : moins du quart des compétences présentes
      → les deux ensemble = signal fort hors domaine

    Cas limite couvert :
      sim=0.25, skills_ratio=0.60 → PAS hors domaine (bons skills, wording ≠)
      sim=0.60, skills_ratio=0.10 → PAS hors domaine (bon wording, skills manquants)
      sim=0.22, skills_ratio=0.10 → hors domaine (les deux signaux faibles)
    """
    return similarity < 0.3 and skills_ratio < 0.25


def _is_bon_profil(similarity: float, skills_ratio: float) -> bool:
    """
    FIX-26 : bon profil = bon wording OU bonnes compétences (pas forcément les deux).

    Remplace `similarity > 0.75` seul dans l'ajustement A2.

    Raisonnement :
      Un reconverti peut avoir skills_ratio = 0.85 mais similarity = 0.45
      (wording CV technique ≠ wording offre) → doit quand même déclencher A2
      (plancher 50 si lettre vide) pour ne pas le pénaliser deux fois.

    Seuils :
      similarity > 0.75 : très proche sémantiquement (wording similaire)
      skills_ratio > 0.65 : majorité des compétences couvertes
    """
    return similarity > 0.75 or skills_ratio > 0.65


# ─────────────────────────────────────────────────────────────────
# JUSTIFICATION STRUCTURÉE
# ─────────────────────────────────────────────────────────────────

def _build_justification(
    cv_profile          : dict,
    skills_matched      : list,
    skills_missing      : list,
    skills_ratio        : float,
    similarity          : float,
    experience_info     : dict,
    score_matching      : int,
    score_motivation    : int,
    score_final         : int,
    decision            : str,
    rules_triggered     : list,
    fallback_used       : bool,
    skills_high_density : list,
    skills_low_density  : list,
    confidence          : dict,
    keyword_stuffing    : bool = False,
) -> dict:
    """
    Justification structurée lisible par le RH.
    FIX-18 : intègre confidence_score et avertissement fallback.
    FIX-19 : distingue skills probablement pratiqués vs juste mentionnés.
    FIX-D  : avertissement illusion de précision si confidence != high.
    FIX-E  : avertissement keyword stuffing si détecté.
    """
    points_forts   = []
    points_faibles = []

    # ── Points forts ─────────────────────────────────────────────
    years = experience_info.get("years_cv", 0) or 0
    if years > 0:
        points_forts.append(f"{years} an(s) d'expérience")

    if skills_matched:
        total = len(skills_matched) + len(skills_missing)
        pct   = int(skills_ratio * 100)
        points_forts.append(
            f"{len(skills_matched)}/{total} compétences correspondantes ({pct}%)"
        )
        # FIX-19 : signaler les skills probablement pratiqués
        if skills_high_density:
            points_forts.append(
                f"Compétences probablement pratiquées (≥{SKILL_DENSITY_THRESHOLD} mentions) : "
                f"{', '.join(skills_high_density[:4])}"
            )

    names = [
        c.get("name", "") for c in (cv_profile.get("certifications", []) or [])
        if c.get("name")
    ]
    if names:
        points_forts.append(f"Certifications : {', '.join(names[:3])}")

    # FIX-C : signal projets pour le RH — deux sources
    # Source 1 : champ projects[] structuré (nom, lien, technologies)
    # Source 2 : fallback achievements (github, portfolio, kaggle...)
    #            → couvre le cas projects=null mais GitHub dans achievements
    projects = cv_profile.get("projects", []) or []
    if projects:
        project_names = [p.get("name", "") for p in projects if isinstance(p, dict) and p.get("name")]
        project_links = sum(
            1 for p in projects
            if isinstance(p, dict) and (p.get("link") or "")
        )
        project_msg = f"{len(projects)} projet(s) personnel(s) détecté(s)"
        if project_names:
            project_msg += f" : {', '.join(project_names[:2])}"
        if project_links:
            project_msg += f" ({project_links} lien(s) GitHub/portfolio/démo)"
        points_forts.append(project_msg)
    elif _has_personal_projects(cv_profile):
        # FIX-C : projets non structurés mais présents dans achievements
        # → signaler au RH sans détail (source non structurée)
        # → protège aussi de l'override R1 (FIX-24) — cohérence visible pour RH
        PROJECT_LINK_KEYWORDS = {"github", "gitlab", "portfolio", "kaggle", "demo", "bitbucket"}
        has_link = any(
            kw in str(ach).lower()
            for section in ("professional_experience", "internships", "alternance")
            for exp in (cv_profile.get(section, []) or [])
            for ach in (exp.get("achievements", []) or [])
            for kw in PROJECT_LINK_KEYWORDS
        )
        project_msg = "Projets personnels détectés dans les achievements"
        if has_link:
            project_msg += " (lien GitHub/portfolio présent)"
        project_msg += " — à explorer en entretien"
        points_forts.append(project_msg)

    # FIX-26 : signal domaine combiné pour les messages RH
    # Avant : similarity seule → misleading pour reconversions
    # Après : sim + skills_ratio → message plus précis et explicable
    if similarity >= 0.7 and skills_ratio >= 0.5:
        points_forts.append(
            f"Profil aligné avec le poste (sémantique {similarity:.2f} + "
            f"{int(skills_ratio*100)}% compétences)"
        )
    elif similarity >= 0.7:
        points_forts.append(
            f"Wording CV proche de l'offre (similarité {similarity:.2f})"
        )
    elif skills_ratio >= 0.65:
        points_forts.append(
            f"Compétences techniques bien couvertes ({int(skills_ratio*100)}%) "
            f"malgré un wording différent (similarité {similarity:.2f})"
        )
    elif similarity >= 0.5 or skills_ratio >= 0.4:
        points_forts.append(
            f"Domaine partiellement aligné "
            f"(similarité {similarity:.2f}, compétences {int(skills_ratio*100)}%)"
        )

    # ── Points faibles ───────────────────────────────────────────
    if skills_missing:
        suffix = f" (+{len(skills_missing)-5} autres)" if len(skills_missing) > 5 else ""
        points_faibles.append(
            f"Compétences manquantes : {', '.join(skills_missing[:5])}{suffix}"
        )

    # FIX-19 : avertir sur skills mentionnés une seule fois
    if skills_low_density:
        points_faibles.append(
            f"Compétences mentionnées une seule fois (à vérifier en entretien) : "
            f"{', '.join(skills_low_density[:4])}"
        )

    # FIX-26 : signal hors-domaine combiné (sim + skills) pour les points faibles
    if _is_hors_domaine(similarity, skills_ratio):
        points_faibles.append(
            f"Profil éloigné du poste : wording (similarité {similarity:.2f}) "
            f"et compétences ({int(skills_ratio*100)}%) tous deux insuffisants"
        )
    elif similarity < 0.3:
        # Wording éloigné MAIS skills partiellement OK → cas reconversion
        points_faibles.append(
            f"Wording du CV éloigné de l'offre (similarité {similarity:.2f}) "
            f"— vérifier en entretien si les compétences sont transférables"
        )

    years_req = experience_info.get("years_required", 0) or 0
    if years_req > 0 and years < years_req:
        points_faibles.append(
            f"Expérience insuffisante : {years} an(s) pour {years_req} requis"
        )

    if score_motivation < 30:
        points_faibles.append("Lettre de motivation peu pertinente ou trop courte")

    # FIX-17 : avertissement explicite si TF-IDF utilisé
    if fallback_used:
        points_faibles.append(
            "⚠ Similarité calculée via TF-IDF (modèle embedding indisponible) — "
            "score sémantique moins fiable, revue manuelle recommandée"
        )

    if rules_triggered:
        points_faibles.append(f"Règles métier : {', '.join(rules_triggered)}")

    # FIX-E : avertissement keyword stuffing
    if keyword_stuffing:
        points_faibles.append(
            "⚠ Densité de mots-clés anormalement élevée dans le CV — "
            "possible keyword stuffing détecté (score skills pénalisé de 20%)"
        )

    # FIX-D : message de synthèse — avertissement illusion de précision
    # Contexte : poids non calibrés sur dataset réel → score 72 vs 68 non significatif
    # Message visible → RH ne doit pas traiter le score comme absolu
    score_is_indicative = confidence.get("score_is_indicative", False)
    if decision == "ENTRETIEN":
        if score_is_indicative:
            analyse = (
                f"Profil solide — correspondance élevée avec le poste (score {score_final}/100). "
                f"⚠ Score indicatif (confiance {confidence['level']}) — validation humaine recommandée."
            )
        else:
            analyse = f"Profil solide — correspondance élevée avec le poste (score {score_final}/100)."
    elif decision == "EN_ATTENTE":
        if score_is_indicative:
            analyse = (
                f"Profil partiellement aligné — à examiner manuellement (score {score_final}/100). "
                f"⚠ Score indicatif (confiance {confidence['level']}) — les poids ne sont pas calibrés sur dataset réel."
            )
        else:
            analyse = f"Profil partiellement aligné — à examiner manuellement (score {score_final}/100)."
    else:
        if score_is_indicative:
            analyse = (
                f"Profil insuffisamment aligné avec le poste (score {score_final}/100). "
                f"⚠ Score indicatif — vérifier que le CV a bien été parsé avant de rejeter définitivement."
            )
        else:
            analyse = f"Profil insuffisamment aligné avec le poste (score {score_final}/100)."

    return {
        "points_forts"  : points_forts   or ["Aucun point fort identifié"],
        "points_faibles": points_faibles or ["Aucun point faible majeur"],
        "scores": {
            "matching"    : score_matching,
            "motivation"  : score_motivation,
            "final"       : score_final,
            "similarity"  : round(similarity, 3),
            "skills_ratio": round(skills_ratio, 3),
        },
        "confidence": confidence,   # FIX-18
        "analyse"   : analyse,
    }


# ─────────────────────────────────────────────────────────────────
# RÉSULTAT D'ERREUR (FIX-15)
# ─────────────────────────────────────────────────────────────────

def _error_result(reason: str) -> dict:
    """
    FIX-15 : jamais None — toujours un dict exploitable.
    FIX-27 : decision = "EN_ATTENTE" (était "REJETÉ").
             Une erreur technique système ≠ rejet du candidat.
             Application.status conservé EN_ATTENTE → revue manuelle obligatoire.
    IA_Log toujours écrit.
    """
    logger.error(f"  [matching] Erreur critique — {reason}")
    return {
        "score_matching"           : 0,
        "score_final"              : 0,
        "signal_final"             : "weak",
        "decision"                 : "EN_ATTENTE",
        "similarity_cv_job"        : 0.0,
        "skills_matched"           : [],
        "skills_missing"           : [],
        "skills_ratio"             : 0.0,
        "skills_weighted_ratio"    : 0.0,
        "skills_high_density"      : [],
        "skills_low_density"       : [],
        "keyword_stuffing_suspected": False,
        "main_reason"              : "system_error",
        "experience_ok"            : False,
        "domain_ok"                : False,
        "justification"            : {
            "points_forts"  : ["Analyse impossible — revue manuelle requise"],
            "points_faibles": [f"Erreur système : {reason}"],
            "scores"        : {
                "matching": 0, "motivation": 0, "final": 0,
                "similarity": 0.0, "skills_ratio": 0.0,
            },
            "confidence": {
                "score": 0, "level": "low",
                "message": "Erreur système — revue manuelle obligatoire.",
                "score_is_indicative": True,
            },
            "analyse": f"⚠ Erreur lors de l'analyse : {reason} — revue manuelle obligatoire.",
        },
        "confidence"               : {
            "score": 0, "level": "low",
            "message": "Erreur système — revue manuelle obligatoire.",
            "score_is_indicative": True,
        },
        "score_is_indicative"      : True,
        "embedding_model"          : "error",
        "fallback_used"            : False,
        "rules_triggered"          : ["ERREUR_SYSTEME"],
        "error"                    : True,
        "error_reason"             : reason,
    }


# ─────────────────────────────────────────────────────────────────
# RAISON PRINCIPALE (main_reason)
# ─────────────────────────────────────────────────────────────────

def _compute_main_reason(
    skills_ratio              : float,
    similarity                : float,
    keyword_stuffing_suspected: bool,
    score_motivation          : int,
    rules_triggered           : list,
    years_pro_cv              : int = 0,
    years_required            : int = 0,
) -> str:
    """
    Retourne la raison principale de la décision — lisible directement par le RH.

    Priorité (du plus critique au moins critique) :
      1. skills_insufficient   — moins de 30% des compétences requises présentes
      2. experience_insufficient — expérience professionnelle insuffisante
                                   (ajout BUG-16 FIX : basé sur years_professional)
      3. domain_mismatch       — wording CV éloigné ET compétences faibles
      4. keyword_stuffing      — densité anormale de mots-clés détectée
      5. low_motivation        — lettre de motivation très faible (< 30)
      6. balanced_evaluation   — aucun signal critique
    """
    if skills_ratio < 0.3:
        return "skills_insufficient"
    # OBS-01 FIX : expérience insuffisante avant keyword_stuffing
    if years_required > 0 and years_pro_cv < years_required and years_pro_cv < years_required * 0.5:
        return "experience_insufficient"
    if similarity < 0.3 and skills_ratio < 0.25:
        return "domain_mismatch"
    if keyword_stuffing_suspected:
        return "keyword_stuffing"
    if score_motivation < 30:
        return "low_motivation"
    return "balanced_evaluation"


# ─────────────────────────────────────────────────────────────────
# FONCTION PRINCIPALE
# ─────────────────────────────────────────────────────────────────

def analyze_matching(
    cv_profile       : dict,
    job              : dict,
    score_motivation : int  = 50,
    signal_motivation: str  = "medium",
    job_id           : int  = 0,
) -> dict:
    """
    Analyse le matching CV ↔ offre.
    FIX-15 : retourne toujours un dict — jamais None.
    """
    try:
        job_title  = (job.get("title", "")           or "").strip()
        job_skills = (job.get("skills_required", "") or "").strip()

        logger.info(f"Début matching — poste : '{job_title}'")

        # ── Étape 1-2 : Textes décorrélés (FIX-10) ───────────────
        cv_text_sem    = _build_cv_text_semantic(cv_profile)
        cv_text_skills = _build_cv_text_skills(cv_profile)
        job_text_sem   = _build_job_text_semantic(job)

        if not cv_text_sem.strip() and not cv_text_skills.strip():
            return _error_result("CV text vide — profil non exploitable")

        # ── Étape 3-4 : Similarité sémantique ────────────────────
        similarity, fallback_used = _compute_similarity(
            cv_text_sem, job_text_sem, job_id=job_id
        )

        # ── Étape 5 : Skills match + densité (FIX-19/22) ────────
        skills_info                = _check_skills_match(cv_text_skills, job_skills)
        skills_matched             = skills_info["skills_matched"]
        skills_missing             = skills_info["skills_missing"]
        skills_ratio               = skills_info["skills_ratio"]
        skills_weighted_ratio      = skills_info["skills_weighted_ratio"]
        skills_high_density        = skills_info["skills_high_density"]
        skills_low_density         = skills_info["skills_low_density"]
        keyword_stuffing_suspected = skills_info["keyword_stuffing_suspected"]  # FIX-E
        job_skills_empty           = not bool(job_skills.strip())

        # ── Étape 6 : Expérience (FIX-21/23) ─────────────────────
        # Passe skills_ratio pour dim_domain découplé (FIX-21)
        exp_info         = _compute_experience_score(
            cv_profile, job, similarity, skills_ratio
        )
        experience_score = exp_info["experience_score"]

        # ── Étape 7 : Score matching (FIX-22) ────────────────────
        # Utilise skills_weighted_ratio à la place de skills_ratio binaire
        score_matching = _calculate_matching_score(
            similarity, skills_weighted_ratio, experience_score
        )

        if score_matching >= SEUIL_ENTRETIEN:   signal_matching = "strong"
        elif score_matching >= SEUIL_ATTENTE:   signal_matching = "medium"
        else:                                   signal_matching = "weak"

        cv_quality_score = float(cv_profile.get("cv_quality_score", 0.0) or 0.0)

        # ── Étape 8 : Overrides absolus (FIX-24/25) ──────────────
        # Passe cv_profile pour détection projets perso et years_experience
        override = _check_overrides(
            similarity, skills_ratio, score_motivation,
            cv_quality_score, cv_profile
        )
        if override:
            score_final_ov = score_matching   # FIX-5
            confidence     = _compute_confidence(
                fallback_used, cv_quality_score, skills_ratio,
                skills_weighted_ratio,               # FIX-A
                similarity, job_skills_empty
            )
            signal_final = _compute_signal(score_final_ov, score_matching, score_motivation)
            justification = _build_justification(
                cv_profile, skills_matched, skills_missing, skills_ratio,
                similarity, exp_info, score_matching, score_motivation,
                score_final_ov, override, ["OVERRIDE_DIRECT"],
                fallback_used, skills_high_density, skills_low_density,
                confidence, keyword_stuffing_suspected
            )
            main_reason = _compute_main_reason(
                skills_ratio, similarity, keyword_stuffing_suspected,
                score_motivation, ["OVERRIDE_DIRECT"],
                years_pro_cv=exp_info.get("years_pro_cv", 0),
                years_required=exp_info.get("years_required", 0),
            )
            result = {
                "score_matching"           : score_matching,
                "score_final"              : score_final_ov,
                "signal_final"             : signal_final,
                "decision"                 : override,
                "main_reason"              : main_reason,
                "similarity_cv_job"        : round(similarity, 3),
                "skills_matched"           : skills_matched,
                "skills_missing"           : skills_missing,
                "skills_ratio"             : round(skills_ratio, 3),
                "skills_weighted_ratio"    : round(skills_weighted_ratio, 3),
                "skills_high_density"      : skills_high_density,
                "skills_low_density"       : skills_low_density,
                "keyword_stuffing_suspected": keyword_stuffing_suspected,
                "experience_ok"            : exp_info["years_ok"],
                "domain_ok"                : exp_info["domain_ok"],
                "title_overlap"            : exp_info.get("title_overlap", 0.0),
                "justification"            : justification,
                "confidence"               : confidence,
                "score_is_indicative"      : confidence.get("score_is_indicative", False),
                "embedding_model"          : MODELE_EMBEDDING if not fallback_used else "tfidf",
                "fallback_used"            : fallback_used,
                "rules_triggered"          : ["OVERRIDE_DIRECT"],
                "error"                    : False,
            }
            logger.info(
                f"Matching OVERRIDE {override} | "
                f"matching={score_matching} sim={similarity:.3f} "
                f"confidence={confidence['level']}"
            )
            return result

        # ── Étape 9 : Score final ─────────────────────────────────
        score_final = _calculate_final_score(score_matching, score_motivation)

        # ── Étape 10 : Ajustements ────────────────────────────────
        score_final, rules_triggered = _apply_adjustments(
            score_final, similarity, skills_ratio,
            score_motivation, signal_motivation, signal_matching,
            cv_quality_score,          # FIX-F : protection CV mal parsé
            keyword_stuffing_suspected # BUG-19 FIX : plafond stuffer
        )

        # FIX-17 : fallback TF-IDF → forcer EN_ATTENTE si score ≥ 70
        # TF-IDF ne comprend pas le contexte → ENTRETIEN non fiable avec ce modèle
        if fallback_used and score_final >= SEUIL_ENTRETIEN:
            score_final = SEUIL_ENTRETIEN - 1   # 69 → EN_ATTENTE
            rules_triggered.append(
                f"FIX17:tfidf_degradation:ENTRETIEN→EN_ATTENTE"
            )
            logger.warning(
                f"  [matching] FIX-17 : fallback TF-IDF actif — "
                f"décision dégradée ENTRETIEN → EN_ATTENTE "
                f"(TF-IDF non fiable pour décision automatique)"
            )

        # ── Étape 11-12 : Décision + signal (FIX-16) ─────────────
        decision     = _compute_decision(score_final)
        signal_final = _compute_signal(score_final, score_matching, score_motivation)


        # ── Confidence (FIX-18) ───────────────────────────────────
        confidence = _compute_confidence(
            fallback_used, cv_quality_score, skills_ratio,
            skills_weighted_ratio,                   # FIX-A
            similarity, job_skills_empty
        )

        # ── Étape 13 : Justification ──────────────────────────────
        justification = _build_justification(
            cv_profile, skills_matched, skills_missing, skills_ratio,
            similarity, exp_info, score_matching, score_motivation,
            score_final, decision, rules_triggered,
            fallback_used, skills_high_density, skills_low_density,
            confidence, keyword_stuffing_suspected
        )

        main_reason = _compute_main_reason(
            skills_ratio, similarity, keyword_stuffing_suspected,
            score_motivation, rules_triggered,
            years_pro_cv=exp_info.get("years_pro_cv", 0),
            years_required=exp_info.get("years_required", 0),
        )
        result = {
            "score_matching"           : score_matching,
            "score_final"              : score_final,
            "signal_final"             : signal_final,
            "decision"                 : decision,
            "main_reason"              : main_reason,
            "similarity_cv_job"        : round(similarity, 3),
            "skills_matched"           : skills_matched,
            "skills_missing"           : skills_missing,
            "skills_ratio"             : round(skills_ratio, 3),
            "skills_weighted_ratio"    : round(skills_weighted_ratio, 3),
            "skills_high_density"      : skills_high_density,
            "skills_low_density"       : skills_low_density,
            "keyword_stuffing_suspected": keyword_stuffing_suspected,
            "experience_ok"            : exp_info["years_ok"],
            "domain_ok"                : exp_info["domain_ok"],
            "title_overlap"            : exp_info.get("title_overlap", 0.0),
            "justification"            : justification,
            "confidence"               : confidence,
            "score_is_indicative"      : confidence.get("score_is_indicative", False),
            "embedding_model"          : MODELE_EMBEDDING if not fallback_used else "tfidf",
            "fallback_used"            : fallback_used,
            "rules_triggered"          : rules_triggered,
            "error"                    : False,
        }

        logger.info(
            f"Matching terminé — {decision} [{signal_final}] "
            f"| final={score_final} matching={score_matching} motivation={score_motivation} "
            f"| sim={similarity:.3f} skills={skills_ratio:.0%} weighted={skills_weighted_ratio:.2f} "
            f"| title_overlap={exp_info.get('title_overlap',0):.2f} "
            f"| confidence={confidence['level']}({confidence['score']})"
        )
        return result

    except Exception as e:
        logger.error(f"Erreur matching_agent : {e}", exc_info=True)
        return _error_result(str(e))


# ─────────────────────────────────────────────────────────────────
# WRAPPER FASTAPI
# ─────────────────────────────────────────────────────────────────

def run_matching_agent(
    cv_profile       : dict,
    job_title        : str = "",
    job_description  : str = "",
    job_skills       : str = "",
    job_company      : str = "",
    score_motivation : int = 50,
    signal_motivation: str = "medium",
    application_id   : int = 0,
    job_id           : int = 0,
    db               = None,
    # FIX-G : feedback RH optionnel — stocké dans IA_Log pour V2
    # Valeurs : "ENTRETIEN" | "EN_ATTENTE" | "REJETÉ" | None
    # Or pour calibration future : {score_ai, decision_ai, decision_rh}
    feedback_rh      : Optional[str] = None,
) -> dict:
    """
    Wrapper FastAPI — retourne toujours un dict (FIX-15).
    FIX-14 : transmet job_id pour cache embedding.
    FIX-17 : en cas d'erreur, Application.status reste EN_ATTENTE.
    FIX-G  : accepte feedback_rh optionnel pour stockage V2.
    """
    from app.models import Application, IA_Log

    job = {
        "title"          : job_title,
        "description"    : job_description,
        "skills_required": job_skills,
        "company"        : job_company,
    }

    result = analyze_matching(
        cv_profile        = cv_profile,
        job               = job,
        score_motivation  = score_motivation,
        signal_motivation = signal_motivation,
        job_id            = job_id,
    )

    if result.get("error"):
        logger.error(
            f"  [matching] Erreur application_id={application_id} : "
            f"{result.get('error_reason')} — status EN_ATTENTE conservé"
        )

    # FIX-G : enrichir le résultat avec le feedback RH si fourni
    if feedback_rh:
        result["feedback_rh"] = feedback_rh
        logger.info(
            f"  [matching] feedback_rh={feedback_rh} "
            f"(ai={result['decision']}) — stocké dans IA_Log pour V2"
        )

    if db:
        application = db.query(Application).filter(
            Application.id == application_id
        ).first()

        if application:
            application.score_matching = float(result["score_matching"])
            application.score_final    = float(result["score_final"])
            if not result.get("error"):
                application.status = result["decision"]
                # ── Point 9 : status_v2 ──────────────────────────────
                application.status_v2 = (
                    "PRESELECTED"   if result["decision"] == "ENTRETIEN" else
                    "REJECTED_AUTO" if result["decision"] == "REJETÉ"   else
                    "MATCHED"
                )
            else:
                # ── Point 9 : ERROR handling ─────────────────────────
                application.status_v2    = "ERROR"
                application.error_stage   = "MATCHING"
                application.error_message = str(result.get("error_reason", "Erreur inconnue"))
                application.retry_count   = (application.retry_count or 0) + 1
            db.commit()
            logger.info(
                f"Application {application_id} mise à jour : "
                f"matching={result['score_matching']} final={result['score_final']} "
                f"decision={result['decision']} signal={result['signal_final']} "
                f"confidence={result['confidence']['level']} "
                f"indicatif={result['score_is_indicative']}"
            )
        else:
            logger.warning(f"Application {application_id} introuvable — scores non sauvegardés")

        log = IA_Log(
            application_id = application_id,
            agent_name     = "matching_agent",
            output_json    = json.dumps(result, ensure_ascii=False),
        )
        db.add(log)
        db.commit()
        logger.info(f"IA_Log sauvegardé — application_id={application_id}")

    return result