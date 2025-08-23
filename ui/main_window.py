# src/ui/main_window.py
"""
Главное окно приложения MirrorScan.
"""
import sys
import os
from pathlib import Path
from typing import Optional, List, Tuple
import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout,
    QSplitter, QTabWidget, QGroupBox, QLabel, QPushButton, QComboBox, QSpinBox,
    QDoubleSpinBox, QTextEdit, QProgressBar, QStatusBar, QFileDialog, QMessageBox,
    QApplication, QAction, QStyle, QSizePolicy
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject, QThread
from PyQt5.QtGui import QColor, QIcon, QPixmap

# Для графика
import matplotlib

matplotlib.use('Qt5Agg')  # Устанавливаем backend до импорта pyplot
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import numpy as np

# Импорты из нашего проекта
from config.config_model import AppConfig
# Форматы вывода и единицы угла берём из scan.data_writer
from scan.data_writer import OutputFormat, AngleUnit
from utils.logger import DataLogger, LogCategory
from hardware.stm32_controller import Stm32ControllerService
from hardware.axis_controller import AxisController
from camera.camera_service import CameraService
from calibration.calibration_service import CalibrationService
from camera.analysis_service import AnalysisService
from scan.scan_engine import ScanEngine
from scan.data_writer import ScanDataWriter


class MplCanvas(FigureCanvas):
    """Холст matplotlib для встраивания в Qt."""

    def __init__(self, parent=None, width=5, height=4, dpi=100):
        fig = Figure(figsize=(width, height), dpi=dpi)
        self.axes = fig.add_subplot(111)
        super(MplCanvas, self).__init__(fig)


class ScanDataProcessor(QObject):
    """
    Обработчик данных сканирования для обновления графика.
    Работает в отдельном потоке.
    """
    data_ready = pyqtSignal(list)  # Сигнал с новыми данными для графика

    def __init__(self):
        super().__init__()
        self._data_buffer: List[Tuple[float, float, float, float]] = []
        self._buffer_lock = threading.Lock()

    def add_data_point(self, radius_mm: float, angle_deg: float, min_temp: float, max_temp: float):
        """Добавляет точку данных в буфер."""
        with self._buffer_lock:
            self._data_buffer.append((radius_mm, angle_deg, min_temp, max_temp))

    def process_data(self):
        """Обрабатывает накопленные данные и отправляет их для отображения."""
        with self._buffer_lock:
            if not self._data_buffer:
                return
            # Копируем данные и очищаем буфер
            data_to_process = self._data_buffer[:]
            self._data_buffer.clear()

        if data_to_process:
            self.data_ready.emit(data_to_process)


