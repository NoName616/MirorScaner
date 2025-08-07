# src/utils/exceptions.py
"""
Пользовательские исключения для проекта.
"""

# --- Исключения для оборудования ---
class HardwareException(Exception):
    """Базовый класс для исключений оборудования."""
    pass

class ControllerException(HardwareException):
    """Исключение для ошибок контроллера."""
    pass

class AxisControllerException(ControllerException):
    """Исключение для ошибок контроллера оси."""
    pass

class StepperConfigException(HardwareException):
    """Исключение для ошибок конфигурации шагового двигателя."""
    pass

# --- Исключения для камеры ---
class CameraException(Exception):
    """Базовый класс для исключений камеры."""
    pass

class OptrisWrapperException(CameraException):
    """Исключение для ошибок обёртки камеры."""
    pass

# --- Исключения для калибровки ---
class CalibrationException(Exception):
    """Базовый класс для исключений калибровки."""
    pass

class CalibrationServiceException(CalibrationException):
    """Исключение для ошибок сервиса калибровки."""
    pass

# --- Исключения для сканирования ---
class ScanException(Exception):
    """Базовый класс для исключений сканирования."""
    pass

class ScanEngineException(ScanException):
    """Исключение для ошибок движка сканирования."""
    pass

class ScanPlannerException(ScanException):
    """Исключение для ошибок планировщика сканирования."""
    pass

# --- Исключения для конфигурации ---
class ConfigException(Exception):
    """Базовый класс для исключений конфигурации."""
    pass

class ConfigManagerException(ConfigException):
    """Исключение для ошибок менеджера конфигурации."""
    pass

# --- Исключения для логгирования ---
class LoggerException(Exception):
    """Исключение для ошибок логгирования."""
    pass

# Пример использования:
# try:
#     # ... some code ...
#     raise AxisControllerException("Ошибка перемещения оси X")
# except AxisControllerException as e:
#     print(f"Ошибка оси: {e}")
# except ControllerException as e:
#     print(f"Ошибка контроллера: {e}")
# except HardwareException as e:
#     print(f"Ошибка оборудования: {e}")
