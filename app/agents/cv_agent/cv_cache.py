"""
cv_cache.py
===========
Cache MD5 PostgreSQL pour le CV parser.

Fonctionnement :
  - Calcule le MD5 du fichier PDF uploadé
  - Vérifie si un résultat existe en base (non expiré)
  - Si oui  → retourne le résultat JSON directement (0 token Groq)
  - Si non  → parse normalement → sauvegarde en base → retourne

Table PostgreSQL : cv_parse_cache
  md5_hash    : empreinte unique du fichier PDF
  result_json : résultat complet du parser (JSON)
  parsed_at   : date/heure du parsing
  expires_at  : date d'expiration (parsed_at + 30 jours)

Configuration via .env :
  DATABASE_URL=postgresql://user:password@localhost:5432/dbname

Utilisation :
  from app.agents.cv_cache import get_cached_result, save_to_cache, compute_md5
"""

import os
import json
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional
from dotenv import load_dotenv

load_dotenv()  # Charge DATABASE_URL depuis .env

logger = logging.getLogger(__name__)

# Durée de validité du cache
CACHE_TTL_DAYS = 30

# ─────────────────────────────────────────
# CONNEXION POSTGRESQL
# ─────────────────────────────────────────

def _get_connection():
    """
    Retourne une connexion PostgreSQL via DATABASE_URL.
    Utilise psycopg2 — installe avec : pip install psycopg2-binary
    """
    try:
        import psycopg2
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise ValueError(
                "DATABASE_URL manquant dans .env\n"
                "Format : postgresql://user:password@localhost:5432/dbname"
            )
        return psycopg2.connect(database_url)
    except ImportError:
        raise ImportError(
            "psycopg2 non installé. Exécute : pip install psycopg2-binary"
        )


# ─────────────────────────────────────────
# INITIALISATION DE LA TABLE
# ─────────────────────────────────────────

def init_cache_table() -> bool:
    """
    Crée la table cv_parse_cache si elle n'existe pas.
    À appeler au démarrage de l'application (dans main.py ou lifespan).

    Retourne True si succès, False si erreur.
    """
    sql = """
    CREATE TABLE IF NOT EXISTS cv_parse_cache (
        id          SERIAL PRIMARY KEY,
        md5_hash    VARCHAR(32)  NOT NULL UNIQUE,
        result_json JSONB        NOT NULL,
        parsed_at   TIMESTAMP    NOT NULL DEFAULT NOW(),
        expires_at  TIMESTAMP    NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_cv_cache_md5     ON cv_parse_cache (md5_hash);
    CREATE INDEX IF NOT EXISTS idx_cv_cache_expires ON cv_parse_cache (expires_at);
    """
    try:
        conn = _get_connection()
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql)
        conn.close()
        logger.info("Table cv_parse_cache prête")
        return True
    except Exception as e:
        logger.error(f"Impossible de créer la table cache : {e}")
        return False


# ─────────────────────────────────────────
# CALCUL MD5
# ─────────────────────────────────────────

