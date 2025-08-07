from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class StepperConfig:
    """
    Data class representing the configuration of a single stepper motor.

    This class unifies the configuration format used throughout the
    application. It provides convenience properties for converting
    between mechanical distances/angles and motor steps.  Fields are
    initialized with sensible defaults so that a config can be created
    without explicitly specifying every parameter.  The attribute
    ``axis_name`` identifies the axis (``"X"`` or ``"Theta"``) and
    should be set by the caller (e.g. ``ConfigManager``) rather than
    parsed from the config line itself.
    """

    # Axis identifier: must be "X" or "Theta"
    axis_name: str = "X"
    # Speed in steps per second
    spd: int = 500
    # Acceleration in steps per second squared
    acc: int = 1000
    # Run current (0–255)
    cur: int = 100
    # Hold current (0–255)
    curh: int = 80
    # Maximum number of steps allowed for this axis
    max_steps: int = 100_000
    # Microstep mode (0 = full step, 1 = half step, …, 7 = 1/128 step)
    microstep: int = 4
    # Number of full steps per revolution of the motor (before microstepping)
    rotate_steps: int = 200
    # Deceleration in steps per second squared
    deceleration: int = 1000
    # Lead screw pitch in millimetres per revolution (for linear axes)
    pitch: float = 8.0

    def __post_init__(self) -> None:
        """Normalize axis name and clamp microstep value."""
        if isinstance(self.axis_name, str):
            self.axis_name = self.axis_name.upper()
        self.microstep = int(max(0, min(7, self.microstep)))
        if self.rotate_steps <= 0:
            self.rotate_steps = 200
        if self.pitch <= 0:
            self.pitch = 8.0

    @property
    def microstep_factor(self) -> int:
        """Return the microstep multiplier (2**microstep)."""
        return 2 ** self.microstep

    @property
    def steps_per_mm(self) -> float:
        """Number of microsteps per millimetre for the X axis."""
        if self.axis_name == "X" and self.pitch > 0:
            return (self.rotate_steps * self.microstep_factor) / self.pitch
        return 0.0

    @property
    def steps_per_degree(self) -> float:
        """Number of microsteps per degree for the Theta axis."""
        if self.axis_name == "THETA":
            steps_per_rev = self.rotate_steps * self.microstep_factor
            return steps_per_rev / 360.0
        return 0.0

    def distance_to_steps(self, distance_mm: float) -> int:
        """Convert millimetres to microsteps (valid for X axis)."""
        return int(round(distance_mm * self.steps_per_mm)) if self.steps_per_mm > 0 else 0

    def steps_to_distance(self, steps: int) -> float:
        """Convert microsteps to millimetres (valid for X axis)."""
        return steps / self.steps_per_mm if self.steps_per_mm > 0 else 0.0

    def angle_to_steps(self, angle_deg: float) -> int:
        """Convert degrees to microsteps (valid for Theta axis)."""
        return int(round(angle_deg * self.steps_per_degree)) if self.steps_per_degree > 0 else 0

    def steps_to_angle(self, steps: int) -> float:
        """Convert microsteps to degrees (valid for Theta axis)."""
        return steps / self.steps_per_degree if self.steps_per_degree > 0 else 0.0

    @classmethod
    def from_string(cls, line: str) -> 'StepperConfig':
        """
        Parse a semicolon-separated config line into a StepperConfig instance.
        Accepted keys: spd, acc, cur, curh, max, microstep, rotatesteps, deceleration, pitch.
        """
        if not isinstance(line, str):
            raise ValueError(f"Config line must be a string, got {type(line)!r}")
        parts = [seg.strip() for seg in line.split(';') if seg.strip()]
        data: Dict[str, Any] = {}
        for part in parts:
            tokens = part.split(maxsplit=1)
            if len(tokens) != 2:
                raise ValueError(f"Invalid segment in config line: '{part}'. Expected 'key value' pairs.")
            key, value_str = tokens[0].lower(), tokens[1].strip()
            if key in data:
                raise ValueError(f"Duplicate key '{key}' in config line: {line}")
            if key == "pitch":
                value = float(value_str)
            else:
                value = int(value_str)
            data[key] = value
        allowed_keys = {
            "spd": "spd",
            "acc": "acc",
            "cur": "cur",
            "curh": "curh",
            "max": "max_steps",
            "microstep": "microstep",
            "rotatesteps": "rotate_steps",
            "deceleration": "deceleration",
            "pitch": "pitch",
        }
        for key in data.keys():
            if key not in allowed_keys:
                raise ValueError(f"Unknown key '{key}' in config line: {line}")
        kwargs: Dict[str, Any] = {}
        for key, field_name in allowed_keys.items():
            if key in data:
                kwargs[field_name] = data[key]
        return cls(**kwargs)

    def to_line(self) -> str:
        """
        Serialize this configuration back into a semicolon-separated line.
        Axis name is omitted because position in the file determines the axis.
        """
        parts = [
            f"spd {self.spd}",
            f"acc {self.acc}",
            f"cur {self.cur}",
            f"curh {self.curh}",
            f"max {self.max_steps}",
            f"microstep {self.microstep}",
            f"rotatesteps {self.rotate_steps}",
            f"deceleration {self.deceleration}",
            f"pitch {self.pitch:.6g}",
        ]
        return ";".join(parts)


class AppConfig:
    """Class to hold the application configuration consisting of multiple StepperConfigs."""
    def __init__(self, steppers: List[StepperConfig]):
        self.steppers: List[StepperConfig] = steppers

    @classmethod
    def from_lines(cls, lines: List[str]) -> 'AppConfig':
        """Parse multiple config lines into an AppConfig instance."""
        steppers: List[StepperConfig] = []
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
            ...
