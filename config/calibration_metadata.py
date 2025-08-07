# src/calibration/calibration_metadata.py

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime

@dataclass
class CalibrationMetadata:
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    sample_radius_mm: Optional[float] = None
    description: str = ""
    calibrated_by: Optional[str] = None
    points_used: Optional[int] = None
    calibration_method: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "created_at": self.created_at,
            "sample_radius_mm": self.sample_radius_mm,
            "description": self.description,
            "calibrated_by": self.calibrated_by,
            "points_used": self.points_used,
            "calibration_method": self.calibration_method,
        }