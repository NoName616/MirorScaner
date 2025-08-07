# src/scan/scan_planner.py
"""
Планировщик траектории сканирования.
Рассчитывает точки для обхода по концентрическим окружностям.
"""
import math
from typing import List, Tuple
from utils.math_utils import normalize_angle_degrees

class ScanPlanner:
    """
    Планировщик траектории сканирования.
    """
    def __init__(self):
        pass

    @staticmethod
    def generate_scan_points(
        radius_mm: float, 
        radial_step_mm: float, 
        arc_step_mm: float,
        angle_deg: float = 360.0
    ) -> List[Tuple[float, float, float]]:
        """
        Генерирует список точек сканирования.
        
        Args:
            radius_mm: Максимальный радиус сканирования в мм.
            radial_step_mm: Шаг по радиусу в мм.
            arc_step_mm: Шаг по дуге в мм.
            angle_deg: Угол сканирования в градусах (по умолчанию 360).
            
        Returns:
            Список кортежей (radius_mm, angle_deg, x_mm, y_mm).
        """
        if radius_mm <= 0 or radial_step_mm <= 0 or arc_step_mm <= 0:
            raise ValueError("Все параметры должны быть положительными")
            
        # Нормализуем угол: ограничиваем [0, 360] диапазон
        if angle_deg <= 0:
            raise ValueError("Угол сканирования должен быть положительным")
        if angle_deg > 360.0:
            angle_deg = 360.0
            
        points = []
        
        # Начинаем с центра
        points.append((0.0, 0.0, 0.0, 0.0))  # (radius, angle, x, y)
        
        # Проходим по концентрическим окружностям
        current_radius = radial_step_mm
        while current_radius <= radius_mm:
            # Рассчитываем количество точек на этой окружности
            circumference = 2 * math.pi * current_radius
            # Угловой шаг, соответствующий шагу по дуге
            angular_step_deg = math.degrees(arc_step_mm / current_radius)
            
            if angular_step_deg <= 0:
                # Это может произойти при очень маленьком радиусе
                angular_step_deg = 1.0  # Минимальный шаг
                
            # Рассчитываем количество точек
            num_points_on_circle = int(round(angle_deg / angular_step_deg))
            if num_points_on_circle <= 0:
                num_points_on_circle = 1
                
            # Корректируем угловой шаг, чтобы точно покрыть angle_deg
            if num_points_on_circle > 1:
                corrected_angular_step_deg = angle_deg / (num_points_on_circle - 1)
            else:
                corrected_angular_step_deg = 0.0
                
            # Генерируем точки на окружности
            for i in range(num_points_on_circle):
                theta_deg = i * corrected_angular_step_deg
                # Нормализуем угол
                theta_deg = normalize_angle_degrees(theta_deg)
                
                x_mm = current_radius * math.cos(math.radians(theta_deg))
                y_mm = current_radius * math.sin(math.radians(theta_deg))
                
                points.append((current_radius, theta_deg, x_mm, y_mm))
                
            # Переходим к следующей окружности
            current_radius += radial_step_mm
            
        return points

    @staticmethod
    def generate_scan_points_simple(
        radius_mm: float, 
        radial_step_mm: float, 
        angular_step_deg: float,
        angle_deg: float = 360.0
    ) -> List[Tuple[float, float, float]]:
        """
        Упрощённая версия генератора точек с фиксированным угловым шагом.
        
        Args:
            radius_mm: Максимальный радиус сканирования в мм.
            radial_step_mm: Шаг по радиусу в мм.
            angular_step_deg: Фиксированный угловой шаг в градусах.
            angle_deg: Угол сканирования в градусах (по умолчанию 360).
            
        Returns:
            Список кортежей (radius_mm, angle_deg, x_mm, y_mm).
        """
        if radius_mm <= 0 or radial_step_mm <= 0 or angular_step_deg <= 0:
            raise ValueError("Все параметры должны быть положительными")
            
        # Нормализуем угол: ограничиваем [0, 360] диапазон
        if angle_deg <= 0:
            raise ValueError("Угол сканирования должен быть положительным")
        if angle_deg > 360.0:
            angle_deg = 360.0
            
        points = []
        
        # Начинаем с центра
        points.append((0.0, 0.0, 0.0, 0.0))  # (radius, angle, x, y)
        
        # Проходим по концентрическим окружностям
        current_radius = radial_step_mm
        while current_radius <= radius_mm:
            # Рассчитываем количество точек на этой окружности
            num_points_on_circle = int(round(angle_deg / angular_step_deg))
            if num_points_on_circle <= 0:
                num_points_on_circle = 1
                
            # Корректируем угловой шаг
            if num_points_on_circle > 1:
                corrected_angular_step_deg = angle_deg / (num_points_on_circle - 1)
            else:
                corrected_angular_step_deg = 0.0
                
            # Генерируем точки на окружности
            for i in range(num_points_on_circle):
                theta_deg = i * corrected_angular_step_deg
                # Нормализуем угол
                theta_deg = normalize_angle_degrees(theta_deg)
                
                x_mm = current_radius * math.cos(math.radians(theta_deg))
                y_mm = current_radius * math.sin(math.radians(theta_deg))
                
                points.append((current_radius, theta_deg, x_mm, y_mm))
                
            # Переходим к следующей окружности
            current_radius += radial_step_mm
            
        return points

# Пример использования
if __name__ == "__main__":
    planner = ScanPlanner()
    
    # Пример 1: Сканирование с шагом по дуге
    print("=== Сканирование с шагом по дуге ===")
    points1 = planner.generate_scan_points(
        radius_mm=10.0,
        radial_step_mm=2.0,
        arc_step_mm=1.0,
        angle_deg=90.0
    )
    print(f"Сгенерировано точек: {len(points1)}")
    for i, (r, a, x, y) in enumerate(points1[:10]):  # Печатаем первые 10
        print(f"  Точка {i}: r={r:.2f}mm, a={a:.2f}°, x={x:.2f}mm, y={y:.2f}mm")
    if len(points1) > 10:
        print("  ...")
        
    print("\n=== Упрощённое сканирование с фиксированным угловым шагом ===")
    points2 = planner.generate_scan_points_simple(
        radius_mm=10.0,
        radial_step_mm=2.0,
        angular_step_deg=30.0,
        angle_deg=90.0
    )
    print(f"Сгенерировано точек: {len(points2)}")
    for i, (r, a, x, y) in enumerate(points2[:10]):  # Печатаем первые 10
        print(f"  Точка {i}: r={r:.2f}mm, a={a:.2f}°, x={x:.2f}mm, y={y:.2f}mm")
    if len(points2) > 10:
        print("  ...")
