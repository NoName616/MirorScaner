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
    # Use WinDLL on Windows to ensure correct stdcall calling convention
    return ctypes.WinDLL(dll_path)

class OptrisWrapperException(Exception):
    """Исключение для ошибок обёртки камеры."""
    pass

class OptrisWrapper:
    """
    Обёртка над функциями библиотеки ImagerIPC2x64.dll.
    """
    def __init__(self, dll_path: str = None):
        # Load the SDK DLL. Use WinDLL to respect stdcall on 64‑bit Windows.
        self.dll = load_optris_dll(dll_path)
        self._is_initialized = False
        self._cam_index = 0
        self.frame_width = 640
        self.frame_height = 480
        self.frame_depth = 2 # 16-bit (2 bytes per pixel)
        
        # --- Определение сигнатур функций ---
        # Экспортированные функции Connect SDK имеют имена SetImagerIPCCount, InitImagerIPC, RunImagerIPC и т. д.
        # См. ImagerIPC2.h для корректных аргументов и возвращаемых типов.
        # HRESULT рассматриваем как 32‑битный int (0 = OK).

        # HRESULT SetImagerIPCCount(WORD count)
        self.dll.SetImagerIPCCount.argtypes = [c_ushort]
        self.dll.SetImagerIPCCount.restype = c_int

        # HRESULT InitImagerIPC(WORD index)
        self.dll.InitImagerIPC.argtypes = [c_ushort]
        self.dll.InitImagerIPC.restype = c_int

        # HRESULT RunImagerIPC(WORD index)
        self.dll.RunImagerIPC.argtypes = [c_ushort]
        self.dll.RunImagerIPC.restype = c_int

        # HRESULT ReleaseImagerIPC(WORD index)
        self.dll.ReleaseImagerIPC.argtypes = [c_ushort]
        self.dll.ReleaseImagerIPC.restype = c_int

        # HRESULT GetFrameConfig(WORD index, int* width, int* height, int* depth)
        self.dll.GetFrameConfig.argtypes = [c_ushort, POINTER(c_int), POINTER(c_int), POINTER(c_int)]
        self.dll.GetFrameConfig.restype = c_int

        # HRESULT GetFrame(WORD index, WORD timeout, void* buffer, uint size, FrameMetadata* metadata)
        self.dll.GetFrame.argtypes = [c_ushort, c_ushort, ctypes.POINTER(c_ushort), c_uint, POINTER(FrameMetadata)]
        self.dll.GetFrame.restype = c_int

        # float SetFixedEmissivity(WORD index, float emissivity)
        self.dll.SetFixedEmissivity.argtypes = [c_ushort, c_float]
        self.dll.SetFixedEmissivity.restype = c_float

        # float SetFixedTempAmbient(WORD index, float temp)
        self.dll.SetFixedTempAmbient.argtypes = [c_ushort, c_float]
        self.dll.SetFixedTempAmbient.restype = c_float

        # HRESULT SetParameter(WORD index, char* name, int value)
        self.dll.SetParameter.argtypes = [c_ushort, c_char_p, c_int]
        self.dll.SetParameter.restype = c_int

        # float GetTempChip(WORD index)
        self.dll.GetTempChip.argtypes = [c_ushort]
        self.dll.GetTempChip.restype = c_float

        # unsigned int GetSerialNumber(WORD index)
        self.dll.GetSerialNumber.argtypes = [c_ushort]
        self.dll.GetSerialNumber.restype = c_uint

        # unsigned short GetFirmware_MSP(WORD index), GetFirmware_Cypress
        self.dll.GetFirmware_MSP.argtypes = [c_ushort]
        self.dll.GetFirmware_MSP.restype = c_ushort
        self.dll.GetFirmware_Cypress.argtypes = [c_ushort]
        self.dll.GetFirmware_Cypress.restype = c_ushort

    def initialize(self, config_path: Optional[str] = None) -> bool:
        """Инициализирует камеру через Connect SDK.

        В отличие от старого IPC2 API, Connect SDK использует последовательность:
        SetImagerIPCCount → InitImagerIPC → RunImagerIPC. Путь к конфигурации
        здесь не передаётся; SDK самостоятельно подгружает параметры.
        """
        try:
            self._cam_index = 0
            # Устанавливаем количество камер (обычно 1)
            res = self.dll.SetImagerIPCCount(c_ushort(1))
            if res != 0:
                print(f"[CAMERA] SetImagerIPCCount вернул код {res}")
                return False
            # Инициализация камеры с индексом 0
            res = self.dll.InitImagerIPC(c_ushort(self._cam_index))
            if res != 0:
                print(f"[CAMERA] InitImagerIPC вернул код {res}")
                return False
            # Запуск захвата кадров
            res = self.dll.RunImagerIPC(c_ushort(self._cam_index))
            if res != 0:
                print(f"[CAMERA] RunImagerIPC вернул код {res}")
                return False
            # Запрос реальных параметров кадра
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
            result = self.dll.GetFrameConfig(c_ushort(self._cam_index), ctypes.byref(width), ctypes.byref(height), ctypes.byref(depth))
            if result == 0:
                self.frame_width = width.value
                self.frame_height = height.value
                # depth возвращается в битах; конвертируем в байты
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
            
            # Переводим timeout в тип WORD (ushort)
            timeout_word = c_ushort(max(0, min(0xFFFF, timeout_ms)))
            result = self.dll.GetFrame(
                c_ushort(self._cam_index),
                timeout_word,
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
            elif result == -2:  # Timeout
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
            # Функция SetFixedEmissivity возвращает фактическое значение эмиссивности как float
            returned = self.dll.SetFixedEmissivity(c_ushort(self._cam_index), c_float(emissivity))
            # Проверяем, совпадает ли возвращённое значение с заданным (с учётом допуска)
            if abs(returned - emissivity) < 1e-3:
                print(f"[CAMERA] Эмиссивность установлена: {emissivity:.3f}")
                return True
            else:
                print(f"[CAMERA] Возвращённое значение эмиссивности {returned:.3f} не совпадает с заданным {emissivity:.3f}")
                return False
        except Exception as e:
            print(f"[CAMERA] Ошибка установки эмиссивности: {e}")
            return False

    def set_ambient_temp(self, temp: float) -> bool:
        """Устанавливает температуру окружающей среды."""
        if not self._is_initialized: 
            print("[CAMERA] Камера не инициализирована")
            return False
        try:
            # Функция SetFixedTempAmbient возвращает установившееся значение температуры как float
            returned = self.dll.SetFixedTempAmbient(c_ushort(self._cam_index), c_float(temp))
            if abs(returned - temp) < 0.5:
                print(f"[CAMERA] Температура окружающей среды установлена: {temp:.1f}°C")
                return True
            else:
                print(f"[CAMERA] Возвращённая температура {returned:.1f}°C не совпадает с заданной {temp:.1f}°C")
                return False
        except Exception as e:
            print(f"[CAMERA] Ошибка установки температуры: {e}")
            return False

    def set_high_precision_mode(self, enabled: bool) -> bool:
        """Включает/выключает режим высокой точности."""
        if not self._is_initialized: 
            print("[CAMERA] Камера не инициализирована")
            return False
        try:
            # Используем SetParameter для установки режима высокой точности.
            param_name = b"HighPrecision"
            value = 1 if enabled else 0
            result = self.dll.SetParameter(c_ushort(self._cam_index), param_name, c_int(value))
            success = (result == 0)
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
            temp = self.dll.GetTempChip(c_ushort(self._cam_index))
            return float(temp)
        except Exception as e:
            print(f"[CAMERA] Ошибка получения температуры чипа: {e}")
            return None

    def get_camera_info(self) -> str:
        """Получает информацию о камере."""
        if not self._is_initialized:
            return "Camera not initialized"
        try:
            serial = self.dll.GetSerialNumber(c_ushort(self._cam_index))
            fw_msp = self.dll.GetFirmware_MSP(c_ushort(self._cam_index))
            fw_cypress = self.dll.GetFirmware_Cypress(c_ushort(self._cam_index))
            return f"Optris PI 640, S/N: {serial}, FW: MSP={fw_msp}, Cypress={fw_cypress}"
        except Exception as e:
            print(f"[CAMERA] Ошибка получения информации о камере: {e}")
            return "Camera info unavailable"

    def release(self):
        """Освобождает ресурсы камеры."""
        if self._is_initialized:
            try:
                result = self.dll.ReleaseImagerIPC(c_ushort(self._cam_index))
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
