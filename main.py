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
import os

app = FastAPI(title="Orientation Service", version="1.0.0")

# Handler pour afficher des logs verbeux lors des erreurs de validation (422)
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger = logging.getLogger("orientation.api")
    try:
        body = await request.body()
    except Exception:
        body = b"<unable to read body>"

    logger.warning(
        "Request validation failed: %s %s | errors=%s | body=%s",
        request.method,
        request.url,
        exc.errors(),
        body.decode("utf-8", errors="replace"),
    )

    # Return standard 422 payload with details so clients keep same behaviour
    return JSONResponse(status_code=422, content={"detail": exc.errors()})

# ============================================================
# 🔐 CORS Configuration
# ============================================================
# Autoriser les requêtes depuis le frontend (quiz.html)
app.add_middleware(
    CORSMiddleware,
    # During development allow all origins to avoid CORS issues from various frontend ports.
    # In production restrict this to the known frontend origins.
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

@app.get("/health")
def health():
    return {"status": "ok"}

# Servir quiz.html à la racine
from fastapi.responses import FileResponse

@app.get("/quiz")
async def get_quiz():
    quiz_path = os.path.join(os.path.dirname(__file__), "quiz.html")
    if os.path.exists(quiz_path):
        return FileResponse(quiz_path, media_type="text/html")
    return {"error": "quiz.html not found"}
