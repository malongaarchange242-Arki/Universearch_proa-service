# models/profile.py

from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Dict

class OrientationProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    domains: Dict[str, float] = Field(default_factory=dict)
    skills: Dict[str, float] = Field(default_factory=dict)

    @field_validator("domains", "skills")
    @classmethod
    def check_values(cls, values: Dict[str, float]):
        for k, v in values.items():
            if not 0.0 <= v <= 1.0:
                raise ValueError(f"{k} hors intervalle [0,1]")
        return values
