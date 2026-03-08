# config.py
import os

# --------------------------------------------------
# Supabase
# --------------------------------------------------
SUPABASE_URL: str | None = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY: str | None = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# --------------------------------------------------
# Moteur d'orientation
# --------------------------------------------------
ENGINE_MODE: str = os.getenv("ENGINE_MODE", "rule")  # "rule" | "ml"
ENGINE_VERSION: str = os.getenv("ENGINE_VERSION", "v1")

# --------------------------------------------------
# PORA (microservice Go)
# --------------------------------------------------
PORA_SERVICE_URL: str = os.getenv("PORA_SERVICE_URL", "http://localhost:8080")
PORA_TIMEOUT_MS: int = int(os.getenv("PORA_TIMEOUT_MS", "3000"))

# --------------------------------------------------
# Application / Runtime
# --------------------------------------------------
APP_ENV: str = os.getenv("APP_ENV", "dev")          # "dev" | "staging" | "prod"
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "info")

# --------------------------------------------------
# Orientation / préparation ML
# --------------------------------------------------
ORIENTATION_VECTOR_SIZE: int = int(os.getenv("ORIENTATION_VECTOR_SIZE", "12"))
QUIZ_VERSION_ACTIVE: str = os.getenv("QUIZ_VERSION_ACTIVE", "v1")

# --------------------------------------------------
# Validation de la configuration (fail fast)
# --------------------------------------------------
def validate_config() -> None:
    """Vérifie que toutes les variables d'environnement essentielles sont présentes et cohérentes."""

    # Supabase
    if not SUPABASE_URL:
        raise RuntimeError("Configuration invalide : la variable SUPABASE_URL est manquante.")
    if not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("Configuration invalide : la clé SUPABASE_SERVICE_ROLE_KEY est manquante.")

    # Moteur d'orientation
    if ENGINE_MODE not in ("rule", "ml"):
        raise RuntimeError(
            f"Configuration invalide : ENGINE_MODE doit être 'rule' ou 'ml' (valeur reçue : '{ENGINE_MODE}')."
        )

    # PORA
    if not PORA_SERVICE_URL.startswith("http"):
        raise RuntimeError(
            f"Configuration invalide : l'URL du service PORA est incorrecte (PORA_SERVICE_URL = '{PORA_SERVICE_URL}')."
        )
    if PORA_TIMEOUT_MS <= 0:
        raise RuntimeError("Configuration invalide : PORA_TIMEOUT_MS doit être strictement supérieur à 0.")

    # Orientation / ML
    if ORIENTATION_VECTOR_SIZE <= 0:
        raise RuntimeError("Configuration invalide : ORIENTATION_VECTOR_SIZE doit être supérieur à 0.")

    # Runtime
    if APP_ENV == "prod" and LOG_LEVEL == "debug":
        raise RuntimeError("Configuration invalide : le niveau de log 'debug' est interdit en production.")
