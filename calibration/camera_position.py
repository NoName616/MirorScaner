# src/calibration/camera_position.py
"""
Позиция камеры относительно образца при калибровке.
"""
from dataclasses import dataclass

@dataclass
class CameraPosition:
    """
    Описывает смещение и угол камеры относительно образца.
    
    Attributes:
        x_offset_mm: Горизонтальное смещение камеры (мм).
        y_offset_mm: Вертикальное смещение камеры (мм).
        z_distance_mm: Расстояние от камеры до образца по оси Z (мм).
        angle_deg: Угол наклона/поворота камеры относительно образца (в градусах).
    """
    x_offset_mm: float = 0.0    # смещение камеры по оси X, мм
    y_offset_mm: float = 0.0    # смещение по оси Y, мм
    z_distance_mm: float = 0.0  # расстояние до образца по оси Z, мм
    angle_deg: float = 0.0      # угол поворота камеры, градусы
