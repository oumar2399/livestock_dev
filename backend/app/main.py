"""
Point d'entrée principal - Application FastAPI
Livestock Monitoring System
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
from datetime import datetime

# Import routes
from app.api.v1 import telemetry, animals, alerts

# Configuration logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================
# CRÉATION APPLICATION FASTAPI
# ============================================================

app = FastAPI(
    title="Livestock Monitoring API",
    description="""
    ## 🐄 Système de monitoring intelligent pour élevage
    
    ### Fonctionnalités principales :
    * **Télémétrie** : Réception données capteurs M5Stack (GPS, activité, température)
    * **Animaux** : Gestion CRUD troupeau
    * **Alertes** : Détection anomalies santé/sécurité
    * **Analytics** : Statistiques et historiques
    
    ### Architecture :
    * Backend : Python FastAPI
    * Base de données : PostgreSQL + TimescaleDB + PostGIS
    * Hardware : M5Stack + GPS + MPU6886 + MLX90614
    
    ### Authentification :
    * JWT tokens (à venir)
    
    ---
    Développé pour concours recherche japonais - Élevage intelligent
    """,
    version="1.0.0",
    docs_url="/docs",  # Swagger UI
    redoc_url="/redoc",  # ReDoc
    openapi_url="/openapi.json"
)

# ============================================================
# MIDDLEWARE CORS (Cross-Origin Resource Sharing)
# ============================================================

# IMPORTANT : Permet dashboard web et app mobile d'appeler l'API
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # React dev server
        "http://localhost:3001",
        "http://localhost:19006",  # Expo dev
        "http://127.0.0.1:3000",
        "*"  # TODO: En production, spécifier domaines exacts
    ],
    allow_credentials=True,
    allow_methods=["*"],  # GET, POST, PUT, DELETE, etc.
    allow_headers=["*"],  # Authorization, Content-Type, etc.
)

# ============================================================
# MIDDLEWARE LOGGING (tracer requêtes)
# ============================================================

@app.middleware("http")
async def log_requests(request, call_next):
    """
    Log toutes les requêtes HTTP
    Utile pour debug et monitoring
    """
    start_time = datetime.utcnow()
    
    # Log requête entrante
    logger.info(f"→ {request.method} {request.url.path}")
    
    # Traiter requête
    response = await call_next(request)
    
    # Log réponse
    duration = (datetime.utcnow() - start_time).total_seconds()
    logger.info(
        f"← {request.method} {request.url.path} "
        f"Status: {response.status_code} "
        f"Duration: {duration:.3f}s"
    )
    
    return response

# ============================================================
# ROUTES PRINCIPALES
# ============================================================

@app.get("/", tags=["root"])
async def root():
    """
    Route racine - Informations API
    
    **Premier endpoint à tester** : GET http://localhost:8000/
    """
    return {
        "message": "🐄 Livestock Monitoring API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/health", tags=["root"])
async def health_check():
    """
    Health check - Vérifie que l'API est vivante
    
    **Utilisé par monitoring/load balancers**
    """
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()
    }

# ============================================================
# INCLUSION ROUTERS (modules API v1)
# ============================================================

# Préfixe /api/v1 pour toutes les routes
API_V1_PREFIX = "/api/v1"

# Router Telemetry
app.include_router(
    telemetry.router,
    prefix=API_V1_PREFIX,
    tags=["telemetry"]
)

# Router Animals
app.include_router(
    animals.router,
    prefix=API_V1_PREFIX,
    tags=["animals"]
)

# Router Alerts
app.include_router(
    alerts.router,
    prefix=API_V1_PREFIX,
    tags=["alerts"]
)

# ============================================================
# GESTION ERREURS GLOBALES
# ============================================================

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """
    Attrape toutes les exceptions non gérées
    Empêche crash serveur, log erreur
    """
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": str(exc),
            "path": request.url.path
        }
    )

# ============================================================
# EVENTS (startup/shutdown)
# ============================================================

@app.on_event("startup")
async def startup_event():
    """
    Exécuté au démarrage du serveur
    """
    logger.info("=" * 60)
    logger.info("🚀 Starting Livestock Monitoring API")
    logger.info("=" * 60)
    logger.info(f"📝 Documentation: http://localhost:8000/docs")
    logger.info(f"🔍 ReDoc: http://localhost:8000/redoc")
    logger.info(f"🏥 Health: http://localhost:8000/health")
    logger.info("=" * 60)

@app.on_event("shutdown")
async def shutdown_event():
    """
    Exécuté à l'arrêt du serveur
    """
    logger.info("=" * 60)
    logger.info("🛑 Shutting down Livestock Monitoring API")
    logger.info("=" * 60)

# ============================================================
# POINT D'ENTRÉE (si exécuté directement)
# ============================================================

if __name__ == "__main__":
    import uvicorn
    
    # Lancer serveur en mode développement
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",  # Écoute sur toutes interfaces réseau
        port=8000,
        reload=True,  # Auto-reload si fichier modifié (dev only)
        log_level="info"
    )