"""
Test guarantee contract for PROA recommendations pipeline:
- compute_recommended_fields() MUST ALWAYS return ≥ 5 items
- Never return empty array
- Handle fallback gracefully
"""

import pytest
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.recommendations import (
    compute_recommended_fields,
    _extract_keywords_from_profile,
    _build_profile_vector,
    _classify_bac_track,
)
from core.output_formatter import ProaResponse
from core.feature_engineering import build_features as build_features_fe


class TestRecommendationsGuarantee:
    """Test that recommendations pipeline never fails or returns empty."""
    
    def test_empty_profile_guarantee(self):
        """Test: Even with empty profile, should return 5+ items."""
        empty_profile = {
            "domains": {},
            "skills": {}
        }
        result = compute_recommended_fields(empty_profile, top_n=5)
        
        assert result is not None, "Result is None!"
        assert "recommended_fields" in result, "Missing 'recommended_fields' key"
        
        fields = result["recommended_fields"]
        assert len(fields) >= 5, f"Expected ≥5 fields, got {len(fields)}"
        
        for field in fields:
            assert "field_name" in field, "Missing field_name"
            assert "score" in field, "Missing score"
            assert "reason" in field, "Missing reason"
            assert "category" in field, "Missing category"
            print(f"  ✓ {field['field_name']}: {field['score']:.3f} ({field['category']})")
    
    def test_minimal_profile_guarantee(self):
        """Test: Even with minimal scores, should return items."""
        minimal_profile = {
            "domains": {
                "technical": 0.1,
                "business": 0.05
            },
            "skills": {
                "analytical": 0.08
            }
        }
        result = compute_recommended_fields(minimal_profile, top_n=5)
        
        fields = result["recommended_fields"]
        assert len(fields) >= 5, f"Expected ≥5 fields with minimal profile, got {len(fields)}"
        print(f"✓ Minimal profile returned {len(fields)} recommendations")
    
    def test_zero_score_profile_guarantee(self):
        """Test: Even all zeros, should return fallback."""
        zero_profile = {
            "domains": {
                "a": 0.0,
                "b": 0.0
            },
            "skills": {
                "x": 0.0
            }
        }
        result = compute_recommended_fields(zero_profile, top_n=5)
        
        fields = result["recommended_fields"]
        assert len(fields) >= 5, f"Expected ≥5 fallback fields, got {len(fields)}"
        
        # Check for fallback category
        has_fallback = any(f["category"] == "fallback" for f in fields)
        assert has_fallback, "Expected fallback recommendations with zero scores"
        print(f"✓ Zero-score profile returned {len(fields)} fallback recommendations")
    
    def test_response_structure_invariant(self):
        """Test: Response structure is always correct."""
        profile = {
            "domains": {"technical": 0.7},
            "skills": {}
        }
        result = compute_recommended_fields(profile, top_n=5)
        
        assert isinstance(result, dict), "Response is not dict"
        assert "recommended_fields" in result, "Missing recommended_fields"
        assert "field_scores" in result, "Missing field_scores"
        assert "insight" in result, "Missing insight"
        
        fields = result["recommended_fields"]
        field_scores = result["field_scores"]
        assert isinstance(fields, list), "recommended_fields is not list"
        assert isinstance(field_scores, dict), "field_scores is not dict"
        assert isinstance(result["insight"], str), "insight is not string"
        
        for field in fields:
            assert isinstance(field["field_name"], str), f"field_name not string: {field}"
            assert isinstance(field["score"], (int, float)), f"score not numeric: {field}"
            assert 0.0 <= field["score"] <= 1.0, f"score out of range: {field['score']}"
            assert isinstance(field["reason"], str), f"reason not string: {field}"
            assert field["category"] in ["Supabase", "fallback"], f"invalid category: {field['category']}"
            assert field["field_name"] in field_scores, f"field_name {field['field_name']} missing from field_scores"
            assert field_scores[field["field_name"]] == field["score"], f"score mismatch for {field['field_name']}"

    def test_keyword_normalization_strips_prefixes(self):
        """Test: Profile keys with domain_/skill_ prefixes normalize correctly."""
        profile = {
            "domains": {
                "domain_technical": 0.8,
                "domain_logic": 0.6,
            },
            "skills": {
                "skill_communication": 0.7,
            }
        }
        keywords = _extract_keywords_from_profile(profile)
        assert ("technical", 0.8) in keywords
        assert ("logic", 0.6) in keywords
        assert ("communication", 0.7) in keywords
        assert all(not key.startswith("domain_") and not key.startswith("skill_") for key, _ in keywords)

    def test_profile_vector_keeps_technical_signal(self):
        """Canonical feature names should not collapse to business-only."""
        profile = {
            "domains": {
                "technical": 1.0,
                "business": 0.8,
            },
            "skills": {
                "logic": 1.0,
                "creativity": 0.8,
            }
        }

        vector = _build_profile_vector(profile)

        assert vector["tech"] > 0.0, f"Expected tech > 0, got {vector}"
        assert vector["expertise"] > 0.0, f"Expected expertise > 0, got {vector}"
        assert vector["creativity"] > 0.0, f"Expected creativity > 0, got {vector}"
        assert vector["business"] < 1.0, f"Profile should not collapse to pure business: {vector}"

    def test_recommendations_can_surface_law_fields_from_db(self, monkeypatch):
        """A legal/public profile should be able to surface legal filieres from DB."""
        fake_filieres = [
            {"id": "1", "nom": "Droit Public", "description": "administration publique et gouvernance"},
            {"id": "2", "nom": "Sciences Politiques", "description": "institutions, politique et diplomatie"},
            {"id": "3", "nom": "Génie Logiciel", "description": "programmation et informatique"},
            {"id": "4", "nom": "Comptabilité et Gestion financière", "description": "finance et audit"},
            {"id": "5", "nom": "Marketing Digital & Communication", "description": "communication et marketing"},
        ]

        monkeypatch.setattr("core.recommendations._fetch_filieres_from_db", lambda: fake_filieres)

        profile = {
            "domains": {
                "analysis": 1.0,
                "communication": 0.8,
                "leadership": 0.7,
            },
            "skills": {
                "logic": 0.6,
            }
        }

        result = compute_recommended_fields(profile, top_n=3)
        names = [field["field_name"] for field in result["recommended_fields"]]

        assert any("Droit" in name or "Politiques" in name for name in names), \
            f"Expected legal/public fields in recommendations, got {names}"

    def test_dynamic_semantic_mapping_uses_raw_choice_metadata(self):
        """Dynamic quiz choices should preserve technical/scientific intent via raw metadata."""
        responses = {
            "q_field_interest": 1,
            "q_bac_type": 4,
            "q_long_focus": 4,
            "q_math_problem_reaction": 3,
        }
        response_metadata = {
            "q_field_interest": {"raw_value": "tech", "selected_text": "Tech", "question_type": "choice"},
            "q_bac_type": {"raw_value": "F3", "selected_text": "F3", "question_type": "autocomplete"},
            "q_long_focus": {"raw_value": 4, "selected_text": "4", "question_type": "likert"},
            "q_math_problem_reaction": {"raw_value": 3, "selected_text": "3", "question_type": "choice"},
        }

        features = build_features_fe(
            responses,
            orientation_type="field",
            response_metadata=response_metadata,
        )

        assert features["domain_technical"] > 0.6, f"Expected strong technical signal, got {features}"
        assert features["domain_analysis"] > 0.6, f"Expected strong analysis signal, got {features}"
        assert features["domain_learning"] > 0.4, f"Expected learning signal, got {features}"
        assert features.get("domain_management", 0.0) < features["domain_technical"], \
            f"Profile should not be dominated by management: {features}"

    def test_dynamic_semantic_mapping_can_surface_tech_fields_from_db(self, monkeypatch):
        """A tech/science dynamic profile should not collapse to business-only recommendations."""
        fake_filieres = [
            {"id": "1", "nom": "GÃ©nie Logiciel", "description": "programmation, architecture logicielle et informatique"},
            {"id": "2", "nom": "Data Science", "description": "analyse de donnÃ©es, statistique et intelligence artificielle"},
            {"id": "3", "nom": "ComptabilitÃ© et Gestion financiÃ¨re", "description": "finance et audit"},
            {"id": "4", "nom": "Droit Public", "description": "administration publique et gouvernance"},
            {"id": "5", "nom": "Marketing Digital & Communication", "description": "communication et marketing"},
        ]

        monkeypatch.setattr("core.recommendations._fetch_filieres_from_db", lambda: fake_filieres)

        responses = {
            "q_science_vs_literature": 1,
            "q_field_interest": 1,
            "q_bac_type": 4,
            "q_long_focus": 4,
            "q_effort_level": 4,
            "q_math_problem_reaction": 3,
        }
        response_metadata = {
            "q_science_vs_literature": {"raw_value": "science", "selected_text": "science", "question_type": "choice"},
            "q_field_interest": {"raw_value": "tech", "selected_text": "tech", "question_type": "choice"},
            "q_bac_type": {"raw_value": "F3", "selected_text": "F3", "question_type": "autocomplete"},
            "q_long_focus": {"raw_value": 4, "selected_text": "4", "question_type": "likert"},
            "q_effort_level": {"raw_value": 4, "selected_text": "4", "question_type": "likert"},
            "q_math_problem_reaction": {"raw_value": 3, "selected_text": "3", "question_type": "choice"},
        }

        features = build_features_fe(
            responses,
            orientation_type="field",
            response_metadata=response_metadata,
        )

        domains = {
            key.replace("domain_", ""): value
            for key, value in features.items()
            if key.startswith("domain_")
        }
        skills = {
            key.replace("skill_", ""): value
            for key, value in features.items()
            if key.startswith("skill_")
        }

        result = compute_recommended_fields({"domains": domains, "skills": skills}, top_n=3)
        names = [field["field_name"] for field in result["recommended_fields"]]

        assert any("Logiciel" in name or "Data Science" in name for name in names), \
            f"Expected technical fields in recommendations, got {names}"

    def test_decision_layer_prefers_dominant_cluster_for_hybrid_profile(self, monkeypatch):
        """Hybrid profiles should still get a coherent dominant cluster in final ranking."""
        fake_filieres = [
            {"id": "1", "nom": "RÃ©seau et TÃ©lÃ©communication", "description": "reseaux, telecom, infrastructure numerique"},
            {"id": "2", "nom": "TÃ©lÃ©communication et RÃ©seaux", "description": "reseaux telecommunication et systemes"},
            {"id": "3", "nom": "GÃ©nie Logiciel", "description": "programmation, architecture logicielle et informatique"},
            {"id": "4", "nom": "Droit PrivÃ©", "description": "juridique, droit civil et justice"},
            {"id": "5", "nom": "Droit PÃ©nal", "description": "justice penale et procedure"},
            {"id": "6", "nom": "Droit Public", "description": "administration publique et gouvernance"},
        ]

        monkeypatch.setattr("core.recommendations._fetch_filieres_from_db", lambda: fake_filieres)

        profile = {
            "domains": {
                "technical": 0.92,
                "analysis": 0.78,
                "communication": 0.42,
                "adaptability": 0.55,
            },
            "skills": {
                "logic": 0.81,
            }
        }

        result = compute_recommended_fields(profile, top_n=3)
        names = [field["field_name"] for field in result["recommended_fields"]]

        assert result.get("dominant_cluster") == "informatique", \
            f"Expected informatique dominant cluster, got {result.get('dominant_cluster')} with {names}"
        assert all("Droit" not in name for name in names[:2]), \
            f"Expected the top of the ranking to stay technical, got {names}"
        assert any("RÃ©seau" in name or "TÃ©lÃ©communication" in name or "Logiciel" in name for name in names), \
            f"Expected technical fields in final ranking, got {names}"

    def test_bac_weighting_f3_favors_technical_fields(self, monkeypatch):
        """F3 should bias hybrid profiles toward technical tracks over law/social tracks."""
        fake_filieres = [
            {"id": "1", "nom": "RÃ©seau et TÃ©lÃ©communication", "description": "reseaux, telecom, infrastructure numerique"},
            {"id": "2", "nom": "TÃ©lÃ©communication et RÃ©seaux", "description": "reseaux telecommunication et systemes"},
            {"id": "3", "nom": "Data Science & Intelligence Artificielle", "description": "analyse de donnees, intelligence artificielle et systemes"},
            {"id": "4", "nom": "Droit PrivÃ©", "description": "juridique, droit civil et justice"},
            {"id": "5", "nom": "Sciences Politiques", "description": "gouvernance, politique et diplomatie"},
        ]

        monkeypatch.setattr("core.recommendations._fetch_filieres_from_db", lambda: fake_filieres)

        profile = {
            "domains": {
                "technical": 0.74,
                "analysis": 0.68,
                "communication": 0.52,
                "leadership": 0.44,
            },
            "skills": {
                "logic": 0.71,
            },
            "context": {
                "bac_type": "F3",
            },
        }

        result = compute_recommended_fields(profile, top_n=3)
        names = [field["field_name"] for field in result["recommended_fields"]]

        assert result.get("bac_track") == "technical", \
            f"Expected bac track 'technical', got {result.get('bac_track')}"
        assert all("Droit" not in name and "Politiques" not in name for name in names[:2]), \
            f"Expected F3 ranking to keep legal fields out of the top 2, got {names}"

        top_item = result["recommended_fields"][0]
        assert top_item.get("bac_score", 0.0) >= 0.75, \
            f"Expected strong bac compatibility on top result, got {top_item}"

    def test_bac_track_classification_supports_target_series(self):
        """The bac rule should recognize the main target series."""
        assert _classify_bac_track("A") == "humanities"
        assert _classify_bac_track("C/D") == "science"
        assert _classify_bac_track("E/F") == "technical"
        assert _classify_bac_track("H") == "informatics"
        assert _classify_bac_track("BG") == "business"
        assert _classify_bac_track("P") == "vocational"

    def test_bac_weighting_h_favors_informatics_and_network_fields(self, monkeypatch):
        """Bac H should prioritize informatique, telecoms, systems and data."""
        fake_filieres = [
            {"id": "1", "nom": "Reseaux et Telecommunication", "description": "reseau telecom systeme infrastructure numerique"},
            {"id": "2", "nom": "Data Science", "description": "analyse de donnees et systemes intelligents"},
            {"id": "3", "nom": "Comptabilite & Gestion", "description": "finance et audit"},
            {"id": "4", "nom": "Droit Public", "description": "administration et gouvernance"},
        ]

        monkeypatch.setattr("core.recommendations._fetch_filieres_from_db", lambda: fake_filieres)

        profile = {
            "domains": {
                "technical": 0.66,
                "analysis": 0.62,
                "communication": 0.4,
                "business": 0.38,
            },
            "skills": {
                "logic": 0.72,
            },
            "context": {
                "bac_type": "H",
            },
        }

        result = compute_recommended_fields(profile, top_n=3)
        names = [field["field_name"] for field in result["recommended_fields"]]

        assert result.get("bac_track") == "informatics", \
            f"Expected bac track 'informatics', got {result.get('bac_track')}"
        assert any("Reseaux" in name or "Data Science" in name for name in names[:2]), \
            f"Expected Bac H top results to stay in IT/network fields, got {names}"
        assert all("Comptabilite" not in name and "Droit" not in name for name in names[:2]), \
            f"Expected non-compatible fields to stay behind IT/network fields, got {names}"
        assert result["recommended_fields"][0].get("bac_score", 0.0) >= 0.75, \
            f"Expected strong Bac H compatibility on the top item, got {result['recommended_fields'][0]}"
        assert result["recommended_fields"][0].get("bac_match_score") == result["recommended_fields"][0].get("bac_score"), \
            f"Expected bac_match_score alias to match bac_score, got {result['recommended_fields'][0]}"

    def test_bac_weighting_bg_favors_management_fields(self, monkeypatch):
        """Bac G/BG should prioritize management, accounting, HR and commerce."""
        fake_filieres = [
            {"id": "1", "nom": "Comptabilite & Gestion", "description": "finance comptabilite entreprise"},
            {"id": "2", "nom": "Ressources Humaines", "description": "management communication equipe"},
            {"id": "3", "nom": "Business Trade & Marketing", "description": "commerce gestion marketing"},
            {"id": "4", "nom": "Genie Logiciel", "description": "programmation informatique"},
            {"id": "5", "nom": "Droit Public", "description": "gouvernance et justice"},
        ]

        monkeypatch.setattr("core.recommendations._fetch_filieres_from_db", lambda: fake_filieres)

        profile = {
            "domains": {
                "business": 0.68,
                "communication": 0.61,
                "analysis": 0.54,
                "technical": 0.38,
            },
            "skills": {
                "leadership": 0.63,
            },
            "context": {
                "bac_type": "BG",
            },
        }

        result = compute_recommended_fields(profile, top_n=3)
        names = [field["field_name"] for field in result["recommended_fields"]]

        assert result.get("bac_track") == "business", \
            f"Expected bac track 'business', got {result.get('bac_track')}"
        assert any(
            "Comptabilite" in name or "Ressources Humaines" in name or "Business" in name
            for name in names[:2]
        ), f"Expected management fields at the top for Bac BG, got {names}"
        assert all("Genie Logiciel" not in name for name in names[:2]), \
            f"Expected technical alternatives to stay behind management fields, got {names}"

    def test_bac_weighting_p_favors_practical_technical_tracks(self, monkeypatch):
        """Bac P should prioritize practical technical tracks like maintenance and BTP."""
        fake_filieres = [
            {"id": "1", "nom": "Maintenance Industrielle", "description": "maintenance industrielle atelier pratique"},
            {"id": "2", "nom": "BTP", "description": "chantier construction batiment"},
            {"id": "3", "nom": "Genie Civil", "description": "travaux publics infrastructure"},
            {"id": "4", "nom": "Comptabilite & Gestion", "description": "finance entreprise"},
            {"id": "5", "nom": "Genie Logiciel", "description": "programmation informatique"},
        ]

        monkeypatch.setattr("core.recommendations._fetch_filieres_from_db", lambda: fake_filieres)

        profile = {
            "domains": {
                "technical": 0.58,
                "organization": 0.44,
                "analysis": 0.35,
                "business": 0.2,
            },
            "skills": {},
            "context": {
                "bac_type": "P",
            },
        }

        result = compute_recommended_fields(profile, top_n=3)
        names = [field["field_name"] for field in result["recommended_fields"]]

        assert result.get("bac_track") == "vocational", \
            f"Expected bac track 'vocational', got {result.get('bac_track')}"
        assert any("Maintenance" in name or "BTP" in name or "Genie Civil" in name for name in names[:2]), \
            f"Expected practical technical fields at the top for Bac P, got {names}"
        assert all("Comptabilite" not in name for name in names[:2]), \
            f"Expected management fields to stay behind vocational tracks, got {names}"

    def test_bac_weighting_keeps_strong_profile_alternatives_visible(self, monkeypatch):
        """Bac compatibility should prioritize, not hard-filter, a very coherent profile."""
        fake_filieres = [
            {"id": "1", "nom": "Droit Public", "description": "justice administration gouvernance"},
            {"id": "2", "nom": "Sciences Humaines", "description": "societe culture communication"},
            {"id": "3", "nom": "Genie Logiciel", "description": "programmation informatique systemes"},
            {"id": "4", "nom": "Data Science", "description": "data statistique analyse"},
        ]

        monkeypatch.setattr("core.recommendations._fetch_filieres_from_db", lambda: fake_filieres)

        profile = {
            "domains": {
                "technical": 0.96,
                "analysis": 0.88,
                "communication": 0.7,
            },
            "skills": {
                "logic": 0.94,
            },
            "context": {
                "bac_type": "A",
            },
        }

        result = compute_recommended_fields(profile, top_n=4)
        names = [field["field_name"] for field in result["recommended_fields"]]

        assert result.get("bac_track") == "humanities", \
            f"Expected bac track 'humanities', got {result.get('bac_track')}"
        assert any("Genie Logiciel" in name or "Data Science" in name for name in names), \
            f"Expected strong technical alternatives to remain visible, got {names}"

    def test_output_formatter_preserves_bac_match_score_for_ui(self):
        """The API formatter should expose bac_match_score to the frontend/UI."""
        response = ProaResponse.compute_orientation(
            user_id="user_bac_ui",
            profile=[0.1, 0.2, 0.3],
            confidence=0.82,
            quiz_version="1.0",
            recommended_fields=[
                {
                    "field_name": "Reseaux et Telecommunication",
                    "score": 0.91,
                    "reason": "Compatibilite forte",
                    "category": "Supabase",
                    "cluster": "informatique",
                    "bac_score": 0.84,
                    "bac_match_score": 0.84,
                    "bac_track": "informatics",
                }
            ],
            field_scores={"Reseaux et Telecommunication": 0.91},
            insight="Profil tres coherent",
        )

        top_field = response["recommended_fields"][0]
        assert top_field["bac_score"] == 0.84
        assert top_field["bac_match_score"] == 0.84
        assert top_field["bac_track"] == "informatics"
        assert top_field["cluster"] == "informatique"

    def test_feature_engineering_no_crash(self):
        """Test: Feature engineering never crashes even with bad input."""
        test_responses = {
            "Q19": 0,
            "Q20": 1,
            "Q21": 2,
            "Q22": 3,
            "Q23": 4,
            "Q24": 5
        }
        
        features = build_features_fe(test_responses, orientation_type="field")
        
        assert features is not None, "Features is None!"
        assert isinstance(features, dict), "Features is not dict"
        assert len(features) > 0, "Features is empty - fallback failed!"
        
        for key, value in features.items():
            assert isinstance(value, (int, float)), f"{key} is not numeric"
            assert 0.0 <= value <= 1.0, f"{key} out of range: {value}"
        
        print(f"✓ Feature engineering generated {len(features)} features")
        print(f"  Features: {features}")
    
    def test_top_n_parameter_respected(self):
        """Test: top_n parameter is respected."""
        profile = {
            "domains": {"technical": 0.8},
            "skills": {}
        }
        
        for top_n in [3, 5, 10]:
            result = compute_recommended_fields(profile, top_n=top_n)
            fields = result["recommended_fields"]
            
            # Should return max(top_n, available) but at least min(top_n, 5)
            expected = max(top_n, min(top_n, 5))
            assert len(fields) >= min(top_n, 5), \
                f"top_n={top_n}: expected ≥{min(top_n, 5)}, got {len(fields)}"
            
            print(f"✓ top_n={top_n}: returned {len(fields)} fields")


if __name__ == "__main__":
    print("=" * 60)
    print("PROA RECOMMENDATIONS GUARANTEE TEST SUITE")
    print("=" * 60)
    
    test = TestRecommendationsGuarantee()
    
    print("\n1. Testing empty profile guarantee...")
    test.test_empty_profile_guarantee()
    
    print("\n2. Testing minimal profile guarantee...")
    test.test_minimal_profile_guarantee()
    
    print("\n3. Testing zero-score profile guarantee...")
    test.test_zero_score_profile_guarantee()
    
    print("\n4. Testing response structure invariant...")
    test.test_response_structure_invariant()
    
    print("\n5. Testing feature engineering robustness...")
    test.test_feature_engineering_no_crash()
    
    print("\n6. Testing top_n parameter...")
    test.test_top_n_parameter_respected()
    
    print("\n" + "=" * 60)
    print("✅ ALL GUARANTEE TESTS PASSED")
    print("=" * 60)
