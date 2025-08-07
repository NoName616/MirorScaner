# src/config/config_manager.py
"""
Управление загрузкой, сохранением и валидацией конфигурации.
"""
import json
import os
from typing import List
from config.config_model import AppConfig, StepperConfig

class ConfigManager:
    """
    Менеджер конфигурации приложения.
    """
    @staticmethod
    def load(path: str = "config.json") -> AppConfig:
        """
        Загружает конфигурацию из файла JSON.
        Если файл не найден, создает конфигурацию по умолчанию и сохраняет её.
        """
        if not os.path.exists(path):
            print(f"[INFO] Файл конфигурации {path} не найден. Создаю конфигурацию по умолчанию.")
            default_config = AppConfig.default()  # Use classmethod for default
            ConfigManager.save(path, default_config)
            return default_config

        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if not content:  # Empty file
                    raise ValueError("Empty config file")
                data = json.loads(content)
            # Валидация и создание объекта конфигурации
            config = AppConfig(**data)
            print(f"[INFO] Конфигурация загружена из {path}")
            return config
        except (json.JSONDecodeError, ValueError) as e:
            print(f"[ERROR] Ошибка загрузки конфигурации из {path}: {e}. Использую конфигурацию по умолчанию.")
            default_config = AppConfig.default()
            ConfigManager.save(path, default_config)  # Overwrite invalid file
            return default_config
        except Exception as e:
            print(f"[ERROR] Ошибка загрузки конфигурации из {path}: {e}. Использую конфигурацию по умолчанию.")
            return AppConfig.default()  # Use default on error

    @staticmethod
    def save(path: str, config: AppConfig):
        """
        Сохраняет конфигурацию в файл JSON.
        """
        try:
            # Убедимся, что директория существует
            dirname = os.path.dirname(path)
            if dirname:  # Skip if empty (current dir)
                os.makedirs(dirname, exist_ok=True)
            
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(config.model_dump(), f, indent=4, ensure_ascii=False)
            print(f"[INFO] Конфигурация сохранена в {path}")
        except Exception as e:
            print(f"[ERROR] Ошибка сохранения конфигурации в {path}: {e}")

    @staticmethod
    def get_stepper_config(config: AppConfig, axis_name: str) -> StepperConfig:
        """
        Получает конфигурацию шагового двигателя для заданной оси.
        """
        for stepper in config.steppers:
            if stepper.axis_name.lower() == axis_name.lower():
                return stepper
        raise ValueError(f"Конфигурация для оси '{axis_name}' не найдена.")

    # --- Методы для работы с config.cfg (формат C#) ---

    @staticmethod
    def load_stepper_configs_from_cfg(path: str) -> List[StepperConfig]:
        """
        Загружает конфигурации шаговых двигателей из файла .cfg в формате C#.
        Формат строки: "spd 500;acc 1000;cur 100;curh 80;max 100000;microstep 4;rotatesteps 200;deceleration 1000;pitch 8.0"
        """
        configs = []
        if not os.path.exists(path):
            print(f"[INFO] Файл конфигурации двигателей {path} не найден. Создаю конфигурации по умолчанию.")
            # Создаем две конфигурации по умолчанию
            default_configs = [
                StepperConfig(axis_name="X"),
                StepperConfig(axis_name="Theta")
            ]
            ConfigManager.save_stepper_configs_to_cfg(path, default_configs)
            return default_configs

        try:
            with open(path, 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f.readlines() if line.strip() and not line.startswith('#')]
            
            # Предполагаем, что первые две строки для X и Theta
            # Если строк меньше двух, создаем недостающие с дефолтами
            axis_names = ["X", "Theta"]
            for i, line in enumerate(lines[:2]): # Обрабатываем максимум 2 строки
                config = ConfigManager._parse_cfg_line(line)
                config.axis_name = axis_names[i]
                configs.append(config)
            
            # Если в файле было меньше 2 строк, добавляем недостающие
            while len(configs) < 2:
                axis_name = axis_names[len(configs)]
                print(f"[WARN] Недостаточно строк в {path} для оси {axis_name}. Используется конфигурация по умолчанию.")
                configs.append(StepperConfig(axis_name=axis_name))
                
            print(f"[INFO] Конфигурации двигателей загружены из {path}")
            return configs
        except Exception as e:
            print(f"[ERROR] Ошибка загрузки конфигураций двигателей из {path}: {e}. Использую конфигурации по умолчанию.")
            return [StepperConfig(axis_name="X"), StepperConfig(axis_name="Theta")]

    @staticmethod
    def save_stepper_configs_to_cfg(path: str, configs: List[StepperConfig]):
        """
        Сохраняет конфигурации шаговых двигателей в файл .cfg в формате C#.
        """
        try:
            dirname = os.path.dirname(path)
            if dirname:
                os.makedirs(dirname, exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                # Записываем комментарий с форматом
                f.write("# Stepper Config Format: spd;acc;cur;curh;max;microstep;rotatesteps;deceleration;pitch\n")
                for config in configs:
                    line = ConfigManager._stepper_config_to_cfg_line(config)
                    f.write(line + '\n')
            print(f"[INFO] Конфигурации двигателей сохранены в {path}")
        except Exception as e:
            print(f"[ERROR] Ошибка сохранения конфигураций двигателей в {path}: {e}")

    @staticmethod
    def _parse_cfg_line(line: str) -> StepperConfig:
        """Парсит строку конфигурации из .cfg файла."""
        # Создаем конфиг с дефолтами, axis_name будет установлен позже
        config = StepperConfig(axis_name="TEMP") 
        parts = line.split(';')
        for part in parts:
            key_value = part.strip().split(' ', 1)
            if len(key_value) != 2:
                continue
            key, value = key_value[0].lower(), key_value[1].strip()
            try:
                if key == "spd":
                    config.spd = int(value)
                elif key == "acc":
                    config.acc = int(value)
                elif key == "cur":
                    config.cur = int(value)
                elif key == "curh":
                    config.curh = int(value)
                elif key == "max":
                    config.max_steps = int(value)
                elif key == "microstep":
                    config.microstep = int(value)
                elif key == "rotatesteps":
                    config.rotate_steps = int(value)
                elif key == "deceleration":
                    config.deceleration = int(value)
                elif key == "pitch":
                    config.pitch = float(value)
                # axis_name не сохраняется/загружается, так как определяется позицией
            except (ValueError, Exception):
                # Игнорируем ошибки парсинга, используем дефолт
                print(f"[WARN] Неверное значение в конфиге: {key}={value}. Используется значение по умолчанию.")
                continue
        return config

    @staticmethod
    def _stepper_config_to_cfg_line(config: StepperConfig) -> str:
        """Преобразует объект StepperConfig в строку для .cfg файла."""
        return (f"spd {config.spd};acc {config.acc};cur {config.cur};curh {config.curh};"
                f"max {config.max_steps};microstep {config.microstep};"
                f"rotatesteps {config.rotate_steps};deceleration {config.deceleration};"
                f"pitch {config.pitch:.6g}") # Используем %g для компактности