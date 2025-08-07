# src/main.py
"""
Точка входа в приложение MirrorScan.
Инициализирует все сервисы, загружает конфигурацию и запускает главное окно UI.
"""
import sys
import os
import argparse
import traceback
from pathlib import Path
from typing import Optional

# Добавляем корневую директорию проекта в sys.path для импортов
project_root = Path(__file__).parent.resolve()  # src directory
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# --- Импорты проекта ---
from config.config_manager import ConfigManager
from utils.logger import DataLogger, LogCategory
from hardware.stm32_controller import Stm32ControllerService
from hardware.axis_controller import AxisController
from camera.camera_service import CameraService
from calibration.calibration_service import CalibrationService
from camera.analysis_service import AnalysisService
from scan.scan_engine import ScanEngine


def create_app_dirs(app_name: str = "MirrorScan") -> Path:
    """
    Создает директории приложения в пользовательском пространстве.
    Возвращает путь к директории данных приложения.
    """
    try:
        if os.name == 'nt':  # Windows
            base_dir = Path(os.environ.get('APPDATA', Path.home() / 'AppData' / 'Roaming'))
        else:  # Linux/macOS
            base_dir = Path.home() / '.local' / 'share'

        app_dir = base_dir / app_name
        app_dir.mkdir(parents=True, exist_ok=True)
        return app_dir
    except Exception as e:
        print(f"[ERROR] Не удалось создать директории приложения по умолчанию: {e}. Используется текущая директория.")
        fallback_dir = Path.cwd() / f".{app_name.lower()}_data"
        fallback_dir.mkdir(exist_ok=True)
        return fallback_dir