class MainWindow(QMainWindow):
    """
    Главное окно приложения MirrorScan.
    """
    # Сигналы для обновления UI из других потоков
    log_message_received = pyqtSignal(str)
    scan_progress_updated = pyqtSignal(int, int)
    scan_finished = pyqtSignal()
    scan_error = pyqtSignal(str)
    controller_status_changed = pyqtSignal(bool)  # connected/disconnected
    camera_status_changed = pyqtSignal(bool)  # connected/disconnected
    plot_data_ready = pyqtSignal(list)  # Для передачи данных в основной поток

    def __init__(self,
                 logger: DataLogger,
                 config: AppConfig,
                 controller_service: Stm32ControllerService,
                 camera_service: CameraService,
                 analysis_service: AnalysisService,
                 x_axis: AxisController,
                 theta_axis: AxisController,
                 calibration_service: CalibrationService,
                 scan_engine: ScanEngine,
                 default_scan_file_path: str,
                 no_xml_config: bool = False) -> None:
        super().__init__()
        # --- Сервисы и конфигурация ---
        self._logger = logger
        self._config = config
        self._controller_service = controller_service
        self._camera_service = camera_service
        self._analysis_service = analysis_service
        self._x_axis = x_axis
        self._theta_axis = theta_axis
        self._calibration_service = calibration_service
        self._scan_engine = scan_engine
        self._default_scan_file_path = default_scan_file_path
        self._no_xml_config = no_xml_config  # Сохраняем флаг

        # --- Состояние UI ---
        self._is_scanning = False
        self._log_lines = []  # Буфер для логов
        self._scan_data_points: List[Tuple[float, float, float, float]] = []  # (r, a, min, max)

        # --- UI компоненты ---
        # Меню и панель инструментов
        self._menu_bar = None
        self._tool_bar = None

        # Статус бар
        self._status_bar: QStatusBar
        self._lbl_status: QLabel
        self._progress_bar: QProgressBar

        # Основной splitter
        self._main_splitter: QSplitter

        # Левая панель (группы)
        self._grp_connection: QGroupBox
        self._combo_ports: QComboBox
        self._btn_refresh_ports: QPushButton
        self._btn_connect_controller: QPushButton
        self._btn_connect_camera: QPushButton

        self._grp_scan_params: QGroupBox
        self._spin_radius: QDoubleSpinBox
        self._spin_radial_step: QDoubleSpinBox
        self._spin_arc_step: QDoubleSpinBox
        self._spin_angle: QDoubleSpinBox
        self._spin_delay: QSpinBox
        self._combo_format: QComboBox
        self._combo_angle_unit: QComboBox

        self._grp_actions: QGroupBox
        self._btn_start_scan: QPushButton
        self._btn_stop_scan: QPushButton
        self._btn_mech_calib: QPushButton
        self._btn_camera_calib: QPushButton

        # Правая панель (вкладки)
        self._tab_widget: QTabWidget
        self._text_log: QTextEdit
        self._canvas: MplCanvas  # Холст для графика

        # --- Таймеры ---
        self._log_update_timer: QTimer
        self._plot_update_timer: QTimer

        # --- Обработчик данных сканирования ---
        self._data_processor = ScanDataProcessor()
        self._data_processor_thread = QThread()
        self._data_processor.moveToThread(self._data_processor_thread)
        self._data_processor_thread.start()

        # --- Инициализация ---
        self._setup_ui()
        self._setup_menu()
        self._setup_signals()
        self._setup_timers()
        self._setup_initial_values()
        self._setup_logger_callback()
        self._update_ui_state()

    def _setup_ui(self):
        """Настройка пользовательского интерфейса."""
        self.setWindowTitle("MirrorScan - Инженерный сканер")
        self.setGeometry(100, 100, 1200, 800)
        self.setMinimumSize(1000, 700)
        # self.setStyleSheet("background-color: #f0f0f0;")  # Убираем общий стиль, пусть системный

        # Центральный виджет
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)

        # Основной разделитель
        self._main_splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(self._main_splitter)

        # --- Левая панель ---
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        # Группа подключения
        self._grp_connection = self._create_connection_group()
        left_layout.addWidget(self._grp_connection)

        # Группа параметров сканирования
        self._grp_scan_params = self._create_scan_params_group()
        left_layout.addWidget(self._grp_scan_params)

        # Группа действий
        self._grp_actions = self._create_actions_group()
        left_layout.addWidget(self._grp_actions)

        left_layout.addStretch()  # Заполнитель для выравнивания по верху
        self._main_splitter.addWidget(left_panel)

        # --- Правая панель ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(5)

        # Вкладки
        self._tab_widget = QTabWidget()
        right_layout.addWidget(self._tab_widget)

        # Вкладка логов
        log_tab = QWidget()
        log_layout = QVBoxLayout(log_tab)
        log_layout.setContentsMargins(0, 0, 0, 0)
        self._text_log = QTextEdit()
        self._text_log.setReadOnly(True)
        # Устанавливаем темный стиль для лога, как в C#
        self._text_log.setStyleSheet(
            "background-color: #1e1e1e; color: #dcdcdc; font-family: Consolas, monospace; font-size: 9pt;"
        )
        log_layout.addWidget(self._text_log)
        self._tab_widget.addTab(log_tab, "Лог")

        # Вкладка графика
        chart_tab = QWidget()
        chart_layout = QVBoxLayout(chart_tab)
        chart_layout.setContentsMargins(0, 0, 0, 0)
        # Создаем холст matplotlib
        self._canvas = MplCanvas(self, width=5, height=4, dpi=100)
        self._canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        chart_layout.addWidget(self._canvas)
        self._tab_widget.addTab(chart_tab, "График")

        self._main_splitter.addWidget(right_panel)

        # --- Статус бар ---
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)

        self._lbl_status = QLabel("Готов к работе")
        self._lbl_status.setStyleSheet("QLabel { font-weight: bold; }")
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setVisible(False)
        self._progress_bar.setFixedWidth(200)

        self._status_bar.addWidget(self._lbl_status, 1)
        self._status_bar.addPermanentWidget(self._progress_bar)

    def _create_connection_group(self) -> QGroupBox:
        """Создает группу подключения."""
        group = QGroupBox("Подключение")
        layout = QGridLayout(group)
        layout.setContentsMargins(10, 15, 10, 15)
        layout.setSpacing(5)
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(2, 1)

        self._combo_ports = QComboBox()
        self._combo_ports.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        layout.addWidget(self._combo_ports, 0, 0, 1, 3)

        self._btn_refresh_ports = QPushButton("Обновить")
        layout.addWidget(self._btn_refresh_ports, 1, 0)

        self._btn_connect_controller = QPushButton("Контроллер")
        layout.addWidget(self._btn_connect_controller, 1, 1)

        self._btn_connect_camera = QPushButton("Камера")
        layout.addWidget(self._btn_connect_camera, 1, 2)

        return group

    def _create_scan_params_group(self) -> QGroupBox:
        """Создает группу параметров сканирования."""
        group = QGroupBox("Параметры сканирования")
        layout = QFormLayout(group)
        layout.setContentsMargins(10, 15, 10, 15)
        layout.setSpacing(5)
        layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self._spin_radius = QDoubleSpinBox()
        self._spin_radius.setRange(1.0, 1000.0)
        self._spin_radius.setSingleStep(0.1)
        self._spin_radius.setDecimals(2)
        self._spin_radius.setSuffix(" мм")
        layout.addRow("Радиус:", self._spin_radius)

        self._spin_radial_step = QDoubleSpinBox()
        self._spin_radial_step.setRange(0.01, 100.0)
        self._spin_radial_step.setSingleStep(0.01)
        self._spin_radial_step.setDecimals(3)
        self._spin_radial_step.setSuffix(" мм")
        layout.addRow("Шаг по радиусу:", self._spin_radial_step)

        self._spin_arc_step = QDoubleSpinBox()
        self._spin_arc_step.setRange(0.01, 100.0)
        self._spin_arc_step.setSingleStep(0.01)
        self._spin_arc_step.setDecimals(3)
        self._spin_arc_step.setSuffix(" мм")
        layout.addRow("Шаг по дуге:", self._spin_arc_step)

        self._spin_angle = QDoubleSpinBox()
        self._spin_angle.setRange(0.1, 360.0)
        self._spin_angle.setSingleStep(1.0)
        self._spin_angle.setDecimals(1)
        self._spin_angle.setSuffix(" °")
        layout.addRow("Угол:", self._spin_angle)

        self._spin_delay = QSpinBox()
        self._spin_delay.setRange(100, 60000)
        self._spin_delay.setSingleStep(100)
        self._spin_delay.setSuffix(" мс")
        layout.addRow("Задержка:", self._spin_delay)

        self._combo_format = QComboBox()
        self._combo_format.addItems(["Txt", "Md", "Csv"])
        layout.addRow("Формат вывода:", self._combo_format)

        self._combo_angle_unit = QComboBox()
        self._combo_angle_unit.addItems(["Degrees", "Dms"])
        layout.addRow("Единицы угла:", self._combo_angle_unit)

        return group

    def _create_actions_group(self) -> QGroupBox:
        """Создает группу действий."""
        group = QGroupBox("Действия")
        layout = QGridLayout(group)
        layout.setContentsMargins(10, 15, 10, 15)
        layout.setSpacing(5)
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 1)

        self._btn_start_scan = QPushButton("Старт сканирования")
        self._btn_start_scan.setStyleSheet("background-color: palegreen;")
        layout.addWidget(self._btn_start_scan, 0, 0)

        self._btn_stop_scan = QPushButton("Стоп")
        self._btn_stop_scan.setStyleSheet("background-color: lightcoral;")
        layout.addWidget(self._btn_stop_scan, 0, 1)

        self._btn_mech_calib = QPushButton("Мех. калибровка")
        layout.addWidget(self._btn_mech_calib, 1, 0)

        self._btn_camera_calib = QPushButton("Калибровка камеры")
        layout.addWidget(self._btn_camera_calib, 1, 1)

        return group

    def _setup_menu(self):
        """Настройка меню и панели инструментов."""
        self._menu_bar = self.menuBar()

        # Меню "Файл"
        file_menu = self._menu_bar.addMenu("Файл")
        action_open_config = QAction("Открыть конфиг", self)
        action_open_config.triggered.connect(self._on_open_config)
        file_menu.addAction(action_open_config)
        action_save_config = QAction("Сохранить конфиг", self)
        action_save_config.triggered.connect(self._on_save_config)
        file_menu.addAction(action_save_config)
        file_menu.addSeparator()
        action_exit = QAction("Выход", self)
        action_exit.triggered.connect(QApplication.quit)
        file_menu.addAction(action_exit)

        # Меню "Инструменты"
        tools_menu = self._menu_bar.addMenu("Инструменты")
        action_debug = QAction("Режим отладки", self)
        action_debug.triggered.connect(self._on_debug_triggered)
        tools_menu.addAction(action_debug)

        action_config_editor = QAction("Редактор конфигурации", self)
        action_config_editor.triggered.connect(self._on_config_editor_triggered)
        tools_menu.addAction(action_config_editor)

        # Меню "Справка"
        help_menu = self._menu_bar.addMenu("Справка")
        action_about = QAction("О программе", self)
        action_about.triggered.connect(self._on_about_triggered)
        help_menu.addAction(action_about)

    def _setup_signals(self):
        """Настройка сигналов и слотов."""
        # Кнопки подключения
        self._btn_refresh_ports.clicked.connect(self._load_available_com_ports)
        self._btn_connect_controller.clicked.connect(self._on_connect_controller_clicked)
        self._btn_connect_camera.clicked.connect(self._on_connect_camera_clicked)

        # Кнопки действий
        self._btn_start_scan.clicked.connect(self._on_start_scan_clicked)
        self._btn_stop_scan.clicked.connect(self._on_stop_scan_clicked)
        self._btn_mech_calib.clicked.connect(self._on_mech_calib_clicked)
        self._btn_camera_calib.clicked.connect(self._on_camera_calib_clicked)

        # Сигналы от контроллера
        self._controller_service.on_connected = lambda: self.controller_status_changed.emit(True)
        self._controller_service.on_disconnected = lambda: self.controller_status_changed.emit(False)
        # Use QTimer.singleShot to ensure UI updates occur in the main thread when errors arrive
        self._controller_service.on_error = lambda msg: QTimer.singleShot(0, lambda m=msg: self._on_controller_error(m))

        # Сигналы от камеры
        # Similarly, route camera errors through the Qt event loop to avoid cross-thread UI updates
        self._camera_service.on_error = lambda msg: QTimer.singleShot(0, lambda m=msg: self._on_camera_error(m))

        # Сигналы для обновления UI
        self.log_message_received.connect(self._append_log_message)
        self.scan_progress_updated.connect(self._update_scan_progress)
        self.scan_finished.connect(self._on_scan_finished_ui)
        self.controller_status_changed.connect(self._on_controller_status_changed)
        self.camera_status_changed.connect(self._on_camera_status_changed)
        self.plot_data_ready.connect(self._update_plot)
        # Подключение событий сканирования к сигналам UI
        self._scan_engine.on_progress = lambda current, total: self.scan_progress_updated.emit(current, total)
        self._scan_engine.on_scan_finished = lambda: self.scan_finished.emit()
        self._scan_engine.on_error = lambda msg: self.scan_error.emit(msg)
        self._scan_engine.on_data_point = lambda r, a, min_t, max_t: self._data_processor.add_data_point(r, a, min_t,
                                                                                                         max_t)

        # Сигналы от обработчика данных
        self._data_processor.data_ready.connect(self.plot_data_ready.emit)

    def _setup_timers(self):
        """Настройка таймеров."""
        self._log_update_timer = QTimer()
        self._log_update_timer.timeout.connect(self._update_log_display)
        self._log_update_timer.setInterval(500)  # Обновляем лог 2 раза в секунду
        self._log_update_timer.start()

        self._plot_update_timer = QTimer()
        self._plot_update_timer.timeout.connect(self._data_processor.process_data)
        self._plot_update_timer.setInterval(1000)  # Обновляем график раз в секунду
        self._plot_update_timer.start()

    def _setup_initial_values(self):
        """Установка начальных значений из конфигурации."""
        self._spin_radius.setValue(self._config.default_radius_mm)
        self._spin_radial_step.setValue(self._config.default_step_mm)
        self._spin_arc_step.setValue(self._config.default_arc_step_mm)
        self._spin_angle.setValue(360.0)  # По умолчанию полный круг
        self._spin_delay.setValue(self._config.default_delay_ms)

        # Установка формата и единиц из конфига
        format_map = {OutputFormat.TXT: 0, OutputFormat.MD: 1, OutputFormat.CSV: 2}
        self._combo_format.setCurrentIndex(format_map.get(self._config.default_output_format, 2))

        unit_map = {AngleUnit.DEGREES: 0, AngleUnit.DMS: 1}
        self._combo_angle_unit.setCurrentIndex(unit_map.get(self._config.default_angle_unit, 0))

        self._load_available_com_ports()

    def _setup_logger_callback(self):
        """Настройка callback для логгера."""
        original_callback = self._logger.on_line_logged

        def ui_log_callback(line: str):
            if original_callback:
                original_callback(line)
            # Добавляем в буфер, UI обновится по таймеру
            self._log_lines.append(line)

        self._logger.on_line_logged = ui_log_callback

    # --- Вспомогательные методы ---
    def _load_available_com_ports(self):
        """Загружает список доступных COM-портов."""
        try:
            ports = Stm32ControllerService.get_available_ports()
            self._combo_ports.clear()
            self._combo_ports.addItems(ports)
            if ports and self._config.com_port in ports:
                self._combo_ports.setCurrentText(self._config.com_port)
            elif ports:
                self._combo_ports.setCurrentIndex(0)
        except Exception as e:
            self._logger.log_error(LogCategory.UI, f"Ошибка получения списка COM-портов: {e}")

    def _update_ui_state(self):
        """Обновляет состояние UI в зависимости от текущего состояния приложения."""
        is_controller_connected = self._controller_service.is_connected()
        is_camera_connected = self._camera_service.is_connected()
        is_scanning = self._is_scanning

        # Кнопки подключения
        self._btn_connect_controller.setText("Отключить" if is_controller_connected else "Контроллер")
        self._btn_connect_camera.setText("Отключить" if is_camera_connected else "Камера")
        self._btn_connect_controller.setStyleSheet(
            "background-color: lightgreen;" if is_controller_connected else ""
        )
        self._btn_connect_camera.setStyleSheet(
            "background-color: lightgreen;" if is_camera_connected else ""
        )

        # Кнопки действий
        self._btn_start_scan.setEnabled(is_controller_connected and is_camera_connected and not is_scanning)
        self._btn_stop_scan.setEnabled(is_scanning)
        self._btn_mech_calib.setEnabled(is_controller_connected and not is_scanning)
        self._btn_camera_calib.setEnabled(is_camera_connected and not is_scanning)

        # Параметры сканирования
        scan_params_enabled = not is_scanning
        self._spin_radius.setEnabled(scan_params_enabled)
        self._spin_radial_step.setEnabled(scan_params_enabled)
        self._spin_arc_step.setEnabled(scan_params_enabled)
        self._spin_angle.setEnabled(scan_params_enabled)
        self._spin_delay.setEnabled(scan_params_enabled)
        self._combo_format.setEnabled(scan_params_enabled)
        self._combo_angle_unit.setEnabled(scan_params_enabled)

        # Обновление статусной строки
        status_parts = []
        if is_controller_connected:
            status_parts.append("Контроллер: Подключен")
        else:
            status_parts.append("Контроллер: Не подключен")

        if is_camera_connected:
            status_parts.append("Камера: Подключена")
        else:
            status_parts.append("Камера: Не подключена")

        if is_scanning:
            status_parts.append("Сканирование: В процессе")
        else:
            status_parts.append("Готов")

        self._lbl_status.setText(" | ".join(status_parts))

    def _update_log_display(self):
        """Обновляет отображение лога из буфера."""
        if self._log_lines:
            lines_to_add = self._log_lines[:]
            self._log_lines.clear()

            if lines_to_add:
                cursor = self._text_log.textCursor()
                cursor.movePosition(cursor.End)
                for line in lines_to_add:
                    cursor.insertText(line + '\n')
                self._text_log.setTextCursor(cursor)
                self._text_log.ensureCursorVisible()

    def _update_plot(self, new_data_points: List[Tuple[float, float, float, float]]):
        """Обновляет график с новыми данными."""
        if not new_data_points:
            return

        # Добавляем новые точки в общий список
        self._scan_data_points.extend(new_data_points)

        if not self._scan_data_points:
            return

        # Очищаем график
        self._canvas.axes.clear()

        try:
            # Извлекаем данные
            radii = np.array([d[0] for d in self._scan_data_points])
            angles_deg = np.array([d[1] for d in self._scan_data_points])
            max_temps = np.array([d[3] for d in self._scan_data_points])

            # Преобразуем в декартовы координаты для scatter plot
            angles_rad = np.radians(angles_deg)
            xs = radii * np.cos(angles_rad)
            ys = radii * np.sin(angles_rad)

            # Строим scatter plot
            scatter = self._canvas.axes.scatter(xs, ys, c=max_temps, cmap='hot', s=20, edgecolors='black',
                                                linewidth=0.2)
            self._canvas.axes.set_xlabel('X (mm)')
            self._canvas.axes.set_ylabel('Y (mm)')
            self._canvas.axes.set_title('Температурное распределение (Max)')
            self._canvas.axes.grid(True, alpha=0.3)
            self._canvas.axes.set_aspect('equal', adjustable='box')

            # Добавляем цветовую шкалу
            if not hasattr(self._canvas, '_colorbar') or self._canvas._colorbar is None:
                self._canvas._colorbar = self._canvas.figure.colorbar(scatter, ax=self._canvas.axes)
                self._canvas._colorbar.set_label('Max Temperature (ADU)')
            else:
                # Обновляем нормализацию цветовой шкалы
                self._canvas._colorbar.update_normal(scatter)

        except Exception as e:
            self._logger.log_error(LogCategory.UI, f"Ошибка обновления графика: {e}")
            self._canvas.axes.clear()
            self._canvas.axes.text(0.5, 0.5, 'Ошибка отображения графика',
                                   horizontalalignment='center', verticalalignment='center',
                                   transform=self._canvas.axes.transAxes)

        # Перерисовываем холст
        self._canvas.draw()

    # --- Обработчики событий UI ---
    def _on_connect_controller_clicked(self):
        """Обработчик кнопки подключения/отключения контроллера."""
        if self._controller_service.is_connected():
            try:
                self._controller_service.disconnect()
                self._logger.log_info(LogCategory.UI, "Контроллер отключен пользователем")
            except Exception as e:
                self._logger.log_error(LogCategory.UI, f"Ошибка отключения контроллера: {e}")
        else:
            port = self._combo_ports.currentText()
            if not port:
                QMessageBox.warning(self, "Ошибка", "Выберите COM-порт")
                return

            try:
                self._btn_connect_controller.setEnabled(False)
                self._btn_connect_controller.setText("Подключение...")
                QApplication.processEvents()

                if self._controller_service.connect(port, self._config.baud_rate):
                    self._logger.log_info(LogCategory.UI, f"Контроллер подключен к {port}")
                else:
                    QMessageBox.warning(self, "Ошибка", "Не удалось подключить контроллер")
                    self._btn_connect_controller.setEnabled(True)
                    self._btn_connect_controller.setText("Контроллер")
            except Exception as e:
                error_msg = f"Ошибка подключения контроллера: {e}"
                self._logger.log_error(LogCategory.UI, error_msg)
                QMessageBox.critical(self, "Ошибка", error_msg)
                self._btn_connect_controller.setEnabled(True)
                self._btn_connect_controller.setText("Контроллер")

    def _on_connect_camera_clicked(self):
        """Обработчик кнопки подключения/отключения камеры."""
        if self._camera_service.is_connected():
            try:
                self._camera_service.disconnect()
                self._logger.log_info(LogCategory.UI, "Камера отключена пользователем")
            except Exception as e:
                self._logger.log_error(LogCategory.UI, f"Ошибка отключения камеры: {e}")
        else:
            try:
                self._btn_connect_camera.setEnabled(False)
                self._btn_connect_camera.setText("Подключение...")
                QApplication.processEvents()

                # Используем путь к XML или None в зависимости от флага
                config_path = None if self._no_xml_config else "pi640_config.xml"

                if self._camera_service.connect(config_path):
                    self._logger.log_info(LogCategory.UI, f"Камера подключена (XML конфиг: {config_path})")
                else:
                    QMessageBox.warning(self, "Ошибка", "Не удалось подключить камеру")
                    self._btn_connect_camera.setEnabled(True)
                    self._btn_connect_camera.setText("Камера")
            except Exception as e:
                error_msg = f"Ошибка подключения камеры: {e}"
                self._logger.log_error(LogCategory.UI, error_msg)
                QMessageBox.critical(self, "Ошибка", error_msg)
                self._btn_connect_camera.setEnabled(True)
                self._btn_connect_camera.setText("Камера")

    def _on_start_scan_clicked(self):
        """Обработчик кнопки запуска сканирования."""
        if self._is_scanning:
            return

        radius = self._spin_radius.value()
        radial_step = self._spin_radial_step.value()
        arc_step = self._spin_arc_step.value()
        angle = self._spin_angle.value()
        delay_ms = self._spin_delay.value()

        if radius <= 0 or radial_step <= 0 or arc_step <= 0 or angle <= 0:
            QMessageBox.warning(self, "Ошибка", "Все параметры сканирования должны быть положительными")
            return

        if not (self._x_axis.is_calibrated() and self._theta_axis.is_calibrated()):
            reply = QMessageBox.question(
                self, "Подтверждение",
                "Оси не откалиброваны. Продолжить сканирование?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.No:
                return

        try:
            # Открываем диалог сохранения файла
            format_map_rev = {0: "txt", 1: "md", 2: "csv"}
            selected_ext = format_map_rev.get(self._combo_format.currentIndex(), "csv")
            filter_map = {
                "txt": "Text Files (*.txt)",
                "md": "Markdown Files (*.md)",
                "csv": "CSV Files (*.csv)"
            }

            file_path, chosen_filter = QFileDialog.getSaveFileName(
                self, "Сохранить данные сканирования",
                self._default_scan_file_path,
                ";;".join(filter_map.values()),
                filter_map[selected_ext]
            )
            if not file_path:
                return

            # Определяем формат по расширению или фильтру
            ext = Path(file_path).suffix.lower()[1:]  # убираем точку
            if ext in ['txt', 'md', 'csv']:
                output_format = OutputFormat(ext.upper())
            else:
                # fallback на выбранный в комбо
                output_format = OutputFormat(selected_ext.upper())

            unit_map_rev = {0: AngleUnit.DEGREES, 1: AngleUnit.DMS}
            angle_unit = unit_map_rev.get(self._combo_angle_unit.currentIndex(), AngleUnit.DEGREES)

            writer = ScanDataWriter(file_path, output_format, angle_unit)
            self._scan_engine.set_data_writer(writer)
            self._scan_engine.set_delay(delay_ms)

            # Очищаем данные графика перед новым сканированием
            self._scan_data_points.clear()
            self._canvas.axes.clear()
            self._canvas.draw()
            if hasattr(self._canvas, '_colorbar'):
                self._canvas._colorbar = None

            self._is_scanning = True
            self._update_ui_state()
            self._progress_bar.setVisible(True)
            self._progress_bar.setValue(0)
            self._logger.log_info(LogCategory.UI, "Запуск сканирования...")

            def run_scan():
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(
                        self._scan_engine.start_scan(radius, radial_step, arc_step, angle)
                    )
                except Exception as e:
                    self._logger.log_error(LogCategory.SCAN, f"Ошибка в потоке сканирования: {e}")
                finally:
                    if 'loop' in locals():
                        loop.close()

            executor = ThreadPoolExecutor(max_workers=1)
            future = executor.submit(run_scan)

        except Exception as e:
            self._is_scanning = False
            self._update_ui_state()
            self._progress_bar.setVisible(False)
            error_msg = f"Ошибка запуска сканирования: {e}"
            self._logger.log_error(LogCategory.UI, error_msg)
            QMessageBox.critical(self, "Ошибка", error_msg)

    def _on_stop_scan_clicked(self):
        """Обработчик кнопки остановки сканирования."""
        if self._is_scanning:
            try:
                self._scan_engine.stop_scan()
                self._logger.log_info(LogCategory.UI, "Остановка сканирования инициирована")
            except Exception as e:
                self._logger.log_error(LogCategory.UI, f"Ошибка остановки сканирования: {e}")

    def _on_mech_calib_clicked(self):
        """Обработчик кнопки механической калибровки."""
        try:
            if not self._controller_service.is_connected():
                QMessageBox.warning(self, "Ошибка", "Контроллер не подключен")
                return

            reply = QMessageBox.question(
                self, "Подтверждение",
                "Запустить механическую калибровку? Оси переместятся в крайние положения.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self._logger.log_info(LogCategory.UI, "Запуск механической калибровки...")
                self._controller_service.start_calibration()
                QMessageBox.information(self, "Успех",
                                        "Команда калибровки отправлена. Следуйте инструкциям на контроллере.")
        except Exception as e:
            error_msg = f"Ошибка механической калибровки: {e}"
            self._logger.log_error(LogCategory.UI, error_msg)
            QMessageBox.critical(self, "Ошибка", error_msg)

    def _on_camera_calib_clicked(self):
        """Обработчик кнопки калибровки камеры."""
        try:
            if not self._camera_service.is_connected():
                QMessageBox.warning(self, "Ошибка", "Камера не подключена")
                return

            from ui.calibration_window import CalibrationWindow
            self._calibration_window = CalibrationWindow(
                self._calibration_service, self._camera_service, self._logger
            )
            self._calibration_window.show()

        except Exception as e:
            error_msg = f"Ошибка открытия окна калибровки камеры: {e}"
            self._logger.log_error(LogCategory.UI, error_msg)
            QMessageBox.critical(self, "Ошибка", error_msg)

    # --- Обработчики событий от сервисов ---
    def _on_scan_finished(self):
        """Обработчик завершения сканирования (из движка)."""
        self.scan_finished.emit()

    def _on_scan_error(self, error_msg: str):
        """Обработчик ошибок сканирования."""
        self._logger.log_error(LogCategory.UI, f"Ошибка сканирования: {error_msg}")
        self._is_scanning = False
        self._update_ui_state()
        self._progress_bar.setVisible(False)
        QMessageBox.critical(self, "Ошибка сканирования", error_msg)

    def _on_controller_error(self, error_msg: str):
        """Обработчик ошибок контроллера."""
        self._logger.log_error(LogCategory.UI, f"Ошибка контроллера: {error_msg}")
        self._btn_connect_controller.setEnabled(True)
        self._btn_connect_controller.setText("Контроллер")

    def _on_camera_error(self, error_msg: str):
        """Обработчик ошибок камеры."""
        self._logger.log_error(LogCategory.UI, f"Ошибка камеры: {error_msg}")
        self._btn_connect_camera.setEnabled(True)
        self._btn_connect_camera.setText("Камера")

    # --- Слоты для сигналов обновления UI ---
    def _append_log_message(self, message: str):
        """Добавляет сообщение в лог (вызывается через сигнал)."""
        self._text_log.append(message)
        cursor = self._text_log.textCursor()
        cursor.movePosition(cursor.End)
        self._text_log.setTextCursor(cursor)
        self._text_log.ensureCursorVisible()

    def _update_scan_progress(self, current: int, total: int):
        """Обновляет прогресс сканирования (вызывается через сигнал)."""
        if total > 0:
            progress_percent = int((current / total) * 100)
            self._progress_bar.setValue(progress_percent)
        else:
            self._progress_bar.setValue(0)

    def _on_scan_finished_ui(self):
        """Обработчик завершения сканирования для UI (вызывается через сигнал)."""
        self._is_scanning = False
        self._update_ui_state()
        self._progress_bar.setVisible(False)
        self._logger.log_info(LogCategory.UI, "Сканирование завершено")
        QMessageBox.information(self, "Успех", "Сканирование завершено успешно!")

    def _on_controller_status_changed(self, is_connected: bool):
        """Обработчик изменения статуса контроллера (вызывается через сигнал)."""
        self._btn_connect_controller.setEnabled(True)
        self._btn_connect_controller.setText("Отключить" if is_connected else "Контроллер")
        self._btn_connect_controller.setStyleSheet(
            "background-color: lightgreen;" if is_connected else ""
        )
        self._update_ui_state()

    def _on_camera_status_changed(self, is_connected: bool):
        """Обработчик изменения статуса камеры (вызывается через сигнал)."""
        self._btn_connect_camera.setEnabled(True)
        self._btn_connect_camera.setText("Отключить" if is_connected else "Камера")
        self._btn_connect_camera.setStyleSheet(
            "background-color: lightgreen;" if is_connected else ""
        )
        self._update_ui_state()

    # --- Обработчики меню ---
    def _on_open_config(self):
        """Обработчик открытия конфигурации."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Открыть конфигурацию", "", "JSON Files (*.json)"
        )
        if file_path:
            try:
                new_config = ConfigManager.load(file_path)
                self._config = new_config
                self._setup_initial_values()  # Update UI with new config
                self._logger.log_info(LogCategory.UI, f"Конфигурация загружена из {file_path}")
            except Exception as e:
                error_msg = f"Ошибка загрузки конфигурации: {e}"
                self._logger.log_error(LogCategory.UI, error_msg)
                QMessageBox.critical(self, "Ошибка", error_msg)

    def _on_save_config(self):
        """Обработчик сохранения конфигурации."""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить конфигурацию", self._config.config_file_path, "JSON Files (*.json)"
        )
        if file_path:
            try:
                ConfigManager.save(file_path, self._config)
                self._logger.log_info(LogCategory.UI, f"Конфигурация сохранена в {file_path}")
            except Exception as e:
                error_msg = f"Ошибка сохранения конфигурации: {e}"
                self._logger.log_error(LogCategory.UI, error_msg)
                QMessageBox.critical(self, "Ошибка", error_msg)

    def _on_debug_triggered(self):
        """Обработчик пункта меню 'Режим отладки'."""
        try:
            from ui.debug_window import DebugWindow
            self._debug_window = DebugWindow(
                self._camera_service,
                self._controller_service,
                self._analysis_service,
                self._logger
            )
            self._debug_window.show()
        except Exception as e:
            error_msg = f"Ошибка открытия окна отладки: {e}"
            self._logger.log_error(LogCategory.UI, error_msg)
            QMessageBox.critical(self, "Ошибка", error_msg)

    def _on_config_editor_triggered(self):
        """Обработчик пункта меню 'Редактор конфигурации'."""
        try:
            # Предполагаем, что путь к config.cfg хранится в основном конфиге
            # или мы используем фиксированное имя рядом с config.json
            import os
            from pathlib import Path
            config_path = self._config.config_file_path
            if config_path:
                cfg_file_path = str(Path(config_path).with_name("config.cfg"))
            else:
                cfg_file_path = "config.cfg"  # Fallback if empty

            from config.config_editor import ConfigEditorWindow
            self._config_editor_window = ConfigEditorWindow(self._logger, cfg_file_path)
            self._config_editor_window.show()
        except Exception as e:
            error_msg = f"Ошибка открытия редактора конфигурации: {e}"
            self._logger.log_error(LogCategory.UI, error_msg)
            QMessageBox.critical(self, "Ошибка", error_msg)

    def _on_about_triggered(self):
        """Обработчик пункта меню 'О программе'."""
        QMessageBox.about(
            self, "О программе",
            "<h2>MirrorScan</h2>"
            "<p>Инженерный сканер для анализа температурного поля зеркал.</p>"
            "<p><b>Версия:</b> 1.0.0 (Python)</p>"
            "<p><b>Автор:</b> Хлюпта Илья Сергеевич/АО НИИ НПО ЛУЧ</p>"
        )

    # --- Обработка закрытия окна ---
    def closeEvent(self, event):
        """Обработчик события закрытия окна."""
        self._logger.log_info(LogCategory.GENERAL, "Закрытие главного окна...")

        self._log_update_timer.stop()
        self._plot_update_timer.stop()

        if self._is_scanning:
            self._scan_engine.stop_scan()
            import time
            time.sleep(0.5)

        # Останавливаем и удаляем поток обработчика данных
        self._data_processor_thread.quit()
        self._data_processor_thread.wait()

        event.accept()
        self._logger.log_info(LogCategory.GENERAL, "Главное окно закрыто")