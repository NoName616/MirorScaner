# src/utils/math_utils.py
"""
Вспомогательные математические функции.
"""
import math
from typing import Tuple

def are_floats_equal(a: float, b: float, tolerance: float = 1e-9) -> bool:
    """
    Проверяет, равны ли два числа с плавающей точкой с заданной точностью.
    
    Args:
        a: Первое число.
        b: Второе число.
        tolerance: Допустимая погрешность.
        
    Returns:
        True, если числа равны с точностью до tolerance, иначе False.
    """
    return abs(a - b) <= tolerance

def degrees_to_dms(degrees: float) -> Tuple[int, int, float]:
    """
    Преобразует десятичные градусы в градусы, минуты и секунды.
    
    Args:
        degrees: Угол в десятичных градусах.
        
    Returns:
        Кортеж (градусы, минуты, секунды).
    """
    is_negative = degrees < 0
    degrees = abs(degrees)
    
    d = int(degrees)
    minutes = (degrees - d) * 60
    m = int(minutes)
    s = (minutes - m) * 60
    
    if is_negative:
        d = -d
        
    return d, m, s

def dms_to_degrees(d: int, m: int, s: float) -> float:
    """
    Преобразует градусы, минуты и секунды в десятичные градусы.
    
    Args:
        d: Градусы.
        m: Минуты.
        s: Секунды.
        
    Returns:
        Угол в десятичных градусах.
    """
    sign = -1 if d < 0 else 1
    d = abs(d)
    decimal_degrees = d + m / 60.0 + s / 3600.0
    return sign * decimal_degrees

def normalize_angle_degrees(angle: float) -> float:
    """
    Нормализует угол в градусах в диапазон [0, 360).
    
    Args:
        angle: Угол в градусах.
        
    Returns:
        Нормализованный угол в градусах.
    """
    return angle % 360.0

def calculate_points_on_circle(center_x: float, center_y: float, radius: float, num_points: int) -> list:
    """
    Рассчитывает точки на окружности.
    
    Args:
        center_x: X-координата центра.
        center_y: Y-координата центра.
        radius: Радиус окружности.
        num_points: Количество точек.
        
    Returns:
        Список кортежей (x, y) с координатами точек.
    """
    points = []
    for i in range(num_points):
        theta = (2 * math.pi * i) / num_points
        x = center_x + radius * math.cos(theta)
        y = center_y + radius * math.sin(theta)
        points.append((x, y))
    return points

# Пример использования
if __name__ == "__main__":
    # Тестирование функций
    print(f"are_floats_equal(0.1 + 0.2, 0.3): {are_floats_equal(0.1 + 0.2, 0.3)}")
    
    deg = 45.123456
    d, m, s = degrees_to_dms(deg)
    print(f"{deg} degrees = {d}° {m}' {s:.2f}\"")
    
    deg_back = dms_to_degrees(d, m, s)
    print(f"{d}° {m}' {s:.2f}\" = {deg_back} degrees")
    
    angle = 370.5
    norm_angle = normalize_angle_degrees(angle)
    print(f"Normalized {angle}° = {norm_angle}°")
    
    points = calculate_points_on_circle(0, 0, 5, 8)
    print("Points on circle (0,0, r=5, n=8):")
    for p in points:
        print(f"  ({p[0]:.2f}, {p[1]:.2f})")
