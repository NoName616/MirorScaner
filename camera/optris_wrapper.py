# src/camera/optris_wrapper.py
"""
Обёртка для взаимодействия с библиотекой ImagerIPC2x64.dll.
Использует ctypes для вызова функций DLL.
"""
import ctypes
import os
import sys
from ctypes import c_ushort, c_uint, c_float, c_int, c_char_p, POINTER, Structure
from typing import Tuple, Optional
import numpy as np

# --- Определения структур и функций из DLL ---
class FrameMetadata(Structure):
    _fields_ = [
        ("counter", c_uint),
        ("reserved", c_uint),
        ("timestamp", c_uint),
    ]

# Предполагаемые сигнатуры функций на основе IPC2.txt и CameraService.txt
# Эти сигнатуры могут отличаться от реальных, но отражают основную логику!

def load_optris_dll(dll_path: str = None) -> ctypes.CDLL:
    """Загружает DLL библиотеку камеры."""
    if dll_path is None:
        # Попробуем найти DLL в стандартных местах
        possible_paths = [
            "ImagerIPC2x64.dll",
            os.path.join(os.getcwd(), "ImagerIPC2x64.dll"),
            os.path.join(os.path.dirname(__file__), "ImagerIPC2x64.dll"),
        ]
        for path in possible_paths:
            if os.path.exists(path):
                dll_path = path
                break
        else:
            raise FileNotFoundError("Библиотека камеры ImagerIPC2x64.dll не найдена")

    if not os.path.exists(dll_path):
        raise FileNotFoundError(f"Библиотека камеры не найдена: {dll_path}")
    return ctypes.CDLL(dll_path)

class OptrisWrapperException(Exception):
    """Исключение для ошибок обёртки камеры."""
    pass

