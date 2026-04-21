"""
Point d'entrée principal - Application FastAPI
Livestock Monitoring System
VERSION 2.0 - Avec authentification JWT
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
from datetime import datetime

# Import routes
from app.api.v1 import telemetry, animals, alerts, auth, devices, activity

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
    - **farmer** : Accès complet à sa ferme
    - **owner** : Lecture seule, métriques économiques
    - **vet** : Données santé, résolution alertes santé
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
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:19006",
        "http://127.0.0.1:3000",
        "*",  # TODO: restreindre en production
    ],
    allow_credentials=True,
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

# ─── Gestion erreurs globales ─────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": str(exc),
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
    logger.info("📝 Documentation: http://localhost:8000/docs")
    logger.info("🏥 Health: http://localhost:8000/health")
    logger.info("=" * 60)

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("🛑 Shutting down Livestock Monitoring API")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)