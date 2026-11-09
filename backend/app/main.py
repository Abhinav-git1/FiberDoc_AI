from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import findings, projects, reports
from app.config import get_settings
from app.db.session import SessionLocal, init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    from app.workflow.seed_rules import seed

    init_db()
    with SessionLocal() as db:
        seed(db)
    yield


app = FastAPI(title="FiberDoc AI", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().cors_origins.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(projects.router)
app.include_router(findings.router)
app.include_router(reports.router)


@app.get("/health")
def health():
    return {"status": "ok"}