class OptrisWrapper:
    """
    Обёртка над функциями библиотеки ImagerIPC2x64.dll.
    """
    def __init__(self, dll_path: str = None):
        self.dll = load_optris_dll(dll_path)
        self._is_initialized = False
        self._cam_index = 0
        self.frame_width = 640
        self.frame_height = 480
        self.frame_depth = 2 # 16-bit (2 bytes per pixel)
        
        # --- Определение сигнатур функций ---
        # int IPC2_Initialize()
        self.dll.IPC2_Initialize.argtypes = []
        self.dll.IPC2_Initialize.restype = c_int
        
        # int IPC2_Init(ushort index, char* configPath)
        self.dll.IPC2_Init.argtypes = [c_ushort, c_char_p]
        self.dll.IPC2_Init.restype = c_int
        
        # int IPC2_Run(ushort index)
        self.dll.IPC2_Run.argtypes = [c_ushort]
        self.dll.IPC2_Run.restype = c_int
        
        # int IPC2_Release(ushort index)
        self.dll.IPC2_Release.argtypes = [c_ushort]
        self.dll.IPC2_Release.restype = c_int
        
        # int IPC2_GetFrameConfig(ushort index, int* width, int* height, int* depth)
        self.dll.IPC2_GetFrameConfig.argtypes = [c_ushort, POINTER(c_int), POINTER(c_int), POINTER(c_int)]
        self.dll.IPC2_GetFrameConfig.restype = c_int
        
        # int IPC2_GetFrame(ushort index, int timeoutMs, void* buffer, uint bufferSize, FrameMetadata* metadata)
        # buffer - указатель на массив ushort
        self.dll.IPC2_GetFrame.argtypes = [c_ushort, c_int, ctypes.POINTER(c_ushort), c_uint, POINTER(FrameMetadata)]
        self.dll.IPC2_GetFrame.restype = c_int
        
        # int IPC2_SetFixedEmissivity(ushort index, float emissivity)
        self.dll.IPC2_SetFixedEmissivity.argtypes = [c_ushort, c_float]
        self.dll.IPC2_SetFixedEmissivity.restype = c_int
        
        # int IPC2_SetFixedTempAmbient(ushort index, float temp)
        self.dll.IPC2_SetFixedTempAmbient.argtypes = [c_ushort, c_float]
        self.dll.IPC2_SetFixedTempAmbient.restype = c_int
        
        # int IPC2_SetParameter(ushort index, char* name, int value)
        # Используется для установки режима высокой точности
        self.dll.IPC2_SetParameter.argtypes = [c_ushort, c_char_p, c_int]
        self.dll.IPC2_SetParameter.restype = c_int

        # int IPC2_GetTempChip(ushort index)
        self.dll.IPC2_GetTempChip.argtypes = [c_ushort]
        self.dll.IPC2_GetTempChip.restype = c_float

        # int IPC2_GetSerialNumber(ushort index)
        self.dll.IPC2_GetSerialNumber.argtypes = [c_ushort]
        self.dll.IPC2_GetSerialNumber.restype = c_uint

        # int IPC2_GetFirmwareVersion(ushort index) - может быть не так, проверить IPC2.txt
        # В C# это IPC2.IPC2.GetFirmwareVersion(index) -> ushort
        # Предположим, что это 2 вызова ushort
        self.dll.IPC2_GetFirmware_MSP.argtypes = [c_ushort]
        self.dll.IPC2_GetFirmware_MSP.restype = c_ushort
        self.dll.IPC2_GetFirmware_Cypress.argtypes = [c_ushort]
        self.dll.IPC2_GetFirmware_Cypress.restype = c_ushort

    def initialize(self, config_path: Optional[str] = "pi640_config.xml") -> bool:
        """Инициализирует камеру."""
        try:
            self._cam_index = 0
            
            # Базовая инициализация IPC2
            base_result = self.dll.IPC2_Initialize()
            if base_result != 0:
                 print(f"[CAMERA] IPC2_Initialize вернул код {base_result}")
                 return False

            # Проверим, предоставлен ли путь к конфигурации
            if config_path:
                 if not os.path.exists(config_path):
                      print(f"[CAMERA] Файл конфигурации не найден: {config_path}")
                      return False
                 config_path_bytes = config_path.encode('utf-8')
                 init_result = self.dll.IPC2_Init(self._cam_index, config_path_bytes)
                 if init_result != 0:
                      print(f"[CAMERA] IPC2_Init вернул код {init_result}")
                      # Можно ли продолжать без конфига? Зависит от DLL.
                      # Для примера, пусть будет критично.
                      return False
            else:
                 print("[CAMERA] Путь к конфигурации не предоставлен. Пропуск IPC2_Init.")

            # Запуск камеры
            run_result = self.dll.IPC2_Run(self._cam_index)
            if run_result != 0:
                print(f"[CAMERA] IPC2_Run вернул код {run_result}")
                return False

            # Получение реальных параметров видео
            self._get_actual_video_format()
            
            print(f"[CAMERA] Камера инициализирована: {self.frame_width}×{self.frame_height}, глубина: {self.frame_depth * 8}-bit")
            self._is_initialized = True
            return True
            
        except Exception as e:
            print(f"[CAMERA] Исключение при инициализации: {e}")
            self._is_initialized = False
            return False

    def _get_actual_video_format(self):
        """Получает фактический формат кадра."""
        try:
            width = c_int()
            height = c_int()
            depth = c_int()
            result = self.dll.IPC2_GetFrameConfig(self._cam_index, ctypes.byref(width), ctypes.byref(height), ctypes.byref(depth))
            if result == 0:
                self.frame_width = width.value
                self.frame_height = height.value
                # depth возвращается в битах, преобразуем в байтах на пиксель
                self.frame_depth = depth.value // 8 
                print(f"[CAMERA] Получен формат кадра: {self.frame_width}×{self.frame_height}, {depth.value}-bit")
            else:
                print(f"[CAMERA] GetFrameConfig вернул {result}, используются значения по умолчанию")
        except Exception as e:
            print(f"[CAMERA] Ошибка получения формата кадра: {e}")

    def is_initialized(self) -> bool:
        """Проверяет, инициализирована ли камера."""
        return self._is_initialized

    def get_frame(self, timeout_ms: int = 500) -> Optional[np.ndarray]:
        """
        Получает один кадр от камеры.
        Возвращает numpy массив формы (height, width) с dtype=np.uint16.
        """
        if not self._is_initialized:
            print("[CAMERA] Камера не инициализирована")
            return None
            
        try:
            buffer_size = self.frame_width * self.frame_height
            # Создаем буфер для кадра как массив ushort
            frame_buffer_type = c_ushort * buffer_size
            frame_buffer = frame_buffer_type()
            
            metadata = FrameMetadata()
            
            result = self.dll.IPC2_GetFrame(
                self._cam_index, 
                timeout_ms, 
                frame_buffer, 
                buffer_size * ctypes.sizeof(c_ushort), 
                ctypes.byref(metadata)
            )
            
            if result == 0: # Успех
                # Преобразуем в numpy массив
                # frame_buffer[:] создаёт копию данных
                frame_array = np.frombuffer(frame_buffer, dtype=np.uint16)
                # Изменяем форму массива
                frame_array = frame_array.reshape((self.frame_height, self.frame_width))
                return frame_array.copy() # Возвращаем копию
            elif result == -2: # Timeout
                print(f"[CAMERA] Таймаут получения кадра ({timeout_ms} мс)")
                return None
            else:
                print(f"[CAMERA] Ошибка получения кадра, код: {result}")
                return None
        except Exception as e:
            print(f"[CAMERA] Исключение при получении кадра: {e}")
            return None

    def set_emissivity(self, emissivity: float) -> bool:
        """Устанавливает значение эмиссивности."""
        if not self._is_initialized: 
            print("[CAMERA] Камера не инициализирована")
            return False
        try:
            result = self.dll.IPC2_SetFixedEmissivity(self._cam_index, c_float(emissivity))
            success = result == 0
            if success:
                print(f"[CAMERA] Эмиссивность установлена: {emissivity:.3f}")
            else:
                print(f"[CAMERA] Ошибка установки эмиссивности, код: {result}")
            return success
        except Exception as e:
            print(f"[CAMERA] Ошибка установки эмиссивности: {e}")
            return False

    def set_ambient_temp(self, temp: float) -> bool:
        """Устанавливает температуру окружающей среды."""
        if not self._is_initialized: 
            print("[CAMERA] Камера не инициализирована")
            return False
        try:
            result = self.dll.IPC2_SetFixedTempAmbient(self._cam_index, c_float(temp))
            success = result == 0
            if success:
                print(f"[CAMERA] Температура окружающей среды установлена: {temp:.1f}°C")
            else:
                print(f"[CAMERA] Ошибка установки температуры, код: {result}")
            return success
        except Exception as e:
            print(f"[CAMERA] Ошибка установки температуры: {e}")
            return False

    def set_high_precision_mode(self, enabled: bool) -> bool:
        """Включает/выключает режим высокой точности."""
        if not self._is_initialized: 
            print("[CAMERA] Камера не инициализирована")
            return False
        try:
            # Используем IPC2_SetParameter для установки режима
            # В C# это делалось через IPC2Extensions.SetHighPrecisionMode
            # Предполагаем, что параметр называется "HighPrecision"
            param_name = b"HighPrecision"
            value = 1 if enabled else 0
            result = self.dll.IPC2_SetParameter(self._cam_index, param_name, c_int(value))
            success = result == 0
            mode_str = "включен" if enabled else "выключен"
            if success:
                print(f"[CAMERA] Режим высокой точности {mode_str}")
            else:
                print(f"[CAMERA] Ошибка установки режима высокой точности, код: {result}")
            return success
        except Exception as e:
            print(f"[CAMERA] Ошибка установки режима высокой точности: {e}")
            return False

    def get_chip_temperature(self) -> Optional[float]:
        """Получает температуру чипа камеры."""
        if not self._is_initialized:
            print("[CAMERA] Камера не инициализирована")
            return None
        try:
            temp = self.dll.IPC2_GetTempChip(self._cam_index)
            return float(temp)
        except Exception as e:
            print(f"[CAMERA] Ошибка получения температуры чипа: {e}")
            return None

    def get_camera_info(self) -> str:
        """Получает информацию о камере."""
        if not self._is_initialized:
            return "Camera not initialized"
        try:
            serial = self.dll.IPC2_GetSerialNumber(self._cam_index)
            fw_msp = self.dll.IPC2_GetFirmware_MSP(self._cam_index)
            fw_cypress = self.dll.IPC2_GetFirmware_Cypress(self._cam_index)
            return f"Optris PI 640, S/N: {serial}, FW: MSP={fw_msp}, Cypress={fw_cypress}"
        except Exception as e:
            print(f"[CAMERA] Ошибка получения информации о камере: {e}")
            return "Camera info unavailable"

    def release(self):
        """Освобождает ресурсы камеры."""
        if self._is_initialized:
            try:
                result = self.dll.IPC2_Release(self._cam_index)
                if result == 0:
                    print("[CAMERA] Ресурсы камеры освобождены")
                else:
                    print(f"[CAMERA] Ошибка освобождения ресурсов, код: {result}")
            except Exception as e:
                print(f"[CAMERA] Исключение при освобождении ресурсов: {e}")
            finally:
                self._is_initialized = False

    def __del__(self):
        """Деструктор для автоматического освобождения ресурсов."""
        self.release()