def main():
    """Основная точка входа в приложение."""

    print("Debug: Starting main function")

    parser = argparse.ArgumentParser(
        description="MirrorScan - Сканирование зеркал",
        epilog="Примеры:\n"
               "  python src/main.py                        # Запуск с дефолтным config.json и pi640_config.xml\n"
               "  python src/main.py --config my_conf.json  # Использовать другой JSON-конфиг\n"
               "  python src/main.py --no-xml-config        # Подключение камеры без XML-файла (если поддерживается DLL)\n"
               "  python src/main.py --debug                # Включить подробное логирование",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--debug', action='store_true', help='Включить подробное логирование (DEBUG)')
    parser.add_argument('--config', type=str, default='config.json',
                        help='Путь к файлу конфигурации JSON (по умолчанию: config.json)')
    parser.add_argument('--no-xml-config', action='store_true',
                        help='Не использовать XML-файл конфигурации для камеры (попытка инициализации без него)')

    args = parser.parse_args()

    # --- 1. Инициализация путей и логгера ---
    app_data_dir = create_app_dirs()
    default_scan_file = app_data_dir / "scan_data.csv"
    log_file_path = app_data_dir / "app.log"
    default_calibration_file = app_data_dir / "calibration_data.json"
    default_camera_xml_config = "pi640_config.xml"  # Дефолтный путь к XML

    print(f"[INFO] Директория данных приложения: {app_data_dir}")

    logger: Optional[DataLogger] = None
    try:
        logger = DataLogger(str(log_file_path))
        log_level = "DEBUG" if args.debug else "INFO"
        logger.log_info(LogCategory.GENERAL, f"=== Запуск приложения MirrorScan (Уровень лога: {log_level}) ===")
        if args.debug:
            logger.log_info(LogCategory.GENERAL, "Режим отладки ВКЛЮЧЕН")
        if args.no_xml_config:
            logger.log_info(LogCategory.GENERAL,
                            "Запуск с опцией --no-xml-config. Камера будет инициализирована без XML-файла.")
    except Exception as e:
        print(f"[CRITICAL] Не удалось инициализировать логгер: {e}")
        sys.exit(1)

    # --- 2. Загрузка конфигурации ---
    config = None
    try:
        config_path = str(project_root / args.config)  # Absolute path
        logger.log_info(LogCategory.GENERAL, f"Загрузка конфигурации из '{config_path}'")
        config = ConfigManager.load(config_path)
        logger.log_info(LogCategory.GENERAL, "Конфигурация загружена успешно")
    except Exception as e:
        logger.log_error(LogCategory.GENERAL, f"Критическая ошибка загрузки конфигурации: {e}")
        logger.log_error(LogCategory.GENERAL, traceback.format_exc())
        sys.exit(1)

    # --- 3. Инициализация сервисов ---
    controller_service: Optional[Stm32ControllerService] = None
    camera_service: Optional[CameraService] = None
    x_axis: Optional[AxisController] = None
    theta_axis: Optional[AxisController] = None
    calibration_service: Optional[CalibrationService] = None
    scan_engine: Optional[ScanEngine] = None
    analysis_service: Optional['AnalysisService'] = None

    try:
        logger.log_info(LogCategory.GENERAL, "Инициализация сервисов...")

        # Сервис контроллера
        controller_service = Stm32ControllerService(logger)
        logger.log_debug(LogCategory.GENERAL, "Сервис Stm32ControllerService создан")

        # Сервис камеры
        # Определяем путь к XML-файлу конфигурации для камеры
        camera_xml_config_path = None if args.no_xml_config else default_camera_xml_config
        camera_service = CameraService(logger)
        logger.log_debug(LogCategory.GENERAL, f"Сервис CameraService создан. XML конфиг: {camera_xml_config_path}")

        # Сервис калибровки камеры
        calib_file_path = config.camera.calibration_file_path or str(default_calibration_file)
        calibration_service = CalibrationService(camera_service, logger, calib_file_path)
        logger.log_debug(LogCategory.GENERAL, f"Сервис CalibrationService создан (файл: {calib_file_path})")

        # Попытка загрузить существующую калибровку
        try:
            if os.path.exists(calib_file_path):
                calibration_service.load_calibration(calib_file_path)
                logger.log_info(LogCategory.GENERAL, f"Калибровка загружена из '{calib_file_path}'")
            else:
                logger.log_info(LogCategory.GENERAL,
                                f"Файл калибровки '{calib_file_path}' не найден. Будет создана новая калибровка.")
        except Exception as e:
            logger.log_warn(LogCategory.GENERAL, f"Не удалось загрузить калибровку: {e}")

        # Сервис анализа изображений
        analysis_service = AnalysisService(logger)
        logger.log_debug(LogCategory.GENERAL, "Сервис AnalysisService создан")

        # Контроллеры осей
        x_axis = AxisController(controller_service, "X", config, logger)
        theta_axis = AxisController(controller_service, "THETA", config, logger)
        logger.log_debug(LogCategory.GENERAL, "Контроллеры осей X и THETA созданы")

        # Движок сканирования
        scan_engine = ScanEngine(x_axis, theta_axis, camera_service, logger)
        logger.log_debug(LogCategory.GENERAL, "Движок сканирования ScanEngine создан")

        logger.log_info(LogCategory.GENERAL, "Все сервисы инициализированы")

    except Exception as e:
        logger.log_error(LogCategory.GENERAL, f"Критическая ошибка инициализации сервисов: {e}")
        logger.log_error(LogCategory.GENERAL, traceback.format_exc())
        sys.exit(1)

    # --- 4. Запуск графического интерфейса ---
    try:
        logger.log_info(LogCategory.GENERAL, "Запуск графического интерфейса...")
        print("Debug: Importing PyQt5 and UI modules")

        from PyQt5.QtWidgets import QApplication

        print("Debug: PyQt5 imported successfully")
        app = QApplication(sys.argv)
        app.setApplicationName("MirrorScan")
        app.setApplicationVersion("1.0.0")

        from ui.main_window import MainWindow

        print("Debug: MainWindow imported successfully")

        # Передаем все созданные и инициализированные сервисы в главное окно
        # Также передаем флаг --no-xml-config, чтобы UI мог отразить это
        main_window = MainWindow(
            logger=logger,
            config=config,
            controller_service=controller_service,
            camera_service=camera_service,
            analysis_service=analysis_service,
            x_axis=x_axis,
            theta_axis=theta_axis,
            calibration_service=calibration_service,
            scan_engine=scan_engine,
            default_scan_file_path=str(default_scan_file),
            no_xml_config=args.no_xml_config
        )
        print("Debug: MainWindow instance created")
        main_window.show()
        print("Debug: MainWindow shown")

        logger.log_info(LogCategory.GENERAL, "Главное окно отображено. Запуск цикла событий Qt.")

        # --- 5. Цикл событий Qt ---
        exit_code = app.exec_()

        logger.log_info(LogCategory.GENERAL, f"Цикл событий Qt завершен с кодом {exit_code}")

    except ImportError as e:
        logger.log_error(LogCategory.GENERAL, f"Не удалось импортировать PyQt5 или UI модули: {e}")
        print(f"[ERROR] Зависимость не найдена: {e}")
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        logger.log_error(LogCategory.GENERAL, f"Критическая ошибка при запуске GUI: {e}")
        logger.log_error(LogCategory.GENERAL, traceback.format_exc())
        print(f"[CRITICAL ERROR] {e}")
        traceback.print_exc()
        sys.exit(1)

    # --- 6. Завершение работы и очистка ресурсов ---
    finally:
        logger.log_info(LogCategory.GENERAL, "Начало процедуры завершения работы и очистки ресурсов...")
        try:
            # Останавливаем сканирование, если оно активно
            if scan_engine and scan_engine.is_running():
                logger.log_info(LogCategory.GENERAL, "Остановка движка сканирования...")
                scan_engine.stop_scan()

            # Отключаем контроллер
            if controller_service and controller_service.is_connected():
                logger.log_info(LogCategory.GENERAL, "Отключение контроллера...")
                controller_service.disconnect()

            # Отключаем камеру
            if camera_service and camera_service.is_connected():
                logger.log_info(LogCategory.GENERAL, "Отключение камеры...")
                camera_service.disconnect()

        except Exception as e:
            logger.log_warn(LogCategory.GENERAL, f"Ошибка при очистке ресурсов: {e}")

        logger.log_info(LogCategory.GENERAL, "=== Приложение завершено ===")
        # Логгер автоматически закроется при уничтожении объекта

    sys.exit(exit_code if 'exit_code' in locals() else 0)


if __name__ == "__main__":
    main()