def compute_md5(pdf_path: str) -> str:
    """
    Calcule l'empreinte MD5 d'un fichier PDF.
    Lit le fichier par chunks pour ne pas saturer la RAM.

    Retourne une chaîne hex de 32 caractères.
    Ex : "a3f8c2d1e5b7f4a2c9d0e1f3b6a8c7d2"
    """
    hasher = hashlib.md5()
    with open(pdf_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


# ─────────────────────────────────────────
# LECTURE DU CACHE
# ─────────────────────────────────────────

def get_cached_result(md5_hash: str) -> Optional[dict]:
    """
    Cherche un résultat en cache pour ce MD5.

    Retourne :
      - dict  : résultat JSON si trouvé et non expiré
      - None  : pas en cache ou expiré
    """
    sql = """
    SELECT result_json, parsed_at, expires_at
    FROM cv_parse_cache
    WHERE md5_hash = %s
      AND expires_at > NOW()
    LIMIT 1;
    """
    try:
        conn = _get_connection()
        with conn.cursor() as cur:
            cur.execute(sql, (md5_hash,))
            row = cur.fetchone()
        conn.close()

        if row:
            result_json, parsed_at, expires_at = row
            # psycopg2 retourne déjà un dict pour JSONB
            result = result_json if isinstance(result_json, dict) else json.loads(result_json)
            days_left = (expires_at - datetime.now()).days
            logger.info(
                f"Cache HIT — MD5 {md5_hash[:8]}... "
                f"(parsé le {parsed_at.strftime('%d/%m/%Y')}, "
                f"expire dans {days_left}j)"
            )
            return result

        logger.info(f"Cache MISS — MD5 {md5_hash[:8]}...")
        return None

    except Exception as e:
        # En cas d'erreur DB → on laisse passer et on re-parse normalement
        logger.warning(f"Erreur lecture cache (fallback parse) : {e}")
        return None


# ─────────────────────────────────────────
# ÉCRITURE DANS LE CACHE
# ─────────────────────────────────────────

def save_to_cache(md5_hash: str, result: dict) -> bool:
    """
    Sauvegarde un résultat de parsing dans le cache.

    Utilise INSERT ... ON CONFLICT UPDATE pour gérer les re-uploads
    d'un même fichier (upsert) — met à jour l'expiration.

    Retourne True si succès, False si erreur.
    """
    sql = """
    INSERT INTO cv_parse_cache (md5_hash, result_json, parsed_at, expires_at)
    VALUES (%s, %s, NOW(), NOW() + INTERVAL '%s days')
    ON CONFLICT (md5_hash) DO UPDATE
        SET result_json = EXCLUDED.result_json,
            parsed_at   = NOW(),
            expires_at  = NOW() + INTERVAL '%s days';
    """
    # Exclure raw_text du cache (trop volumineux, inutile en cache)
    result_to_cache = {k: v for k, v in result.items() if k != "raw_text"}

    try:
        conn = _get_connection()
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql, (
                    md5_hash,
                    json.dumps(result_to_cache, ensure_ascii=False),
                    CACHE_TTL_DAYS,
                    CACHE_TTL_DAYS,
                ))
        conn.close()
        logger.info(
            f"Cache SAVE — MD5 {md5_hash[:8]}... "
            f"(expire dans {CACHE_TTL_DAYS}j, "
            f"candidat: {result.get('full_name', 'inconnu')})"
        )
        return True

    except Exception as e:
        logger.error(f"Erreur écriture cache : {e}")
        return False


# ─────────────────────────────────────────
# NETTOYAGE DES ENTRÉES EXPIRÉES
# ─────────────────────────────────────────

def purge_expired_cache() -> int:
    """
    Supprime les entrées expirées de la table.
    À appeler périodiquement (ex: tâche cron quotidienne).

    Retourne le nombre d'entrées supprimées.
    """
    sql = "DELETE FROM cv_parse_cache WHERE expires_at <= NOW();"
    try:
        conn = _get_connection()
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                deleted = cur.rowcount
        conn.close()
        if deleted:
            logger.info(f"Cache purge : {deleted} entrée(s) expirée(s) supprimée(s)")
        return deleted
    except Exception as e:
        logger.error(f"Erreur purge cache : {e}")
        return 0


# ─────────────────────────────────────────
# STATISTIQUES DU CACHE
# ─────────────────────────────────────────

def get_cache_stats() -> dict:
    """
    Retourne des statistiques sur le cache.
    Utile pour monitoring / dashboard admin.
    """
    sql = """
    SELECT
        COUNT(*)                                    AS total_entries,
        COUNT(*) FILTER (WHERE expires_at > NOW())  AS active_entries,
        COUNT(*) FILTER (WHERE expires_at <= NOW()) AS expired_entries,
        MIN(parsed_at)                              AS oldest_entry,
        MAX(parsed_at)                              AS newest_entry
    FROM cv_parse_cache;
    """
    try:
        conn = _get_connection()
        with conn.cursor() as cur:
            cur.execute(sql)
            row = cur.fetchone()
        conn.close()
        return {
            "total":    row[0],
            "active":   row[1],
            "expired":  row[2],
            "oldest":   row[3].isoformat() if row[3] else None,
            "newest":   row[4].isoformat() if row[4] else None,
            "ttl_days": CACHE_TTL_DAYS,
        }
    except Exception as e:
        logger.error(f"Erreur stats cache : {e}")
        return {}