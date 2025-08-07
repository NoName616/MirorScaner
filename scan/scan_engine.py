# src/scan/scan_engine.py
"""
Движок сканирования. Координирует перемещение осей и захват данных с камеры.
"""
import asyncio
import time
from typing import List, Tuple, Optional, Callable
from dataclasses import dataclass
from hardware.axis_controller import AxisController
from camera.camera_service import CameraService
from scan.scan_planner import ScanPlanner
from scan.data_writer import IScanDataWriter
from utils.logger import DataLogger, LogCategory

@dataclass
class ScanPoint:
    """Точка сканирования."""
    radius_mm: float
    angle_deg: float
    x_mm: float
    y_mm: float

class ScanEngineException(Exception):
    """Исключение для ошибок движка сканирования."""
    pass

class ScanEngine:
    """
    Движок сканирования. Управляет процессом автоматического сканирования.
    """
    def __init__(self, x_axis: AxisController, theta_axis: AxisController,
                 camera: CameraService, logger: DataLogger):
        self._x_axis = x_axis
        self._theta_axis = theta_axis
        self._camera = camera
        self._logger = logger
        
        self._is_running = False
        self._is_paused = False
        self._current_point_index = 0
        self._total_points = 0
        self._scan_points: List[ScanPoint] = []
        self._data_writer: Optional[IScanDataWriter] = None
        self._delay_ms = 1000
        
        # Callbacks
        self.on_progress: Optional[Callable[[int, int], None]] = None  # (current, total)
        self.on_scan_started: Optional[Callable[[], None]] = None
        self.on_scan_paused: Optional[Callable[[], None]] = None
        self.on_scan_resumed: Optional[Callable[[], None]] = None
        self.on_scan_stopped: Optional[Callable[[], None]] = None
        self.on_scan_finished: Optional[Callable[[], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None
        self.on_data_point: Optional[Callable[[float, float, float, float], None]] = None  # (radius_mm, angle_deg, min_temp, max_temp)

    def is_running(self) -> bool:
        """Проверяет, идет ли сканирование."""
        return self._is_running

    def is_paused(self) -> bool:
        """Проверяет, приостановлено ли сканирование."""
        return self._is_paused

    def get_progress(self) -> Tuple[int, int]:
        """Возвращает текущий прогресс (current, total)."""
        return self._current_point_index, self._total_points

    def set_delay(self, delay_ms: int):
        """Устанавливает задержку между точками."""
        if delay_ms < 0:
            raise ValueError("Задержка не может быть отрицательной")
        self._delay_ms = delay_ms

    def set_data_writer(self, writer: IScanDataWriter):
        """Устанавливает writer для записи данных."""
        self._data_writer = writer

    async def start_scan(self, radius_mm: float, radial_step_mm: float, 
                         arc_step_mm: float, angle_deg: float = 360.0):
        """
        Начинает процесс сканирования.
        """
        if self._is_running:
            raise ScanEngineException("Сканирование уже запущено")

        if not (self._x_axis.is_calibrated() and self._theta_axis.is_calibrated()):
            raise ScanEngineException("Оси не откалиброваны")

        if not self._camera.is_connected():
            raise ScanEngineException("Камера не подключена")

        if self._data_writer is None:
            raise ScanEngineException("DataWriter не установлен")

        try:
            self._logger.log_info(LogCategory.SCAN, "Начало планирования сканирования...")
            # Генерируем точки
            raw_points = ScanPlanner.generate_scan_points(
                radius_mm, radial_step_mm, arc_step_mm, angle_deg
            )
            
            # Преобразуем в ScanPoint
            self._scan_points = [
                ScanPoint(r, a, x, y) for r, a, x, y in raw_points
            ]
            self._total_points = len(self._scan_points)
            self._current_point_index = 0
            self._is_running = True
            self._is_paused = False
            
            self._logger.log_info(LogCategory.SCAN, 
                f"Планирование завершено. Всего точек: {self._total_points}")
            
            # Записываем заголовок
            self._data_writer.write_header(radius_mm, radial_step_mm, arc_step_mm, angle_deg)
            
            self._logger.log_info(LogCategory.SCAN, "Начало сканирования...")
            if self.on_scan_started:
                self.on_scan_started()
                
            await self._execute_scan_loop()
            
        except Exception as e:
            error_msg = f"Ошибка запуска сканирования: {e}"
            self._logger.log_error(LogCategory.SCAN, error_msg)
            if self.on_error:
                self.on_error(error_msg)
            self._is_running = False
            raise ScanEngineException(error_msg) from e

    async def _execute_scan_loop(self):
        """Основной цикл сканирования."""
        try:
            for i, point in enumerate(self._scan_points):
                if not self._is_running:
                    break
                    
                while self._is_paused:
                    await asyncio.sleep(0.1)
                    
                self._current_point_index = i
                self._logger.log_info(LogCategory.SCAN, 
                    f"Перемещение к точке {i+1}/{self._total_points}: "
                    f"r={point.radius_mm:.2f}mm, a={point.angle_deg:.2f}°"
                )
                
                # Уведомляем о прогрессе
                if self.on_progress:
                    self.on_progress(i, self._total_points)
                
                # Перемещаем оси
                await self._x_axis.move_to_async(point.x_mm)
                await self._theta_axis.move_to_async(point.angle_deg)
                
                # Задержка для стабилизации
                delay_sec = self._delay_ms / 1000.0
                await asyncio.sleep(delay_sec)
                
                # Захват кадра и анализ
                frame = self._camera.get_single_frame()
                if frame is not None:
                    # Для простоты анализируем весь кадр
                    # В реальном приложении может быть ROI
                    try:
                        min_temp, max_temp = self._camera.get_min_max_temperature_in_roi(frame)
                        # Записываем данные
                        self._data_writer.write_data(point.radius_mm, point.angle_deg, min_temp, max_temp)
                        if self.on_data_point:
                            self.on_data_point(point.radius_mm, point.angle_deg, min_temp, max_temp)
                        self._logger.log_debug(LogCategory.SCAN, 
                            f"  Температуры записаны: min={min_temp}, max={max_temp}")
                    except Exception as e:
                        self._logger.log_warn(LogCategory.SCAN, 
                            f"  Ошибка анализа кадра для точки {i+1}: {e}")
                else:
                    self._logger.log_warn(LogCategory.SCAN, 
                        f"  Не удалось получить кадр для точки {i+1}")
                        
            # Сканирование завершено
            self._is_running = False
            self._logger.log_info(LogCategory.SCAN, "Сканирование завершено")
            if self.on_scan_finished:
                self.on_scan_finished()
                
        except Exception as e:
            self._is_running = False
            error_msg = f"Ошибка в процессе сканирования: {e}"
            self._logger.log_error(LogCategory.SCAN, error_msg)
            if self.on_error:
                self.on_error(error_msg)
            raise ScanEngineException(error_msg) from e
        finally:
            self._is_running = False
            # Close data writer file if open
            if self._data_writer is not None:
                try:
                    self._data_writer.close()
                except Exception as e:
                    self._logger.log_error(LogCategory.SCAN, f"Ошибка при закрытии файла данных: {e}")

    def pause_scan(self):
        """Приостанавливает сканирование."""
        if self._is_running and not self._is_paused:
            self._is_paused = True
            self._logger.log_info(LogCategory.SCAN, "Сканирование приостановлено")
            if self.on_scan_paused:
                self.on_scan_paused()

    def resume_scan(self):
        """Возобновляет сканирование."""
        if self._is_running and self._is_paused:
            self._is_paused = False
            self._logger.log_info(LogCategory.SCAN, "Сканирование возобновлено")
            if self.on_scan_resumed:
                self.on_scan_resumed()

    def stop_scan(self):
        """Останавливает сканирование."""
        if self._is_running:
            self._is_running = False
            self._is_paused = False
            try:
                self._x_axis.emergency_stop()
                self._theta_axis.emergency_stop()
            except Exception as e:
                self._logger.log_warn(LogCategory.SCAN, f"Ошибка аварийной остановки: {e}")
            self._logger.log_info(LogCategory.SCAN, "Сканирование остановлено")
            if self.on_scan_stopped:
                self.on_scan_stopped()
