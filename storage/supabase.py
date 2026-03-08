# storage/supabase.py

from postgrest import SyncPostgrestClient
from typing import Any, Dict, List
import logging

from config import (
    SUPABASE_URL,
    SUPABASE_SERVICE_ROLE_KEY,
)

logger = logging.getLogger("supabase.storage")


class SupabaseStorage:
    """
    Couche d'accès aux données Supabase (PostgREST).
    Utilisée par le moteur d'orientation (rule / ml).
    """

    def __init__(self) -> None:
        if not SUPABASE_URL:
            raise RuntimeError("SUPABASE_URL manquant dans la configuration")

        if not SUPABASE_SERVICE_ROLE_KEY:
            raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY manquant dans la configuration")

        self.client = SyncPostgrestClient(
            f"{SUPABASE_URL}/rest/v1",
            headers={
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=5.0,  # sécurité prod
        )

        logger.info("Client Supabase initialisé avec succès")

    # --------------------------------------------------
    # Méthodes génériques
    # --------------------------------------------------

    def fetch_all(
        self,
        table: str,
        columns: str = "*",
        filters: Dict[str, Any] | None = None,
        limit: int | None = None,
    ) -> List[Dict[str, Any]]:
        try:
            query = self.client.from_(table).select(columns)

            if filters:
                for key, value in filters.items():
                    query = query.eq(key, value)

            if limit:
                query = query.limit(limit)

            response = query.execute()
            return response.data or []

        except Exception as exc:
            logger.error(
                "Erreur Supabase fetch_all | table=%s | erreur=%s",
                table,
                str(exc),
            )
            raise

    def fetch_one(
        self,
        table: str,
        filters: Dict[str, Any],
        columns: str = "*",
    ) -> Dict[str, Any] | None:
        results = self.fetch_all(table, columns, filters, limit=1)
        return results[0] if results else None

    def insert(
        self,
        table: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        try:
            response = self.client.from_(table).insert(payload).execute()
            return response.data[0] if response.data else {}

        except Exception as exc:
            logger.error(
                "Erreur Supabase insert | table=%s | payload=%s | erreur=%s",
                table,
                payload,
                str(exc),
            )
            raise

    def update(
        self,
        table: str,
        payload: Dict[str, Any],
        filters: Dict[str, Any],
    ) -> int:
        try:
            query = self.client.from_(table).update(payload)

            for key, value in filters.items():
                query = query.eq(key, value)

            response = query.execute()
            return len(response.data) if response.data else 0

        except Exception as exc:
            logger.error(
                "Erreur Supabase update | table=%s | filters=%s | erreur=%s",
                table,
                filters,
                str(exc),
            )
            raise

    def delete(
        self,
        table: str,
        filters: Dict[str, Any],
    ) -> int:
        try:
            query = self.client.from_(table).delete()

            for key, value in filters.items():
                query = query.eq(key, value)

            response = query.execute()
            return len(response.data) if response.data else 0

        except Exception as exc:
            logger.error(
                "Erreur Supabase delete | table=%s | filters=%s | erreur=%s",
                table,
                filters,
                str(exc),
            )
            raise
