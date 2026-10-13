from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def resource_root() -> Path:
    configured = os.environ.get("RF_DESIGN_RESOURCE_DIR")
    if configured: return Path(configured).expanduser().resolve()
    if getattr(sys, "frozen", False): return Path(getattr(sys, "_MEIPASS"))
    return PROJECT_ROOT


def data_dir() -> Path:
    configured = os.environ.get("RF_DESIGN_DATA_DIR")
    if configured: return Path(configured).expanduser().resolve()
    return PROJECT_ROOT / "data"


def reference_dir() -> Path:
    return resource_root() / "references"


def config_path() -> Path:
    return resource_root() / "backend/config.json"


def csv_has_data(path: Path) -> bool:
    if not path.exists(): return False
    with path.open(encoding="utf-8-sig") as handle:
        next(handle, None)
        return any(line.strip() for line in handle)


def ensure_runtime_data() -> Path:
    destination = data_dir()
    destination.mkdir(parents=True, exist_ok=True)
    source = resource_root() / "data"
    relative_files = (
        Path("catalog/manufacturer_product_seeds.csv"),
        Path("components.csv"),
        Path("mcs.csv"),
    )
    for relative in relative_files:
        source_file      = source / relative
        destination_file = destination / relative
        if source_file == destination_file or not source_file.exists(): continue
        if destination_file.exists() and csv_has_data(destination_file): continue
        destination_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, destination_file)
    return destination
