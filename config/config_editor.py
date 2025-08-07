# src/ui/config_editor.py
"""
Окно редактора конфигурации шаговых двигателей (.cfg).
Совместим с форматом оригинальной C# программы.
"""
import sys
from typing import List, Optional
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QMessageBox, QHeaderView, QFileDialog, QAbstractItemView,
    QStyledItemDelegate, QLineEdit, QToolTip
)
from PyQt5.QtCore import Qt, QEvent, QRect
from PyQt5.QtGui import QValidator, QHelpEvent

# Импорты из нашего проекта
from config.config_model import StepperConfig
from config.config_manager import ConfigManager
from utils.logger import DataLogger, LogCategory


class IntegerValidator(QValidator):
    """Валидатор для целых чисел."""
    def __init__(self, min_value: Optional[int] = None, max_value: Optional[int] = None, parent=None):
        super().__init__(parent)
        self.min_value = min_value
        self.max_value = max_value

    def validate(self, input_str: str, pos: int):
        if not input_str:
            return QValidator.Intermediate, input_str, pos

        try:
            value = int(input_str)
            if self.min_value is not None and value < self.min_value:
                return QValidator.Invalid, input_str, pos
            if self.max_value is not None and value > self.max_value:
                return QValidator.Invalid, input_str, pos
            return QValidator.Acceptable, input_str, pos
        except ValueError:
            return QValidator.Invalid, input_str, pos


class DoubleValidator(QValidator):
    """Валидатор для чисел с плавающей точкой."""
    def __init__(self, min_value: Optional[float] = None, max_value: Optional[float] = None, parent=None):
        super().__init__(parent)
        self.min_value = min_value
        self.max_value = max_value

    def validate(self, input_str: str, pos: int):
        if not input_str:
            return QValidator.Intermediate, input_str, pos

        try:
            value = float(input_str)
            if self.min_value is not None and value < self.min_value:
                return QValidator.Invalid, input_str, pos
            if self.max_value is not None and value > self.max_value:
                return QValidator.Invalid, input_str, pos
            return QValidator.Acceptable, input_str, pos
        except ValueError:
            return QValidator.Invalid, input_str, pos


class ValidatingDelegate(QStyledItemDelegate):
    """Делегат для валидации ячеек таблицы."""
    def __init__(self, parent=None):
        super().__init__(parent)
        # Карта валидаторов для столбцов: {column_index: validator_instance}
        # Индексы соответствуют порядку в config.cfg
        self._validators = {
            0: IntegerValidator(min_value=1),  # Spd
            1: IntegerValidator(min_value=1),  # Acc
            2: IntegerValidator(min_value=0, max_value=255),  # Cur
            3: IntegerValidator(min_value=0, max_value=255),  # CurH
            4: IntegerValidator(),  # Max (int)
            5: IntegerValidator(min_value=0, max_value=7),  # Microstep
            6: IntegerValidator(min_value=1),  # RotateSteps
            7: IntegerValidator(min_value=1),  # Deceleration
            8: DoubleValidator(min_value=0.0001),  # Pitch
        }
        # Подсказки для столбцов
        self._tooltips = {
            0: "Speed: Положительное целое >0 (шагов/сек)",
            1: "Acceleration: Положительное целое >0 (шагов/сек²)",
            2: "Current (run): Неотрицательное целое 0-255",
            3: "Current (hold): Неотрицательное целое 0-255",
            4: "Max value: Целое (макс. шагов)",
            5: "Microstep power: Целое 0-7 (0=full, 7=1/128)",
            6: "Steps per rotation: Положительное целое >0 (обычно 200)",
            7: "Deceleration: Положительное целое >0 (шагов/сек²)",
            8: "Pitch (mm/rev): Положительное число >0 (e.g., 8.0 for T8 screw)",
        }

    def createEditor(self, parent, option, index):
        """Создает редактор для ячейки."""
        editor = QLineEdit(parent)
        column = index.column()
        if column in self._validators:
            editor.setValidator(self._validators[column])
        # Устанавливаем подсказку
        if column in self._tooltips:
            editor.setToolTip(self._tooltips[column])
        return editor

    def eventFilter(self, editor, event):
        """Фильтр событий для отображения подсказок."""
        if event.type() == QEvent.ToolTip and isinstance(event, QHelpEvent):
            # Показываем подсказку при наведении на редактор
            column = self.parent().currentIndex().column() if self.parent() else -1
            if column in self._tooltips:
                QToolTip.showText(event.globalPos(), self._tooltips[column], editor)
                return True
        return super().eventFilter(editor, event)


