from app.database import SessionLocal
from app import models
from passlib.context import CryptContext

db = SessionLocal()
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Supprimer l'ancien utilisateur RH si existe
db.query(models.User).filter(models.User.email == "admin@dynamix.com").delete()
db.query(models.User).filter(models.User.email == "rh@recruitment.com").delete()
db.commit()

# Créer nouveau
hashed = pwd.hash("Admin1234!")
print(f"Hash généré: {hashed[:20]}...")

user = models.User(
    email="admin@dynamix.com",
    hashed_password=hashed,
    role="RH",
    full_name="Admin RH",
    poste="RH Manager"
)
db.add(user)
db.commit()
db.refresh(user)

# Vérifier
test = pwd.verify("Admin1234!", user.hashed_password)
print(f"Vérification mot de passe: {test}")
print(f"Utilisateur créé: {user.email}")
db.close()