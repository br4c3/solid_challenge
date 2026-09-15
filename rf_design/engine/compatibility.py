from __future__ import annotations

from typing import Iterable, List, Optional

from ..models import CheckResult, Component, LinkRequirement, Status


STATUS_PRIORITY = {Status.PASS: 0, Status.WARN: 1, Status.UNKNOWN: 2, Status.FAIL: 3}


def overall_status(checks: Iterable[CheckResult]) -> Status:
    checks = list(checks)
    return max((check.status for check in checks), key=STATUS_PRIORITY.get) if checks else Status.UNKNOWN


def required_function(requirement: LinkRequirement) -> str:
    direction = requirement.direction.strip().lower()
    if direction in {"tx", "transmit"}:
        return "Tx"
    if direction in {"rx", "receive"}:
        return "Rx"
    if direction in {"ul", "uplink"}:
        return "Tx" if requirement.application.lower() == "terminal" else "Rx"
    if direction in {"dl", "downlink"}:
        return "Rx" if requirement.application.lower() == "terminal" else "Tx"
    return requirement.direction


def esa_band(application: str, direction: str):
    requirement = LinkRequirement(application, direction, 1.0, 1.0, 0.0, 1.0, 90.0)
    function    = required_function(requirement)
    if application.strip().lower() == "terminal": return (27.5,31.0) if function == "Tx" else (17.7,21.2)
    if application.strip().lower() == "payload": return (17.7,21.2) if function == "Tx" else (27.5,31.0)

    return None


def _frequency_range(component: Component):
    if component.category.upper() == "MIXER":
        return component.value("rf_min_ghz"),component.value("rf_max_ghz")
    if component.category.upper() == "PLL":
        return component.value("output_freq_min_ghz"),component.value("output_freq_max_ghz")
    if component.category.upper() in {"ADC","DAC","CONVERTER"}:
        bandwidth = component.value("analog_bandwidth_ghz")
        return component.freq_min_ghz or 0.0,component.freq_max_ghz or bandwidth
    return component.freq_min_ghz,component.freq_max_ghz


def check_application(component: Component, requirement: LinkRequirement) -> CheckResult:
    application = component.application.strip().lower()
    wanted = requirement.application.strip().lower()
    if application in {"common", "공용", "t/p", ""} or application == wanted:
        return CheckResult("application", Status.PASS, f"{component.application} 적용 가능")
    return CheckResult("application", Status.FAIL, f"요구 적용 대상은 {requirement.application}, 부품은 {component.application}")


def check_function(component: Component, requirement: LinkRequirement) -> CheckResult:
    category = component.category.upper()
    if category in {"PLL", "SWITCH"}:
        return CheckResult("function", Status.PASS, "방향 공용 stage")
    wanted = required_function(requirement).lower()
    function = component.function.lower()
    if not function:
        return CheckResult("function", Status.UNKNOWN, "기능 정보 없음")
    if "integrated fem" in function or "통합 fem" in function:
        return CheckResult("function", Status.PASS, "통합 FEM은 Tx/Rx 경로 지원")
    if "trx" in function or wanted in function or (wanted == "tx" and any(x in function for x in ("pa", "up", "dac"))) or (wanted == "rx" and any(x in function for x in ("lna", "down", "adc"))):
        return CheckResult("function", Status.PASS, f"{component.function} 방향 일치")
    return CheckResult("function", Status.FAIL, f"요구 방향 {wanted.upper()}와 부품 기능 {component.function} 불일치")


def check_frequency(component: Component, requirement: LinkRequirement) -> CheckResult:
    low,high = _frequency_range(component)
    if component.category.upper() in {"ADC","DAC","CONVERTER"} and requirement.if_freq_ghz is not None:
        required_low  = requirement.if_freq_ghz-requirement.channel_bw_mhz / 2000.0
        required_high = requirement.if_freq_ghz+requirement.channel_bw_mhz / 2000.0
        label         = "IF"
    else:
        required_low  = requirement.required_low_ghz
        required_high = requirement.required_high_ghz
        label         = "RF"
    details = {"required_low_ghz": required_low, "required_high_ghz": required_high, "supported_low_ghz": low, "supported_high_ghz": high}
    if low is None or high is None:
        return CheckResult("frequency", Status.UNKNOWN, "주파수 범위 정보 없음", details)
    if low <= required_low and high >= required_high:
        edge_margin = min(required_low-low, high-required_high)
        status = Status.WARN if edge_margin < requirement.channel_bw_mhz / 1000.0 else Status.PASS
        return CheckResult("frequency", status, f"필요 {label} {required_low:.4f}~{required_high:.4f} GHz가 지원 범위에 포함", {**details, "edge_margin_ghz": edge_margin})
    return CheckResult("frequency", Status.FAIL, f"필요 {label} {required_low:.4f}~{required_high:.4f} GHz, 지원 {low:g}~{high:g} GHz", details)


def check_bandwidth(component: Component, requirement: LinkRequirement) -> CheckResult:
    bandwidth = component.value("channel_bandwidth_ghz", "analog_bandwidth_ghz")
    if bandwidth is None:
        return CheckResult("bandwidth", Status.UNKNOWN, "대역폭 정보 없음")
    required = requirement.channel_bw_mhz / 1000.0
    if bandwidth >= required:
        margin = bandwidth-required
        return CheckResult("bandwidth", Status.PASS if margin >= required * 0.1 else Status.WARN, f"대역폭 여유 {margin:.3f} GHz", {"margin_ghz": margin})
    return CheckResult("bandwidth", Status.FAIL, f"필요 {required:.3f} GHz, 지원 {bandwidth:.3f} GHz")


