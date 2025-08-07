# src/ui/calibration_window.py
"""
Окно калибровки камеры.
"""
import sys
import os
from typing import Optional, Tuple
import numpy as np

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout,
    QLabel, QPushButton, QMessageBox, QFileDialog, QStatusBar, QSizePolicy,
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsLineItem,
    QButtonGroup, QRadioButton, QInputDialog
)
from PyQt5.QtCore import Qt, QTimer, QRectF, QPointF, QPoint, pyqtSignal
from PyQt5.QtGui import QPixmap, QImage, QPainter, QPen, QColor, QFont, QMouseEvent, QWheelEvent

# Импорты из нашего проекта
from calibration.calibration_service import CalibrationService
from camera.camera_service import CameraService
from utils.logger import DataLogger, LogCategory
from utils.exceptions import CalibrationServiceException


class CalibrationGraphicsView(QGraphicsView):
    """
    Вид для отображения изображения с камеры и добавления точек калибровки.
    """
    # Сигнал, испускаемый при клике на изображении
    point_clicked = pyqtSignal(QPointF) # QPointF в координатах сцены

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        # Включаем интерактивность для получения событий мыши
        self.setInteractive(True)
        # Устанавливаем курсор крестик
        self.setCursor(Qt.CrossCursor)
        
        # Для отслеживания кликов
        self._scene_item: Optional[QGraphicsPixmapItem] = None

    def set_scene_item(self, item: QGraphicsPixmapItem):
        """Устанавливает QGraphicsPixmapItem, на который можно кликать."""
        self._scene_item = item

    def mousePressEvent(self, event: QMouseEvent):
        """Обработчик нажатия кнопки мыши."""
        if event.button() == Qt.LeftButton and self._scene_item:
            # Преобразуем позицию клика в координаты сцены
            scene_pos = self.mapToScene(event.pos())
            # Проверяем, попал ли клик в область изображения
            if self._scene_item.contains(self._scene_item.mapFromScene(scene_pos)):
                self.point_clicked.emit(scene_pos)
        super().mousePressEvent(event)

    def wheelEvent(self, event: QWheelEvent):
        """Обработчик прокрутки колеса мыши для зума."""
        zoom_in_factor = 1.25
        zoom_out_factor = 1 / zoom_in_factor

        # Получаем текущую позицию курсора в координатах сцены
        scene_pos = self.mapToScene(event.pos())

        # Вычисляем масштаб
        if event.angleDelta().y() > 0:
            zoom_factor = zoom_in_factor
        else:
            zoom_factor = zoom_out_factor

        # Применяем масштаб
        self.scale(zoom_factor, zoom_factor)

        # Получаем новую позицию курсора после масштабирования
        view_pos = event.pos()
        scene_pos_after_scale = self.mapToScene(view_pos)

        # Вычисляем разницу и корректируем центр вида, чтобы зум был "к курсору"
        delta = scene_pos_after_scale - scene_pos
        self.translate(delta.x(), delta.y())

        event.accept()


