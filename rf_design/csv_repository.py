from __future__ import annotations

import csv
import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Iterable, List, Optional

from .models import Component, MCS


DEFAULT_STORE = Path(__file__).resolve().parent.parent / "data"

COMPONENT_FIELDS = [
    "component_id","category","manufacturer","part_no","application","function","process",
    "freq_min_ghz","freq_max_ghz","supply_voltage_v","power_consumption_w","package",
    "operating_temp_min_c","operating_temp_max_c","product_url","datasheet_url",
    "datasheet_revision","datasheet_page","source_file","source_date","extraction_method",
    "extraction_evidence","note","image_url",
]

SPEC_FIELDS = [
    "number_channels","number_beams","gain_db","channel_bandwidth_ghz","output_p1db_dbm",
    "psat_dbm","oip3_dbm","noise_figure_db","input_p1db_dbm","pa_gain_db","pa_pae_percent",
    "lna_gain_db","lna_iip3_dbm","insertion_loss_db","isolation_db","power_handling_dbm",
    "rf_min_ghz","rf_max_ghz","if_min_ghz","if_max_ghz","lo_min_ghz","lo_max_ghz",
    "lo_multiplier","conversion_gain_db","lo_drive_min_dbm","lo_drive_max_dbm",
    "output_freq_min_ghz","output_freq_max_ghz","output_power_dbm","phase_noise_1khz",
    "phase_noise_10khz","phase_noise_100khz","phase_noise_1mhz","resolution_bit",
    "sample_rate_gsps","analog_bandwidth_ghz","snr_db","sinad_db","enob_bit","sfdr_dbc",
    "digital_interface",
]

MCS_FIELDS = ["mcs_index","modulation_order","min_snr_db","max_snr_db","spectral_efficiency","target_code_rate"]


def _number(value, integer: bool = False):
    if value in (None,""): return None
    return int(float(value)) if integer else float(value)


class ComponentRepository:
    def __init__(self, path: Path = DEFAULT_STORE):
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)
        if not self.component_path.exists(): self._write(self.component_path, [], COMPONENT_FIELDS+SPEC_FIELDS)
        if not self.mcs_path.exists(): self._write(self.mcs_path, [], MCS_FIELDS)

    @property
    def component_path(self) -> Path: return self.path / "components.csv"

    @property
    def mcs_path(self) -> Path: return self.path / "mcs.csv"

    @staticmethod
    def _read(path: Path) -> List[dict]:
        if not path.exists(): return []
        with path.open(encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))

    @staticmethod
    def _write(path: Path, rows: List[dict], fields: List[str]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8-sig", newline="", dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            writer    = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader(); writer.writerows(rows)
        os.replace(temporary, path)

    @staticmethod
    def _component(row: dict) -> Component:
        values = {key: row.get(key) or None for key in COMPONENT_FIELDS}
        values["component_id"]         = _number(values["component_id"], integer=True)
        values["freq_min_ghz"]         = _number(values["freq_min_ghz"])
        values["freq_max_ghz"]         = _number(values["freq_max_ghz"])
        values["supply_voltage_v"]     = _number(values["supply_voltage_v"])
        values["power_consumption_w"]  = _number(values["power_consumption_w"])
        values["operating_temp_min_c"] = _number(values["operating_temp_min_c"])
        values["operating_temp_max_c"] = _number(values["operating_temp_max_c"])
        values["application"]          = values["application"] or "Common"
        values["function"]             = values["function"] or ""
        values["specs"]                = {
            key: row[key] if key == "digital_interface" else _number(row[key])
            for key in SPEC_FIELDS
            if row.get(key) not in (None,"")
        }
        return Component(**values)

    @staticmethod
    def _component_row(component: Component) -> dict:
        row = asdict(component)
        row.update(row.pop("specs"))
        return row

    def replace_components(self, components: Iterable[Component]) -> None:
        rows = []
        for component_id,component in enumerate(components, start=1):
            component.component_id = component_id
            rows.append(self._component_row(component))
        self._write(self.component_path, rows, COMPONENT_FIELDS+SPEC_FIELDS)

    def upsert(self, component: Component) -> int:
        rows  = self._read(self.component_path)
        match = None
        if component.component_id is not None:
            match = next((row for row in rows if _number(row.get("component_id"), integer=True) == component.component_id), None)
        if match is None:
            match = next((row for row in rows if (
                row.get("category"),row.get("manufacturer"),row.get("part_no")
            ) == (component.category,component.manufacturer,component.part_no)), None)

        component_id           = _number(match.get("component_id"), integer=True) if match else max([_number(row.get("component_id"), integer=True) or 0 for row in rows], default=0)+1
        component.component_id = component_id
        new_row                = self._component_row(component)
        if match: rows[rows.index(match)] = new_row
        else: rows.append(new_row)
        self._write(self.component_path, rows, COMPONENT_FIELDS+SPEC_FIELDS)
        return component_id

    def get(self, component_id: int) -> Optional[Component]:
        row = next((row for row in self._read(self.component_path) if _number(row.get("component_id"), integer=True) == component_id), None)
        return self._component(row) if row else None

    def list(self, category: Optional[str] = None) -> List[Component]:
        items = [self._component(row) for row in self._read(self.component_path)]
        if category: items = [item for item in items if item.category == category]
        return sorted(items, key=lambda item: (item.category,item.manufacturer,item.part_no))

    def delete(self, component_id: int) -> None:
        rows = [row for row in self._read(self.component_path) if _number(row.get("component_id"), integer=True) != component_id]
        self._write(self.component_path, rows, COMPONENT_FIELDS+SPEC_FIELDS)

    def replace_mcs(self, rows: Iterable[MCS]) -> None:
        values = [{
            "mcs_index": item.index,
            "modulation_order": item.modulation_order,
            "min_snr_db": item.min_snr_db,
            "max_snr_db": item.max_snr_db,
            "spectral_efficiency": item.spectral_efficiency,
            "target_code_rate": item.target_code_rate,
        } for item in rows]
        self._write(self.mcs_path, values, MCS_FIELDS)

    def list_mcs(self) -> List[MCS]:
        return [MCS(
            _number(row["mcs_index"], integer=True),
            _number(row["modulation_order"], integer=True),
            _number(row["min_snr_db"]),
            _number(row["max_snr_db"]),
            _number(row["spectral_efficiency"]),
            _number(row.get("target_code_rate")),
        ) for row in self._read(self.mcs_path)]
