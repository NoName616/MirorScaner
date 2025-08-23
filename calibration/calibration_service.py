# src/camera/calibration_service.py
"""
Сервис для управления процессом калибровки камеры.
"""
from typing import List, Optional, Callable, Tuple, Dict, Any
import numpy as np
from scipy.spatial.distance import cdist
import cv2 # Для более сложных преобразований, если понадобится
from datetime import datetime
import json
import os

from calibration.calibration_data import CameraCalibrationData, CalibrationPoint, CalibrationMetadata
from camera.camera_service import CameraService
from utils.logger import DataLogger, LogCategory
from utils.exceptions import CalibrationServiceException, CalibrationException


class CalibrationService:
    """
    Сервис для управления процессом калибровки камеры.
    """
    def __init__(self, camera_service: CameraService, logger: DataLogger, 
                 calibration_file_path: str = "calibration_data.json"):
        self._camera_service = camera_service
        self._logger = logger
        self._calibration_file_path = calibration_file_path
        
        self._calibration_data = CameraCalibrationData()
        self._is_calibrating = False
        
        # Коэффициенты для преобразования координат (простая линейная модель)
        self._scale_x: float = 1.0
        self._scale_y: float = 1.0
        self._offset_x: float = 0.0
        self._offset_y: float = 0.0
        self._is_calibrated: bool = False
        
        # Матрицы преобразования OpenCV (более сложная модель)
        self._homography_matrix: Optional[np.ndarray] = None # 3x3
        self._use_homography: bool = False # Флаг для переключения между моделями

        # Callbacks
        self.on_calibration_started: Optional[Callable[[], None]] = None
        self.on_calibration_point_added: Optional[Callable[[CalibrationPoint], None]] = None
        self.on_calibration_finished: Optional[Callable[[], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None

    def get_calibration_data(self) -> CameraCalibrationData:
        """Возвращает текущие данные калибровки."""
        return self._calibration_data

    def set_calibration_data(self, data: CameraCalibrationData) -> None:
        """
        Sets the current calibration data.

        Parameters:
            data: A ``CameraCalibrationData`` instance containing calibration points,
                  metadata and camera position.
        """
        self._calibration_data = data


    def is_calibrated(self) -> bool:
        """Проверяет, была ли выполнена калибровка."""
        # В Python проверяем по флагу и наличию точек/матрицы
        has_points = len(self._calibration_data.points) > 0
        is_calculated = self._is_calibrated or (self._use_homography and self._homography_matrix is not None)
        return has_points and is_calculated

    def is_calibrating(self) -> bool:
        """Проверяет, идет ли процесс калибровки."""
        return self._is_calibrating

    def get_calibration_file_path(self) -> str:
        """Возвращает путь к файлу калибровки."""
        return self._calibration_file_path

    def set_camera_position(self, x_offset_mm: float, y_offset_mm: float, z_distance_mm: float):
        """Устанавливает физическое положение камеры."""
        self._calibration_data.camera_position.x_offset_mm = x_offset_mm
        self._calibration_data.camera_position.y_offset_mm = y_offset_mm
        self._calibration_data.camera_position.z_distance_mm = z_distance_mm
        self._logger.log_info(
            LogCategory.CALIBRATION,
            f"Установлено физическое положение камеры: X={x_offset_mm:.2f}, "
            f"Y={y_offset_mm:.2f}, Z={z_distance_mm:.2f}"
        )

    def start_calibration(self, sample_radius_mm: Optional[float] = None, description: str = ""):
        """
        Начинает новый процесс калибровки.
        """
        if self._is_calibrating:
            raise CalibrationServiceException("Калибровка уже идет")
            
        self._is_calibrating = True
        self._calibration_data = CameraCalibrationData()
        self._calibration_data.metadata.sample_radius_mm = sample_radius_mm
        self._calibration_data.metadata.description = description
        # Обновляем дату создания
        self._calibration_data.metadata.created_at = datetime.now().isoformat()
        
        self._logger.log_info(LogCategory.CALIBRATION, "Начало нового процесса калибровки")
        if self.on_calibration_started:
            self.on_calibration_started()

    def add_calibration_point(self, point: CalibrationPoint) -> bool:
        """
        Добавляет точку калибровки.
        """
        if not self._is_calibrating:
            raise CalibrationServiceException("Калибровка не начата")
            
        self._calibration_data.add_point(point)
        
        self._logger.log_info(
            LogCategory.CALIBRATION, 
            f"Добавлена точка калибровки: {point}"
        )
        if self.on_calibration_point_added:
            self.on_calibration_point_added(point)
        return True

    # --- Методы для простого линейного преобразования ---
    def calculate_transformation_simple(self) -> bool:
        """
        Рассчитывает простые коэффициенты преобразования.
        Требует минимум 3 точки.
        """
        points = self._calibration_data.points
        if len(points) < 3:
            self._logger.log_error(
                LogCategory.CALIBRATION, 
                f"Недостаточно точек для расчета калибровки: {len(points)}/3"
            )
            return False

        try:
            self._logger.log_info(
                LogCategory.CALIBRATION, 
                f"Расчет простой калибровки на основе {len(points)} точек..."
            )
            
            # --- Простая линейная модель ---
            # Предполагаем, что world_point это (radius_mm, angle_deg)
            # и image_point это (x_px, y_px)
            
            # 1. Рассчитываем смещение (пример: центр изображения или среднее)
            img_points = np.array([p.image_point for p in points], dtype=np.float32)
            # world_points_rad = np.array([(p.world_point[0], np.deg2rad(p.world_point[1])) for p in points], dtype=np.float32)
            world_points = np.array([p.world_point for p in points], dtype=np.float32)
            
            # Центр в пикселях (среднее)
            self._offset_x = float(np.mean(img_points[:, 0]))
            self._offset_y = float(np.mean(img_points[:, 1]))
            
            # 2. Рассчитываем масштаб
            # Это упрощенный пример. В реальности масштаб зависит от Z и угла.
            # Для радиуса: px_per_mm = delta_px_radius / delta_mm_radius
            # Для угла: px_per_deg = delta_px_angle / delta_deg_angle
            
            if len(points) >= 2:
                # Берем две точки для расчета масштаба
                p1, p2 = points[0], points[1]
                delta_img = np.sqrt((p1.image_point[0] - p2.image_point[0])**2 + 
                                   (p1.image_point[1] - p2.image_point[1])**2)
                delta_world_r = abs(p1.world_point[0] - p2.world_point[0])
                delta_world_a = abs(p1.world_point[1] - p2.world_point[1])
                
                if delta_world_r > 1e-6: # Избегаем деления на ноль
                    self._scale_x = delta_img / delta_world_r # Примерный масштаб
                else:
                    self._scale_x = 1.0
                    
                if delta_world_a > 1e-6:
                    self._scale_y = delta_img / delta_world_a # Примерный масштаб
                else:
                    self._scale_y = 1.0
            else:
                self._scale_x = 1.0
                self._scale_y = 1.0

            self._is_calibrated = True
            self._use_homography = False
            self._homography_matrix = None
            
            self._logger.log_info(
                LogCategory.CALIBRATION,
                f"Простая калибровка рассчитана: "
                f"scaleX={self._scale_x:.4f}, scaleY={self._scale_y:.4f}, "
                f"offset=({self._offset_x:.2f}, {self._offset_y:.2f})"
            )
            return True
            
        except Exception as e:
            self._logger.log_error(
                LogCategory.CALIBRATION, 
                f"Ошибка расчета простой калибровки: {e}"
            )
            return False

    # --- Методы для преобразования на основе гомографии OpenCV ---
    def calculate_transformation_homography(self) -> bool:
        """
        Рассчитывает матрицу гомографии OpenCV.
        Требует минимум 4 точки.
        """
        points = self._calibration_data.points
        if len(points) < 4:
            self._logger.log_warn(
                LogCategory.CALIBRATION, 
                f"Недостаточно точек для гомографии: {len(points)}/4. Используйте простую калибровку."
            )
            return False

        try:
            self._logger.log_info(
                LogCategory.CALIBRATION, 
                f"Расчет калибровки (гомография) на основе {len(points)} точек..."
            )
            
            # Подготавливаем точки
            img_points = np.array([p.image_point for p in points], dtype=np.float32)
            # Для гомографии world_points тоже должны быть в пиксельных координатах
            # или мы должны определить их на плоскости образца.
            # Предположим, что world_point это (x_mm, y_mm) на плоскости образца.
            # Нам нужно отобразить это в "виртуальные пиксели" для гомографии.
            # Для простоты, будем считать 1мм = 1 "виртуальный пиксель" с центром в (0,0)
            world_points_mm = np.array([p.world_point for p in points], dtype=np.float32)
            
            # Вычисляем гомографию
            # cv2.findHomography(srcPoints (world), dstPoints (image))
            matrix, status = cv2.findHomography(world_points_mm, img_points, cv2.RANSAC, 5.0)
            
            if matrix is not None:
                self._homography_matrix = matrix
                self._use_homography = True
                self._is_calibrated = True
                # Сбрасываем простые коэффициенты
                self._scale_x = self._scale_y = 1.0
                self._offset_x = self._offset_y = 0.0
                
                inliers = np.sum(status)
                self._logger.log_info(
                    LogCategory.CALIBRATION,
                    f"Гомография рассчитана. Матрица 3x3. Inliers: {inliers}/{len(points)}"
                )
                return True
            else:
                self._logger.log_error(
                    LogCategory.CALIBRATION, 
                    "Не удалось рассчитать матрицу гомографии"
                )
                return False
                
        except ImportError:
            self._logger.log_error(
                LogCategory.CALIBRATION, 
                "OpenCV не найден. Установите opencv-python для гомографии."
            )
            return False
        except Exception as e:
            self._logger.log_error(
                LogCategory.CALIBRATION, 
                f"Ошибка расчета гомографии: {e}"
            )
            return False

    def finish_calibration(self, use_homography: bool = False) -> bool:
        """
        Завершает процесс калибровки и рассчитывает преобразование.
        """
        if not self._is_calibrating:
            raise CalibrationServiceException("Калибровка не начата")
            
        point_count = self._calibration_data.get_point_count()
        min_points = 4 if use_homography else 3
        if point_count < min_points:
            error_msg = f"Недостаточно точек для калибровки: {point_count} < {min_points}"
            self._logger.log_error(LogCategory.CALIBRATION, error_msg)
            if self.on_error:
                self.on_error(error_msg)
            # Не останавливаем калибровку, пусть пользователь решает
            return False
            
        self._is_calibrating = False
        
        # Выполняем расчет
        success = False
        if use_homography:
            success = self.calculate_transformation_homography()
        else:
            success = self.calculate_transformation_simple()
            
        if success:
            # Обновляем метаданные
            self._calibration_data.metadata.created_at = datetime.now().isoformat()
            import getpass
            self._calibration_data.metadata.calibrated_by = getpass.getuser()
            self._calibration_data.metadata.points_used = point_count
            method = "Homography (OpenCV)" if use_homography else "Simple Linear"
            self._calibration_data.metadata.calibration_method = method
            self._calibration_data.metadata.description = \
                f"Калибровка выполнена с {point_count} точками методом {method}"
            
            self._logger.log_info(LogCategory.CALIBRATION, 
                f"Калибровка завершена. Добавлено точек: {point_count}")
            if self.on_calibration_finished:
                self.on_calibration_finished()
        else:
            error_msg = "Не удалось рассчитать калибровочные коэффициенты"
            self._logger.log_error(LogCategory.CALIBRATION, error_msg)
            if self.on_error:
                self.on_error(error_msg)
                
        return success

    def cancel_calibration(self):
        """
        Отменяет текущий процесс калибровки.
        """
        if self._is_calibrating:
            self._is_calibrating = False
            self._calibration_data.clear_points()
            self._logger.log_info(LogCategory.CALIBRATION, "Калибровка отменена")

    # --- Методы преобразования координат ---
    def world_to_image(self, world_x_mm: float, world_y_mm_or_angle_deg: float) -> Optional[Tuple[int, int]]:
        """
        Преобразует физические координаты в координаты изображения.
        
        Для простой калибровки:
            world_x_mm = radius_mm
            world_y_mm_or_angle_deg = angle_deg
        
        Для гомографии:
            world_x_mm = x_mm на плоскости образца
            world_y_mm_or_angle_deg = y_mm на плоскости образца
        """
        if not self.is_calibrated():
            self._logger.log_warn(LogCategory.CALIBRATION, 
                "Попытка преобразования координат без калибровки")
            return None

        try:
            if self._use_homography and self._homography_matrix is not None:
                # Используем гомографию
                # src = world point (x_mm, y_mm)
                src_point = np.array([[[world_x_mm, world_y_mm_or_angle_deg]]], dtype=np.float32)
                dst_point = cv2.perspectiveTransform(src_point, self._homography_matrix)
                x_px = int(round(dst_point[0][0][0]))
                y_px = int(round(dst_point[0][0][1]))
                return (x_px, y_px)
            else:
                # Используем простую линейную модель
                # Эта модель является приближением и может быть неточной
                # world_x_mm is radius_mm
                # world_y_mm_or_angle_deg is angle_deg
                radius_mm = world_x_mm
                angle_deg = world_y_mm_or_angle_deg
                
                # Преобразование полярных координат в декартовы (относительно центра)
                angle_rad = np.deg2rad(angle_deg)
                x_rel_mm = radius_mm * np.cos(angle_rad)
                y_rel_mm = radius_mm * np.sin(angle_rad)
                
                # Применяем масштаб и смещение
                # Это очень упрощенная модель, на практике нужно учитывать перспективу
                x_px = int(round(self._offset_x + x_rel_mm * self._scale_x))
                y_px = int(round(self._offset_y + y_rel_mm * self._scale_y))
                return (x_px, y_px)
                
        except Exception as e:
            self._logger.log_error(LogCategory.CALIBRATION, 
                f"Ошибка преобразования world->image: {e}")
            return None

    def image_to_world(self, image_x_px: int, image_y_px: int) -> Optional[Tuple[float, float]]:
        """
        Преобразует координаты изображения в физические координаты.
        Возвращает (radius_mm, angle_deg) для простой калибровки.
        Возвращает (x_mm, y_mm) для гомографии.
        """
        if not self.is_calibrated():
            self._logger.log_warn(LogCategory.CALIBRATION, 
                "Попытка обратного преобразования координат без калибровки")
            return None

        try:
            if self._use_homography and self._homography_matrix is not None:
                # Используем обратную гомографию
                inv_matrix = np.linalg.inv(self._homography_matrix)
                src_point = np.array([[[image_x_px, image_y_px]]], dtype=np.float32)
                dst_point = cv2.perspectiveTransform(src_point, inv_matrix)
                x_mm = float(dst_point[0][0][0])
                y_mm = float(dst_point[0][0][1])
                return (x_mm, y_mm)
            else:
                # Используем простую линейную модель (обратное преобразование)
                # Это очень упрощенная модель
                dx_px = image_x_px - self._offset_x
                dy_px = image_y_px - self._offset_y
                
                if abs(self._scale_x) > 1e-6 and abs(self._scale_y) > 1e-6:
                    # Переводим в мм (приблизительно)
                    x_rel_mm = dx_px / self._scale_x
                    y_rel_mm = dy_px / self._scale_y
                    
                    # Переводим декартовы в полярные
                    radius_mm = np.sqrt(x_rel_mm**2 + y_rel_mm**2)
                    angle_rad = np.arctan2(y_rel_mm, x_rel_mm)
                    angle_deg = np.rad2deg(angle_rad)
                    # Нормализация угла
                    if angle_deg < 0:
                        angle_deg += 360
                    return (float(radius_mm), float(angle_deg))
                else:
                    self._logger.log_warn(LogCategory.CALIBRATION, 
                        "Масштаб калибровки равен нулю")
                    return (0.0, 0.0)
                    
        except Exception as e:
            self._logger.log_error(LogCategory.CALIBRATION, 
                f"Ошибка преобразования image->world: {e}")
            return None

    # --- Методы сохранения/загрузки ---
    def save_calibration(self, file_path: Optional[str] = None) -> bool:
        """
        Сохраняет данные калибровки в файл.
        """
        try:
            path = file_path or self._calibration_file_path
            
            if not self._calibration_data.points:
                raise CalibrationException("Нет данных для сохранения")

            # Добавляем коэффициенты в метаданные для возможности восстановления
            extra_data = {
                "transformation": {
                    "is_calibrated": self._is_calibrated,
                    "use_homography": self._use_homography,
                    "scale_x": self._scale_x,
                    "scale_y": self._scale_y,
                    "offset_x": self._offset_x,
                    "offset_y": self._offset_y,
                }
            }
            if self._use_homography and self._homography_matrix is not None:
                extra_data["transformation"]["homography_matrix"] = self._homography_matrix.tolist()
            
            # Создаем словарь для сохранения
            data_to_save = self._calibration_data.to_dict()
            data_to_save.update(extra_data)
            
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, indent=4, ensure_ascii=False)
                
            self._logger.log_info(LogCategory.CALIBRATION, 
                f"Калибровка сохранена в {path}. Точек: {len(self._calibration_data.points)}")
            return True
            
        except Exception as e:
            error_msg = f"Ошибка сохранения калибровки в {path}: {e}"
            self._logger.log_error(LogCategory.CALIBRATION, error_msg)
            if self.on_error:
                self.on_error(f"Save error: {e}")
            return False

    def load_calibration(self, file_path: Optional[str] = None) -> bool:
        """
        Загружает данные калибровки из файла.
        """
        try:
            path = file_path or self._calibration_file_path
            
            if not os.path.exists(path):
                self._logger.log_warn(LogCategory.CALIBRATION, 
                    f"Файл калибровки не найден: {path}")
                raise FileNotFoundError(f"Файл калибровки не найден: {path}")

            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Создаем объект калибровки из данных
            self._calibration_data = CameraCalibrationData.from_dict(data)
            
            # Восстанавливаем коэффициенты преобразования, если они есть
            self._is_calibrated = False
            self._use_homography = False
            self._homography_matrix = None
            self._scale_x = self._scale_y = 1.0
            self._offset_x = self._offset_y = 0.0
            
            if "transformation" in data:
                trans_data = data["transformation"]
                self._is_calibrated = trans_data.get("is_calibrated", False)
                self._use_homography = trans_data.get("use_homography", False)
                self._scale_x = trans_data.get("scale_x", 1.0)
                self._scale_y = trans_data.get("scale_y", 1.0)
                self._offset_x = trans_data.get("offset_x", 0.0)
                self._offset_y = trans_data.get("offset_y", 0.0)
                
                if self._use_homography and "homography_matrix" in trans_data:
                    try:
                        matrix_list = trans_data["homography_matrix"]
                        self._homography_matrix = np.array(matrix_list, dtype=np.float32)
                    except Exception as e:
                        self._logger.log_warn(LogCategory.CALIBRATION, 
                            f"Не удалось восстановить матрицу гомографии: {e}")
                        self._homography_matrix = None
            
            self._logger.log_info(LogCategory.CALIBRATION,
                f"Калибровка загружена из {path}. Точек: {len(self._calibration_data.points)}")
            return True
            
        except FileNotFoundError:
            # Пробрасываем исключение, чтобы вызывающая сторона могла обработать его специально
            raise
        except Exception as e:
            error_msg = f"Ошибка загрузки калибровки из {path}: {e}"
            self._logger.log_error(LogCategory.CALIBRATION, error_msg)
            if self.on_error:
                self.on_error(f"Load error: {e}")
            return False
