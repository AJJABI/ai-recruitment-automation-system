import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv()

# ── Validation DATABASE_URL ───────────────────────────────────────────────────
# Raise explicite au démarrage si DATABASE_URL est absent ou mal configuré.
# Evite une erreur cryptique SQLAlchemy "NoneType is not a valid URL".
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise EnvironmentError(
        "DATABASE_URL manquant dans le fichier .env\n"
        "Format attendu : postgresql://user:password@localhost:5432/nom_db\n"
        "Exemple        : postgresql://postgres:admin@localhost:5432/recruitment_ai"
    )

if not DATABASE_URL.startswith(("postgresql://", "postgresql+psycopg2://")):
    raise EnvironmentError(
        f"DATABASE_URL invalide : '{DATABASE_URL}'\n"
        "Seul PostgreSQL est supporté.\n"
        "Format attendu : postgresql://user:password@localhost:5432/nom_db"
    )

# ── Connexion SQLAlchemy ──────────────────────────────────────────────────────
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,    # vérifie la connexion avant chaque requête
    pool_size=5,           # connexions simultanées max
    max_overflow=10,       # connexions supplémentaires si pool plein
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()