class CalibrationWindow(QMainWindow):
    """
    Окно калибровки камеры.
    """
    def __init__(self, calibration_service: CalibrationService, 
                 camera_service: CameraService, logger: DataLogger):
        super().__init__()
        # --- Сервисы ---
        self._calibration_service = calibration_service
        self._camera_service = camera_service
        self._logger = logger

        # --- Состояние ---
        self._is_live_view_running = False
        self._current_frame: Optional[np.ndarray] = None
        self._overlay_items = [] # Список QGraphicsItem для отображения точек/линий
        self._sample_radius_mm: float = 50.0  # Default, will prompt user

        # --- UI компоненты ---
        self._graphics_view: CalibrationGraphicsView
        self._scene: QGraphicsScene
        self._pixmap_item: QGraphicsPixmapItem
        self._btn_start: QPushButton
        self._btn_stop: QPushButton
        self._btn_add_point: QPushButton
        self._btn_save_calib: QPushButton
        self._btn_load_calib: QPushButton
        self._btn_run_calib: QPushButton
        self._lbl_status: QLabel
        self._status_bar: QStatusBar
        self._radio_group: QButtonGroup
        self._radio_center: QRadioButton
        self._radio_radius: QRadioButton
        self._radio_angle: QRadioButton

        # --- Таймеры ---
        self._live_view_timer: QTimer
        self._update_timer: QTimer

        # --- Инициализация ---
        self._setup_ui()
        self._setup_signals()
        self._setup_timers()
        self._update_ui_state()

        # Подписываемся на события от камеры
        self._camera_service.on_frame_ready = self._on_camera_frame_ready
        self._camera_service.on_error = self._on_camera_error

        # Prompt for sample radius
        self._prompt_sample_radius()
        # Начинаем новый процесс калибровки
        try:
            self._calibration_service.start_calibration(sample_radius_mm=self._sample_radius_mm)
        except CalibrationServiceException as e:
            self._logger.log_error(LogCategory.CALIBRATION, f"Ошибка начала калибровки: {e}")
            QMessageBox.critical(self, "Ошибка", f"Не удалось начать калибровку: {e}")

    def _prompt_sample_radius(self):
        """Prompt user for sample radius."""
        radius, ok = QInputDialog.getDouble(self, "Размер образца", "Введите радиус образца (мм, 10-100+):", 50.0, 10.0, 1000.0, 1)
        if ok:
            self._sample_radius_mm = radius
        else:
            self.close()  # Cancel calibration if no input

    def _setup_ui(self):
        """Настройка пользовательского интерфейса."""
        self.setWindowTitle("Мастер калибровки камеры - MirrorScan")
        self.resize(1000, 800) # Начальный размер
        self.setMinimumSize(950, 800) # Минимальный размер из C#
        self.setStyleSheet("background-color: #f0f0f0;")

        # Центральный виджет
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # --- Кнопки управления ---
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        
        self._btn_start = QPushButton("Старт")
        self._btn_stop = QPushButton("Стоп")
        self._btn_add_point = QPushButton("Добавить точку")
        self._btn_save_calib = QPushButton("Сохранить")
        self._btn_load_calib = QPushButton("Загрузить")
        self._btn_run_calib = QPushButton("Запустить калибровку")

        button_layout.addWidget(self._btn_start)
        button_layout.addWidget(self._btn_stop)
        button_layout.addWidget(self._btn_add_point)
        button_layout.addStretch()
        button_layout.addWidget(self._btn_save_calib)
        button_layout.addWidget(self._btn_load_calib)
        button_layout.addWidget(self._btn_run_calib)
        
        main_layout.addLayout(button_layout)

        # --- Выбор типа точки ---
        point_type_layout = QHBoxLayout()
        point_type_layout.addWidget(QLabel("Тип точки:"))
        
        self._radio_group = QButtonGroup(self)
        
        self._radio_center = QRadioButton("Центр (0,0°)")
        self._radio_radius = QRadioButton("Радиус")
        self._radio_angle = QRadioButton("Угол")
        
        self._radio_group.addButton(self._radio_center, 1)
        self._radio_group.addButton(self._radio_radius, 2)
        self._radio_group.addButton(self._radio_angle, 3)
        
        # По умолчанию выбран центр
        self._radio_center.setChecked(True)
        
        point_type_layout.addWidget(self._radio_center)
        point_type_layout.addWidget(self._radio_radius)
        point_type_layout.addWidget(self._radio_angle)
        point_type_layout.addStretch()
        
        main_layout.addLayout(point_type_layout)

        # --- Графическое представление ---
        self._graphics_view = CalibrationGraphicsView()
        self._graphics_view.setStyleSheet("background-color: black; border: 1px solid gray;") # Черный фон из C#
        self._graphics_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # Создаем сцену
        self._scene = QGraphicsScene(self._graphics_view)
        self._graphics_view.setScene(self._scene)
        
        # Создаем элемент для изображения
        self._pixmap_item = QGraphicsPixmapItem()
        self._pixmap_item.setZValue(0) # На заднем плане
        self._scene.addItem(self._pixmap_item)
        
        # Устанавливаем элемент для кликов
        self._graphics_view.set_scene_item(self._pixmap_item)
        
        main_layout.addWidget(self._graphics_view)

        # --- Статусная строка ---
        self._lbl_status = QLabel("Готов к калибровке. Начните с точки ЦЕНТР (0, 0°).")
        self._lbl_status.setStyleSheet(
            "QLabel { background-color : lightgray; padding: 5px; border-radius: 3px; }" # Серый фон из C#
        )
        self._lbl_status.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._lbl_status.setMinimumHeight(30)
        self._lbl_status.setWordWrap(True)
        main_layout.addWidget(self._lbl_status)

        # --- Статус бар (для сообщений) ---
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)

    def _setup_signals(self):
        """Настройка сигналов и слотов."""
        self._btn_start.clicked.connect(self._on_start_clicked)
        self._btn_stop.clicked.connect(self._on_stop_clicked)
        self._btn_add_point.clicked.connect(self._on_add_point_clicked)
        self._btn_save_calib.clicked.connect(self._on_save_calib_clicked)
        self._btn_load_calib.clicked.connect(self._on_load_calib_clicked)
        self._btn_run_calib.clicked.connect(self._on_run_calib_clicked)
        
        # Сигнал от графического вида при клике
        self._graphics_view.point_clicked.connect(self._on_image_clicked)

        # Подписываемся на события от сервиса калибровки
        self._calibration_service.on_calibration_point_added = self._on_calibration_point_added
        self._calibration_service.on_calibration_finished = self._on_calibration_finished
        self._calibration_service.on_error = self._on_calibration_error

    def _setup_timers(self):
        """Настройка таймеров."""
        # Таймер для захвата кадров в режиме Live View
        self._live_view_timer = QTimer()
        self._live_view_timer.timeout.connect(self._grab_camera_frame)
        self._live_view_timer.setInterval(50) # 50 ms для более плавного отображения

        # Таймер для обновления отображения
        self._update_timer = QTimer()
        self._update_timer.timeout.connect(self._update_display)
        self._update_timer.setInterval(50) # 50 ms, как в C# (100 ms -> 50 ms для более частого обновления)
        self._update_timer.start()

    # --- Вспомогательные методы ---
    def _update_ui_state(self):
        """Обновляет состояние UI в зависимости от текущего состояния."""
        is_camera_connected = self._camera_service.is_connected()
        point_count = self._calibration_service.get_calibration_data().get_point_count()
        
        self._btn_start.setEnabled(is_camera_connected and not self._is_live_view_running)
        self._btn_stop.setEnabled(self._is_live_view_running)
        self._btn_add_point.setEnabled(self._is_live_view_running)
        self._btn_save_calib.setEnabled(point_count > 0)
        self._btn_load_calib.setEnabled(True) # Всегда можно попробовать загрузить
        self._btn_run_calib.setEnabled(point_count >= 3)
        
        # Обновляем состояние радио-кнопок и подсказки
        # Improvement: Dynamic labels with sample radius
        self._radio_radius.setText(f"Радиус ({self._sample_radius_mm}мм, 0°)")
        self._radio_angle.setText(f"Угол ({self._sample_radius_mm}мм, 90°)")
        if point_count == 0:
            self._radio_center.setChecked(True)
            self._radio_center.setEnabled(True)
            self._radio_radius.setEnabled(False)
            self._radio_angle.setEnabled(False)
            self._update_status(f"Начните с точки ЦЕНТР (0, 0°). Кликните в центр зеркала радиусом {self._sample_radius_mm}мм.")
        elif point_count == 1:
            self._radio_radius.setChecked(True)
            self._radio_center.setEnabled(False)
            self._radio_radius.setEnabled(True)
            self._radio_angle.setEnabled(False)
            self._update_status(f"Добавьте точку РАДИУС ({self._sample_radius_mm}мм, 0°). Кликните на краю зеркала при угле 0°.")
        elif point_count == 2:
            self._radio_angle.setChecked(True)
            self._radio_center.setEnabled(False)
            self._radio_radius.setEnabled(False)
            self._radio_angle.setEnabled(True)
            self._update_status(f"Добавьте точку УГОЛ ({self._sample_radius_mm}мм, 90°). Кликните на краю зеркала при угле 90°.")
        else: # point_count >= 3
            self._radio_center.setEnabled(False)
            self._radio_radius.setEnabled(False)
            self._radio_angle.setEnabled(False)
            self._update_status(f"Все точки добавлены для радиуса {self._sample_radius_mm}мм. Нажмите 'Запустить калибровку'.")

    def _update_status(self, message: str):
        """Обновляет текст статусной строки."""
        self._lbl_status.setText(message)

    def _show_message(self, message: str, timeout: int = 3000):
        """Показывает временное сообщение в статус баре."""
        self._status_bar.showMessage(message, timeout)

    def _draw_crosshair(self, scene_x: float, scene_y: float, color: QColor = QColor(0, 255, 0)):
        """
        Рисует перекрестие на сцене.
        """
        pen = QPen(color, 2)
        line_length = 10
        
        line_h = QGraphicsLineItem(scene_x - line_length, scene_y, scene_x + line_length, scene_y)
        line_h.setPen(pen)
        line_v = QGraphicsLineItem(scene_x, scene_y - line_length, scene_x, scene_y + line_length)
        line_v.setPen(pen)
        
        self._scene.addItem(line_h)
        self._scene.addItem(line_v)
        
        # Сохраняем ссылки, чтобы можно было удалить позже
        self._overlay_items.extend([line_h, line_v])

    def _clear_overlay(self):
        """Удаляет все нарисованные элементы с изображения."""
        for item in self._overlay_items:
            self._scene.removeItem(item)
        self._overlay_items.clear()

    def _get_scanner_coordinates_for_current_radio(self) -> Tuple[float, float]:
        """Возвращает координаты сканера (радиус, угол) для текущей выбранной радио-кнопки."""
        point_count = self._calibration_service.get_calibration_data().get_point_count()
        if self._radio_center.isChecked():
            return (0.0, 0.0)
        elif self._radio_radius.isChecked():
            return (self._sample_radius_mm, 0.0)
        elif self._radio_angle.isChecked():
            return (self._sample_radius_mm, 90.0)
        else:
            # Fallback, не должно произойти
            return (0.0, 0.0)

    # --- Обработчики событий UI ---
    def _on_start_clicked(self):
        """Обработчик кнопки 'Старт'."""
        if not self._camera_service.is_connected():
            QMessageBox.warning(self, "Ошибка", "Камера не подключена")
            return

        try:
            self._btn_start.setEnabled(False)
            self._update_status("Запуск Live View...")
            
            self._camera_service.start_live_view()
            self._is_live_view_running = True
            self._live_view_timer.start()
            
            self._update_status("Live View запущен. Кликните на изображении или нажмите 'Добавить точку'.")
            self._show_message("Live View запущен", 2000)
            
        except Exception as e:
            error_msg = f"Ошибка запуска Live View: {e}"
            self._logger.log_error(LogCategory.CALIBRATION, error_msg)
            QMessageBox.critical(self, "Ошибка", error_msg)
            self._btn_start.setEnabled(True)
        finally:
            self._update_ui_state()

    def _on_stop_clicked(self):
        """Обработчик кнопки 'Стоп'."""
        try:
            self._live_view_timer.stop()
            self._camera_service.stop_live_view()
            self._is_live_view_running = False
            self._current_frame = None
            
            # Очищаем изображение
            self._pixmap_item.setPixmap(QPixmap())
            self._clear_overlay()
            
            self._update_status("Live View остановлен")
            self._show_message("Live View остановлен", 2000)
            
        except Exception as e:
            error_msg = f"Ошибка остановки Live View: {e}"
            self._logger.log_error(LogCategory.CALIBRATION, error_msg)
            QMessageBox.critical(self, "Ошибка", error_msg)
        finally:
            self._update_ui_state()

    def _on_add_point_clicked(self):
        """Обработчик кнопки 'Добавить точку'."""
        # Сообщаем пользователю, что нужно кликнуть
        self._show_message("Кликните на изображении в нужной точке", 3000)

    def _on_save_calib_clicked(self):
        """Обработчик кнопки 'Сохранить'."""
        try:
            default_path = self._calibration_service.get_calibration_file_path()
            file_path, _ = QFileDialog.getSaveFileName(
                self, "Сохранить калибровку",
                default_path,
                "JSON Files (*.json)"
            )
            if file_path:
                self._calibration_service.save_calibration(file_path)
                self._show_message(f"Калибровка сохранена в {file_path}", 3000)
                self._logger.log_info(LogCategory.CALIBRATION, f"Калибровка сохранена в {file_path}")
        except Exception as e:
            error_msg = f"Ошибка сохранения калибровки: {e}"
            self._logger.log_error(LogCategory.CALIBRATION, error_msg)
            QMessageBox.critical(self, "Ошибка", error_msg)

    def _on_load_calib_clicked(self):
        """Обработчик кнопки 'Загрузить'."""
        try:
            file_path, _ = QFileDialog.getOpenFileName(
                self, "Загрузить калибровку",
                "", "JSON Files (*.json)"
            )
            if file_path:
                self._calibration_service.load_calibration(file_path)
                self._show_message(f"Калибровка загружена из {file_path}", 3000)
                self._logger.log_info(LogCategory.CALIBRATION, f"Калибровка загружена из {file_path}")
                # Обновляем UI
                self._update_ui_state()
                # Перерисовываем точки, если они есть
                self._redraw_calibration_points()
        except FileNotFoundError:
            QMessageBox.information(self, "Информация", "Файл калибровки не найден.")
        except Exception as e:
            error_msg = f"Ошибка загрузки калибровки: {e}"
            self._logger.log_error(LogCategory.CALIBRATION, error_msg)
            QMessageBox.critical(self, "Ошибка", error_msg)

    def _on_run_calib_clicked(self):
        """Обработчик кнопки 'Запустить калибровку'."""
        try:
            point_count = self._calibration_service.get_calibration_data().get_point_count()
            if point_count < 3:
                QMessageBox.warning(self, "Ошибка", f"Недостаточно точек для калибровки: {point_count}/3")
                return

            self._update_status("Выполнение калибровки...")
            self._show_message("Выполнение калибровки...", 2000)
            
            # Выполняем расчет калибровки
            success = self._calibration_service.finish_calibration(use_homography=False)
            
            if success:
                self._show_message("Калибровка выполнена успешно!", 3000)
                self._update_status("Калибровка выполнена успешно. Можно закрывать окно.")
            else:
                QMessageBox.warning(self, "Ошибка", "Не удалось выполнить калибровку")
                self._update_status("Ошибка калибровки")
                
        except Exception as e:
            error_msg = f"Ошибка выполнения калибровки: {e}"
            self._logger.log_error(LogCategory.CALIBRATION, error_msg)
            QMessageBox.critical(self, "Ошибка", error_msg)
            self._update_status("Ошибка калибровки")

    def _on_image_clicked(self, scene_pos: QPointF):
        """Обработчик клика на изображении."""
        if not self._is_live_view_running:
            return
            
        # scene_pos - это QPointF с координатами в системе сцены
        # Нам нужно получить координаты относительно изображения (пиксели)
        
        # Преобразуем координаты сцены в координаты элемента pixmap
        pixmap_pos = self._pixmap_item.mapFromScene(scene_pos)
        
        # Получаем размеры pixmap
        pixmap_rect = self._pixmap_item.pixmap().rect()
        
        # Проверяем, что клик был внутри изображения
        if pixmap_rect.contains(pixmap_pos.toPoint()):
            x_pixel = int(pixmap_pos.x())
            y_pixel = int(pixmap_pos.y())
            
            # Получаем координаты сканера из выбранной радио-кнопки
            scanner_radius_mm, scanner_angle_deg = self._get_scanner_coordinates_for_current_radio()
            
            # Добавляем точку в сервис калибровки
            from camera.calibration_point import CalibrationPoint
            point = CalibrationPoint(
                image_point=(x_pixel, y_pixel),
                world_point=(scanner_radius_mm, scanner_angle_deg)
            )
            
            try:
                self._calibration_service.add_calibration_point(point)
                # UI обновится через on_calibration_point_added
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось добавить точку: {e}")
                self._logger.log_error(LogCategory.CALIBRATION, f"Ошибка добавления точки: {e}")
        else:
            self._show_message("Клик вне области изображения", 2000)

    # --- Обработчики событий от сервисов ---
    def _on_camera_frame_ready(self, frame: np.ndarray):
        """Обработчик нового кадра от камеры."""
        # Сохраняем кадр для последующего отображения
        # Копируем, чтобы избежать проблем с многопоточностью
        self._current_frame = frame.copy()

    def _on_camera_error(self, error_msg: str):
        """Обработчик ошибок камеры."""
        self._logger.log_error(LogCategory.CALIBRATION, f"Ошибка камеры: {error_msg}")
        self._show_message(f"Ошибка камеры: {error_msg}", 5000)
        # Останавливаем Live View
        if self._is_live_view_running:
            self._on_stop_clicked()

    def _on_calibration_point_added(self, point):
        """Обработчик добавления точки в сервисе калибровки."""
        # point - это CalibrationPoint
        x_px, y_px = point.image_point
        r_mm, a_deg = point.world_point
        
        # Рисуем точку на изображении
        # Преобразуем пиксельные координаты в координаты сцены
        # Предполагаем, что pixmap занимает всю сцену или его позиция (0,0)
        self._draw_crosshair(float(x_px), float(y_px))
        
        point_count = self._calibration_service.get_calibration_data().get_point_count()
        self._show_message(
            f"Точка {point_count} добавлена: ({x_px}, {y_px}) -> ({r_mm:.1f}мм, {a_deg:.1f}°)", 
            3000
        )
        self._logger.log_info(
            LogCategory.CALIBRATION,
            f"Точка {point_count} добавлена: изображение({x_px}, {y_px}) -> "
            f"сканер({r_mm:.1f}мм, {a_deg:.1f}°)"
        )
        
        # Обновляем состояние UI
        self._update_ui_state()
        
        # Improvement: Hints already handled in _update_ui_state

    def _on_calibration_finished(self):
        """Обработчик завершения калибровки в сервисе."""
        self._show_message("Калибровка завершена успешно!", 3000)
        self._update_status("Калибровка завершена успешно. Можно закрывать окно.")

    def _on_calibration_error(self, error_msg: str):
        """Обработчик ошибок в сервисе калибровки."""
        self._logger.log_error(LogCategory.CALIBRATION, f"Ошибка калибровки: {error_msg}")
        self._show_message(f"Ошибка калибровки: {error_msg}", 5000)

    def _redraw_calibration_points(self):
        """Перерисовывает точки калибровки на изображении."""
        self._clear_overlay()
        points = self._calibration_service.get_calibration_data().points
        for point in points:
            x_px, y_px = point.image_point
            self._draw_crosshair(float(x_px), float(y_px))

    # --- Методы обновления отображения ---
    def _grab_camera_frame(self):
        """Захват кадра от камеры (вызывается по таймеру)."""
        # В данном случае камера сама отправляет кадры через on_frame_ready
        # Этот метод может быть пустым или использоваться для других целей
        pass

    def _update_display(self):
        """Обновляет отображение изображения (вызывается по таймеру)."""
        if self._current_frame is not None:
            try:
                frame = self._current_frame
                
                # Преобразование numpy массива в QImage
                if frame.dtype == np.uint16:
                    # Нормализация для отображения
                    if frame.max() != frame.min():
                        frame_normalized = ((frame.astype(np.float32) - frame.min()) / 
                                          (frame.max() - frame.min()) * 255).astype(np.uint8)
                    else:
                        frame_normalized = np.zeros_like(frame, dtype=np.uint8)
                else:
                    frame_normalized = frame.astype(np.uint8)
                
                height, width = frame_normalized.shape
                bytes_per_line = width
                
                q_img = QImage(
                    frame_normalized.data, width, height, bytes_per_line, 
                    QImage.Format_Grayscale8
                )
                
                # Создаем QPixmap из QImage
                pixmap = QPixmap.fromImage(q_img)
                
                # Устанавливаем pixmap в элемент сцены
                self._pixmap_item.setPixmap(pixmap)
                
                # Подгоняем сцену под размер изображения
                self._scene.setSceneRect(QRectF(pixmap.rect()))
                
            except Exception as e:
                self._logger.log_error(LogCategory.CALIBRATION, f"Ошибка обновления изображения: {e}")

    # --- Обработка закрытия окна ---
    def closeEvent(self, event):
        """Обработчик события закрытия окна."""
        self._logger.log_info(LogCategory.CALIBRATION, "Закрытие окна калибровки...")
        
        # Останавливаем таймеры
        self._live_view_timer.stop()
        self._update_timer.stop()
        
        # Останавливаем Live View, если он запущен
        if self._is_live_view_running:
            try:
                self._camera_service.stop_live_view()
            except:
                pass
        
        # Отписываемся от событий
        self._camera_service.on_frame_ready = None
        self._camera_service.on_error = None
        self._calibration_service.on_calibration_point_added = None
        self._calibration_service.on_calibration_finished = None
        self._calibration_service.on_error = None
        
        event.accept()
        self._logger.log_info(LogCategory.CALIBRATION, "Окно калибровки закрыто")