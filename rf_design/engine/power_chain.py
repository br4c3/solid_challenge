from __future__ import annotations

from typing import Iterable

from ..models import Component, PowerChainResult, PowerStageResult, Status
from .compatibility import STATUS_PRIORITY


def _gain(component: Component):
    category = component.category.upper()
    if category == "MIXER":
        return component.value("conversion_gain_db")
    if category in {"SWITCH", "T/R SWITCH"}:
        loss = component.value("insertion_loss_db")
        return -loss if loss is not None else None
    if category in {"PA", "FEM"}:
        return component.value("pa_gain_db", "gain_db")
    return component.value("gain_db", "lna_gain_db", default=0.0 if category in {"DAC", "ADC", "PLL"} else None)


def calculate_tx_chain(components: Iterable[Component], input_power_dbm: float, backoff_db: float = 3.0) -> PowerChainResult:
    power = input_power_dbm
    stages = []
    for component in components:
        gain = _gain(component)
        if gain is None:
            stages.append(PowerStageResult(component.category, component.part_no, power, 0.0, power, None, Status.UNKNOWN, "Gain/loss 정보 없음"))
            continue
        output = power+gain
        limit  = component.value("output_p1db_dbm", "pa_p1db_dbm")
        if component.category.upper() in {"SWITCH", "T/R SWITCH"}:
            limit = component.value("power_handling_dbm")
            allowed = limit
        else:
            allowed = limit-backoff_db if limit is not None else None
        if allowed is None:
            status,message = Status.UNKNOWN,"선형 출력 한계 정보 없음"
        elif output > allowed:
            status,message = Status.FAIL,f"선형 한계를 {output-allowed:.2f} dB 초과"
        elif allowed-output < 1:
            status,message = Status.WARN,f"선형 여유 {allowed-output:.2f} dB"
        else:
            status,message = Status.PASS,f"선형 여유 {allowed-output:.2f} dB"
        stages.append(PowerStageResult(component.category, component.part_no, power, gain, output, allowed, status, message))
        power = output
    status = max((stage.status for stage in stages), key=STATUS_PRIORITY.get) if stages else Status.UNKNOWN
    return PowerChainResult(stages, power, status)
