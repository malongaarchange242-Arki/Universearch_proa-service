"""
PROA Routes - FastAPI endpoints for the complete PROA scoring system
"""

import logging
from fastapi import APIRouter, HTTPException, status
from datetime import datetime

from models.proa import ProaComputeRequest, ProaComputeResponse, UserType
from core.proa_orchestrator import ProaOrchestrator
from db.repository import supabase

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/proa", tags=["PROA Orientation"])

# Initialize orchestrator
orchestrator = ProaOrchestrator(supabase)


# ============================================================================
# HEALTH & INFO
# ============================================================================

@router.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "ok",
        "service": "PROA Scoring Engine",
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/info")
async def info():
    """PROA system information"""
    return {
        "name": "PROA - Platform for University Orientation & Recommendations",
        "version": "1.0.0",
        "features": [
            "Feature engineering (DB-driven)",
            "Domain scoring (with caching)",
            "Filière matching (with confidence)",
            "PORA scoring (popularity + engagement + orientation)",
            "Personalized recommendations (filieres + universites + centres)"
        ],
        "user_types": ["bachelier", "etudiant", "parent"],
        "optimization": "1 query per domain (nested select), 1h cache TTL",
        "performance": "~100-200ms per computation"
    }


# ============================================================================
# MAIN COMPUTE ENDPOINT
# ============================================================================

