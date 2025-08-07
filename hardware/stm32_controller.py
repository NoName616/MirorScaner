# src/hardware/stm32_controller.py
"""
Модуль для взаимодействия с контроллером STM32 через COM-порт.
Использует pyserial для связи.
"""
import serial
import time
import threading
from typing import Optional, Callable, Dict, Any
import asyncio
from concurrent.futures import ThreadPoolExecutor
from utils.logger import DataLogger, LogCategory

class Stm32ControllerException(Exception):
    """Исключение для ошибок контроллера STM32."""
    pass

class Stm32ControllerService:
    """
    Сервис для управления контроллером STM32F415RGT6 через COM-порт.
    """
    def __init__(self, logger: DataLogger):
        self._logger = logger
        self._serial: Optional[serial.Serial] = None
        self._is_connected = False
        self._firmware_version: Optional[str] = None
        self._controller_id: Optional[str] = None
        self._response_buffer: list = []
        self._buffer_lock = threading.Lock()
        self._read_thread: Optional[threading.Thread] = None
        self._command_lock = threading.Lock() # Для синхронизации команд
        self._running = False
        self._executor = ThreadPoolExecutor(max_workers=1) # Для асинхронных команд
        
        # Обработчики команд
        self._command_handlers: Dict[str, Callable[[str], None]] = {
            "id:": self._handle_id,
            "fw:": self._handle_fw,
            "error:": self._handle_error,
            "calibration_done": self._handle_calibration_done,
            "homing_done": self._handle_homing_done,
            "move_done": self._handle_move_done,
        }
        
        # События
        self.on_data_received: Optional[Callable[[str], None]] = None
        self.on_connected: Optional[Callable[[], None]] = None
        self.on_disconnected: Optional[Callable[[], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None
        self.on_calibration_done: Optional[Callable[[], None]] = None
        self.on_homing_done: Optional[Callable[[str], None]] = None
        self.on_movement_done: Optional[Callable[[], None]] = None

    def connect(self, port: str, baudrate: int = 115200, timeout: float = 2.0) -> bool:
        """Подключается к контроллеру через COM-порт."""
        try:
            if self._is_connected and self._serial and self._serial.is_open:
                self._logger.log_warn(LogCategory.CONTROLLER, "Уже подключен к контроллеру.")
                return True

            self._serial = serial.Serial(
                port, baudrate=baudrate, timeout=timeout,
                bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE
            )
            self._serial.reset_input_buffer()
            self._serial.reset_output_buffer()
            time.sleep(0.1) # Небольшая пауза
            
            # Проверка связи и handshake
            if not self._perform_handshake():
                self._logger.log_error(LogCategory.CONTROLLER, "Handshake с контроллером не удался.")
                self._serial.close()
                return False
                
            self._is_connected = True
            self._running = True
            self._start_read_thread()
            
            self._logger.log_info(LogCategory.CONTROLLER, f"Подключен к контроллеру на {port}")
            if self.on_connected:
                self.on_connected()
            return True
                
        except Exception as e:
            self._logger.log_error(LogCategory.CONTROLLER, f"Ошибка подключения к {port}: {e}")
            if self.on_error:
                self.on_error(f"Ошибка подключения: {e}")
            return False

    def _perform_handshake(self) -> bool:
        """Выполняет handshake с контроллером."""
        try:
            # Первая попытка
            if self._try_handshake_once():
                return True
            # Вторая попытка с задержкой
            time.sleep(0.5)
            if self._try_handshake_once():
                return True
            return False
        except Exception as e:
            self._logger.log_error(LogCategory.CONTROLLER, f"Ошибка handshake: {e}")
            return False

    def _try_handshake_once(self) -> bool:
        """Одна попытка handshake."""
        self._send_command_internal("getid")
        time.sleep(0.1)
        self._send_command_internal("getver")
        time.sleep(0.1)
        
        # Ожидаем ответы
        start_time = time.time()
        while time.time() - start_time < 2.0: # Таймаут 2 секунды
            with self._buffer_lock:
                buffer_copy = self._response_buffer[:]
                self._response_buffer.clear()
            
            for line in buffer_copy:
                self._process_response(line)
            
            if self._controller_id and self._firmware_version:
                return True
            time.sleep(0.05)
        return False

    def _handle_id(self, response: str):
        """Обработчик ID контроллера."""
        self._controller_id = response[4:].strip() # Убираем "id:"
        self._logger.log_debug(LogCategory.CONTROLLER, f"Получен ID контроллера: {self._controller_id}")

    def _handle_fw(self, response: str):
        """Обработчик версии прошивки."""
        self._firmware_version = response[4:].strip() # Убираем "fw:"
        self._logger.log_debug(LogCategory.CONTROLLER, f"Получена версия прошивки: {self._firmware_version}")

    def _handle_error(self, response: str):
        """Обработчик ошибок от контроллера."""
        error_msg = response[7:].strip() # Убираем "error:"
        self._logger.log_error(LogCategory.CONTROLLER, f"Ошибка контроллера: {error_msg}")
        if self.on_error:
            self.on_error(f"Controller error: {error_msg}")

    def _handle_calibration_done(self, response: str):
        """Обработчик завершения калибровки."""
        self._logger.log_info(LogCategory.CONTROLLER, "Калибровка завершена")
        if self.on_calibration_done:
            self.on_calibration_done()

    def _handle_homing_done(self, response: str):
        """Обработчик завершения homing."""
        parts = response.split(":")
        axis = parts[1].strip() if len(parts) > 1 else "Unknown"
        self._logger.log_info(LogCategory.CONTROLLER, f"Homing оси {axis} завершён")
        if self.on_homing_done:
            self.on_homing_done(axis)

    def _handle_move_done(self, response: str):
        """Обработчик завершения перемещения."""
        self._logger.log_info(LogCategory.CONTROLLER, "Перемещение завершено")
        if self.on_movement_done:
            self.on_movement_done()

    def disconnect(self):
        """Отключается от контроллера."""
        self._running = False
        if self._read_thread and self._read_thread.is_alive():
            self._read_thread.join(timeout=2.0)
            
        if self._serial and self._serial.is_open:
            self._serial.close()
            
        self._is_connected = False
        self._firmware_version = None
        self._controller_id = None
        self._logger.log_info(LogCategory.CONTROLLER, "Отключен от контроллера")
        if self.on_disconnected:
            self.on_disconnected()

    def is_connected(self) -> bool:
        """Проверяет, подключен ли контроллер."""
        return self._is_connected and self._serial is not None and self._serial.is_open

    def get_firmware_version(self) -> Optional[str]:
        """Возвращает версию прошивки."""
        return self._firmware_version

    def get_controller_id(self) -> Optional[str]:
        """Возвращает ID контроллера."""
        return self._controller_id

    def _send_command_internal(self, command: str):
        """Внутренний метод для отправки команды."""
        if not self.is_connected():
            raise Stm32ControllerException("Контроллер не подключен")
            
        try:
            cmd_bytes = f"{command}\n".encode('utf-8')
            self._serial.write(cmd_bytes)
            self._logger.log_debug(LogCategory.CONTROLLER, f"Отправлена команда: {command}")
        except Exception as e:
            error_msg = f"Ошибка отправки команды '{command}': {e}"
            self._logger.log_error(LogCategory.CONTROLLER, error_msg)
            raise Stm32ControllerException(error_msg) from e

    def send_command(self, command: str):
        """Отправляет команду контроллеру."""
        with self._command_lock:
            self._send_command_internal(command)

    def _start_read_thread(self):
        """Запускает поток для чтения данных из порта."""
        self._read_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._read_thread.start()

    def _read_loop(self):
        """Цикл чтения данных из COM-порта."""
        while self._running and self._serial and self._serial.is_open:
            try:
                if self._serial.in_waiting > 0:
                    line = self._serial.readline().decode('utf-8').strip()
                    if line:
                        with self._buffer_lock:
                            self._response_buffer.append(line)
                        
                        self._logger.log_debug(LogCategory.CONTROLLER, f"Получено: {line}")
                        if self.on_data_received:
                            self.on_data_received(line)
                            
                        # Обработка ответа
                        self._process_response(line)
                        
            except serial.SerialException as se:
                if self._running: # Ошибка только если не остановка
                    error_msg = f"Ошибка последовательного порта (RX): {se}"
                    self._logger.log_error(LogCategory.CONTROLLER, error_msg, se)
                    if self.on_error:
                        self.on_error(error_msg)
                break
            except Exception as e:
                if self._running:
                    error_msg = f"Неожиданная ошибка в потоке чтения: {e}"
                    self._logger.log_error(LogCategory.CONTROLLER, error_msg, e)
                    if self.on_error:
                        self.on_error(error_msg)
                break
        self._logger.log_info(LogCategory.CONTROLLER, "Поток чтения остановлен")

    def _process_response(self, response: str):
        """Обрабатывает ответ от контроллера."""
        try:
            # Поиск обработчика по префиксу
            for prefix, handler in self._command_handlers.items():
                if response.lower().startswith(prefix.lower()):
                    handler(response)
                    return
            # Если не найден специфичный обработчик, просто логгируем
            self._logger.log_debug(LogCategory.CONTROLLER, f"Необработанный ответ: {response}")
        except Exception as e:
            self._logger.log_error(LogCategory.CONTROLLER, f"Ошибка обработки ответа '{response}': {e}")

    # --- Команды ---
    def start_calibration(self):
        """Отправляет команду калибровки."""
        self._logger.log_info(LogCategory.CONTROLLER, "Отправка команды калибровки (calibrate)")
        self.send_command("calibrate")

    def start_homing(self, axis: str):
        """Отправляет команду homing для оси."""
        axis_cmd = axis.lower()
        if axis_cmd == "x":
            self._logger.log_info(LogCategory.CONTROLLER, "Отправка команды homing для оси X (homex)")
            self.send_command("homex")
        elif axis_cmd == "theta":
            self._logger.log_info(LogCategory.CONTROLLER, "Отправка команды homing для оси Theta (hometheta)")
            self.send_command("hometheta")
        else:
            self._logger.log_warn(LogCategory.CONTROLLER, f"Неизвестная ось для homing: {axis}")

    def move_to(self, x_mm: float, theta_deg: float):
        """Отправляет команду перемещения."""
        # Предполагается, что контроллер понимает команду вида "move x y theta"
        # Где x в мм, theta в градусах, y=0 если не используется
        cmd = f"move 0 {x_mm:.3f} {theta_deg:.3f}"
        self._logger.log_info(LogCategory.CONTROLLER, f"Отправка команды перемещения: {cmd}")
        self.send_command(cmd)

    def set_zero(self):
        """Устанавливает текущую позицию как ноль."""
        self._logger.log_info(LogCategory.CONTROLLER, "Отправка команды установки нуля (setzero)")
        self.send_command("setzero")

    def emergency_stop(self):
        """Отправляет команду аварийной остановки."""
        self._logger.log_warn(LogCategory.CONTROLLER, "Отправка команды аварийной остановки (estop)!")
        self.send_command("estop")

    @staticmethod
    def get_available_ports() -> list:
        """Возвращает список доступных COM-портов."""
        import serial.tools.list_ports
        ports = serial.tools.list_ports.comports()
        return [port.device for port in ports]

    # --- Асинхронные команды ---
    async def send_command_async(self, command: str, timeout: float = 5.0) -> Optional[str]:
        """
        Отправляет команду и ждёт ответ.
        Возвращает ответ или None при таймауте.
        """
        future = asyncio.get_event_loop().create_future()
        response_received = threading.Event()
        response_value = [None] # Используем список для мутации внутри замыкания
        
        def on_data_received(data: str) -> None:
    """
    Temporary handler capturing a single response from the controller.
    Assigns the received data to ``response_value`` and resolves the
    awaiting future exactly once.
    """
    if not future.done():
        response_value[0] = data
        response_received.set()
        future.set_result(data)

        
        # Временно подменяем обработчик
        original_handler = self.on_data_received
        self.on_data_received = on_data_received
        
        try:
            self.send_command(command)
            # Ждём ответ или таймаут
            await asyncio.wait_for(future, timeout=timeout)
            return response_value[0]
        except asyncio.TimeoutError:
            self._logger.log_warn(LogCategory.CONTROLLER, f"Таймаут ожидания ответа на команду '{command}'")
            if not future.done():
                future.set_result(None)
            return None
        finally:
            # Восстанавливаем оригинальный обработчик
            self.on_data_received = original_handler

    async def get_controller_info_async(self) -> Dict[str, Any]:
        """Асинхронно получает информацию о контроллере."""
        id_result = await self.send_command_async("getid", timeout=3.0)
        fw_result = await self.send_command_async("getver", timeout=3.0)
        
        return {
            "id": id_result[4:].strip() if id_result and id_result.startswith("id:") else "Unknown",
            "firmware": fw_result[4:].strip() if fw_result and fw_result.startswith("fw:") else "Unknown"
        }
