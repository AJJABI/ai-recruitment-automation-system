from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base
from app import models
from app.routers import jobs, applications, auth
from app.routers import decision
from app.routers import interviews
from app.routers import tests
from app.routers import notifications
from app.routers import managers


app = FastAPI(title="Recruitment AI Backend")

# ── CORS — doit être déclaré AVANT les routers ────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",  
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs.router)
app.include_router(applications.router)
app.include_router(auth.router)
app.include_router(decision.router)
app.include_router(interviews.router)
app.include_router(tests.router)
app.include_router(notifications.router)
app.include_router(managers.router)


Base.metadata.create_all(bind=engine)

# ── Cache MD5 PostgreSQL ──────────────────────────────────────────────────────
from app.agents.cv_agent.cv_cache import init_cache_table
init_cache_table()

@app.get("/")
def root():
    return {"message": "Backend Recruitment AI opérationnel"}