@router.post("/compute", response_model=dict)
async def compute_proa(request: ProaComputeRequest):
    """
    Compute complete PROA score and recommendations
    
    Pipeline:
    1. Feature Engineering (normalized)
    2. Domain Scoring (DB-driven)
    3. Filière Scoring (domain match)
    4. PORA Scoring (universities + centres)
    5. Recommendations (personalized)
    
    Args:
        request: ProaComputeRequest
            - user_id: str
            - user_type: "bachelier" | "etudiant" | "parent"
            - quiz_version: str (e.g., "1.0")
            - orientation_type: "field" | "career" | "general"
            - responses: {q1: 3, q2: 4, ...} (Likert 1-4)
    
    Returns:
        ProaComputeResponse with all scores and recommendations
    
    Examples:
        POST /api/v1/proa/compute
        {
            "user_id": "student@uni.cd",
            "user_type": "bachelier",
            "quiz_version": "1.0",
            "orientation_type": "field",
            "responses": {
                "q1": 3, "q2": 4, "q3": 2, "q4": 3, "q5": 4,
                "q6": 2, "q7": 3, "q8": 4, "q9": 2, "q10": 3,
                "q11": 4, "q12": 2, "q13": 3, "q14": 4, "q15": 2,
                "q16": 3, "q17": 4, "q18": 2, "q19": 3, "q20": 4,
                "q21": 2, "q22": 3, "q23": 4, "q24": 2
            }
        }
    
    Response (201 Created):
        {
            "user_id": "student@uni.cd",
            "timestamp": "2026-03-29T10:30:00.000Z",
            
            "features": {
                "domain_logic": {"score": 0.62, ...},
                "domain_technical": {"score": 0.75, ...}
            },
            
            "domain_scores": [
                {
                    "domain_id": "uuid",
                    "domain_name": "logic",
                    "score": 0.62,
                    "confidence": 0.95
                }
            ],
            
            "filiere_scores": [
                {
                    "filiere_id": "uuid",
                    "filiere_name": "Informatique",
                    "field": "STEM",
                    "score": 0.85,
                    "compatibility_level": "excellent",
                    "top_domains": ["logic", "technical"]
                }
            ],
            
            "universites": [
                {
                    "universite_id": "uuid",
                    "universite_name": "Université de Kinshasa",
                    "pora_score": 0.78,
                    "ranking": 1
                }
            ],
            
            "centres": [
                {
                    "centre_id": "uuid",
                    "centre_name": "Centre STEM Kinshasa",
                    "pora_score": 0.82,
                    "ranking": 1
                }
            ],
            
            "recommendations": {
                "filieres": [
                    {
                        "id": "uuid",
                        "name": "Informatique",
                        "type": "filieres",
                        "score": 0.85,
                        "reason": "Excellent match - your top domains strongly align"
                    }
                ],
                "universites": [
                    {
                        "id": "uuid",
                        "name": "Université de Kinshasa",
                        "type": "universites",
                        "score": 0.79,
                        "reason": "Offers your top recommended filieres"
                    }
                ],
                "centres": [...]
            },
            
            "coverage": 0.95,
            "confidence": 0.92,
            "computation_time_ms": 145.23,
            "total_questions": 24,
            "matched_questions": 24,
            
            "metrics": {
                "domain_stats": {...},
                "filiere_stats": {...},
                "universite_stats": {...},
                "centre_stats": {...}
            }
        }
    
    Errors:
        400: Invalid request (missing fields, invalid values)
        422: Validation error (bad user_type, etc)
        500: Server error (DB connection, etc)
    """
    logger.info(f"📥 Received PROA compute request for {request.user_id}")
    
    try:
        # Validate request
        validation = orchestrator.validate_request(request)
        if not validation["valid"]:
            logger.error(f"Request validation failed: {validation['errors']}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "Invalid request",
                    "errors": validation["errors"],
                    "warnings": validation["warnings"]
                }
            )
        
        # Compute PROA scores
        response = orchestrator.compute(request)
        
        # Convert to dict for JSON response
        response_dict = {
            "user_id": response.user_id,
            "timestamp": response.timestamp.isoformat(),
            "features": {
                name: {
                    "score": feature.score,
                    "weight": feature.weight,
                    "contribution": feature.contribution,
                    "question_count": feature.question_count
                }
                for name, feature in response.features.items()
            },
            "domain_scores": [
                {
                    "domain_id": d.domain_id,
                    "domain_name": d.domain_name,
                    "score": d.score,
                    "confidence": d.confidence,
                    "total_weight": d.total_weight
                }
                for d in response.domain_scores
            ],
            "filiere_scores": [
                {
                    "filiere_id": f.filiere_id,
                    "filiere_name": f.filiere_name,
                    "field": f.field,
                    "duration_years": f.duration_years,
                    "score": f.score,
                    "compatibility_level": f.compatibility_level,
                    "top_domains": f.top_domains,
                    "domain_matches": [
                        {
                            "domain_id": match.domain_id,
                            "domain_name": match.domain_name,
                            "domain_score": match.domain_score,
                            "importance": match.importance,
                            "contribution": match.contribution
                        }
                        for match in f.domain_matches
                    ]
                }
                for f in response.filiere_scores
            ],
            "universites": [
                {
                    "universite_id": u.universite_id,
                    "universite_name": u.universite_name,
                    "pora_score": u.pora_score,
                    "popularity": u.popularity,
                    "filiere_match": u.filiere_match,
                    "ranking": u.ranking,
                    "filieres": u.filieres[:5]
                }
                for u in response.universites
            ],
            "centres": [
                {
                    "centre_id": c.centre_id,
                    "centre_name": c.centre_name,
                    "universite_name": c.universite_name,
                    "pora_score": c.pora_score,
                    "popularity": c.popularity,
                    "engagement_score": c.engagement_score,
                    "ranking": c.ranking
                }
                for c in response.centres
            ],
            "recommendations": {
                "filieres": [
                    {
                        "id": r.id,
                        "name": r.name,
                        "type": r.type.value,
                        "score": r.score,
                        "reason": r.reason,
                        "metadata": r.metadata
                    }
                    for r in response.recommendations["filieres"]
                ],
                "universites": [
                    {
                        "id": r.id,
                        "name": r.name,
                        "type": r.type.value,
                        "score": r.score,
                        "reason": r.reason,
                        "metadata": r.metadata
                    }
                    for r in response.recommendations["universites"]
                ],
                "centres": [
                    {
                        "id": r.id,
                        "name": r.name,
                        "type": r.type.value,
                        "score": r.score,
                        "reason": r.reason,
                        "metadata": r.metadata
                    }
                    for r in response.recommendations["centres"]
                ]
            },
            "coverage": response.coverage,
            "confidence": response.confidence,
            "computation_time_ms": response.computation_time_ms,
            "total_questions": response.total_questions,
            "matched_questions": response.matched_questions,
            "metrics": response.metrics
        }
        
        logger.info(f"✅ PROA computation successful for {request.user_id}")
        return response_dict
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ PROA computation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Computation failed: {str(e)}"
        )


# ============================================================================
# DIAGNOSTIC ENDPOINTS
# ============================================================================

