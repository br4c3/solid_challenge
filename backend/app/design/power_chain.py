from __future__ import annotations

from typing import Iterable

from ..models import STATUS_PRIORITY, Component, PowerChainResult, PowerStageResult, Status


def _gain(component: Component):
    category = component.category.upper()
    if category == "MIXER": return component.value("conversion_gain_db")
    if category in {"SWITCH", "T/R SWITCH"}:
        loss = component.value("insertion_loss_db")

        # A passive insertion loss is represented as negative stage gain.
        return -loss if loss is not None else None
    if category in {"PA", "FEM"}: return component.value("pa_gain_db", "gain_db")

    return component.value("gain_db", "lna_gain_db", default=0.0 if category in {"DAC", "ADC", "PLL"} else None)


def _allowed_output(component: Component, backoff_db: float):
    category = component.category.upper()
    if category in {"SWITCH", "T/R SWITCH"}:
        return component.value("power_handling_dbm"), "power handling"

    limit = component.value("output_p1db_dbm", "pa_p1db_dbm")
    if limit is not None:
        # PA operating limit[dBm] = OP1dB[dBm] - output backoff[dB].
        if category in {"PA", "FEM"}: return limit - backoff_db, "OP1dB backoff"

        return limit, "OP1dB"

    psat = component.value("psat_dbm")
    if category in {"PA", "FEM"} and psat is not None: return psat - backoff_db, "estimated Psat backoff"

    return None, ""


def _planned_output(components, index: int, raw_output: float, backoff_db: float):
    if index + 1 >= len(components): return raw_output, None

    next_component = components[index + 1]
    if next_component.category.upper() not in {"PA", "FEM"}: return raw_output, None

    next_gain       = _gain(next_component)
    next_allowed, _ = _allowed_output(next_component, backoff_db)
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
) -> PowerChainResult:
    components = list(components)
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
        raw_output      = power + gain
        output          = raw_output
        level_reduction = None
        if automatic_level_control:
            output, level_reduction = _planned_output(components, index, raw_output, backoff_db)

        allowed, limit_basis = _allowed_output(component, backoff_db)
        if automatic_level_control and allowed is not None and output > allowed:
            level_reduction = (level_reduction or 0.0) + output - allowed
            output          = allowed

        if allowed is None and category in {"DAC", "ADC", "PLL"}:
            status, message = Status.PASS, "Drive-reference stage"
        elif allowed is None:
            status, message = Status.UNKNOWN, "Linear output limit is unavailable"
        elif output > allowed:
            status, message = Status.FAIL, f"Exceeds the {limit_basis} limit by {output-allowed:.2f} dB"
        elif automatic_level_control and level_reduction is not None:
            status, message = Status.PASS, f"Applied {level_reduction:.2f} dB automatic level control; {limit_basis} is satisfied"
        elif automatic_level_control and category in {"PA", "FEM"} and abs(allowed - output) < 1e-9:
            status, message = Status.PASS, f"Configured {limit_basis} target output"
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
