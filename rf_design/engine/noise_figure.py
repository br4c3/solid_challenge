from __future__ import annotations

import math
from typing import Iterable, Tuple

from ..models import Component
from .power_chain import _gain


def _noise_figure(component: Component):
    category = component.category.upper()
    if category in {"SWITCH", "T/R SWITCH"}:
        return component.value("insertion_loss_db")
    return component.value("noise_figure_db", "lna_nf_db")


def calculate_receiver_nf(components: Iterable[Component]) -> Tuple[float, float]:
    total_factor    = None
    cumulative_gain = 1.0
    total_gain_db   = 0.0
    for component in components:
        gain_db = component.value("lna_gain_db", "gain_db") if component.category.upper() == "FEM" else _gain(component)
        nf_db   = _noise_figure(component)
        if gain_db is None or nf_db is None: raise ValueError(f"{component.part_no}: gain 또는 NF 정보가 없습니다.")
        factor = 10**(nf_db / 10.0)
        if total_factor is None:
            total_factor = factor
        else:
            total_factor += (factor-1.0) / cumulative_gain
        cumulative_gain *= 10**(gain_db / 10.0)
        total_gain_db += gain_db
    if total_factor is None: raise ValueError("수신 chain이 비어 있습니다.")
    return total_gain_db,10.0 * math.log10(total_factor)
