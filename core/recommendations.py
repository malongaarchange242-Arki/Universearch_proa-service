import json
import os
from typing import Dict, List, Any

_MAPPING_CACHE: Dict[str, Any] = {}


def _load_mapping() -> Dict[str, Any]:
    if _MAPPING_CACHE:
        return _MAPPING_CACHE

    base = os.path.dirname(os.path.dirname(__file__))
    path = os.path.join(base, "config", "fields_mapping.json")
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    # Normalize mapping into list of entries
    _MAPPING_CACHE.update(cfg)
    return _MAPPING_CACHE


def _get_score_for_key(profile: Dict[str, Dict[str, float]], key: str) -> float:
    # profile expected to be {"domains": {...}, "skills": {...}}
    domains = profile.get("domains", {}) if isinstance(profile, dict) else {}
    skills = profile.get("skills", {}) if isinstance(profile, dict) else {}

    # check domains first then skills
    if key in domains:
        return float(domains.get(key) or 0.0)
    if key in skills:
        return float(skills.get(key) or 0.0)
    return 0.0


def compute_recommended_fields(profile: Dict[str, Any], top_n: int = 5) -> Dict[str, List[Dict[str, Any]]]:
    """
    Calcule les filières recommandées à partir d'un profil PROA.

    Args:
        profile: dict avec clés `domains` et `skills`, chacune mappée key->score (0..1).
                 Example: {"domains": {"computer_science": 0.8, ...}, "skills": {...}}
        top_n: nombre max de filières retournées.

    Returns:
        {"recommended_fields": [{"field": ..., "category": ..., "score": 0.82}, ...]}

    Logique: pour chaque filière, faire la moyenne des valeurs des domaines/skills associés.
            Les clés absentes sont comptées comme 0.0 (facile à changer si on préfère ignorer).
    """
    mapping = _load_mapping()
    fields = mapping.get("fields", [])

    results: List[Dict[str, Any]] = []

    for entry in fields:
        keys = entry.get("domains", [])
        if not keys:
            continue

        # compute average (missing keys -> 0)
        scores = [_get_score_for_key(profile, k) for k in keys]
        avg = sum(scores) / len(keys)
        # clamp 0..1
        avg = max(0.0, min(1.0, avg))

        results.append({
            "field": entry.get("field"),
            "category": entry.get("category"),
            "score": round(avg, 4),
        })

    # sort desc and take top_n
    results.sort(key=lambda r: r["score"], reverse=True)
    top = results[:top_n]

    return {"recommended_fields": top}


if __name__ == "__main__":
    # petit test local rapide
    sample_profile = {
        "domains": {"computer_science": 0.8, "technical": 0.7, "logic": 0.75, "marketing": 0.2},
        "skills": {}
    }
    print(json.dumps(compute_recommended_fields(sample_profile, top_n=6), ensure_ascii=False, indent=2))
