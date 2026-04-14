#!/usr/bin/env python3
"""
Script de test pour démarrer PROA et vérifier l'intégration JWT
"""

import sys
import os

# Ajouter le répertoire au path
sys.path.insert(0, os.path.dirname(__file__))

try:
    # Tester les imports critiques
    from fastapi import APIRouter, HTTPException, status, Depends
    print("✅ FastAPI imports OK")

    import jwt
    print("✅ PyJWT OK")

    from core.auth import verify_jwt_token, get_current_user_profile, get_user_profile_dict
    print("✅ Auth module OK")

    # Tester la configuration
    jwt_secret = os.getenv("JWT_SECRET")
    if jwt_secret:
        print("✅ JWT_SECRET configuré")
    else:
        print("❌ JWT_SECRET manquant")
        sys.exit(1)

    # Tester l'import des routes
    from api.routes import router
    print("✅ Routes importées avec succès")

    print("🎉 Service PROA prêt à démarrer !")

except Exception as e:
    print(f"❌ Erreur: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)