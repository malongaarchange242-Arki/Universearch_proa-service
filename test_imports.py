#!/usr/bin/env python3
"""
Test rapide des imports pour PROA avec JWT
"""

try:
    import jwt
    print("✅ PyJWT importé avec succès")
except ImportError:
    print("❌ PyJWT n'est pas installé")
    exit(1)

try:
    from fastapi import Depends
    print("✅ Depends importé avec succès")
except ImportError:
    print("❌ Depends n'est pas disponible")
    exit(1)

try:
    from core.auth import verify_jwt_token, get_current_user_profile
    print("✅ Module auth importé avec succès")
except ImportError as e:
    print(f"❌ Erreur import auth: {e}")
    exit(1)

import os
jwt_secret = os.getenv("JWT_SECRET")
if jwt_secret:
    print("✅ JWT_SECRET configuré")
else:
    print("❌ JWT_SECRET manquant")

print("🎉 Tous les imports réussis !")