class ConfigEditorWindow(QMainWindow):
    """
    Окно редактора конфигурации шаговых двигателей.
    """
    def __init__(self, logger: DataLogger, config_file_path: str):
        super().__init__()
        self._logger = logger
        self._config_file_path = config_file_path
        self._stepper_configs: List[StepperConfig] = []

        # --- UI компоненты ---
        self._table: QTableWidget
        self._btn_save: QPushButton
        self._btn_cancel: QPushButton

        # --- Инициализация ---
        self._setup_ui()
        self._setup_signals()
        self._load_configs()

    def _setup_ui(self):
        """Настройка пользовательского интерфейса."""
        self.setWindowTitle("Edit config.cfg - MirrorScan")
        self.resize(900, 300)
        self.setMinimumSize(700, 250)

        # Центральный виджет
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Таблица
        self._table = QTableWidget()
        self._table.setColumnCount(9)
        self._table.setHorizontalHeaderLabels([
            "Spd", "Acc", "Cur", "CurH", "Max", "Microstep", "RotateSteps", "Deceleration", "Pitch"
        ])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        # Разрешаем редактирование
        self._table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        
        # Устанавливаем делегат для валидации
        delegate = ValidatingDelegate(self._table)
        self._table.setItemDelegate(delegate)

        layout.addWidget(self._table)

        # Кнопки
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self._btn_save = QPushButton("Save")
        self._btn_save.setStyleSheet("background-color: lightgreen;")
        self._btn_cancel = QPushButton("Cancel")

        button_layout.addWidget(self._btn_save)
        button_layout.addWidget(self._btn_cancel)

        layout.addLayout(button_layout)

    def _setup_signals(self):
        """Настройка сигналов и слотов."""
        self._btn_save.clicked.connect(self._on_save_clicked)
        self._btn_cancel.clicked.connect(self.close) # Простое закрытие

    def _load_configs(self):
        """Загружает конфигурации из файла и отображает в таблице."""
        try:
            self._stepper_configs = ConfigManager.load_stepper_configs_from_cfg(self._config_file_path)
            self._display_configs_in_table()
            self._logger.log_info(LogCategory.UI, f"Stepper configs loaded from {self._config_file_path}")
        except Exception as e:
            error_msg = f"Error loading configs: {e}"
            self._logger.log_error(LogCategory.UI, error_msg)
            QMessageBox.critical(self, "Error", error_msg)

    def _display_configs_in_table(self):
        """Отображает текущие конфигурации в таблице."""
        self._table.setRowCount(len(self._stepper_configs))
        for row, config in enumerate(self._stepper_configs):
            # spd
            item = QTableWidgetItem(str(config.spd))
            item.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(row, 0, item)
            # acc
            item = QTableWidgetItem(str(config.acc))
            item.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(row, 1, item)
            # cur
            item = QTableWidgetItem(str(config.cur))
            item.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(row, 2, item)
            # curh
            item = QTableWidgetItem(str(config.curh))
            item.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(row, 3, item)
            # max_steps
            item = QTableWidgetItem(str(config.max_steps))
            item.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(row, 4, item)
            # microstep
            item = QTableWidgetItem(str(config.microstep))
            item.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(row, 5, item)
            # rotate_steps
            item = QTableWidgetItem(str(config.rotate_steps))
            item.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(row, 6, item)
            # deceleration
            item = QTableWidgetItem(str(config.deceleration))
            item.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(row, 7, item)
            # pitch
            item = QTableWidgetItem(f"{config.pitch:.6g}") # Используем %g для компактности, как в C#
            item.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(row, 8, item)

    def _collect_configs_from_table(self) -> List[StepperConfig]:
        """
        Собирает конфигурации из таблицы.
        Выбрасывает ValueError при некорректных данных.
        """
        configs = []
        for row in range(self._table.rowCount()):
            try:
                # Собираем значения
                spd_text = self._table.item(row, 0).text()
                acc_text = self._table.item(row, 1).text()
                cur_text = self._table.item(row, 2).text()
                curh_text = self._table.item(row, 3).text()
                max_steps_text = self._table.item(row, 4).text()
                microstep_text = self._table.item(row, 5).text()
                rotate_steps_text = self._table.item(row, 6).text()
                deceleration_text = self._table.item(row, 7).text()
                pitch_text = self._table.item(row, 8).text()
                
                # Валидация и преобразование
                spd = int(spd_text)
                acc = int(acc_text)
                cur = int(cur_text)
                curh = int(curh_text)
                max_steps = int(max_steps_text)
                microstep = int(microstep_text)
                rotate_steps = int(rotate_steps_text)
                deceleration = int(deceleration_text)
                pitch = float(pitch_text)
                
                # Создаем временную конфигурацию для валидации
                # Pydantic автоматически проверит диапазоны
                temp_config = StepperConfig(
                    axis_name=f"Axis_{row}", # Временное имя
                    spd=spd, acc=acc, cur=cur, curh=curh,
                    max_steps=max_steps, microstep=microstep,
                    rotate_steps=rotate_steps, deceleration=deceleration,
                    pitch=pitch
                )
                configs.append(temp_config)
            except (ValueError, AttributeError) as e: # AttributeError если item is None
                raise ValueError(f"Invalid data in row {row + 1}") from e
            except Exception as e:
                raise ValueError(f"Error in row {row + 1}: {e}") from e
        return configs

    # --- Обработчики событий UI ---
    def _on_save_clicked(self):
        """Обработчик кнопки 'Save'."""
        try:
            # Собираем данные из таблицы с валидацией
            self._stepper_configs = self._collect_configs_from_table()
            # Сохраняем в файл
            ConfigManager.save_stepper_configs_to_cfg(self._config_file_path, self._stepper_configs)
            self._logger.log_info(LogCategory.UI, f"Stepper configs saved to {self._config_file_path}")
            QMessageBox.information(self, "Success", f"Configs saved successfully to {self._config_file_path}")
            self.close() # Закрываем окно после сохранения
        except ValueError as e:
            error_msg = f"Data error: {e}"
            self._logger.log_warn(LogCategory.UI, f"Config validation error: {error_msg}")
            QMessageBox.warning(self, "Data Error", error_msg)
        except Exception as e:
            error_msg = f"Error saving configs: {e}"
            self._logger.log_error(LogCategory.UI, error_msg)
            QMessageBox.critical(self, "Error", error_msg)
