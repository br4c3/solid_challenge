from __future__ import annotations

from typing import Iterable

from ..models import Component, PowerChainResult, PowerStageResult, Status
from .compatibility import STATUS_PRIORITY


def _gain(component: Component):
    category = component.category.upper()
    if category == "MIXER": return component.value("conversion_gain_db")
    if category in {"SWITCH","T/R SWITCH"}:
        loss = component.value("insertion_loss_db")

        return -loss if loss is not None else None
    if category in {"PA","FEM"}: return component.value("pa_gain_db", "gain_db")

    return component.value("gain_db", "lna_gain_db", default=0.0 if category in {"DAC","ADC","PLL"} else None)


def _allowed_output(component: Component, backoff_db: float):
    category = component.category.upper()
    if category in {"SWITCH","T/R SWITCH"}:
        return component.value("power_handling_dbm"),"power handling"

    limit = component.value("output_p1db_dbm", "pa_p1db_dbm")
    if limit is not None:
        if category in {"PA","FEM"}: return limit-backoff_db,"OP1dB backoff"

        return limit,"OP1dB"

    psat = component.value("psat_dbm")
    if category in {"PA","FEM"} and psat is not None: return psat-backoff_db,"Psat backoff 추정"

    return None,""


def _planned_output(components, index: int, raw_output: float, backoff_db: float):
    if index+1 >= len(components): return raw_output,None

    next_component = components[index+1]
    if next_component.category.upper() not in {"PA","FEM"}: return raw_output,None

    next_gain      = _gain(next_component)
    next_allowed,_ = _allowed_output(next_component, backoff_db)
    if next_gain is None or next_allowed is None: return raw_output,None

    required_input = next_allowed-next_gain
    if raw_output <= required_input: return raw_output,None

    return required_input,raw_output-required_input


def calculate_tx_chain(
    components: Iterable[Component],
    input_power_dbm: float,
    backoff_db: float=3.0,
    automatic_level_control: bool=False,
) -> PowerChainResult:
    components = list(components)
    power      = input_power_dbm
    stages     = []
    for index,component in enumerate(components):
        category = component.category.upper()
        gain     = _gain(component)
        if gain is None:
            stages.append(PowerStageResult(component.category, component.part_no, power, 0.0, power, None, Status.UNKNOWN, "Gain/loss 정보 없음"))
            continue

        raw_output      = power+gain
        output          = raw_output
        level_reduction = None
        if automatic_level_control:
            output,level_reduction = _planned_output(components, index, raw_output, backoff_db)

        allowed,limit_basis = _allowed_output(component, backoff_db)
        if automatic_level_control and allowed is not None and output > allowed:
            level_reduction = (level_reduction or 0.0)+output-allowed
            output          = allowed

        if allowed is None and category in {"DAC","ADC","PLL"}:
            status,message = Status.PASS,"구동 기준 stage"
        elif allowed is None:
            status,message = Status.UNKNOWN,"선형 출력 한계 정보 없음"
        elif output > allowed:
            status,message = Status.FAIL,f"{limit_basis} 한계를 {output-allowed:.2f} dB 초과"
        elif automatic_level_control and level_reduction is not None:
            status,message = Status.PASS,f"자동 레벨 제어 {level_reduction:.2f} dB 적용, {limit_basis} 만족"
        elif automatic_level_control and category in {"PA","FEM"} and abs(allowed-output) < 1e-9:
            status,message = Status.PASS,f"설정한 {limit_basis} 목표 출력"
        elif allowed-output < 1:
            status,message = Status.WARN,f"{limit_basis} 여유 {allowed-output:.2f} dB"
        else:
            status,message = Status.PASS,f"{limit_basis} 여유 {allowed-output:.2f} dB"

        stages.append(PowerStageResult(component.category, component.part_no, power, output-power, output, allowed, status, message))
        power = output

    status = max((stage.status for stage in stages), key=STATUS_PRIORITY.get) if stages else Status.UNKNOWN

    return PowerChainResult(stages, power, status)
