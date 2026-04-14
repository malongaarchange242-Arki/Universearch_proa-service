# core/auth.py

import os
import jwt
import logging
from typing import Dict, Optional, Any
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from db.repository import supabase

logger = logging.getLogger("orientation.auth")

# Configuration JWT
JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    raise RuntimeError("JWT_SECRET environment variable is required")

# Schéma pour le payload du token JWT
class AuthTokenPayload(BaseModel):
    id: str
    email: str | None
    role: str

# Schéma pour le profil utilisateur récupéré depuis Supabase
class UserProfile(BaseModel):
    id: str
    user_type: str | None
    email: str | None
    nom: str | None
    prenom: str | None
    telephone: str | None
    profile_type: str | None
    date_naissance: str | None
    genre: str | None

# Sécurité HTTP Bearer pour l'extraction du token
security = HTTPBearer()

def verify_jwt_token(token: str) -> AuthTokenPayload:
    """
    Vérifie et décode un token JWT.

    Args:
        token: Le token JWT à vérifier

    Returns:
        AuthTokenPayload: Le payload décodé du token

    Raises:
        HTTPException: Si le token est invalide ou expiré
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return AuthTokenPayload(**payload)
    except jwt.ExpiredSignatureError:
        logger.warning("Token JWT expiré")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expiré",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as e:
        logger.warning(f"Token JWT invalide: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide",
            headers={"WWW-Authenticate": "Bearer"},
        )

async def get_current_user_profile(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> UserProfile:
    """
    Dépendance FastAPI pour récupérer le profil utilisateur depuis le token JWT.

    Args:
        credentials: Les credentials HTTP Bearer (token JWT)

    Returns:
        UserProfile: Le profil complet de l'utilisateur

    Raises:
        HTTPException: Si l'utilisateur n'est pas trouvé ou le token invalide
    """
    # Vérifier et décoder le token
    token_payload = verify_jwt_token(credentials.credentials)

    # Récupérer le profil utilisateur depuis Supabase
    try:
        # Essayer la jointure si elle existe (comme dans identity-service)
        result = supabase.table('utilisateurs').select(
            'id, user_type, created_at, updated_at, profiles(email, nom, prenom, telephone, profile_type, date_naissance, genre)'
        ).eq('id', token_payload.id).single()

        if result.data is None:
            logger.warning(f"Utilisateur non trouvé: {token_payload.id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Utilisateur non trouvé"
            )

        # Extraire le profil (peut être un objet ou un array)
        profile_data = result.data.get('profiles')
        if isinstance(profile_data, list) and len(profile_data) > 0:
            profile_data = profile_data[0]
        elif not profile_data:
            profile_data = {}

        # Construire le profil utilisateur
        user_profile = UserProfile(
            id=result.data['id'],
            user_type=result.data.get('user_type'),
            email=profile_data.get('email'),
            nom=profile_data.get('nom'),
            prenom=profile_data.get('prenom'),
            telephone=profile_data.get('telephone'),
            profile_type=profile_data.get('profile_type'),
            date_naissance=profile_data.get('date_naissance'),
            genre=profile_data.get('genre')
        )

        logger.info(f"Profil utilisateur récupéré: {user_profile.id}")
        return user_profile

    except Exception as e:
        logger.error(f"Erreur lors de la récupération du profil utilisateur {token_payload.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la récupération du profil utilisateur"
        )

def get_user_profile_dict(user_profile: UserProfile) -> Dict[str, Any]:
    """
    Convertit un UserProfile en dictionnaire compatible avec l'ancien format.

    Args:
        user_profile: Le profil utilisateur

    Returns:
        Dict[str, Any]: Dictionnaire avec les données du profil
    """
    return {
        "user_id": user_profile.id,
        "user_type": user_profile.user_type,
        "email": user_profile.email,
        "nom": user_profile.nom,
        "prenom": user_profile.prenom,
        "telephone": user_profile.telephone,
        "profile_type": user_profile.profile_type,
        "date_naissance": user_profile.date_naissance,
        "genre": user_profile.genre
    }