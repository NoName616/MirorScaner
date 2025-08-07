# src/calibration/calibration_point.py
"""
Точка калибровки камеры, связывающая пиксель на изображении с физической точкой.
"""
from typing import Tuple
from dataclasses import dataclass

@dataclass
class CalibrationPoint:
    """
    Представляет одну точку калибровки, связывающую пиксель на изображении
    с физической точкой в реальном мире.
    
    Attributes:
        image_point: Координаты (x, y) на изображении (в пикселях).
        world_point: Физические координаты (x, y) в реальном мире (в мм).
    """
    image_point: Tuple[int, int]        # (x, y) координаты на изображении в пикселях
    world_point: Tuple[float, float]   # (x, y) физические координаты в миллиметрах

    def __str__(self) -> str:
        img_x, img_y = self.image_point
        world_x, world_y = self.world_point
        return f"Image({img_x}, {img_y}) <-> World({world_x:.2f}, {world_y:.2f})"

    def to_dict(self) -> dict:
        """Преобразует объект CalibrationPoint в словарь для сериализации."""
        return {
            "image_point": {"x": self.image_point[0], "y": self.image_point[1]},
            "world_point": {"x": self.world_point[0], "y": self.world_point[1]}
        }

  @classmethod
  def from_dict(cls, data: dict) -> 'CalibrationPoint':
    """
    Creates a calibration point from a dictionary representation.
    The expected format is:
    {"image_point": {"x": int, "y": int}, "world_point": {"x": float, "y": float}}.
    """
    img_data = data.get("image_point", {})
    world_data = data.get("world_point", {})
    return cls(
        image_point=(int(img_data.get("x", 0)), int(img_data.get("y", 0))),
        world_point=(float(world_data.get("x", 0.0)), float(world_data.get("y", 0.0)))
    )

