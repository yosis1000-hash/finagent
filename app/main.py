import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base
from app.routes import auth, users, teams, work_items, dashboard, reports, emails
from app.scheduler import start_scheduler
from app import seed

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create all tables
    Base.metadata.create_all(bind=engine)
    # Seed initial data if DB is empty
    await seed.init_db()
    # Start background scheduler
    start_scheduler()
    logger.info("FinAgent started")
    yield
    logger.info("FinAgent shutting down")


app = FastAPI(
    title="FinAgent",
    description="AI-Powered Division Management System - Bank of Israel",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(teams.router)
app.include_router(work_items.router)
app.include_router(dashboard.router)
app.include_router(reports.router)
app.include_router(emails.router)

# Serve static frontend
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/")
async def serve_index():
    return FileResponse("static/index.html")


@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    # API paths are handled by routers above — only serve SPA for frontend routes
    if full_path.startswith("api/"):
        return Response(status_code=404)
    return FileResponse("static/index.html")
