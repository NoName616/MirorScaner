# src/utils/logger.py
"""
Модуль для ведения логов приложения.
Соответствует функциональности DataLogger из C#-версии.
"""
import logging
from enum import Enum
from datetime import datetime
from typing import Optional, Callable
import os
from pathlib import Path

# --- Определение категорий логов, как в C# ---
class LogCategory(Enum):
    """Категории логов для классификации сообщений."""
    GENERAL = "GENERAL"
    CONTROLLER = "CONTROLLER"
    CAMERA = "CAMERA"
    CALIBRATION = "CALIBRATION"
    SCAN = "SCAN"
    UI = "UI"

# --- Класс логгера ---
class DataLogger:
    """
    Логгер данных приложения с поддержкой категорий и уровней.
    Использует стандартную библиотеку logging Python.
    """
    _instance = None # Для потенциальной реализации Singleton, если потребуется

    def __init__(self, log_file_path: str = "app.log"):
        """
        Инициализирует логгер.
        
        Args:
            log_file_path (str): Путь к файлу лога. Создает директории при необходимости.
        """
        # Создаем директорию для лог-файла, если её нет
        log_path = Path(log_file_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Имя логгера для изоляции
        self.logger = logging.getLogger(f"MirrorScan.{id(self)}")
        # Устанавливаем самый низкий уровень, чтобы обработчики сами фильтровали
        self.logger.setLevel(logging.DEBUG) 
        # Избегаем дублирования сообщений, если логгер уже существует
        self.logger.propagate = False
        
        # Очищаем существующие обработчики, если они есть (например, при повторной инициализации)
        if self.logger.hasHandlers():
            self.logger.handlers.clear()

        # Форматтер для сообщений
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)-8s] [%(name)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Обработчик для консоли (INFO и выше)
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(logging.INFO)
        self.logger.addHandler(console_handler)
        
        # Обработчик для файла (DEBUG и выше)
        file_handler = logging.FileHandler(log_file_path, encoding='utf-8')
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.DEBUG)
        self.logger.addHandler(file_handler)
        
        # Callback для передачи строк лога в UI (аналог OnLineLogged в C#)
        self.on_line_logged: Optional[Callable[[str], None]] = None

        self.logger.info("DataLogger инициализирован.")

    def _log(self, level: int, category: LogCategory, message: str, exc_info: Optional[Exception] = None):
        """
        Внутренний метод для форматирования и записи лога.
        
        Args:
            level (int): Уровень логгирования (например, logging.INFO).
            category (LogCategory): Категория сообщения.
            message (str): Текст сообщения.
            exc_info (Exception, optional): Исключение для логгирования.
        """
        # Форматируем сообщение для файлового/консольного логгера
        formatted_message = f"[{category.value}] {message}"
        self.logger.log(level, formatted_message, exc_info=exc_info)
        
        # Форматируем сообщение для UI callback (если он нужен в том же виде, что и в C#)
        if self.on_line_logged:
            try:
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                level_name = logging.getLevelName(level)
                # Формат, аналогичный тому, что может ожидать UI (как в DebugForm C#)
                line = f"{timestamp} [{level_name:<8}] [{category.value}] {message}"
                # Вызываем callback в блоке try-except, чтобы ошибка в UI не сломала логгер
                self.on_line_logged(line)
            except Exception as e:
                # Если callback сломался, логгируем это в основной логгер, но не через себя же
                print(f"[LOGGER ERROR] Ошибка в on_line_logged callback: {e}")

    # --- Методы для различных уровней логгирования ---
    def log_debug(self, category: LogCategory, message: str):
        """Логгировать сообщение уровня DEBUG."""
        self._log(logging.DEBUG, category, message)

    def log_info(self, category: LogCategory, message: str):
        """Логгировать сообщение уровня INFO."""
        self._log(logging.INFO, category, message)

    def log_warn(self, category: LogCategory, message: str):
        """Логгировать сообщение уровня WARNING."""
        self._log(logging.WARNING, category, message)

    def log_error(self, category: LogCategory, message: str, exc_info: Optional[Exception] = None):
        """Логгировать сообщение уровня ERROR."""
        self._log(logging.ERROR, category, message, exc_info)

# --- (Опционально) Глобальный логгер, как в C# Program.cs ---
# Это можно использовать, если нужен действительно глобальный доступ,
# хотя передача экземпляра через зависимости (как сделано в проекте) предпочтительнее.
# GLOBAL_LOGGER: Optional[DataLogger] = None
# def get_global_logger() -> Optional[DataLogger]:
#     """Получить глобальный экземпляр логгера."""
#     global GLOBAL_LOGGER
#     return GLOBAL_LOGGER
