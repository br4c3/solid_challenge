from __future__ import annotations

from typing import Iterable

from ..models import STATUS_PRIORITY, Component, PowerChainResult, PowerStageResult, Status
from ..formulas import FormulaEngine, default_profile


def _gain(component: Component):
    category = component.category.upper()
    if category == "MIXER": return component.value("conversion_gain_db")
    if category in {"SWITCH", "T/R SWITCH"}:
        loss = component.value("insertion_loss_db")

        # A passive insertion loss is represented as negative stage gain.
        return -loss if loss is not None else None
    if category in {"PA", "FEM"}: return component.value("pa_gain_db", "gain_db")

    return component.value("gain_db", "lna_gain_db", default=0.0 if category in {"DAC", "ADC", "PLL"} else None)


def _allowed_output(component: Component, backoff_db: float, formula_engine: FormulaEngine | None = None):
    category = component.category.upper()
    if category in {"SWITCH", "T/R SWITCH"}:
        return component.value("power_handling_dbm"), "power handling"

    limit = component.value("output_p1db_dbm", "pa_p1db_dbm")
    if limit is not None:
        engine = formula_engine or FormulaEngine(default_profile())
        allowed = engine.evaluate(
            "tx_allowed_output_dbm", {
                "limit_dbm": limit,
                "output_backoff_db": backoff_db,
                "is_pa": float(category in {"PA", "FEM"}),
            }
        )
        return allowed, "OP1dB backoff" if category in {"PA", "FEM"} else "OP1dB"

    psat = component.value("psat_dbm")
    if category in {"PA", "FEM"} and psat is not None:
        engine = formula_engine or FormulaEngine(default_profile())
        allowed = engine.evaluate(
            "tx_allowed_output_dbm", {
                "limit_dbm": psat,
                "output_backoff_db": backoff_db,
                "is_pa": 1.0,
            }
        )
        return allowed, "estimated Psat backoff"

    return None, ""


def _planned_output(
    components,
    index: int,
    raw_output: float,
    backoff_db: float,
    formula_engine: FormulaEngine | None = None,
):
    if index + 1 >= len(components): return raw_output, None

    next_component = components[index + 1]
    if next_component.category.upper() not in {"PA", "FEM"}: return raw_output, None

    next_gain       = _gain(next_component)
    next_allowed, _ = _allowed_output(next_component, backoff_db, formula_engine)
    if next_gain is None or next_allowed is None: return raw_output, None

    # Required stage input[dBm] = target output[dBm] - stage gain[dB].
    required_input = next_allowed - next_gain
    if raw_output <= required_input: return raw_output, None

    return required_input, raw_output - required_input


def calculate_tx_chain(
    components: Iterable[Component],
    input_power_dbm: float,
    backoff_db: float = 3.0,
    automatic_level_control: bool = False,
    formula_engine: FormulaEngine | None = None,
    calculation_trace: list[dict] | None = None,
) -> PowerChainResult:
    components = list(components)
    engine     = formula_engine or FormulaEngine(default_profile())
    power      = input_power_dbm
    stages     = []
    for index, component in enumerate(components):
        category = component.category.upper()
        gain     = _gain(component)
        if gain is None:
            stages.append(
                PowerStageResult(
                    component.category, component.part_no, power, 0.0, power, None, Status.UNKNOWN,
                    "Gain/loss information is unavailable"
                )
            )
            continue

        # Cascaded level propagation in logarithmic units: Pout[dBm] = Pin[dBm] + G[dB].
        raw_output = engine.evaluate(
            "tx_stage_output_dbm", {
                "input_dbm": power,
                "gain_db": gain
            },
            calculation_trace,
            component={
                "category": component.category,
                "part_no": component.part_no
            }
        )
        output          = raw_output
        level_reduction = None
        if automatic_level_control:
            output, level_reduction = _planned_output(components, index, raw_output, backoff_db, engine)

        allowed, limit_basis = _allowed_output(component, backoff_db, engine)
        if automatic_level_control and allowed is not None and output > allowed:
            level_reduction = (level_reduction or 0.0) + output - allowed
            output          = allowed

        if allowed is None and category in {"DAC", "ADC", "PLL"}:
            status, message = Status.PASS, "Drive-reference stage"
        elif allowed is None:
            status, message = Status.UNKNOWN, "Linear output limit is unavailable"
        elif output > allowed:
            status, message = Status.FAIL, f"{limit_basis} 제한을 {output-allowed:.2f} dB 초과합니다"
        elif automatic_level_control and level_reduction is not None:
            status, message = Status.PASS, f"{level_reduction:.2f} dB 자동 레벨 제어를 적용하여 {limit_basis} 조건을 만족합니다"
        elif automatic_level_control and category in {"PA", "FEM"} and abs(allowed - output) < 1e-9:
            status, message = Status.PASS, f"{limit_basis} 목표 출력을 설정했습니다"
        elif allowed - output < 1:
            status, message = Status.WARN, f"{limit_basis} margin is {allowed-output:.2f} dB"
        else:
            status, message = Status.PASS, f"{limit_basis} margin is {allowed-output:.2f} dB"

        stages.append(
            PowerStageResult(
                component.category, component.part_no, power, output - power, output, allowed, status, message
            )
        )
        power = output

    status = max((stage.status for stage in stages), key=STATUS_PRIORITY.get) if stages else Status.UNKNOWN

    return PowerChainResult(stages, power, status)