# --- Пример использования (для тестирования) ---
if __name__ == "__main__":
    # Этот блок будет выполнен только при прямом запуске этого файла
    try:
        wrapper = OptrisWrapper()
        if wrapper.initialize():
            print("Инициализация успешна")
            print(wrapper.get_camera_info())
            print(f"Chip Temp: {wrapper.get_chip_temperature():.2f}°C")
            
            # Настройка параметров
            wrapper.set_emissivity(0.95)
            wrapper.set_ambient_temp(23.0)
            wrapper.set_high_precision_mode(True)
            
            # Получение кадра
            frame = wrapper.get_frame(timeout_ms=1000)
            if frame is not None:
                print(f"Получен кадр, форма: {frame.shape}, dtype: {frame.dtype}")
                # Простой пример: найти min/max
                min_val = np.min(frame)
                max_val = np.max(frame)
                print(f"Min ADU: {min_val}")
                print(f"Max ADU: {max_val}")
                # Конвертация в температуру (пример, коэффициент нужно уточнить)
                # scale = 0.01 # Примерный коэффициент
                # print(f"Min T: {min_val * scale:.2f} °C")
                # print(f"Max T: {max_val * scale:.2f} °C")
            else:
                print("Не удалось получить кадр")
                
            # Освобождение ресурсов
            wrapper.release()
        else:
            print("Ошибка инициализации")
    except Exception as e:
        print(f"Ошибка: {e}")