def check_beams(component: Component, requirement: LinkRequirement) -> CheckResult:
    if component.category.upper() != "BFIC":
        return CheckResult("beams", Status.PASS, "빔 수 검사 대상 아님")
    beams = component.value("number_beams")
    if beams is None:
        return CheckResult("beams", Status.UNKNOWN, "빔 수 정보 없음")
    if beams >= requirement.num_beams:
        return CheckResult("beams", Status.PASS, f"{int(beams)}개 빔 지원")
    return CheckResult("beams", Status.FAIL, f"요구 {requirement.num_beams}개, 지원 {int(beams)}개")


def check_component(component: Component, requirement: LinkRequirement) -> List[CheckResult]:
    checks = [check_application(component, requirement), check_function(component, requirement)]
    if component.category.upper() != "PLL":
        checks.append(check_frequency(component, requirement))
    if component.category.upper() in {"BFIC", "MIXER", "ADC", "DAC", "CONVERTER"}:
        checks.append(check_bandwidth(component, requirement))
    checks.append(check_beams(component, requirement))
    return checks


def check_bfic_pa(bfic: Component, pa: Component, backoff_db: float = 3.0) -> CheckResult:
    bfic_limit = bfic.value("output_p1db_dbm")
    pa_gain    = pa.value("pa_gain_db", "gain_db")
    pa_op1     = pa.value("output_p1db_dbm", "pa_p1db_dbm")
    pa_ip1     = pa.value("input_p1db_dbm", "pa_input_p1db_dbm")
    estimated  = False
    if pa_op1 is None and pa.value("psat_dbm") is not None:
        pa_op1    = pa.value("psat_dbm")
        estimated = True
    if pa_ip1 is None and pa_gain is not None and pa_op1 is not None:
        pa_ip1 = pa_op1-pa_gain
        estimated = True
    if bfic_limit is None or pa_gain is None or pa_op1 is None or pa_ip1 is None:
        return CheckResult("bfic_pa_power", Status.UNKNOWN, "BFIC/PA P1dB 또는 gain 정보 부족")
    required_input = pa_op1-backoff_db-pa_gain
    available      = bfic_limit
    margin         = available-required_input
    if margin < 0:
        status,message = Status.FAIL,f"BFIC 선형 출력이 PA 권장 입력보다 {-margin:.2f} dB 부족"
    elif margin < 1:
        status,message = Status.WARN,f"PA 구동 여유가 {margin:.2f} dB로 작음"
    else:
        status,message = Status.PASS,f"PA 구동 여유 {margin:.2f} dB"
    return CheckResult("bfic_pa_power", status, message, {"required_input_dbm": required_input, "available_dbm": available, "pa_ip1db_dbm": pa_ip1, "margin_db": margin}, estimated)


def check_pll_mixer(pll: Component, mixer: Component, rf_freq_ghz: float, if_freq_ghz: Optional[float], routing_loss_db: float = 1.0) -> CheckResult:
    if if_freq_ghz is None:
        return CheckResult("pll_mixer", Status.UNKNOWN, "IF 주파수 정보 없음")
    mixer_lo_min,mixer_lo_max = mixer.value("lo_min_ghz"),mixer.value("lo_max_ghz")
    pll_min,pll_max           = pll.value("output_freq_min_ghz"),pll.value("output_freq_max_ghz")
    if None in (mixer_lo_min, mixer_lo_max, pll_min, pll_max):
        return CheckResult("pll_mixer", Status.UNKNOWN, "PLL 또는 Mixer LO 주파수 범위 정보 부족")
    multiplier = mixer.value("lo_multiplier") or 1.0
    internal_candidates = sorted({abs(rf_freq_ghz-if_freq_ghz),rf_freq_ghz+if_freq_ghz})
    candidates          = [(internal,internal / multiplier) for internal in internal_candidates]
    valid               = [(internal,lo_input) for internal,lo_input in candidates if mixer_lo_min <= lo_input <= mixer_lo_max and pll_min <= lo_input <= pll_max]
    if not valid:
        return CheckResult("pll_mixer", Status.FAIL, f"가능 LO 입력 {[round(x[1], 6) for x in candidates]} GHz가 Mixer/PLL 공통 범위에 없음", {"internal_lo_candidates_ghz": internal_candidates, "lo_input_candidates_ghz": [x[1] for x in candidates], "lo_multiplier": multiplier})
    output = pll.value("output_power_dbm")
    drive_min = mixer.value("lo_drive_min_dbm")
    if output is None or drive_min is None:
        return CheckResult("pll_mixer", Status.UNKNOWN, f"LO 입력 {valid[0][1]:g} GHz (내부 LO {valid[0][0]:g} GHz) 가능, LO power 정보 부족", {"selected_lo_ghz": valid[0][1], "selected_internal_lo_ghz": valid[0][0], "lo_multiplier": multiplier})
    delivered = output-routing_loss_db
    margin    = delivered-drive_min
    status    = Status.FAIL if margin < 0 else Status.WARN if margin < 1 else Status.PASS
    return CheckResult("pll_mixer", status, f"LO 입력 {valid[0][1]:g} GHz (내부 LO {valid[0][0]:g} GHz), drive margin {margin:.2f} dB", {"selected_lo_ghz": valid[0][1], "selected_internal_lo_ghz": valid[0][0], "lo_multiplier": multiplier, "delivered_dbm": delivered, "margin_db": margin})
