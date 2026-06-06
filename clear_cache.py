"""
clear_cache.py
Vide TOUT le cache PostgreSQL pour forcer un re-parsing.
Usage : python clear_cache.py
"""
from dotenv import load_dotenv
load_dotenv()
import psycopg2, os

conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = conn.cursor()
cur.execute("DELETE FROM cv_parse_cache;")
conn.commit()
print(f"Cache vidé : {cur.rowcount} entrée(s) supprimée(s)")
conn.close()