"""
PROA Orchestrator - Main orchestration engine
Coordinates feature engineering → domain scoring → filière scoring → PORA → recommendations
"""

import logging
from datetime import datetime
from typing import Dict, Optional, Any
from supabase import Client

from models.proa import (
    ProaComputeRequest, ProaComputeResponse, FeatureScore,
    ComputationStats, UserType
)
from core.feature_engineering import build_features
from core.domain_scoring import DomainScoringEngine
from core.filiere_scoring import FiliereEngineScore
from core.pora_scoring import PoraScoring
from core.recommendation_engine import RecommendationEngine
from core.utils import normalize_responses

logger = logging.getLogger(__name__)


class ProaOrchestrator:
    """
    Main orchestrator for complete PROA computation
    
    Pipeline:
    1. Feature Engineering: responses → normalized features
    2. Domain Scoring: features → domain scores
    3. Filière Scoring: domains → filière compatibility scores
    4. PORA Scoring: filière scores → université/centre rankings
    5. Recommendations: Generate personalized recommendations
    """
    
    def __init__(self, supabase: Client):
        self.supabase = supabase
        
        # Initialize sub-engines
        self.domain_scorer = DomainScoringEngine(supabase)
        self.filiere_scorer = FiliereEngineScore(supabase)
        self.pora_scorer = PoraScoring(supabase)
        self.recommendation_engine = RecommendationEngine(supabase)
        
        # Statistics
        self.stats = None
    
    # =========================================================================
    # MAIN COMPUTATION
    # =========================================================================
    
    def compute(self, request: ProaComputeRequest) -> ProaComputeResponse:
        """
        Complete PROA computation pipeline
        
        Args:
            request: ProaComputeRequest with user data and responses
        
        Returns:
            ProaComputeResponse with all scores and recommendations
        """
        logger.info(f"🚀 Starting PROA computation for user {request.user_id}")
        logger.info(f"   User type: {request.user_type}")
        logger.info(f"   Responses: {len(request.responses)} questions")
        
        start_time = datetime.utcnow()
        
        # Initialize statistics
        self.stats = ComputationStats(
            user_id=request.user_id,
            user_type=request.user_type.value,
            start_time=start_time,
            end_time=None,
            total_responses=len(request.responses),
            valid_responses=0,
            missing_responses=0,
            invalid_responses=0,
            domain_coverage=0.0,
            feature_coverage=0.0,
            filiere_coverage=0.0,
            db_query_count=0,
            cache_hits=0,
            cache_misses=0
        )
        
        try:
            # ===================================================================
            # STEP 1: FEATURE ENGINEERING
            # ===================================================================
            logger.info("\n📊 STEP 1: Feature Engineering")
            logger.info("=" * 60)
            
            features_dict = build_features(
                request.responses,
                self.supabase,
                request.orientation_type
            )
            
            # Convert to FeatureScore objects
            features = {}
            for feature_name, score in features_dict.items():
                features[feature_name] = FeatureScore(
                    name=feature_name,
                    score=float(score),
                    weight=1.0,  # Will be refined per domain
                    contribution=float(score),
                    question_count=0
                )
            
            logger.info(f"✅ Feature engineering complete: {len(features)} features")
            self.stats.feature_coverage = len(features) / 24.0 if len(features) > 0 else 0.0
            
            # ===================================================================
            # STEP 2: DOMAIN SCORING
            # ===================================================================
            logger.info("\n🧠 STEP 2: Domain Scoring")
            logger.info("=" * 60)
            
            domain_scores, domain_stats = self.domain_scorer.compute_domain_scores(
                request.responses,
                features
            )
            
            logger.info(f"✅ Domain scoring complete: {len(domain_scores)} domains")
            self.stats.domain_coverage = domain_stats.get("avg_confidence", 0.0)
            
            # ===================================================================
            # STEP 3: FILIÈRE SCORING
            # ===================================================================
            logger.info("\n🎓 STEP 3: Filière Scoring")
            logger.info("=" * 60)
            
            filiere_scores, filiere_stats = self.filiere_scorer.compute_filiere_scores(
                domain_scores
            )
            
            logger.info(f"✅ Filière scoring complete: {len(filiere_scores)} filieres scored")
            self.stats.filiere_coverage = filiere_stats.get("filieres_scored", 0) / max(1, filiere_stats.get("total_filieres", 1))
            
            # ===================================================================
            # STEP 4: PORA SCORING (University + Centre)
            # ===================================================================
            logger.info("\n🎯 STEP 4: PORA Scoring (Universités & Centres)")
            logger.info("=" * 60)
            
            universite_scores, uni_stats = self.pora_scorer.compute_universite_scores(
                filiere_scores,
                top_n=50  # Keep more for recommendations
            )
            
            centre_scores, centre_stats = self.pora_scorer.compute_centre_scores(
                filiere_scores,
                top_n=50
            )
            
            logger.info(f"✅ PORA scoring complete:")
            logger.info(f"   Universités: {len(universite_scores)} ranked")
            logger.info(f"   Centres: {len(centre_scores)} ranked")
            
            # ===================================================================
            # STEP 5: RECOMMENDATIONS
            # ===================================================================
            logger.info("\n💡 STEP 5: Recommendations")
            logger.info("=" * 60)
            
            filiere_recommendations = self.recommendation_engine.recommend_filieres(
                filiere_scores,
                top_n=7,
                min_score=0.3
            )
            
            universite_recommendations = self.recommendation_engine.recommend_universites(
                universite_scores,
                filiere_recommendations,
                top_n=7
            )
            
            centre_recommendations = self.recommendation_engine.recommend_centres(
                centre_scores,
                top_n=7
            )
            
            logger.info(f"✅ Recommendations generated:")
            logger.info(f"   Filieres: {len(filiere_recommendations)}")
            logger.info(f"   Universités: {len(universite_recommendations)}")
            logger.info(f"   Centres: {len(centre_recommendations)}")
            
            # ===================================================================
            # COMPUTE COVERAGE METRICS
            # ===================================================================
            normalized_responses = normalize_responses(request.responses)
            valid_count = len([v for v in normalized_responses.values() if v is not None])
            
            self.stats.valid_responses = valid_count
            self.stats.missing_responses = len(request.responses) - valid_count
            
            total_q = len(request.responses)
            coverage = valid_count / total_q if total_q > 0 else 0.0
            
            # ===================================================================
            # ASSEMBLE RESPONSE
            # ===================================================================
            self.stats.end_time = datetime.utcnow()
            
            response = ProaComputeResponse(
                user_id=request.user_id,
                timestamp=datetime.utcnow(),
                features=features,
                domain_scores=domain_scores,
                filiere_scores=filiere_scores[:10],  # Top 10 for response
                universites=universite_scores[:7],
                centres=centre_scores[:7],
                recommendations={
                    "filieres": filiere_recommendations,
                    "universites": universite_recommendations,
                    "centres": centre_recommendations
                },
                total_questions=len(request.responses),
                matched_questions=valid_count,
                coverage=round(coverage, 4),
                confidence=round(
                    (self.stats.domain_coverage + self.stats.filiere_coverage) / 2,
                    4
                ),
                computation_time_ms=self.stats.computation_time_ms,
                metrics={
                    "domain_stats": domain_stats,
                    "filiere_stats": filiere_stats,
                    "universite_stats": uni_stats,
                    "centre_stats": centre_stats
                }
            )
            
            # ===================================================================
            # LOGGING & SUMMARY
            # ===================================================================
            logger.info("\n" + "=" * 60)
            logger.info("✅ PROA COMPUTATION COMPLETE")
            logger.info("=" * 60)
            logger.info(f"User: {request.user_id} ({request.user_type.value})")
            logger.info(f"Coverage: {response.coverage * 100:.1f}% ({valid_count}/{total_q} questions)")
            logger.info(f"Confidence: {response.confidence * 100:.1f}%")
            logger.info(f"Time: {response.computation_time_ms:.2f}ms")
            logger.info(f"Domains: {len(response.domain_scores)}")
            logger.info(f"Top filière: {filiere_scores[0].filiere_name if filiere_scores else 'N/A'}")
            logger.info(f"Top université: {universite_scores[0].universite_name if universite_scores else 'N/A'}")
            logger.info(f"Recommendations generated: {sum(len(r) for r in response.recommendations.values())}")
            logger.info("=" * 60 + "\n")
            
            return response
            
        except Exception as e:
            logger.error(f"❌ PROA computation failed: {e}", exc_info=True)
            raise
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def validate_request(self, request: ProaComputeRequest) -> Dict[str, Any]:
        """
        Validate ProaComputeRequest
        
        Returns:
            Dict with validation results
        """
        logger.info("🔍 Validating request...")
        
        validation = {
            "valid": True,
            "errors": [],
            "warnings": []
        }
        
        # Check user_id
        if not request.user_id or len(request.user_id) == 0:
            validation["errors"].append("user_id is required")
        
        # Check user_type
        try:
            UserType(request.user_type.value)
        except ValueError:
            validation["errors"].append(f"Invalid user_type: {request.user_type}")
        
        # Check responses
        if not request.responses or len(request.responses) == 0:
            validation["errors"].append("Responses are required")
        
        # Check response values (should be 1-4 for Likert)
        invalid_responses = []
        for q_code, value in request.responses.items():
            if not isinstance(value, (int, float)):
                invalid_responses.append(f"{q_code}: not a number")
            elif value < 1 or value > 4:
                validation["warnings"].append(f"{q_code}: value {value} outside [1-4] range")
        
        if invalid_responses:
            validation["errors"].extend(invalid_responses)
        
        validation["valid"] = len(validation["errors"]) == 0
        
        if validation["errors"]:
            logger.error(f"❌ Validation failed: {validation['errors']}")
        elif validation["warnings"]:
            logger.warning(f"⚠️ Warnings: {validation['warnings']}")
        else:
            logger.info("✅ Request validation passed")
        
        return validation