@router.get("/diagnostics/domains")
async def diagnose_domains():
    """Get domain mapping diagnostics"""
    try:
        domains = supabase.table("domaines").select("*").execute()
        return {
            "total_domains": len(domains.data),
            "domains": [
                {
                    "id": d.get("id"),
                    "name": d.get("name"),
                    "description": d.get("description")
                }
                for d in domains.data
            ]
        }
    except Exception as e:
        logger.error(f"Error fetching domains: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/diagnostics/filieres")
async def diagnose_filieres():
    """Get filière statistics"""
    try:
        filieres = supabase.table("filieres").select("*").execute()
        return {
            "total_filieres": len(filieres.data),
            "fields": list(set(f.get("field") for f in filieres.data if f.get("field"))),
            "sample": filieres.data[:5]
        }
    except Exception as e:
        logger.error(f"Error fetching filieres: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/diagnostics/cache")
async def diagnose_cache():
    """Check cache status"""
    return {
        "domain_mapping_cache": {
            "cached": orchestrator.domain_scorer._domain_mapping_cache is not None,
            "timestamp": orchestrator.domain_scorer._cache_timestamp.isoformat() if orchestrator.domain_scorer._cache_timestamp else None,
            "ttl_seconds": orchestrator.domain_scorer.cache_ttl_seconds
        },
        "filiere_domain_cache": {
            "cached": orchestrator.filiere_scorer._filiere_domain_cache is not None,
            "timestamp": orchestrator.filiere_scorer._cache_timestamp.isoformat() if orchestrator.filiere_scorer._cache_timestamp else None,
            "ttl_seconds": orchestrator.filiere_scorer.cache_ttl_seconds
        }
    }


# ============================================================================
# RECOMMENDATIONS - CANDIDATE MANAGEMENT
# ============================================================================

