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


# ---
# The original AppConfig defined in this file was merely a shell around a list of
# StepperConfigs parsed from the legacy C# style ``config.cfg`` file.  However,
# the Python application relies on a much richer configuration loaded from a
# JSON file (see ``config.json``) which includes global settings (COM port,
# baud rate, default scanning parameters, output formats, etc.), camera
# settings and a list of stepper motor configurations.  To support this
# structure we define a new pydantic-based model below.  Using pydantic
# simplifies validation and serialisation, and ensures that enumerations are
# correctly handled.  The legacy dataclass ``StepperConfig`` defined above
# remains intact for compatibility with the ``config.cfg`` editor and parsing
# routines.

from pydantic import BaseModel, Field, validator
from typing import Optional, List

# Re‑use the pydantic StepperConfig used in the scanning module so that
# distances/angles can be converted correctly.  Note: this import is
# intentionally local to avoid a circular import at module load time.
from scan.stepper_config import StepperConfig as PydanticStepperConfig
from scan.data_writer import OutputFormat, AngleUnit


class CameraConfig(BaseModel):
    """Configuration related to the thermal camera."""
    calibration_file_path: str = Field(
        "calibration_data.json",
        description="Path to the file where camera calibration data is stored"
    )


class AppConfig(BaseModel):
    """
    High level application configuration loaded from ``config.json``.

    This model defines all of the tunable parameters exposed in the GUI,
    including serial settings, default scanning parameters, output format
    preferences, camera settings and a list of stepper motor definitions.

    A ``config_file_path`` attribute is stored alongside the parsed data so
    that the UI knows where the configuration originated.  When a new
    configuration is loaded via the ``open config`` menu the path is updated.
    """

    # Serial port settings
    com_port: str = Field(
        default="",
        description="The name of the COM port used to communicate with the STM32 controller"
    )
    baud_rate: int = Field(
        default=115200,
        ge=1200,
        le=1000000,
        description="Baud rate for the serial connection"
    )

    # Default scanning parameters
    default_radius_mm: float = Field(
        default=50.0,
        gt=0.0,
        description="Maximum radius of the scan in millimetres"
    )
    default_step_mm: float = Field(
        default=1.0,
        gt=0.0,
        description="Radial step in millimetres between concentric circles"
    )
    default_arc_step_mm: float = Field(
        default=1.0,
        gt=0.0,
        description="Arc step in millimetres along a given circle"
    )
    default_delay_ms: int = Field(
        default=1000,
        ge=0,
        description="Delay in milliseconds between measurements"
    )

    # Output file format and angle units
    default_output_format: OutputFormat = Field(
        default=OutputFormat.CSV,
        description="Default file format for scan results (txt, md or csv)"
    )
    default_angle_unit: AngleUnit = Field(
        default=AngleUnit.DEGREES,
        description="Units for representing angles (degrees or dms)"
    )

    # Nested camera configuration
    camera: CameraConfig = Field(
        default_factory=CameraConfig,
        description="Embedded configuration specific to the thermal camera"
    )

    # List of stepper motor configurations.  Two motors (X and Theta) are
    # created by default.  Each entry is parsed into the pydantic
    # ``StepperConfig`` from ``scan.stepper_config`` for consistency with the
    # motion control logic.
    steppers: List[PydanticStepperConfig] = Field(
        default_factory=lambda: [
            PydanticStepperConfig(axis_name="X"),
            PydanticStepperConfig(axis_name="Theta")
        ],
        description="List of stepper motor configurations"
    )

    # Path to the JSON file from which this configuration was loaded.  This
    # attribute is not present in the JSON itself but is set by the
    # ``ConfigManager`` when reading.  It enables the GUI to prepopulate
    # file dialogs and to save the configuration back to the correct file.
    config_file_path: Optional[str] = Field(
        default=None,
        description="Internal: path of the loaded configuration file"
    )

    class Config:
        # When serialising models to dict/JSON include enumerations as their
        # underlying values (e.g. "csv" instead of OutputFormat.CSV).  This
        # ensures compatibility with the existing config.json format.
        use_enum_values = True
        # Ignore unknown keys in the input JSON so that older configs don't
        # break when new fields are added.
        extra = "ignore"

    # Validator to convert legacy stepper definitions with different key
    # names (e.g. 'max' instead of 'max_steps') into proper ``StepperConfig``
    # objects.  The ``pre=True`` flag ensures this runs before pydantic
    # attempts to coerce the list elements.
    @validator('steppers', pre=True)
    def _parse_steppers(cls, v):
        if not v:
            # If no steppers provided, return default two motors
            return [
                PydanticStepperConfig(axis_name="X"),
                PydanticStepperConfig(axis_name="Theta")
            ]
        processed = []
        for item in v:
            if isinstance(item, dict):
                # Rename keys from legacy config.json to match pydantic model
                mapped = {}
                for k, val in item.items():
                    key = k.lower()
                    if key == 'max':
                        # Clamp negative values of max_steps to default by not setting
                        if isinstance(val, (int, float)) and val >= 1:
                            mapped['max_steps'] = val
                    elif key == 'rotatesteps':
                        mapped['rotate_steps'] = val
                    else:
                        mapped[key] = val
                # Ensure axis name is uppercase
                if 'axis_name' in mapped and isinstance(mapped['axis_name'], str):
                    mapped['axis_name'] = mapped['axis_name'].upper()
                processed.append(PydanticStepperConfig(**mapped))
            elif isinstance(item, PydanticStepperConfig):
                processed.append(item)
            else:
                # Unsupported type
                raise ValueError(f"Invalid stepper config: {item}")
        return processed

    @classmethod
    def default(cls) -> 'AppConfig':
        """
        Returns a default AppConfig instance.  All values mirror sensible
        defaults found in the original C# application.  Two stepper motors
        (X and Theta) are created with default parameters.
        """
        return cls()
