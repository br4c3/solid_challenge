from __future__ import annotations

from typing import Iterable, Tuple

from ..models import Component
from ..formulas import FormulaEngine, default_profile
from .power_chain import _gain


def _noise_figure(component: Component):
    category = component.category.upper()
    if category in {"SWITCH", "T/R SWITCH"}:
        return component.value("insertion_loss_db")
    return component.value("noise_figure_db", "lna_nf_db")


def calculate_receiver_nf(
    components: Iterable[Component],
    formula_engine: FormulaEngine | None = None,
    calculation_trace: list[dict] | None = None,
) -> Tuple[float, float]:
    engine          = formula_engine or FormulaEngine(default_profile())
    total_factor    = None
    cumulative_gain = 1.0
    total_gain_db   = 0.0
    for component in components:
        gain_db = component.value("lna_gain_db", "gain_db") if component.category.upper() == "FEM" else _gain(component)
        nf_db   = _noise_figure(component)
        if gain_db is None or nf_db is None:
            raise ValueError(f"{component.part_no}: gain or noise figure is unavailable.")
        # Convert dB values to linear factors before applying the Friis cascade equation.
        factor = engine.evaluate(
            "rx_noise_factor", {"noise_figure_db": nf_db},
            calculation_trace,
            component={
                "category": component.category,
                "part_no": component.part_no
            }
        )
        contribution = engine.evaluate(
            "rx_friis_contribution", {
                "noise_factor": factor,
                "preceding_gain_linear": cumulative_gain,
                "is_first_stage": float(total_factor is None),
            },
            calculation_trace,
            component={
                "category": component.category,
                "part_no": component.part_no
            }
        )
        total_factor = (total_factor or 0.0) + contribution
        cumulative_gain *= 10**(gain_db / 10.0)
        total_gain_db = engine.evaluate(
            "rx_total_gain_db", {
                "current_total_gain_db": total_gain_db,
                "stage_gain_db": gain_db,
            },
            calculation_trace,
            component={
                "category": component.category,
                "part_no": component.part_no
            }
        )
    if total_factor is None: raise ValueError("Receiver chain is empty.")
    total_nf_db = engine.evaluate("rx_total_nf_db", {"total_noise_factor": total_factor}, calculation_trace)
    return total_gain_db, total_nf_db
