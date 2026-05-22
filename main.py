# main.py

# ⚠️ IMPORTANT: Charger .env AVANT tous les autres imports!
from dotenv import load_dotenv
load_dotenv()

# Maintenant les autres imports
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
import logging
from api.routes import router
from api.quiz_routes import router as quiz_router
from api.admin_routes import router as admin_router
from api.proa_routes import router as proa_router
import os

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("orientation.main")

app = FastAPI(title="Orientation Service", version="2.0.0")

# ============================================================
# 📊 MIDDLEWARE DE LOGGING POUR DEBUG CORS
# ============================================================
from starlette.middleware.base import BaseHTTPMiddleware

class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Log des infos importantes pour debug CORS
        logger.info(f"[REQUEST] {request.method} {request.url.path}")
        logger.info(f"[CORS] Origin: {request.headers.get('origin', 'No origin')}")
        logger.info(f"[CORS] Host: {request.headers.get('host', 'No host')}")
        
        response = await call_next(request)
        
        # Log des headers de réponse CORS
        logger.info(f"[RESPONSE] Status: {response.status_code}")
        logger.info(f"[CORS] Access-Control-Allow-Origin: {response.headers.get('access-control-allow-origin', 'Not set')}")
        
        return response

# Ajouter le middleware de logging (optionnel, pour debug)
# Décommente pour activer le logging détaillé
# app.add_middleware(LoggingMiddleware)

# ============================================================
# 🔐 CORS Configuration - VERSION CORRIGÉE
# ============================================================

# Liste explicite des origines autorisées
ALLOWED_ORIGINS = [
    "https://pora-frontend.onrender.com",
    "https://universearch-proa-service.onrender.com",
    "https://universearch-pora-service.onrender.com",
    "http://localhost:5500",
    "http://localhost:3000",
    "http://localhost:8000",
    "http://127.0.0.1:5500",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8000",
    "https://*.onrender.com",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=r"https?://(.*\.)?onrender\.com|https?://localhost:\d+|https?://127\.0\.0\.1:\d+",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH", "HEAD"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "Accept",
        "Origin",
        "X-Requested-With",
        "X-User-ID",
        "X-Admin-Token",
        "apikey",
        "Prefer",
    ],
    expose_headers=[
        "Content-Length",
        "Content-Type",
        "X-Total-Count",
        "X-RateLimit-Limit",
        "X-RateLimit-Remaining",
    ],
    max_age=86400,  # 24 heures
)

# ============================================================
# 🚀 HANDLER POUR LES ERREURS DE VALIDATION
# ============================================================

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning(
        "Request validation failed: %s %s | errors=%s",
        request.method,
        request.url,
        exc.errors(),
    )
    
    # Tentative de lire le body pour debug
    try:
        body = await request.body()
        logger.warning(f"Request body: {body.decode('utf-8', errors='replace')[:500]}")
    except Exception:
        pass

    # Convert errors to JSON-serializable format
    errors = []
    for error in exc.errors():
        error_dict = {
            'type': error.get('type'),
            'loc': error.get('loc'),
            'msg': error.get('msg'),
            'input': error.get('input')
        }
        errors.append(error_dict)

    return JSONResponse(status_code=422, content={"detail": errors})

# ============================================================
# 🔧 HANDLER POUR LES ERREURS 500
# ============================================================

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "message": str(exc)}
    )

# ============================================================
# 📡 ROUTES
# ============================================================

app.include_router(router)
app.include_router(quiz_router)
app.include_router(admin_router)
app.include_router(proa_router)

# ============================================================
# 🏠 ENDPOINTS DE BASE
# ============================================================

@app.api_route("/", methods=["GET", "HEAD"])
def root():
    return {
        "service": "PROA Service",
        "version": "2.0.0",
        "status": "running",
        "cors_enabled": True,
        "allowed_origins": ALLOWED_ORIGINS
    }

@app.api_route("/health", methods=["GET", "HEAD"])
def health():
    return {
        "status": "ok",
        "service": "PROA Service",
        "version": "2.0.0"
    }

@app.options("/{path:path}")
async def options_handler(path: str, request: Request):
    """Handler explicite pour les requêtes OPTIONS (preflight CORS)"""
    logger.info(f"[CORS] OPTIONS request for: /{path}")
    return JSONResponse(
        status_code=200,
        content={},
        headers={
            "Access-Control-Allow-Origin": request.headers.get("origin", "*"),
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH",
            "Access-Control-Allow-Headers": "Authorization, Content-Type, Accept, Origin, X-Requested-With, X-User-ID, X-Admin-Token, apikey, Prefer",
            "Access-Control-Max-Age": "86400",
        }
    )

# ============================================================
# 📄 SERVIR QUIZ.HTML
# ============================================================

from fastapi.responses import FileResponse

@app.get("/quiz")
async def get_quiz():
    quiz_path = os.path.join(os.path.dirname(__file__), "quiz.html")
    if os.path.exists(quiz_path):
        return FileResponse(quiz_path, media_type="text/html")
    return {"error": "quiz.html not found"}

# ============================================================
# 🚀 DÉMARRAGE
# ============================================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info"
    )