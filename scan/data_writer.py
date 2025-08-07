# src/scan/data_writer.py
"""
Интерфейс и реализации для записи данных сканирования.
"""
import os
import csv
from abc import ABC, abstractmethod
from typing import Optional
from enum import Enum
from utils.math_utils import degrees_to_dms

class OutputFormat(Enum):
    TXT = "txt"
    MD = "md"
    CSV = "csv"

class AngleUnit(Enum):
    DEGREES = "degrees"
    DMS = "dms"

class IScanDataWriter(ABC):
    """Интерфейс для записи данных сканирования."""
    
    @abstractmethod
    def write_header(self, radius_mm: float, radial_step_mm: float, 
                     arc_step_mm: float, angle_deg: float):
        """Записывает заголовок файла."""
        pass
    
    @abstractmethod
    def write_data(self, radius_mm: float, angle_deg: float, 
                   min_temp: float, max_temp: float):
        """Записывает одну строку данных."""
        pass

class ScanDataWriter(IScanDataWriter):
    """
    Реализация IScanDataWriter для записи в различные форматы.
    """
    def __init__(self, file_path: str, output_format: OutputFormat, 
                 angle_unit: AngleUnit = AngleUnit.DEGREES):
        self._file_path = file_path
        self._format = output_format
        self._angle_unit = angle_unit
        self._file_handle = None
        self._csv_writer = None
        
        # Создаем директорию, если её нет
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

    def write_header(self, radius_mm: float, radial_step_mm: float, 
                     arc_step_mm: float, angle_deg: float):
        """Записывает заголовок файла."""
        self._close_file() # Закрываем предыдущий файл, если был
        
        self._file_handle = open(self._file_path, 'w', encoding='utf-8', newline='')
        
        if self._format == OutputFormat.CSV:
            self._csv_writer = csv.writer(self._file_handle)
            header = ["Radius (mm)", "Angle", "Min Temperature (ADU)", "Max Temperature (ADU)"]
            self._csv_writer.writerow(header)
        else:
            # TXT и MD имеют одинаковый формат заголовка
            header_lines = [
                f"# Сканирование зеркала",
                f"# Максимальный радиус: {radius_mm:.2f} мм",
                f"# Шаг по радиусу: {radial_step_mm:.2f} мм",
                f"# Шаг по дуге: {arc_step_mm:.2f} мм",
                f"# Угол сканирования: {angle_deg:.2f}°",
                f"# Единицы угла: {self._angle_unit.value}",
                ""
            ]
            if self._format == OutputFormat.MD:
                # Добавляем заголовок таблицы для Markdown
                header_lines.append("| Radius (mm) | Angle | Min Temp (ADU) | Max Temp (ADU) |")
                header_lines.append("|-------------|-------|----------------|----------------|")
            else: # TXT
                header_lines.append("Radius (mm)\tAngle\tMin Temp (ADU)\tMax Temp (ADU)")
                
            self._file_handle.write('\n'.join(header_lines) + '\n')
        
        self._file_handle.flush()

    def write_data(self, radius_mm: float, angle_deg: float, 
                   min_temp: float, max_temp: float):
        """Записывает одну строку данных."""
        if self._file_handle is None:
            raise IOError("Файл не открыт. Вызовите write_header() сначала.")
            
        # Форматируем угол
        if self._angle_unit == AngleUnit.DMS:
            d, m, s = degrees_to_dms(angle_deg)
            angle_str = f"{d}°{m:02d}'{s:05.2f}\""
        else: # DEGREES
            angle_str = f"{angle_deg:.4f}°"
            
        if self._format == OutputFormat.CSV:
            if self._csv_writer:
                self._csv_writer.writerow([f"{radius_mm:.4f}", angle_str, 
                                         f"{min_temp:.2f}", f"{max_temp:.2f}"])
        else:
            # TXT и MD
            line = f"{radius_mm:.4f}\t{angle_str}\t{min_temp:.2f}\t{max_temp:.2f}"
            if self._format == OutputFormat.MD:
                line = f"| {radius_mm:.4f} | {angle_str} | {min_temp:.2f} | {max_temp:.2f} |"
            self._file_handle.write(line + '\n')
            
        self._file_handle.flush()

    def _close_file(self):
        """Закрывает файл, если он открыт."""
        if self._file_handle:
            self._file_handle.close()
            self._file_handle = None
            self._csv_writer = None

    def __del__(self):
        """Деструктор для закрытия файла."""
        self._close_file()

    def close(self):
        """Явно закрывает файл."""
        self._close_file()
