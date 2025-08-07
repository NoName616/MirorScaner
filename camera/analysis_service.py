"""
Сервис анализа изображений для вычисления температур по выбранной области и линиям.
"""
import time
from datetime import datetime
from typing import List, Tuple, Optional
import numpy as np

class AnalysisService:
    """Сервис для аналитики теплового изображения."""
    def __init__(self, logger=None, max_buffer_size: int = 5):
        """
        :param logger: опционально, экземпляр DataLogger для логирования.
        :param max_buffer_size: количество кадров для усреднения во втором методе.
        """
        self._logger = logger
        self._max_buffer_size = max_buffer_size
        self._frame_buffer: List[np.ndarray] = []  # хранит последние кадры для метода 2
        self._roi: Optional[Tuple[int, int, int, int]] = None  # ROI (x1, y1, x2, y2) в координатах изображения
        self._lines: List[Tuple[Tuple[int, int], Tuple[int, int]]] = []  # список линий (начало, конец) в координатах изображения
        self._method: str = "fast"    # "fast" – быстрый, "precise" – точный метод
        self._object_type: str = "flat"  # "flat" – плоская поверхность, "round" – круглая (криволинейная) поверхность
        self._recording: bool = False
        self._output_file = None
        self._output_file_path = None
        # Improvement: Track previous max temp and position to avoid repeats in small angle changes
        self._previous_max_temp: Optional[float] = None
        self._previous_max_pos: Optional[Tuple[int, int]] = None

    @property
    def method(self) -> str:
        return self._method

    @method.setter
    def method(self, value: str):
        if value not in ["fast", "precise"]:
            raise ValueError("Invalid method type. Use 'fast' or 'precise'.")
        self._method = value
        # Очистим буфер кадров при переключении метода, чтобы не смешивать режимы
        self._frame_buffer.clear()

    @property
    def object_type(self) -> str:
        return self._object_type

    @object_type.setter
    def object_type(self, value: str):
        if value not in ["flat", "round"]:
            raise ValueError("Invalid object type. Use 'flat' or 'round'.")
        self._object_type = value
        # При смене типа поверхности можно при необходимости загрузить другую калибровку
        if self._logger:
            self._logger.log_info("GENERAL", f"Установлен тип поверхности: {value}")

    @property
    def roi(self) -> Optional[Tuple[int, int, int, int]]:
        """Возвращает текущую выбранную область ROI (координаты x1,y1,x2,y2) или None."""
        return self._roi

    @property
    def lines(self) -> List[Tuple[Tuple[int, int], Tuple[int, int]]]:
        """Возвращает список выбранных линий для анализа."""
        return list(self._lines)

    @property
    def is_recording(self) -> bool:
        """Возвращает True, если сейчас идет запись результатов в файл."""
        return self._recording

    def set_roi(self, x1: int, y1: int, x2: int, y2: int):
        """Задает регион интереса (ROI) по координатам двух углов прямоугольника (в координатах изображения)."""
        # Упорядочим координаты: левый верхний и правый нижний углы
        x_min, x_max = sorted([x1, x2])
        y_min, y_max = sorted([y1, y2])
        self._roi = (x_min, y_min, x_max, y_max)
        # Очистить предыдущие линии, так как они относятся к старому ROI
        self._lines.clear()
        # Очистить буфер кадров при новой области
        self._frame_buffer.clear()
        # Reset previous max tracking
        self._previous_max_temp = None
        self._previous_max_pos = None
        if self._logger:
            self._logger.log_info("GENERAL", f"ROI задан: ({x_min}, {y_min}) - ({x_max}, {y_max})")
        # Если запись была активна, остановим её (новая область – новое измерение)
        if self._recording:
            self.stop_recording()

    def add_line(self, x1: int, y1: int, x2: int, y2: int):
        """Добавляет линию для измерения температуры (в координатах изображения). Предполагается, что линия находится внутри ROI."""
        if not self._roi:
            raise RuntimeError("ROI is not set before adding a line.")
        # Ограничим координаты концов линии пределами текущего ROI
        rx1, ry1, rx2, ry2 = self._roi
        nx1 = min(max(x1, rx1), rx2)
        ny1 = min(max(y1, ry1), ry2)
        nx2 = min(max(x2, rx1), rx2)
        ny2 = min(max(y2, ry1), ry2)
        self._lines.append(((nx1, ny1), (nx2, ny2)))
        if self._logger:
            self._logger.log_info("GENERAL", f"Добавлена линия: ({nx1}, {ny1}) - ({nx2}, {ny2})")
        # В данной реализации не поддерживается добавление линии во время записи

    def clear_lines(self):
        """Полностью сбрасывает выбор области и линий."""
        self._lines.clear()
        self._roi = None
        self._frame_buffer.clear()
        self._previous_max_temp = None
        self._previous_max_pos = None
        if self._logger:
            self._logger.log_info("GENERAL", "Выбор области и линий сброшен.")
        # Остановка записи, если она шла
        if self._recording:
            self.stop_recording()

    def start_recording(self) -> bool:
        """Начинает запись результатов анализа в CSV-файл."""
        if not self._roi or len(self._lines) == 0:
            # Нет данных для записи
            return False
        # Формируем имя файла с меткой времени
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._output_file_path = f"analysis_output_{timestamp}.csv"
        try:
            self._output_file = open(self._output_file_path, mode='w', encoding='utf-8')
        except Exception as e:
            if self._logger:
                self._logger.log_error("GENERAL", f"Не удалось открыть файл для записи: {e}")
            return False
        # Записываем заголовок CSV: Timestamp и столбцы для каждой линии (avg, min, max)
        header = "Timestamp"
        for i in range(len(self._lines)):
            header += f", Line{i+1}_avg, Line{i+1}_min, Line{i+1}_max"
        self._output_file.write(header + "\n")
        self._recording = True
        if self._logger:
            self._logger.log_info("GENERAL", f"Запись результатов в файл {self._output_file_path} начата.")
        return True

    def stop_recording(self):
        """Останавливает запись результатов и закрывает файл."""
        if self._recording:
            self._recording = False
            if self._output_file:
                try:
                    self._output_file.close()
                except Exception:
                    pass
                self._output_file = None
            if self._logger:
                self._logger.log_info("GENERAL", "Запись результатов в файл остановлена.")

    def _get_line_pixels(self, frame: np.ndarray, p1: Tuple[int, int], p2: Tuple[int, int]) -> List[int]:
        """Возвращает список значений пикселей вдоль линии p1->p2 (алгоритм Брезенхэма)."""
        x1, y1 = p1
        x2, y2 = p2
        pixels: List[int] = []
        dx = abs(x2 - x1)
        dy = abs(y2 - y1)
        sx = 1 if x1 < x2 else -1
        sy = 1 if y1 < y2 else -1
        err = dx - dy
        while True:
            if 0 <= x1 < frame.shape[1] and 0 <= y1 < frame.shape[0]:
                pixels.append(int(frame[y1, x1]))
            if x1 == x2 and y1 == y2:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x1 += sx
            if e2 < dx:
                err += dx
                y1 += sy
        return pixels

    def process_frame(self, frame: np.ndarray) -> List[Tuple[float, float, float]]:
        """
        Обрабатывает очередной кадр и возвращает список результатов (avg, min, max) для каждой линии.
        """
        results: List[Tuple[float, float, float]] = []
        if not self._roi or len(self._lines) == 0:
            return results
        # Если выбран точный метод (усреднение по нескольким кадрам)
        if self._method == "precise":
            # Добавляем новый кадр в буфер
            self._frame_buffer.append(frame.copy())
            if len(self._frame_buffer) > self._max_buffer_size:
                self._frame_buffer.pop(0)
            # Вычисляем среднее изображение из буфера (float)
            if len(self._frame_buffer) > 0:
                mean_frame = np.mean(np.stack(self._frame_buffer, axis=0), axis=0)
            else:
                mean_frame = frame.astype(np.float32)
            frame_to_analyze = mean_frame
        else:
            # Быстрый метод: используем текущий кадр без усреднения
            frame_to_analyze = frame
        # Рассчитываем показатели для каждой линии
        for (p1, p2) in self._lines:
            pixels = np.array(self._get_line_pixels(frame_to_analyze, p1, p2))
            if len(pixels) == 0:
                avg_val = 0.0
                min_val = 0.0
                max_val = 0.0
            else:
                # Improvement: Avoid repeating the same max temp from previous hot spot
                max_idx = np.argmax(pixels)
                # Calculate approximate position along the line
                t = max_idx / (len(pixels) - 1) if len(pixels) > 1 else 0
                current_max_pos = (int(p1[0] + t * (p2[0] - p1[0])),
                                   int(p1[1] + t * (p2[1] - p1[1])))
                max_val = float(np.max(pixels))
                if self._previous_max_temp is not None and abs(max_val - self._previous_max_temp) < 1e-6 and \
                   self._previous_max_pos == current_max_pos:
                    # If same max value and position, mask it and find next max
                    pixels[max_idx] = np.min(pixels) - 1  # Mask below min to exclude
                    max_val = float(np.max(pixels))
                # Update previous
                self._previous_max_temp = max_val
                self._previous_max_pos = current_max_pos
                avg_val = float(np.mean(pixels))
                min_val = float(np.min(pixels))
            results.append((avg_val, min_val, max_val))
        # Если идет запись в файл – добавляем строку с результатами
        if self._recording and self._output_file:
            ts_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]  # текущее время с мс
            line_values = ""
            for (avg_val, min_val, max_val) in results:
                line_values += f", {avg_val:.2f}, {min_val:.2f}, {max_val:.2f}"
            self._output_file.write(ts_str + line_values + "\n")
        return results