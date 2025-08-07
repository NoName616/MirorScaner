# src/scan/stepper_config.py
"""
Конфигурация шагового двигателя и преобразование импульсов в расстояние/угол.
"""
from typing import Optional
from pydantic import BaseModel, Field, field_validator

class StepperConfig(BaseModel):
    """
    Конфигурация для одного шагового двигателя.
    """
    axis_name: str = Field(..., description="Название оси: 'X' или 'Theta'")
    spd: int = Field(500, ge=1, le=10000, description="Скорость (шагов/с)")
    acc: int = Field(1000, ge=1, le=50000, description="Ускорение (шагов/с²)")
    deceleration: int = Field(1000, ge=1, le=50000, description="Замедление (шагов/с²)")
    cur: int = Field(100, ge=0, le=255, description="Ток удержания (0-255)")
    curh: int = Field(80, ge=0, le=255, description="Ток удержания (0-255)")
    max_steps: int = Field(100000, ge=1, description="Максимальное количество шагов")
    microstep: int = Field(4, ge=0, le=7, description="Режим микрошага (0=полный шаг, 7=1/128)")
    rotate_steps: int = Field(200, ge=1, description="Шагов на полный оборот двигателя (без учета микрошагов)")
    pitch: float = Field(8.0, gt=0, description="Шаг винта в мм на оборот")

    @field_validator('axis_name')
    @classmethod
    def validate_axis_name(cls, v):
        if v.upper() not in ['X', 'THETA']:
            raise ValueError("axis_name must be 'X' or 'Theta'")
        return v.upper()

    @property
    def microstep_factor(self) -> int:
        """
        Вычисляет множитель микрошага для драйвера L6470H.
        0 = 1/1, 1 = 1/2, ..., 7 = 1/128
        """
        return 2 ** self.microstep

    @property
    def steps_per_mm(self) -> float:
        """
        Вычисляет количество шагов на миллиметр для линейной оси (X).
        """
        if self.pitch > 0 and self.rotate_steps > 0:
            return (self.rotate_steps * self.microstep_factor) / self.pitch
        return 0.0

    @property
    def steps_per_degree(self) -> float:
        """
        Вычисляет количество шагов на градус для угловой оси (Theta).
        """
        steps_per_revolution = self.rotate_steps * self.microstep_factor
        if steps_per_revolution > 0:
            return steps_per_revolution / 360.0
        return 0.0

    def distance_to_steps(self, distance_mm: float) -> int:
        """
        Преобразует расстояние в миллиметрах в количество шагов.
        """
        return int(round(distance_mm * self.steps_per_mm))

    def steps_to_distance(self, steps: int) -> float:
        """
        Преобразует количество шагов в расстояние в миллиметрах.
        """
        if self.steps_per_mm > 0:
            return steps / self.steps_per_mm
        return 0.0

    def angle_to_steps(self, angle_deg: float) -> int:
        """
        Преобразует угол в градусах в количество шагов.
        """
        return int(round(angle_deg * self.steps_per_degree))

    def steps_to_angle(self, steps: int) -> float:
        """
        Преобразует количество шагов в угол в градусах.
        """
        if self.steps_per_degree > 0:
            return steps / self.steps_per_degree
        return 0.0

    def __str__(self) -> str:
        return (
            f"StepperConfig({self.axis_name}): "
            f"Spd: {self.spd} steps/s, "
            f"Acc: {self.acc} steps/s², "
            f"Dec: {self.deceleration} steps/s², "
            f"Cur: {self.cur}/255 (run), {self.curh}/255 (hold), "
            f"Microstep: 1/{self.microstep_factor} (mode {self.microstep}), "
            f"RotateSteps: {self.rotate_steps} steps/rev, "
            f"Pitch: {self.pitch} mm/rev, "
            f"Steps/mm: {self.steps_per_mm:.2f}, "
            f"Steps/deg: {self.steps_per_degree:.2f}, "
            f"Max: {self.max_steps} steps"
        )
