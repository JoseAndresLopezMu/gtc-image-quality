"""Quality-control configuration (SPEC 6), read from config.yaml."""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class QCConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_stars: int = Field(5, ge=1)
    max_ellipticity: float = Field(0.20, gt=0, lt=1)
    fwhm_outlier_mad: float = Field(3.0, gt=0)
    background_outlier_mad: float = Field(3.0, gt=0)
    max_saturated_fraction: float = Field(0.02, gt=0, lt=1)
    # Below this many measured frames in a filter and night, median and MAD say nothing.
    min_group_frames: int = Field(5, ge=3)


def load_config(path: Path) -> QCConfig:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"{path}: expected a mapping of settings")
    return QCConfig.model_validate(loaded.get("qc", {}))