@router.get("/recommendations/list")
async def get_recommendations_list(
    target_id: str = None,
    score_min: float = 0.0,
    rank: int = None,
    user_type: str = None,
    search: str = None,
    limit: int = 25,
    offset: int = 0
):
    """
    Get recommended candidates for universities/centres with advanced filtering.
    
    Query Parameters:
        - target_id: Filter by establishment/centre ID (universite_id or centre_id)
        - score_min: Minimum score threshold (0.0-1.0)
        - rank: Filter by rank ("top-10", "top-50", "top-100", or specific number)
        - user_type: Filter by user type ("etudiant", "bachelier", "lycéen")
        - search: Search by candidate name or email
        - limit: Items per page (default 25)
        - offset: Pagination offset (default 0)
    
    Returns:
        {
            "total": int,
            "count": int,
            "page": int,
            "limit": int,
            "candidates": [
                {
                    "id": str,
                    "user_id": str,
                    "name": str,
                    "email": str,
                    "telephone": str,
                    "user_type": str,
                    "filiere": str,
                    "target_name": str,
                    "target_type": str,
                    "score": float,
                    "rank": int,
                    "confidence": float,
                    "reason": str,
                    "created_at": str
                }
            ],
            "stats": {
                "avg_score": float,
                "top_10_count": int,
                "selected_count": int
            }
        }
    """
    try:
        # Build base query using RLS-safe method
        query = supabase.table("orientation_recommandation").select("*")
        
        # Apply filters
        if target_id:
            query = query.eq("target_id", target_id)
        
        if score_min > 0:
            query = query.gte("score", score_min)
        
        if rank:
            rank_int = int(rank)
            if rank == "top-10":
                query = query.lte("rank", 10)
            elif rank == "top-50":
                query = query.lte("rank", 50)
            elif rank == "top-100":
                query = query.lte("rank", 100)
            else:
                query = query.lte("rank", rank_int)
        
        # Execute query without pagination first for total count
        response = query.execute()
        all_recommendations = response.data if response.data else []
        
        # Post-process to add user data and apply remaining filters
        processed_candidates = []
        
        for rec in all_recommendations:
            try:
                # Fetch user data
                user_response = supabase.table("users").select("*").eq("id", rec.get("user_id")).execute()
                user = user_response.data[0] if user_response.data else None
                
                if not user:
                    logger.warning(f"User not found for recommendation: {rec.get('user_id')}")
                    continue
                
                # Apply user_type filter
                user_type_value = user.get("user_type", "").strip()
                if user_type and user_type.lower() != user_type_value.lower():
                    continue
                
                # Apply search filter
                if search:
                    search_lower = search.lower()
                    name = f"{user.get('nom', '')} {user.get('prenom', '')}".lower()
                    email = user.get('email', '').lower()
                    if search_lower not in name and search_lower not in email:
                        continue
                
                # Get filière name (optional)
                filiere_name = "N/A"
                try:
                    # Try to get from profile or orientation data
                    profile_response = supabase.table("orientation_profiles").select("*").eq("user_id", rec.get("user_id")).limit(1).execute()
                    if profile_response.data:
                        profile_data = profile_response.data[0]
                        filiere_name = profile_data.get("matched_filieres", [None])[0] if profile_data.get("matched_filieres") else "N/A"
                except:
                    pass
                
                # Build candidate object
                candidate = {
                    "id": rec.get("id"),
                    "user_id": rec.get("user_id"),
                    "name": f"{user.get('prenom', '')} {user.get('nom', '')}".strip(),
                    "email": user.get("email", ""),
                    "telephone": user.get("telephone", ""),
                    "user_type": user_type_value,
                    "filiere": filiere_name,
                    "target_name": rec.get("target_name", ""),
                    "target_type": rec.get("target_type", ""),
                    "score": rec.get("score", 0.0),
                    "rank": rec.get("rank", 0),
                    "confidence": rec.get("confidence", 0.0),
                    "reason": rec.get("reason", ""),
                    "created_at": rec.get("created_at", "")
                }
                
                processed_candidates.append(candidate)
                
            except Exception as e:
                logger.error(f"Error processing recommendation {rec.get('id')}: {str(e)}")
                continue
        
        # Sort by score descending
        processed_candidates.sort(key=lambda x: x["score"], reverse=True)
        
        # Calculate total
        total = len(processed_candidates)
        
        # Apply pagination
        paginated = processed_candidates[offset:offset + limit]
        page = (offset // limit) + 1 if limit > 0 else 1
        
        # Calculate stats
        avg_score = sum(c["score"] for c in processed_candidates) / len(processed_candidates) if processed_candidates else 0.0
        top_10_count = sum(1 for c in processed_candidates if c["rank"] <= 10)
        
        return {
            "total": total,
            "count": len(paginated),
            "page": page,
            "limit": limit,
            "offset": offset,
            "candidates": paginated,
            "stats": {
                "avg_score": round(avg_score, 4),
                "top_10_count": top_10_count,
                "selected_count": 0  # To be computed on frontend
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.exception(f"Error fetching recommendations: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch recommendations: {str(e)}"
        )


@router.get("/recommendations/stats")
async def get_recommendations_stats(target_id: str = None):
    """
    Get statistics for recommendations dashboard.
    
    Returns:
        {
            "total_recommendations": int,
            "unique_candidates": int,
            "avg_score": float,
            "score_distribution": {"[0-0.25]": int, "[0.25-0.5]": int, ...},
            "by_target_type": {"universite": int, "centre": int}
        }
    """
    try:
        query = supabase.table("orientation_recommandation").select("*")
        
        if target_id:
            query = query.eq("target_id", target_id)
        
        response = query.execute()
        recommendations = response.data if response.data else []
        
        # Calculate statistics
        unique_users = set(r.get("user_id") for r in recommendations)
        scores = [r.get("score", 0.0) for r in recommendations]
        avg_score = sum(scores) / len(scores) if scores else 0.0
        
        # Score distribution
        score_dist = {
            "[0-0.25]": sum(1 for s in scores if 0 <= s < 0.25),
            "[0.25-0.5]": sum(1 for s in scores if 0.25 <= s < 0.5),
            "[0.5-0.75]": sum(1 for s in scores if 0.5 <= s < 0.75),
            "[0.75-1.0]": sum(1 for s in scores if 0.75 <= s <= 1.0)
        }
        
        # By target type
        universite_count = sum(1 for r in recommendations if r.get("target_type") == "universite")
        centre_count = sum(1 for r in recommendations if r.get("target_type") == "centre")
        
        return {
            "total_recommendations": len(recommendations),
            "unique_candidates": len(unique_users),
            "avg_score": round(avg_score, 4),
            "score_distribution": score_dist,
            "by_target_type": {
                "universite": universite_count,
                "centre": centre_count
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.exception(f"Error calculating stats: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to calculate statistics")
