import logging
from typing import Dict

logger = logging.getLogger("orientation.utils")


def normalize_responses(responses: Dict[str, int]) -> Dict[str, int]:
    """
    Normalize question codes to lowercase.
    
    Transform: {"Q1": 3, "Q2": 4} → {"q1": 3, "q2": 4}
    
    Args:
        responses: Raw user responses with any case
    
    Returns:
        Normalized responses (all keys lowercase)
    """
    if not responses:
        return {}
    
    normalized = {}
    for key, value in responses.items():
        normalized_key = str(key).lower()
        normalized[normalized_key] = value
        
        if normalized_key != key:
            logger.debug(f"Normalized: {key} → {normalized_key}")
    
    logger.info(f"Responses normalized: {len(normalized)} entries")
    return normalized


def validate_response_values(responses: Dict[str, int]) -> bool:
    """
    Validate that all response values are in range [1-4].
    
    Returns:
        True if valid, raises ValueError otherwise
    """
    for key, value in responses.items():
        if not isinstance(value, (int, float)):
            raise ValueError(f"Response {key} must be numeric, got {type(value)}")
        
        if not (1 <= value <= 4):
            raise ValueError(f"Response {key} must be 1-4, got {value}")
    
    return True


def normalize_and_validate(responses: Dict[str, int]) -> Dict[str, int]:
    """
    Combined: normalize + validate
    """
    if not responses:
        raise ValueError("Responses cannot be empty")
    
    normalized = normalize_responses(responses)
    validate_response_values(normalized)
    
    return normalized
