# src/plotting/chart_controller.py
"""
Модуль для построения графиков температур.
"""
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
from typing import List, Tuple, Optional
import os

class ChartController:
    """
    Контроллер для построения графиков температур.
    """
    def __init__(self):
        # Устанавливаем стиль по умолчанию
        plt.style.use('seaborn-v0_8-darkgrid')
        self._figure = None
        self._ax = None

    def plot_temperature_map(self, data: List[Tuple[float, float, float, float]],
                             title: str = "Temperature Map") -> None:
        """
        Строит тепловую карту температур.
        
        Args:
             Список кортежей (radius_mm, angle_deg, min_temp, max_temp).
            title: Заголовок графика.
        """
        if not data:
            print("Нет данных для построения графика")
            return

        # Извлекаем координаты и температуры
        radii = [d[0] for d in data]
        angles_deg = [d[1] for d in data]
        min_temps = [d[2] for d in data]
        max_temps = [d[3] for d in data]
        
        # Преобразуем полярные координаты в декартовы
        angles_rad = np.radians(angles_deg)
        xs = np.array(radii) * np.cos(angles_rad)
        ys = np.array(radii) * np.sin(angles_rad)
        
        # Создаем фигуру
        self._figure, self._ax = plt.subplots(figsize=(10, 8))
        
        # Строим scatter plot для максимальных температур
        scatter = self._ax.scatter(xs, ys, c=max_temps, cmap='hot', s=50, edgecolors='black')
        self._ax.set_xlabel('X (mm)')
        self._ax.set_ylabel('Y (mm)')
        self._ax.set_title(f'{title} - Max Temperature')
        self._ax.grid(True)
        self._ax.set_aspect('equal', adjustable='box')
        
        # Добавляем цветовую шкалу
        cbar = plt.colorbar(scatter, ax=self._ax)
        cbar.set_label('Max Temperature (ADU)')
        
        plt.tight_layout()
        plt.show()

    def plot_temperature_profile(self, data: List[Tuple[float, float, float, float]],
                                 title: str = "Temperature Profile") -> None:
        """
        Строит профиль температур (температура vs. радиус или угол).
        
        Args:
             Список кортежей (radius_mm, angle_deg, min_temp, max_temp).
            title: Заголовок графика.
        """
        if not data:
            print("Нет данных для построения графика")
            return

        # Сортируем данные по радиусу для профиля по радиусу
        sorted_data = sorted(data, key=lambda x: x[0])
        radii = [d[0] for d in sorted_data]
        max_temps = [d[3] for d in sorted_data]
        min_temps = [d[2] for d in sorted_data]
        
        # Создаем фигуру
        self._figure, self._ax = plt.subplots(figsize=(10, 6))
        
        # Строим линии
        self._ax.plot(radii, max_temps, label='Max Temperature', marker='o', linestyle='-')
        self._ax.plot(radii, min_temps, label='Min Temperature', marker='s', linestyle='--')
        
        self._ax.set_xlabel('Radius (mm)')
        self._ax.set_ylabel('Temperature (ADU)')
        self._ax.set_title(f'{title} - Temperature vs Radius')
        self._ax.legend()
        self._ax.grid(True)
        
        plt.tight_layout()
        plt.show()

    def plot_polar_temperature(self, data: List[Tuple[float, float, float, float]],
                               title: str = "Polar Temperature Distribution") -> None:
        """
        Строит полярный график распределения температур.
        
        Args:
             Список кортежей (radius_mm, angle_deg, min_temp, max_temp).
            title: Заголовок графика.
        """
        if not data:
            print("Нет данных для построения графика")
            return

        # Извлекаем данные
        radii = [d[0] for d in data]
        angles_deg = [d[1] for d in data]
        max_temps = [d[3] for d in data]
        
        # Преобразуем углы в радианы
        angles_rad = np.radians(angles_deg)
        
        # Создаем фигуру
        self._figure, self._ax = plt.subplots(figsize=(10, 8), subplot_kw=dict(projection='polar'))
        
        # Строим scatter plot
        scatter = self._ax.scatter(angles_rad, radii, c=max_temps, cmap='hot', s=50)
        self._ax.set_title(f'{title} - Max Temperature')
        self._ax.set_theta_zero_location('N')  # 0° наверху
        self._ax.set_theta_direction(-1)       # По часовой стрелке
        
        # Добавляем цветовую шкалу
        cbar = plt.colorbar(scatter, ax=self._ax)
        cbar.set_label('Max Temperature (ADU)')
        
        plt.tight_layout()
        plt.show()

    def close_all_plots(self):
        """Закрывает все открытые графики."""
        plt.close('all')
        self._figure = None
        self._ax = None

    def save_current_plot(self, file_path: str, dpi: int = 300):
        """
        Сохраняет текущий график в файл.
        
        Args:
            file_path: Путь к файлу для сохранения.
            dpi: Разрешение изображения.
        """
        if self._figure is not None:
            # Создаем директорию, если её нет
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            self._figure.savefig(file_path, dpi=dpi, bbox_inches='tight')
            print(f"График сохранён в {file_path}")
        else:
            print("Нет активного графика для сохранения")

# Пример использования:
# if __name__ == "__main__":
#     controller = ChartController()
#     
#     # Имитация данных
#     test_data = [
#         (0.0, 0.0, 100.0, 200.0),
#         (1.0, 0.0, 110.0, 210.0),
#         (1.0, 90.0, 105.0, 205.0),
#         (1.0, 180.0, 115.0, 215.0),
#         (1.0, 270.0, 108.0, 208.0),
#         (2.0, 0.0, 120.0, 220.0),
#         (2.0, 45.0, 125.0, 225.0),
#     ]
#     
#     # controller.plot_temperature_map(test_data, "Тестовая тепловая карта")
#     # controller.plot_temperature_profile(test_data, "Тестовый температурный профиль")
#     # controller.plot_polar_temperature(test_data, "Тестовое полярное распределение")
