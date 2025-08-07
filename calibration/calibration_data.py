# src/calibration/calibration_data.py

from dataclasses import dataclass, field
from typing import List

from .calibration_point import CalibrationPoint
from .calibration_metadata import CalibrationMetadata



@dataclass
class CameraCalibrationData:
    """
    Основные данные калибровки: точки, метаданные и позиция камеры.
    """
    points: List[CalibrationPoint] = field(default_factory=list)
    metadata: CalibrationMetadata = field(default_factory=lambda: CalibrationMetadata())
    camera_position: CameraPosition = field(default_factory=CameraPosition)

    def add_point(self, point: CalibrationPoint):
        self.points.append(point)

    def get_point_count(self) -> int:
        return len(self.points)

    def clear_points(self):
        self.points.clear()

    def to_dict(self) -> dict:
        return {
            "points": [p.to_dict() for p in self.points],
            "metadata": self.metadata.to_dict(),
            "camera_position": self.camera_position.__dict__,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'CameraCalibrationData':
        instance = cls()
        if "points" in data:
            instance.points = [CalibrationPoint.from_dict(p) for p in data["points"]]
        if "metadata" in data:
            instance.metadata = CalibrationMetadata(**data["metadata"])
        if "camera_position" in data:
            instance.camera_position = CameraPosition(**data["camera_position"])
        return instance