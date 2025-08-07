# src/ui/debug_window.py
"""
Окно отладки для тестирования камеры, контроллера и анализа изображений.
"""
import sys
import os
from typing import List, Optional
import numpy as np

# Пример использования PyQt5 (можно заменить на PySide2)
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QPushButton, QTextEdit, QLabel, QComboBox, QSpinBox, QDoubleSpinBox,
    QGroupBox, QTabWidget, QMessageBox, QFileDialog, QFrame, QSizePolicy
)
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QImage, QPixmap

# Импорты из нашего проекта
from camera.camera_service import CameraService
from hardware.stm32_controller import Stm32ControllerService
from utils.logger import DataLogger, LogCategory
from camera.analysis_service import AnalysisService

class DebugWindow(QMainWindow):
    """
    Окно отладки для тестирования камеры, контроллера и анализа изображений.
    """
    def __init__(self, camera_service: CameraService, 
                 controller_service: Stm32ControllerService, 
                 analysis_service: AnalysisService,
                 logger: DataLogger):
        super().__init__()
        self._camera_service = camera_service
        self._controller_service = controller_service
        self._analysis_service = analysis_service
        self._logger = logger
        
        # Состояние
        self._is_live_view_running = False
        self._current_frame: Optional[np.ndarray] = None
        
        # UI компоненты
        self._tab_widget: QTabWidget
        self._text_log: QTextEdit
        self._combo_com_ports: QComboBox
        self._btn_refresh_ports: QPushButton
        self._btn_connect_camera: QPushButton
        self._btn_disconnect_camera: QPushButton
        self._btn_start_live_view: QPushButton
        self._btn_stop_live_view: QPushButton
        self._label_camera_preview: QLabel
        self._btn_connect_controller: QPushButton
        self._btn_send_command: QPushButton
        self._text_command: QTextEdit
        self._text_response: QTextEdit
        self._btn_clear_log: QPushButton
        self._btn_test_homing: QPushButton
        self._spin_roi_x1: QSpinBox
        self._spin_roi_y1: QSpinBox
        self._spin_roi_x2: QSpinBox
        self._spin_roi_y2: QSpinBox
        self._btn_set_roi: QPushButton
        self._btn_clear_roi: QPushButton
        self._spin_line_x1: QSpinBox
        self._spin_line_y1: QSpinBox
        self._spin_line_x2: QSpinBox
        self._spin_line_y2: QSpinBox
        self._btn_add_line: QPushButton
        self._combo_method: QComboBox
        self._combo_object_type: QComboBox
        self._text_analysis_results: QTextEdit
        self._btn_start_record: QPushButton
        self._btn_stop_record: QPushButton
        
        # Таймеры
        self._live_view_timer: QTimer
        
        self._setup_ui()
        self._setup_signals()
        self._setup_timers()
        
        # Инициализация
        self._update_connection_status()
        self._load_available_com_ports()
        self._setup_logger_callback()

    def _setup_ui(self):
        """Настройка пользовательского интерфейса."""
        self.setWindowTitle("Режим отладки - MirrorScan")
        self.setGeometry(100, 100, 900, 700)
        
        # Центральный виджет
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Вкладки
        self._tab_widget = QTabWidget()
        layout = QVBoxLayout(central_widget)
        layout.addWidget(self._tab_widget)
        
        # --- Вкладка камеры ---
        self._setup_camera_tab()
        
        # --- Вкладка контроллера ---
        self._setup_controller_tab()
        
        # --- Вкладка анализа ---
        self._setup_analysis_tab()
        
        # --- Вкладка логов ---
        self._setup_logs_tab()

    def _setup_camera_tab(self):
        """Настройка вкладки камеры."""
        camera_tab = QWidget()
        layout = QVBoxLayout(camera_tab)
        
        # Группа подключения камеры
        grp_connection = QGroupBox("Подключение камеры")
        conn_layout = QFormLayout(grp_connection)
        
        self._btn_connect_camera = QPushButton("Подключить камеру")
        self._btn_disconnect_camera = QPushButton("Отключить камеру")
        self._btn_disconnect_camera.setEnabled(False)
        
        cam_conn_layout = QHBoxLayout()
        cam_conn_layout.addWidget(self._btn_connect_camera)
        cam_conn_layout.addWidget(self._btn_disconnect_camera)
        conn_layout.addRow(cam_conn_layout)
        
        layout.addWidget(grp_connection)
        
        # Группа предварительного просмотра
        grp_preview = QGroupBox("Предварительный просмотр")
        preview_layout = QVBoxLayout(grp_preview)
        
        self._label_camera_preview = QLabel("Предварительный просмотр камеры")
        self._label_camera_preview.setAlignment(Qt.AlignCenter)
        self._label_camera_preview.setMinimumSize(400, 300)
        self._label_camera_preview.setFrameShape(QFrame.Box)
        self._label_camera_preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        preview_btn_layout = QHBoxLayout()
        self._btn_start_live_view = QPushButton("Начать Live View")
        self._btn_stop_live_view = QPushButton("Остановить Live View")
        self._btn_stop_live_view.setEnabled(False)
        preview_btn_layout.addWidget(self._btn_start_live_view)
        preview_btn_layout.addWidget(self._btn_stop_live_view)
        
        preview_layout.addWidget(self._label_camera_preview)
        preview_layout.addLayout(preview_btn_layout)
        layout.addWidget(grp_preview)
        
        # Группа калибровки камеры (заглушка)
        grp_calibration = QGroupBox("Калибровка камеры")
        cal_layout = QVBoxLayout(grp_calibration)
        btn_test_calib = QPushButton("Проверить калибровку (заглушка)")
        cal_layout.addWidget(btn_test_calib)
        layout.addWidget(grp_calibration)
        
        layout.addStretch()
        self._tab_widget.addTab(camera_tab, "Камера")

    def _setup_controller_tab(self):
        """Настройка вкладки контроллера."""
        controller_tab = QWidget()
        layout = QVBoxLayout(controller_tab)
        
        # Группа подключения контроллера
        grp_connection = QGroupBox("Подключение контроллера")
        conn_layout = QFormLayout(grp_connection)
        
        # Выбор COM-порта
        port_layout = QHBoxLayout()
        self._combo_com_ports = QComboBox()
        self._btn_refresh_ports = QPushButton("Обновить")
        port_layout.addWidget(self._combo_com_ports)
        port_layout.addWidget(self._btn_refresh_ports)
        conn_layout.addRow("COM-порт:", port_layout)
        
        self._btn_connect_controller = QPushButton("Подключить контроллер")
        conn_layout.addRow(self._btn_connect_controller)
        
        layout.addWidget(grp_connection)
        
        # Группа команд контроллера
        grp_commands = QGroupBox("Команды контроллера")
        cmd_layout = QVBoxLayout(grp_commands)
        
        # Поле ввода команды
        self._text_command = QTextEdit()
        self._text_command.setMaximumHeight(60)
        cmd_layout.addWidget(QLabel("Команда:"))
        cmd_layout.addWidget(self._text_command)
        
        # Кнопка отправки
        self._btn_send_command = QPushButton("Отправить команду")
        cmd_layout.addWidget(self._btn_send_command)
        
        # Поле ответа
        self._text_response = QTextEdit()
        self._text_response.setMaximumHeight(100)
        self._text_response.setReadOnly(True)
        cmd_layout.addWidget(QLabel("Ответ:"))
        cmd_layout.addWidget(self._text_response)
        
        layout.addWidget(grp_commands)
        
        # Группа механической калибровки (homing)
        grp_homing = QGroupBox("Механическая калибровка")
        homing_layout = QVBoxLayout(grp_homing)
        self._btn_test_homing = QPushButton("Тест Homing (mech. calibration)")
        homing_layout.addWidget(self._btn_test_homing)
        layout.addWidget(grp_homing)
        
        layout.addStretch()
        self._tab_widget.addTab(controller_tab, "Контроллер")

    def _setup_analysis_tab(self):
        """Настройка вкладки анализа."""
        analysis_tab = QWidget()
        layout = QVBoxLayout(analysis_tab)
        
        # Группа выбора области ROI
        grp_roi = QGroupBox("Область (ROI)")
        roi_layout = QVBoxLayout(grp_roi)
        # Координаты ROI
        coord_layout1 = QHBoxLayout()
        coord_layout2 = QHBoxLayout()
        coord_layout1.addWidget(QLabel("x1:"))
        self._spin_roi_x1 = QSpinBox()
        self._spin_roi_x1.setRange(0, 639)
        coord_layout1.addWidget(self._spin_roi_x1)
        coord_layout1.addWidget(QLabel("y1:"))
        self._spin_roi_y1 = QSpinBox()
        self._spin_roi_y1.setRange(0, 479)
        coord_layout1.addWidget(self._spin_roi_y1)
        coord_layout2.addWidget(QLabel("x2:"))
        self._spin_roi_x2 = QSpinBox()
        self._spin_roi_x2.setRange(0, 639)
        coord_layout2.addWidget(self._spin_roi_x2)
        coord_layout2.addWidget(QLabel("y2:"))
        self._spin_roi_y2 = QSpinBox()
        self._spin_roi_y2.setRange(0, 479)
        coord_layout2.addWidget(self._spin_roi_y2)
        roi_layout.addLayout(coord_layout1)
        roi_layout.addLayout(coord_layout2)
        # Кнопки ROI
        roi_btn_layout = QHBoxLayout()
        self._btn_set_roi = QPushButton("Задать ROI")
        self._btn_clear_roi = QPushButton("Сбросить ROI/линии")
        roi_btn_layout.addWidget(self._btn_set_roi)
        roi_btn_layout.addWidget(self._btn_clear_roi)
        roi_layout.addLayout(roi_btn_layout)
        layout.addWidget(grp_roi)
        
        # Группа линий
        grp_lines = QGroupBox("Линии")
        lines_layout = QVBoxLayout(grp_lines)
        line_coord1 = QHBoxLayout()
        line_coord2 = QHBoxLayout()
        line_coord1.addWidget(QLabel("x1:"))
        self._spin_line_x1 = QSpinBox()
        self._spin_line_x1.setRange(0, 639)
        line_coord1.addWidget(self._spin_line_x1)
        line_coord1.addWidget(QLabel("y1:"))
        self._spin_line_y1 = QSpinBox()
        self._spin_line_y1.setRange(0, 479)
        line_coord1.addWidget(self._spin_line_y1)
        line_coord2.addWidget(QLabel("x2:"))
        self._spin_line_x2 = QSpinBox()
        self._spin_line_x2.setRange(0, 639)
        line_coord2.addWidget(self._spin_line_x2)
        line_coord2.addWidget(QLabel("y2:"))
        self._spin_line_y2 = QSpinBox()
        self._spin_line_y2.setRange(0, 479)
        line_coord2.addWidget(self._spin_line_y2)
        lines_layout.addLayout(line_coord1)
        lines_layout.addLayout(line_coord2)
        self._btn_add_line = QPushButton("Добавить линию")
        self._btn_add_line.setEnabled(False)
        lines_layout.addWidget(self._btn_add_line)
        layout.addWidget(grp_lines)
        
        # Группа настроек анализа
        grp_settings = QGroupBox("Настройки анализа")
        settings_layout = QFormLayout(grp_settings)
        self._combo_method = QComboBox()
        self._combo_method.addItem("Быстрый")   # fast
        self._combo_method.addItem("Точный")    # precise
        self._combo_object_type = QComboBox()
        self._combo_object_type.addItem("Плоская")  # flat
        self._combo_object_type.addItem("Круглая")  # round
        settings_layout.addRow("Метод:", self._combo_method)
        settings_layout.addRow("Тип объекта:", self._combo_object_type)
        layout.addWidget(grp_settings)
        
        # Группа результатов анализа
        grp_results = QGroupBox("Результаты анализа")
        results_layout = QVBoxLayout(grp_results)
        self._text_analysis_results = QTextEdit()
        self._text_analysis_results.setReadOnly(True)
        self._text_analysis_results.setMaximumHeight(150)
        results_layout.addWidget(self._text_analysis_results)
        layout.addWidget(grp_results)
        
        # Группа записи результатов
        grp_record = QGroupBox("Запись результатов")
        record_layout = QHBoxLayout(grp_record)
        self._btn_start_record = QPushButton("Начать запись")
        self._btn_stop_record = QPushButton("Остановить запись")
        self._btn_stop_record.setEnabled(False)
        record_layout.addWidget(self._btn_start_record)
        record_layout.addWidget(self._btn_stop_record)
        layout.addWidget(grp_record)
        
        layout.addStretch()
        self._tab_widget.addTab(analysis_tab, "Анализ")
        
        # Установка начальных значений combobox согласно текущим настройкам AnalysisService
        if self._analysis_service.method == "precise":
            self._combo_method.setCurrentIndex(1)
        else:
            self._combo_method.setCurrentIndex(0)
        if self._analysis_service.object_type == "round":
            self._combo_object_type.setCurrentIndex(1)
        else:
            self._combo_object_type.setCurrentIndex(0)

    def _setup_logs_tab(self):
        """Настройка вкладки логов."""
        logs_tab = QWidget()
        layout = QVBoxLayout(logs_tab)
        
        self._text_log = QTextEdit()
        self._text_log.setReadOnly(True)
        
        btn_layout = QHBoxLayout()
        self._btn_clear_log = QPushButton("Очистить лог")
        btn_layout.addStretch()
        btn_layout.addWidget(self._btn_clear_log)
        
        layout.addWidget(self._text_log)
        layout.addLayout(btn_layout)
        
        self._tab_widget.addTab(logs_tab, "Логи")

    def _setup_signals(self):
        """Настройка сигналов и слотов."""
        # Камера
        self._btn_connect_camera.clicked.connect(self._on_connect_camera_clicked)
        self._btn_disconnect_camera.clicked.connect(self._on_disconnect_camera_clicked)
        self._btn_start_live_view.clicked.connect(self._on_start_live_view_clicked)
        self._btn_stop_live_view.clicked.connect(self._on_stop_live_view_clicked)
        
        # Контроллер
        self._btn_refresh_ports.clicked.connect(self._load_available_com_ports)
        self._btn_connect_controller.clicked.connect(self._on_connect_controller_clicked)
        self._btn_send_command.clicked.connect(self._on_send_command_clicked)
        self._btn_test_homing.clicked.connect(self._on_test_homing_clicked)
        
        # Анализ
        self._btn_set_roi.clicked.connect(self._on_set_roi_clicked)
        self._btn_clear_roi.clicked.connect(self._on_clear_roi_clicked)
        self._btn_add_line.clicked.connect(self._on_add_line_clicked)
        self._combo_method.currentIndexChanged.connect(self._on_method_changed)
        self._combo_object_type.currentIndexChanged.connect(self._on_object_type_changed)
        self._btn_start_record.clicked.connect(self._on_start_record_clicked)
        self._btn_stop_record.clicked.connect(self._on_stop_record_clicked)
        
        # Логи
        self._btn_clear_log.clicked.connect(self._text_log.clear)
        
        # Подписки на сервисы
        self._camera_service.on_frame_ready = self._on_camera_frame_ready
        self._camera_service.on_error = self._on_camera_error
        self._controller_service.on_data_received = self._on_controller_data_received
        self._controller_service.on_error = self._on_controller_error
        self._controller_service.on_connected = self._on_controller_connected
        self._controller_service.on_disconnected = self._on_controller_disconnected

    def _setup_timers(self):
        """Настройка таймеров."""
        self._live_view_timer = QTimer()
        self._live_view_timer.timeout.connect(self._update_camera_preview)
        self._live_view_timer.setInterval(100)  # 10 FPS

    def _setup_logger_callback(self):
        """Настройка callback для логгера."""
        # Сохраняем оригинальный callback
        original_callback = self._logger.on_line_logged
        
        def debug_log_callback(line: str):
            # Вызываем оригинальный callback
            if original_callback:
                original_callback(line)
            # Обновляем UI
            self._append_log_line(line)
        
        self._logger.on_line_logged = debug_log_callback

    def _append_log_line(self, line: str):
        """Добавляет строку в лог в потоке UI."""
        if self._text_log:
            self._text_log.append(line)
            # Автопрокрутка
            cursor = self._text_log.textCursor()
            cursor.movePosition(cursor.End)
            self._text_log.setTextCursor(cursor)
            self._text_log.ensureCursorVisible()

    # --- Обработчики событий UI ---
    def _on_connect_camera_clicked(self):
        """Обработчик кнопки подключения камеры."""
        try:
            config_path = "pi640_config.xml"
            if self._camera_service.connect(config_path):
                self._logger.log_info(LogCategory.UI, "[DEBUG] Камера подключена")
                self._btn_connect_camera.setEnabled(False)
                self._btn_disconnect_camera.setEnabled(True)
            else:
                QMessageBox.warning(self, "Ошибка", "Не удалось подключить камеру")
        except Exception as e:
            error_msg = f"Ошибка подключения камеры: {e}"
            self._logger.log_error(LogCategory.UI, f"[DEBUG] {error_msg}")
            QMessageBox.critical(self, "Ошибка", error_msg)

    def _on_disconnect_camera_clicked(self):
        """Обработчик кнопки отключения камеры."""
        try:
            self._camera_service.disconnect()
            self._logger.log_info(LogCategory.UI, "[DEBUG] Камера отключена")
            self._btn_connect_camera.setEnabled(True)
            self._btn_disconnect_camera.setEnabled(False)
            self._stop_live_view()
        except Exception as e:
            error_msg = f"Ошибка отключения камеры: {e}"
            self._logger.log_error(LogCategory.UI, f"[DEBUG] {error_msg}")
            QMessageBox.critical(self, "Ошибка", error_msg)

    def _on_start_live_view_clicked(self):
        """Обработчик кнопки запуска Live View."""
        if not self._camera_service.is_connected():
            QMessageBox.warning(self, "Ошибка", "Камера не подключена")
            return
        self._start_live_view()

    def _on_stop_live_view_clicked(self):
        """Обработчик кнопки остановки Live View."""
        self._stop_live_view()

    def _start_live_view(self):
        """Запускает режим реального времени камеры."""
        try:
            self._camera_service.start_live_view()
            self._live_view_timer.start()
            self._is_live_view_running = True
            self._btn_start_live_view.setEnabled(False)
            self._btn_stop_live_view.setEnabled(True)
            self._logger.log_info(LogCategory.UI, "[DEBUG] Запущен режим реального времени камеры")
        except Exception as e:
            error_msg = f"Ошибка запуска Live View: {e}"
            self._logger.log_error(LogCategory.UI, f"[DEBUG] {error_msg}")
            QMessageBox.critical(self, "Ошибка", error_msg)

    def _stop_live_view(self):
        """Останавливает режим реального времени камеры."""
        self._live_view_timer.stop()
        self._camera_service.stop_live_view()
        self._is_live_view_running = False
        self._btn_start_live_view.setEnabled(True)
        self._btn_stop_live_view.setEnabled(False)
        self._logger.log_info(LogCategory.UI, "[DEBUG] Остановлен режим реального времени камеры")

    def _on_connect_controller_clicked(self):
        """Обработчик кнопки подключения контроллера."""
        if self._combo_com_ports.currentText() == "":
            QMessageBox.warning(self, "Ошибка", "Выберите COM-порт")
            return
        port = self._combo_com_ports.currentText()
        try:
            self._btn_connect_controller.setEnabled(False)
            baudrate = 115200
            if self._controller_service.connect(port, baudrate):
                self._logger.log_info(LogCategory.UI, f"[DEBUG] Контроллер подключен к {port}")
                # Статус обновится через on_controller_connected
            else:
                QMessageBox.warning(self, "Ошибка", "Не удалось подключить контроллер")
                self._btn_connect_controller.setEnabled(True)
        except Exception as e:
            error_msg = f"Ошибка подключения контроллера: {e}"
            self._logger.log_error(LogCategory.UI, f"[DEBUG] {error_msg}")
            QMessageBox.critical(self, "Ошибка", error_msg)
            self._btn_connect_controller.setEnabled(True)

    def _on_send_command_clicked(self):
        """Обработчик кнопки отправки команды контроллеру."""
        if not self._controller_service.is_connected():
            QMessageBox.warning(self, "Ошибка", "Контроллер не подключен")
            return
        command = self._text_command.toPlainText().strip()
        if not command:
            QMessageBox.warning(self, "Ошибка", "Введите команду")
            return
        try:
            self._logger.log_debug(LogCategory.UI, f"[DEBUG] Отправка команды: {command}")
            self._controller_service.send_command(command)
            self._text_response.setPlainText("Команда отправлена. Ожидайте ответ...")
        except Exception as e:
            error_msg = f"Ошибка отправки команды: {e}"
            self._text_response.setPlainText(error_msg)
            self._logger.log_error(LogCategory.UI, f"[DEBUG] {error_msg}")

    def _on_test_homing_clicked(self):
        """Обработчик кнопки тестирования homing."""
        try:
            if not self._controller_service.is_connected():
                QMessageBox.warning(self, "Ошибка", "Контроллер не подключен")
                return
            self._logger.log_info(LogCategory.UI, "[DEBUG] Начало механической калибровки (homing)...")
            self._controller_service.send_command("home")
            self._logger.log_info(LogCategory.UI, "[DEBUG] Команда homing отправлена")
            QMessageBox.information(self, "Успех", "Команда механической калибровки отправлена")
        except Exception as e:
            error_msg = f"Ошибка механической калибровки: {e}"
            self._logger.log_error(LogCategory.UI, f"[DEBUG] {error_msg}")
            QMessageBox.critical(self, "Ошибка", error_msg)

    def _on_set_roi_clicked(self):
        """Обработчик кнопки задания ROI."""
        x1 = self._spin_roi_x1.value()
        y1 = self._spin_roi_y1.value()
        x2 = self._spin_roi_x2.value()
        y2 = self._spin_roi_y2.value()
        was_recording = self._analysis_service.is_recording
        try:
            self._analysis_service.set_roi(x1, y1, x2, y2)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось задать ROI: {e}")
            return
        # Включаем возможность добавлять линии, отключаем запись (пока нет линий)
        self._btn_add_line.setEnabled(True)
        self._btn_start_record.setEnabled(False)
        # Если во время изменения ROI шла запись – она остановлена
        if was_recording:
            self._btn_stop_record.setEnabled(False)
            QMessageBox.information(self, "Запись остановлена", 
                                    "Из-за изменения ROI запись результатов была остановлена.")

    def _on_clear_roi_clicked(self):
        """Обработчик кнопки сброса ROI и линий."""
        try:
            self._analysis_service.clear_lines()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка сброса ROI/линий: {e}")
            return
        # Отключаем ввод линий и запись
        self._btn_add_line.setEnabled(False)
        self._btn_start_record.setEnabled(False)
        self._btn_stop_record.setEnabled(False)
        # Очищаем вывод результатов
        self._text_analysis_results.clear()

    def _on_add_line_clicked(self):
        """Обработчик кнопки добавления линии анализа."""
        if self._analysis_service.roi is None:
            QMessageBox.warning(self, "Ошибка", "Сначала задайте область ROI")
            return
        x1 = self._spin_line_x1.value()
        y1 = self._spin_line_y1.value()
        x2 = self._spin_line_x2.value()
        y2 = self._spin_line_y2.value()
        try:
            self._analysis_service.add_line(x1, y1, x2, y2)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось добавить линию: {e}")
            return
        # После добавления первой линии разрешаем запись результатов
        if len(self._analysis_service.lines) > 0:
            self._btn_start_record.setEnabled(True)

    def _on_start_record_clicked(self):
        """Обработчик кнопки начала записи результатов."""
        if not self._analysis_service.roi or len(self._analysis_service.lines) == 0:
            QMessageBox.warning(self, "Ошибка", "Нет данных для записи. Выберите ROI и линии.")
            return
        try:
            started = self._analysis_service.start_recording()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка при начале записи: {e}")
            return
        if not started:
            # Не удалось начать запись (например, нет ROI/линий или ошибка открытия файла)
            QMessageBox.warning(self, "Ошибка", "Не удалось начать запись результатов. Убедитесь, что выбраны область и линии.")
        else:
            self._logger.log_info(LogCategory.UI, "[DEBUG] Запись результатов начата")
            self._btn_start_record.setEnabled(False)
            self._btn_stop_record.setEnabled(True)
            # На время записи запрещаем добавлять новые линии
            self._btn_add_line.setEnabled(False)

    def _on_stop_record_clicked(self):
        """Обработчик кнопки остановки записи результатов."""
        try:
            if self._analysis_service.is_recording:
                self._analysis_service.stop_recording()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка при остановке записи: {e}")
            return
        # Запись остановлена
        self._logger.log_info(LogCategory.UI, "[DEBUG] Запись результатов остановлена")
        self._btn_start_record.setEnabled(True)
        self._btn_stop_record.setEnabled(False)
        # Разрешаем добавлять линии снова (если ROI еще задан)
        if self._analysis_service.roi is not None:
            self._btn_add_line.setEnabled(True)

    def _on_method_changed(self, index: int):
        """Обработчик изменения метода анализа."""
        method = "fast" if index == 0 else "precise"
        try:
            self._analysis_service.method = method
            method_str = "быстрый" if method == "fast" else "точный"
            self._logger.log_info(LogCategory.UI, f"[DEBUG] Установлен метод анализа: {method_str}")
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось изменить метод анализа: {e}")

    def _on_object_type_changed(self, index: int):
        """Обработчик изменения типа поверхности объекта."""
        object_type = "flat" if index == 0 else "round"
        try:
            self._analysis_service.object_type = object_type
            # AnalysisService сам пишет лог об изменении типа поверхности
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось изменить тип объекта: {e}")

    # --- Обработчики событий от сервисов ---
    def _on_camera_frame_ready(self, frame: np.ndarray):
        """Обработчик нового кадра от камеры."""
        self._current_frame = frame.copy()

    def _on_camera_error(self, error_msg: str):
        """Обработчик ошибок камеры."""
        self._logger.log_error(LogCategory.UI, f"[DEBUG] Ошибка камеры: {error_msg}")
        # Останавливаем live view при ошибке
        if self._is_live_view_running:
            self._stop_live_view()

    def _on_controller_data_received(self, data: str):
        """Обработчик получения данных от контроллера."""
        # Проверяем, если это ответ на команду
        if self._text_response and "command" in self._text_response.toPlainText():
            self._text_response.setPlainText(data)
        self._logger.log_debug(LogCategory.UI, f"[DEBUG] Данные от контроллера: {data}")

    def _on_controller_error(self, error_msg: str):
        """Обработчик ошибок контроллера."""
        self._logger.log_error(LogCategory.UI, f"[DEBUG] Ошибка контроллера: {error_msg}")
        # Восстанавливаем кнопку подключения
        self._btn_connect_controller.setEnabled(True)

    def _on_controller_connected(self):
        """Обработчик события подключения контроллера."""
        self._btn_connect_controller.setEnabled(True)
        self._update_connection_status()

    def _on_controller_disconnected(self):
        """Обработчик события отключения контроллера."""
        self._btn_connect_controller.setEnabled(True)
        self._update_connection_status()

    # --- Вспомогательные методы ---
    def _update_connection_status(self):
        """Обновляет статус подключения в UI."""
        # В реальном приложении можно добавить QLabel для отображения статуса
        pass

    def _load_available_com_ports(self):
        """Загружает список доступных COM-портов."""
        try:
            ports = Stm32ControllerService.get_available_ports()
            self._combo_com_ports.clear()
            self._combo_com_ports.addItems(ports)
            if ports:
                self._combo_com_ports.setCurrentIndex(0)
        except Exception as e:
            self._logger.log_error(LogCategory.UI, f"[DEBUG] Ошибка получения списка COM-портов: {e}")

    def _update_camera_preview(self):
        """Обновляет изображение в предварительном просмотре."""
        if self._current_frame is not None and self._label_camera_preview:
            try:
                # Преобразование numpy массива в QImage
                frame = self._current_frame
                if frame.dtype == np.uint16:
                    # Нормализация uint16 -> uint8 для отображения
                    frame_normalized = ((frame.astype(np.float32) - frame.min()) /
                                        (frame.max() - frame.min()) * 255).astype(np.uint8)
                else:
                    frame_normalized = frame.astype(np.uint8)
                height, width = frame_normalized.shape
                bytes_per_line = width
                q_img = QImage(frame_normalized.data, width, height, bytes_per_line, QImage.Format_Grayscale8)
                pixmap = QPixmap.fromImage(q_img)
                self._label_camera_preview.setPixmap(
                    pixmap.scaled(
                        self._label_camera_preview.size(),
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation
                    )
                )
            except Exception as e:
                self._logger.log_error(LogCategory.UI, f"[DEBUG] Ошибка обновления превью: {e}")
            # Обновляем результаты анализа для текущего кадра
            try:
                results = self._analysis_service.process_frame(self._current_frame)
                if results:
                    # Формируем текст с результатами для каждой линии
                    lines_text = []
                    for i, (avg_val, min_val, max_val) in enumerate(results, start=1):
                        lines_text.append(f"Линия {i}: ср={avg_val:.2f}, мин={min_val:.2f}, макс={max_val:.2f}")
                    self._text_analysis_results.setPlainText("\n".join(lines_text))
                else:
                    # Если нет выбранных ROI/линий, подсказываем пользователю
                    self._text_analysis_results.setPlainText("Выберите область ROI и линии для анализа.")
                # Автопрокрутка к концу (на случай накопления строк)
                self._text_analysis_results.moveCursor(self._text_analysis_results.textCursor().End)
            except Exception as e:
                self._logger.log_error(LogCategory.UI, f"[DEBUG] Ошибка анализа кадра: {e}")

    def closeEvent(self, event):
        """Обработчик события закрытия окна."""
        # Остановка таймеров и освобождение ресурсов
        self._live_view_timer.stop()
        if self._is_live_view_running:
            self._stop_live_view()
        # Остановка записи результатов, если она шла
        if self._analysis_service and self._analysis_service.is_recording:
            try:
                self._analysis_service.stop_recording()
            except Exception:
                pass
        # Отписываемся от событий
        self._camera_service.on_frame_ready = None
        self._camera_service.on_error = None
        self._controller_service.on_data_received = None
        self._controller_service.on_error = None
        self._controller_service.on_connected = None
        self._controller_service.on_disconnected = None
        
        event.accept()
