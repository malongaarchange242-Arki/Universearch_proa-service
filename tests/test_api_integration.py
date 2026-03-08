"""
Tests d'intégration pour l'API endpoints
"""

import pytest
import sys
import os
import json
from datetime import datetime
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


class TestHealthEndpoint:
    
    def test_health_ok(self):
        """Test que le health check fonctionne"""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


class TestComputeEndpoint:
    
    @pytest.fixture
    def valid_quiz_submission(self):
        """Fixture: soumission de quiz valide"""
        return {
            "user_id": "user_123",
            "quiz_version": "1.0",
            "responses": {
                "logic_1": 5.0,
                "technical_1": 4.0,
                "creativity_1": 3.0,
                "entrepreneurship_1": 4.0,
                "leadership_1": 3.0,
                "management_1": 4.0,
                "communication_1": 5.0,
                "teamwork_1": 4.0,
                "analysis_1": 3.0,
                "organization_1": 4.0,
                "resilience_1": 3.0,
                "negotiation_1": 2.0,
            }
        }
    
    @patch('api.routes.save_orientation_profile')
    @patch('api.routes.save_quiz_responses')
    def test_valid_submission(self, mock_save_quiz, mock_save_profile, valid_quiz_submission):
        """Test une soumission valide"""
        # Mock les saves pour éviter les erreurs DB
        mock_save_quiz.return_value = "sub_123"
        mock_save_profile.return_value = "prof_123"
        
        response = client.post("/orientation/compute", json=valid_quiz_submission)
        
        assert response.status_code == 201
        data = response.json()
        
        assert data["user_id"] == "user_123"
        assert data["quiz_version"] == "1.0"
        assert isinstance(data["profile"], list)
        assert isinstance(data["confidence"], float)
        assert 0.0 <= data["confidence"] <= 1.0
        assert "created_at" in data
    
    def test_missing_questions(self):
        """Test avec questions manquantes"""
        incomplete = {
            "user_id": "user_456",
            "quiz_version": "1.0",
            "responses": {
                "logic_1": 5.0,  # Incomplet
            }
        }
        
        response = client.post("/orientation/compute", json=incomplete)
        assert response.status_code == 422  # Validation error
        
        # Extraire le message d'erreur - detail est une liste d'erreurs Pydantic
        error_response = response.json()
        error_str = str(error_response)  # Convertir en string pour vérifier
        assert "Questions manquantes" in error_str
    
    def test_invalid_score_range(self):
        """Test avec scores hors limites [1, 5]"""
        invalid = {
            "user_id": "user_789",
            "quiz_version": "1.0",
            "responses": {
                "logic_1": 6.0,  # > 5
                "technical_1": 4.0,
                "creativity_1": 3.0,
                "entrepreneurship_1": 4.0,
                "leadership_1": 3.0,
                "management_1": 4.0,
                "communication_1": 5.0,
                "teamwork_1": 4.0,
                "analysis_1": 3.0,
                "organization_1": 4.0,
                "resilience_1": 3.0,
                "negotiation_1": 2.0,
            }
        }
        
        response = client.post("/orientation/compute", json=invalid)
        assert response.status_code == 422
        
        error_response = response.json()
        error_str = str(error_response)  # Pydantic v2 retourne une liste de dicts
        assert "hors intervalle" in error_str
    
    def test_zero_score(self):
        """Test avec score 0 (invalide)"""
        invalid = {
            "user_id": "user_000",
            "quiz_version": "1.0",
            "responses": {
                "logic_1": 0.0,  # < 1
                "technical_1": 4.0,
                "creativity_1": 3.0,
                "entrepreneurship_1": 4.0,
                "leadership_1": 3.0,
                "management_1": 4.0,
                "communication_1": 5.0,
                "teamwork_1": 4.0,
                "analysis_1": 3.0,
                "organization_1": 4.0,
                "resilience_1": 3.0,
                "negotiation_1": 2.0,
            }
        }
        
        response = client.post("/orientation/compute", json=invalid)
        assert response.status_code == 422
    
    def test_non_numeric_score(self):
        """Test avec scores non-numériques"""
        invalid = {
            "user_id": "user_abc",
            "quiz_version": "1.0",
            "responses": {
                "logic_1": "not_a_number",
                "technical_1": 4.0,
                "creativity_1": 3.0,
                "entrepreneurship_1": 4.0,
                "leadership_1": 3.0,
                "management_1": 4.0,
                "communication_1": 5.0,
                "teamwork_1": 4.0,
                "analysis_1": 3.0,
                "organization_1": 4.0,
                "resilience_1": 3.0,
                "negotiation_1": 2.0,
            }
        }
        
        response = client.post("/orientation/compute", json=invalid)
        assert response.status_code in [422, 500]
    
    @patch('api.routes.save_orientation_profile')
    @patch('api.routes.save_quiz_responses')
    def test_profile_consistency(self, mock_save_quiz, mock_save_profile, valid_quiz_submission):
        """Test que le profil est déterministe"""
        mock_save_quiz.return_value = "sub_123"
        mock_save_profile.return_value = "prof_123"
        
        response1 = client.post("/orientation/compute", json=valid_quiz_submission)
        response2 = client.post("/orientation/compute", json={
            **valid_quiz_submission,
            "user_id": "user_duplicate"  # Même quiz, utilisateur différent
        })
        
        assert response1.status_code == 201
        assert response2.status_code == 201
        
        # Le profil devrait être identique (même quiz)
        profile1 = response1.json()["profile"]
        profile2 = response2.json()["profile"]
        
        assert profile1 == profile2  # Déterministe


class TestScoreOnlyEndpoint:
    
    @pytest.fixture
    def valid_quiz_submission(self):
        return {
            "user_id": "user_score",
            "quiz_version": "1.0",
            "responses": {
                "logic_1": 5.0,
                "technical_1": 4.0,
                "creativity_1": 3.0,
                "entrepreneurship_1": 4.0,
                "leadership_1": 3.0,
                "management_1": 4.0,
                "communication_1": 5.0,
                "teamwork_1": 4.0,
                "analysis_1": 3.0,
                "organization_1": 4.0,
                "resilience_1": 3.0,
                "negotiation_1": 2.0,
            }
        }
    
    def test_score_only_valid(self, valid_quiz_submission):
        """Test endpoint /score-only"""
        response = client.post("/orientation/score-only", json=valid_quiz_submission)
        
        assert response.status_code == 200
        data = response.json()
        assert "score" in data
        assert 0.0 <= data["score"] <= 1.0


class TestFeedbackEndpoint:
    
    @patch('api.routes.save_orientation_feedback')
    def test_valid_feedback(self, mock_save_feedback):
        """Test soumission de feedback valide"""
        mock_save_feedback.return_value = None
        
        feedback = {
            "user_id": "user_feedback",
            "satisfaction": 4,
            "changed_orientation": False,
            "success": True,
        }
        
        response = client.post("/orientation/feedback", json=feedback)
        assert response.status_code == 200
        assert response.json()["status"] == "feedback_saved"
    
    def test_invalid_satisfaction(self):
        """Test avec satisfaction hors intervalle [1, 5]"""
        feedback = {
            "user_id": "user_bad",
            "satisfaction": 10,  # > 5
        }
        
        response = client.post("/orientation/feedback", json=feedback)
        assert response.status_code == 422


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
