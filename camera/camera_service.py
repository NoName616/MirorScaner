import numpy as np
import threading
import time
from typing import Optional, Callable, Tuple
from camera.optris_wrapper import OptrisWrapper, OptrisWrapperException
from utils.logger import DataLogger, LogCategory

class CameraException(Exception):
    """Исключение для ошибок камеры."""
    pass

class CameraService:
    def __init__(self, logger: DataLogger):
        self._logger = logger
        self._wrapper: Optional[OptrisWrapper] = None
        self._is_initialized = False
        self._grab_thread: Optional[threading.Thread] = None
        self._running = False
        self._current_frame: Optional[np.ndarray] = None
        self._frame_lock = threading.Lock()

        # Параметры калибровки
        self._emissivity = 0.95
        self._ambient_temp = 23.0
        self._high_precision_mode = False

        # События
        self.on_frame_ready: Optional[Callable[[np.ndarray], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None

    def connect(self, config_path: Optional[str] = "pi640_config.xml") -> bool:
        if self._is_initialized:
            self._logger.log_warn(LogCategory.CAMERA, "Камера уже инициализирована")
            return True

        try:
            self._logger.log_info(LogCategory.CAMERA, f"Инициализация камеры с конфигом: {config_path}")
            self._wrapper = OptrisWrapper()
            if not self._wrapper.initialize(config_path):
                raise CameraException("Ошибка инициализации камеры через wrapper")

            self._apply_calibration_settings()
            time.sleep(0.6)

            self._is_initialized = True
            self._logger.log_info(LogCategory.CAMERA,
                f"Камера подключена: {self._wrapper.frame_width}×{self._wrapper.frame_height}, "
                f"глубина: {self._wrapper.frame_depth * 8}-bit")
            return True
        except Exception as e:
            self._is_initialized = False
            error_msg = f"Ошибка подключения камеры: {e}"
            self._logger.log_error(LogCategory.CAMERA, error_msg)
            if self.on_error:
                self.on_error(f"Camera error: {e}")
            return False

    def disconnect(self):
        self._running = False
        if self._grab_thread and self._grab_thread.is_alive():
            self._grab_thread.join(timeout=2.0)

        if self._wrapper:
            self._wrapper.release()
            self._wrapper = None

        self._is_initialized = False
        self._logger.log_info(LogCategory.CAMERA, "Камера отключена")

    def is_connected(self) -> bool:
        return self._is_initialized and self._wrapper is not None

    def get_camera_info(self) -> str:
        if self.is_connected() and self._wrapper:
            return self._wrapper.get_camera_info()
        return "Camera not connected"

    def get_chip_temperature(self) -> Optional[float]:
        if self.is_connected() and self._wrapper:
            return self._wrapper.get_chip_temperature()
        return None

    def _apply_calibration_settings(self):
        if not self.is_connected():
            return
        try:
            success1 = self._wrapper.set_emissivity(self._emissivity)
            success2 = self._wrapper.set_ambient_temp(self._ambient_temp)
            success3 = self._wrapper.set_high_precision_mode(self._high_precision_mode)
            if success1 and success2 and success3:
                self._logger.log_info(LogCategory.CAMERA,
                    f"Параметры камеры применены: ε={self._emissivity:.2f}, "
                    f"Tₐ={self._ambient_temp:.1f}°C, HP={self._high_precision_mode}")
            else:
                self._logger.log_warn(LogCategory.CAMERA, "Не все параметры камеры были успешно применены")
        except Exception as e:
            error_msg = f"Ошибка настройки камеры: {e}"
            self._logger.log_error(LogCategory.CAMERA, error_msg)
            if self.on_error:
                self.on_error(f"Camera config error: {e}")

    def get_emissivity(self) -> float:
        return self._emissivity

    def set_emissivity(self, value: float):
        if 0.01 <= value <= 1.0:
            self._emissivity = value
            self._apply_calibration_settings()
        else:
            raise ValueError("Эмиссивность должна быть в диапазоне 0.01 - 1.0")

    def get_ambient_temp(self) -> float:
        return self._ambient_temp

    def set_ambient_temp(self, value: float):
        self._ambient_temp = value
        self._apply_calibration_settings()

    def get_high_precision_mode(self) -> bool:
        return self._high_precision_mode

    def set_high_precision_mode(self, enabled: bool):
        self._high_precision_mode = enabled
        self._apply_calibration_settings()

    def get_single_frame(self, timeout_ms: int = 500) -> Optional[np.ndarray]:
        if not self.is_connected():
            raise CameraException("Камера не подключена")
        return self._wrapper.get_frame(timeout_ms)

    def start_live_view(self):
        if not self.is_connected():
            raise CameraException("Камера не подключена")
        if self._running:
            self._logger.log_warn(LogCategory.CAMERA, "Поток захвата уже запущен")
            return

        self._running = True
        self._grab_thread = threading.Thread(target=self._grab_loop, daemon=True)
        self._grab_thread.name = "CameraGrabber"
        self._grab_thread.start()
        self._logger.log_info(LogCategory.CAMERA, "Поток захвата кадров запущен")

    def stop_live_view(self):
        self._running = False
        if self._grab_thread and self._grab_thread.is_alive():
            self._grab_thread.join(timeout=2.0)
        self._logger.log_info(LogCategory.CAMERA, "Поток захвата кадров остановлен")

    def _grab_loop(self):
        error_count = 0
        max_errors = 10

        while self._running and self.is_connected():
            try:
                frame = self._wrapper.get_frame(timeout_ms=500)
                if frame is not None:
                    error_count = 0
                    with self._frame_lock:
                        self._current_frame = frame.copy()
                    if self.on_frame_ready:
                        self.on_frame_ready(frame.copy())
                else:
                    error_count += 1
                    if error_count >= max_errors:
                        msg = f"Превышено максимальное количество ошибок захвата ({max_errors})"
                        self._logger.log_error(LogCategory.CAMERA, msg)
                        if self.on_error:
                            self.on_error(msg)
                        break
            except Exception as e:
                error_count += 1
                msg = f"Ошибка в потоке захвата: {e}"
                self._logger.log_error(LogCategory.CAMERA, msg)
                if self.on_error:
                    self.on_error(msg)
                if error_count >= max_errors:
                    break
                time.sleep(0.1)

    def get_last_frame(self) -> Optional[np.ndarray]:
        with self._frame_lock:
            return self._current_frame.copy() if self._current_frame is not None else None

    def get_min_max_temperature_in_roi(self, frame: np.ndarray,
                                       roi: Optional[Tuple[int, int, int, int]] = None) -> Tuple[float, float]:
        if frame is None:
            raise CameraException("Кадр не предоставлен")
        try:
            if roi is not None:
                x, y, w, h = roi
                if (x < 0 or y < 0 or x + w > frame.shape[1] or y + h > frame.shape[0] or w <= 0 or h <= 0):
                    raise ValueError("Некорректные координаты ROI")
                roi_frame = frame[y:y + h, x:x + w]
            else:
                roi_frame = frame
            return float(np.min(roi_frame)), float(np.max(roi_frame))
        except Exception as e:
            raise CameraException(f"Ошибка анализа кадра: {e}") from e

    def adu_to_celsius(self, adu_value: float, scale: float = 0.01) -> float:
        return adu_value * scale

    def capture_for_analysis(self, analysis_service):
        try:
            frame = self.get_single_frame()
            return analysis_service.process_frame(frame)
        except Exception as e:
            self._logger.log_error(LogCategory.CAMERA, f"Ошибка при анализе кадра: {e}")
            return []

    def capture_and_record(self, analysis_service):
        try:
            frame = self.get_single_frame()
            analysis_service.process_frame(frame)
        except Exception as e:
            self._logger.log_error(LogCategory.CAMERA, f"Ошибка при записи анализа: {e}")
