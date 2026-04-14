#!/usr/bin/env python3
"""
Test rapide du système d'orientation intelligent
"""

import sys
import os

# Ajouter le répertoire au path
sys.path.insert(0, os.path.dirname(__file__))

try:
    # Tester les imports
    from fastapi import APIRouter, HTTPException, status, Depends
    print("✅ FastAPI imports OK")

    import jwt
    print("✅ PyJWT OK")

    from core.auth import verify_jwt_token, get_current_user_profile, get_user_profile_dict
    print("✅ Auth module OK")

    from api.routes import get_adaptive_quiz
    print("✅ Fonction get_adaptive_quiz OK")

    # Tester la configuration
    jwt_secret = os.getenv("JWT_SECRET")
    if jwt_secret:
        print("✅ JWT_SECRET configuré")
    else:
        print("❌ JWT_SECRET manquant")
        sys.exit(1)

    # Tester la fonction get_adaptive_quiz
    test_quiz = get_adaptive_quiz("bachelier")
    print(f"✅ Quiz bachelier généré: {test_quiz['question_count']} questions")

    test_quiz = get_adaptive_quiz("etudiant")
    print(f"✅ Quiz étudiant généré: {test_quiz['question_count']} questions")

    test_quiz = get_adaptive_quiz("parent")
    print(f"✅ Quiz parent généré: {test_quiz['question_count']} questions")

    print("🎉 Système d'orientation intelligent prêt !")

except Exception as e:
    print(f"❌ Erreur: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)