#!/usr/bin/env python3
"""
Test script pour vérifier l'intégration JWT dans PROA
"""

import sys
import os

# Ajouter le répertoire courant au path
sys.path.insert(0, os.path.dirname(__file__))

try:
    # Tester l'import du module auth
    from core.auth import verify_jwt_token, get_current_user_profile
    print("✅ Module auth importé avec succès")

    # Tester l'import PyJWT
    import jwt
    print("✅ PyJWT disponible")

    # Tester la configuration JWT_SECRET
    jwt_secret = os.getenv("JWT_SECRET")
    if jwt_secret:
        print("✅ JWT_SECRET configuré")
    else:
        print("❌ JWT_SECRET manquant")

    print("🎉 Toutes les vérifications passées !")

except ImportError as e:
    print(f"❌ Erreur d'import: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ Erreur: {e}")
    sys.exit(1)