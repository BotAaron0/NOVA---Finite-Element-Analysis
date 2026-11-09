"""Strict, Notepad-friendly key=value configuration."""
from dataclasses import dataclass, fields
import math
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    log_range_decades: float = 3.0
    geometry_mode: str = "strict"
    wall_thickness_m: float = 0.02
    prepared_voxel_size_m: float = 0.0025
    model_scale: float = 1.0
    young_modulus_pa: float = 2e9
    poisson_ratio: float = 0.3
    density_kg_m3: float = 1200.0
    gravity_m_s2: float = 9.81
    voxel_size_m: float = 0.01
    up_axis: str = "y"
    fixed_base_depth_m: float = 0.005
    top_load_depth_m: float = 0.005
    force_x_n: float = 0.0
    force_y_n: float = 0.0
    force_z_n: float = 0.0
    max_voxels: int = 2000


def read_settings(path):
    values = {}
    allowed = {f.name for f in fields(Settings)}
    for number, line in enumerate(Path(path).read_text(encoding="utf-8-sig").splitlines(), 1):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        key, sep, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not sep or key not in allowed or key in values:
            raise ValueError(f"Invalid or duplicate setting on line {number}: {key}")
        values[key] = value if key in ("up_axis", "geometry_mode") else int(value) if key == "max_voxels" else float(value)
    settings = Settings(**values)
    for field in fields(settings):
        value = getattr(settings, field.name)
        if isinstance(value, (int, float)) and not math.isfinite(value):
            raise ValueError(f"{field.name} must be finite")
    for key in ("model_scale", "young_modulus_pa", "voxel_size_m", "max_voxels", "density_kg_m3", "wall_thickness_m", "prepared_voxel_size_m"):
        if getattr(settings, key) <= 0:
            raise ValueError(f"{key} must be positive")
    if not 0 < settings.log_range_decades <= 12:
        raise ValueError("log_range_decades must be greater than 0 and at most 12")
    if not -1 < settings.poisson_ratio < 0.49:
        raise ValueError("poisson_ratio must be between -1 and 0.49")
    if settings.geometry_mode not in ("strict", "vase"):
        raise ValueError("geometry_mode must be strict or vase")
    if settings.up_axis not in ("x", "y", "z"):
        raise ValueError("up_axis must be x, y, or z")
    if min(settings.fixed_base_depth_m, settings.top_load_depth_m) < 0:
        raise ValueError("Selection depths must be nonnegative")
    if settings.gravity_m_s2 < 0:
        raise ValueError("gravity_m_s2 must be nonnegative")
    if not any((settings.force_x_n, settings.force_y_n, settings.force_z_n, settings.gravity_m_s2)):
        raise ValueError("Specify gravity or a nonzero applied force")
    return settings
