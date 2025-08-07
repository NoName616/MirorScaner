# src/hardware/axis_controller.py
"""
Контроллер для управления отдельной осью (X или Theta)
с поддержкой калибровки, перемещения и управления нулевой точкой.
"""
import asyncio
import time
from typing import Optional, Callable
from hardware.stm32_controller import Stm32ControllerService
from config.config_manager import ConfigManager
from config.config_model import AppConfig, StepperConfig
from utils.logger import DataLogger, LogCategory

class AxisControllerException(Exception):
    """Исключение для ошибок контроллера оси."""
    pass

class AxisController:
    """
    Контроллер для управления одной осью (X или Theta).
    """
    def __init__(self, controller: Stm32ControllerService, axis_name: str, 
                 config: AppConfig, logger: DataLogger):
        self._controller = controller
        self._axis = axis_name.upper()
        self._logger = logger
        self._config = config
        
        if self._axis not in ["X", "THETA"]:
            raise ValueError("Недопустимое имя оси. Допустимые значения: 'X' или 'THETA'")
            
        # Получаем конфигурацию шагового двигателя для этой оси
        try:
            self._stepper_config = ConfigManager.get_stepper_config(config, self._axis)
        except ValueError as e:
            self._logger.log_error(LogCategory.CONTROLLER, f"Ошибка получения конфигурации для оси {self._axis}: {e}")
            raise AxisControllerException(f"Ошибка конфигурации оси {self._axis}") from e
            
        self._is_calibrated = False
        self._zero_offset_steps = 0
        self._current_position_steps = 0
        # Improvement: For theta, simulate encoder value
        self._encoder_value = 0  # Placeholder for encoder reading
        
        # Подписываемся на события контроллера
        self._controller.on_calibration_done = self._on_calibration_done
        self._controller.on_homing_done = self._on_homing_done

    def _on_calibration_done(self):
        """Обработчик завершения калибровки."""
        self._is_calibrated = True
        self._logger.log_info(LogCategory.CONTROLLER, f"Калибровка оси {self._axis} завершена")
        # Improvement: Send current position after calibration
        if self._axis == "THETA":
            self._controller.send_command(f"setpos {self._encoder_value}")

    def _on_homing_done(self, axis: str):
        """Обработчик завершения homing."""
        if axis.upper() == self._axis:
            self._current_position_steps = 0 # После homing позиция 0
            self._logger.log_info(LogCategory.CONTROLLER, f"Homing оси {self._axis} завершён, позиция установлена в 0")
            # For theta, read encoder
            if self._axis == "THETA":
                self._encoder_value = self._read_encoder()  # Simulated

    def _read_encoder(self) -> int:
        """Simulated encoder reading for theta axis."""
        # In real implementation, send command to controller to get encoder value
        return 0  # Placeholder

    def get_stepper_config(self) -> StepperConfig:
        """Возвращает конфигурацию шагового двигателя для этой оси."""
        return self._stepper_config

    def is_calibrated(self) -> bool:
        """Проверяет, была ли выполнена калибровка."""
        return self._is_calibrated

    def get_current_position_mm(self) -> float:
        """Возвращает текущую позицию в миллиметрах (для линейной оси)."""
        if self._axis == "X":
            steps_per_mm = self._stepper_config.steps_per_mm
            if steps_per_mm > 0:
                return (self._current_position_steps - self._zero_offset_steps) / steps_per_mm
        return 0.0

    def get_current_position_deg(self) -> float:
        """Возвращает текущую позицию в градусах (для угловой оси)."""
        if self._axis == "THETA":
            steps_per_rev = self._stepper_config.rotate_steps * self._stepper_config.microstep_factor
            if steps_per_rev > 0:
                # Improvement: Use encoder for more accurate position
                encoder_deg = (self._encoder_value / steps_per_rev) * 360.0
                return encoder_deg
        return 0.0

    def mm_to_steps(self, mm: float) -> int:
        """Преобразует миллиметры в шаги."""
        if self._axis != "X":
            raise AxisControllerException("Преобразование мм->шаги доступно только для оси X")
        return int(round(mm * self._stepper_config.steps_per_mm))

    def deg_to_steps(self, degrees: float) -> int:
        """Преобразует градусы в шаги."""
        if self._axis != "THETA":
            raise AxisControllerException("Преобразование градусы->шаги доступно только для оси Theta")
        steps_per_rev = self._stepper_config.rotate_steps * self._stepper_config.microstep_factor
        return int(round((degrees / 360.0) * steps_per_rev))

    def start_calibration(self):
        """Запускает калибровку оси."""
        if not self._controller.is_connected():
            raise AxisControllerException("Контроллер не подключен")
        self._logger.log_info(LogCategory.CONTROLLER, f"Запуск калибровки оси {self._axis}")
        self._controller.start_calibration()

    def start_homing(self):
        """Запускает homing оси."""
        if not self._controller.is_connected():
            raise AxisControllerException("Контроллер не подключен")
        self._logger.log_info(LogCategory.CONTROLLER, f"Запуск homing оси {self._axis}")
        self._controller.start_homing(self._axis)

    async def move_to_async(self, position_mm_or_deg: float, timeout: float = 30.0) -> bool:
        """
        Асинхронно перемещает ось в заданную позицию.
        Для оси X позиция в мм, для Theta в градусах.
        """
        if not self._controller.is_connected():
            raise AxisControllerException("Контроллер не подключен")
            
        steps = 0
        if self._axis == "X":
            steps = self.mm_to_steps(position_mm_or_deg)
            self._logger.log_info(LogCategory.CONTROLLER, f"Перемещение оси X на {position_mm_or_deg:.3f} мм ({steps} шагов)")
        elif self._axis == "THETA":
            steps = self.deg_to_steps(position_mm_or_deg)
            self._logger.log_info(LogCategory.CONTROLLER, f"Поворот оси Theta на {position_mm_or_deg:.3f}° ({steps} шагов)")
        
        # Отправляем команду перемещения
        # Здесь мы предполагаем, что контроллер понимает абсолютные координаты
        # с учётом нуля. В C# коде это реализовано через move 0 x theta
        # Мы будем использовать move_to контроллера напрямую
        if self._axis == "X":
            self._controller.move_to(position_mm_or_deg, 0) # Y=0, Theta=0
        elif self._axis == "THETA":
            self._controller.move_to(0, position_mm_or_deg) # X=0, Y=0
            
        # Ждём завершения перемещения
        try:
            # Создаём future для ожидания события завершения
            future = asyncio.get_event_loop().create_future()
            
            def on_move_done():
                if not future.done():
                    future.set_result(True)
            
            # Временно подменяем обработчик
            original_handler = self._controller.on_movement_done
            self._controller.on_movement_done = on_move_done
            
            try:
                await asyncio.wait_for(future, timeout=timeout)
                self._current_position_steps = steps + self._zero_offset_steps
                return True
            except asyncio.TimeoutError:
                self._logger.log_error(LogCategory.CONTROLLER, f"Таймаут перемещения оси {self._axis}")
                return False
            finally:
                # Восстанавливаем оригинальный обработчик
                self._controller.on_movement_done = original_handler
                
        except Exception as e:
            self._logger.log_error(LogCategory.CONTROLLER, f"Ошибка перемещения оси {self._axis}: {e}")
            raise AxisControllerException(f"Ошибка перемещения: {e}") from e

    def set_zero(self):
        """Устанавливает текущую позицию как ноль."""
        if not self._controller.is_connected():
            raise AxisControllerException("Контроллер не подключен")
        self._logger.log_info(LogCategory.CONTROLLER, f"Установка нуля для оси {self._axis}")
        self._controller.set_zero()
        self._zero_offset_steps = self._current_position_steps
        self._current_position_steps = 0

    def emergency_stop(self):
        """Аварийная остановка."""
        self._controller.emergency_stop()