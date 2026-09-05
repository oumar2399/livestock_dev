"""
Point d'entrée principal - Application FastAPI
Livestock Monitoring System
VERSION 2.0 - Avec authentification JWT
"""
from fastapi import Depends, FastAPI, Response, status
# pyrefly: ignore [missing-import]
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
from datetime import datetime
from app.api.v1.predict import router as predict_router
from app.db.database import get_db
from app.schemas.health import LivenessResponse, ReadinessResponse
from app.services.system_health import build_readiness
from app.core.timezone import utc_now
from sqlalchemy.orm import Session

# Import routes
from app.api.v1 import telemetry, animals, alerts, auth, devices, activity, farms, admin, feedback, memberships, reports, history, geofences
from app.core.scheduler import start_scheduler, stop_scheduler
from app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ─── Application ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="Livestock Monitoring API",
    description="""
    ## 🐄 Système de monitoring intelligent pour élevage
    
    ### Authentification :
    1. **POST /api/v1/auth/register** → Créer un compte
    2. **POST /api/v1/auth/login** → Obtenir le token JWT
    3. Cliquer **Authorize** (🔒) en haut à droite de Swagger
    4. Entrer : `Bearer <votre_token>`
    
    ### Rôles :
    - **owner** : Gestion de la ferme, des animaux, membres et devices
    - **farmer** : Consultation des animaux et feedback terrain
    - **vet** : Consultation des animaux et feedback vétérinaire
    - **admin** : Accès total, gestion utilisateurs
    """,
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    # Configuration sécurité Swagger UI
    swagger_ui_init_oauth={
        "usePkceWithAuthorizationCodeGrant": True,
    },
)

# ─── CORS ─────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Middleware logging ────────────────────────────────────────────────────────

@app.middleware("http")
async def log_requests(request, call_next):
    start_time = datetime.utcnow()
    logger.info(f"→ {request.method} {request.url.path}")
    response = await call_next(request)
    duration = (datetime.utcnow() - start_time).total_seconds()
    logger.info(
        f"← {request.method} {request.url.path} "
        f"Status: {response.status_code} "
        f"Duration: {duration:.3f}s"
    )
    return response

# ─── Routes publiques ─────────────────────────────────────────────────────────

@app.get("/", tags=["root"])
async def root():
    return {
        "message": "🐄 Livestock Monitoring API v2.0",
        "status": "running",
        "docs": "/docs",
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/health", tags=["root"])
async def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


@app.get("/health/live", response_model=LivenessResponse, tags=["root"])
def liveness_check():
    return {"status": "alive", "checked_at": utc_now()}


@app.get(
    "/health/ready",
    response_model=ReadinessResponse,
    tags=["root"],
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadinessResponse}},
)
def readiness_check(
    response: Response,
    db: Session = Depends(get_db),
):
    result = build_readiness(db)
    if result["status"] != "ready":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result

# ─── Routers ──────────────────────────────────────────────────────────────────

API_V1_PREFIX = "/api/v1"

# Auth (public : login + register, protégé : me + admin)
app.include_router(auth.router, prefix=API_V1_PREFIX, tags=["auth"])

# Données (protégées - voir protection dans chaque router)
app.include_router(telemetry.router, prefix=API_V1_PREFIX, tags=["telemetry"])
app.include_router(animals.router,   prefix=API_V1_PREFIX, tags=["animals"])
app.include_router(alerts.router,    prefix=API_V1_PREFIX, tags=["alerts"])
app.include_router(devices.router,   prefix=API_V1_PREFIX, tags=["devices"])
app.include_router(activity.router, prefix=API_V1_PREFIX, tags=["activity"])
app.include_router(farms.router,    prefix=API_V1_PREFIX, tags=["farms"])
app.include_router(admin.router,    prefix=API_V1_PREFIX, tags=["admin"])
app.include_router(feedback.router, prefix=API_V1_PREFIX, tags=["feedback"])
app.include_router(memberships.router, prefix=API_V1_PREFIX, tags=["memberships"])
app.include_router(reports.router, prefix=API_V1_PREFIX, tags=["reports"])
app.include_router(history.router, prefix=API_V1_PREFIX, tags=["history"])
app.include_router(geofences.router, prefix=API_V1_PREFIX, tags=["geofences"])
app.include_router(predict_router)

# ─── Gestion erreurs globales ─────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": str(exc) if settings.EXPOSE_INTERNAL_ERRORS else "An unexpected error occurred",
            "path": request.url.path
        }
    )

# ─── Events ───────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    logger.info("=" * 60)
    logger.info("🚀 Starting Livestock Monitoring API v2.0")
    logger.info("🔐 JWT Authentication: ENABLED")
    logger.info("=" * 60)

    # Load the ML behavior classifier into memory (singleton)
    from app.services import ml_inference
    ml_inference.load_model()

    # Start APScheduler background scheduler (if SCHEDULER_ENABLED=true)
    start_scheduler()

    logger.info("📝 Documentation: http://localhost:8000/docs")
    logger.info("🏥 Health: http://localhost:8000/health")
    logger.info("=" * 60)

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("🛑 Shutting down Livestock Monitoring API")
    stop_scheduler()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
