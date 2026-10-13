from __future__ import annotations

from typing import Iterable, List, Optional

from ..models import STATUS_PRIORITY, CheckResult, Component, LinkRequirement, Status

DIRECTION_ALIASES = {
    "tx": "Tx",
    "transmit": "Tx",
    "rx": "Rx",
    "receive": "Rx",
}

FUNCTION_KEYWORDS = {
    "tx": ("pa", "up", "dac"),
    "rx": ("lna", "down", "adc"),
}


def overall_status(checks: Iterable[CheckResult]) -> Status:
    results = list(checks)
    if not results:
        return Status.UNKNOWN
    return max((result.status for result in results), key=STATUS_PRIORITY.get)


def required_function(requirement: LinkRequirement) -> str:
    direction = requirement.direction.strip().lower()
    if direction in DIRECTION_ALIASES:
        return DIRECTION_ALIASES[direction]

    is_terminal = requirement.application.strip().lower() == "terminal"
    if direction in {"ul", "uplink"}:
        return "Tx" if is_terminal else "Rx"
    if direction in {"dl", "downlink"}:
        return "Rx" if is_terminal else "Tx"
    return requirement.direction


def esa_band(application: str, direction: str):
    requirement = LinkRequirement(application, direction, 1.0, 1.0, 0.0, 1.0, 90.0)
    function    = required_function(requirement)
    normalized  = application.strip().lower()
    if normalized == "terminal":
        return (27.5, 31.0) if function == "Tx" else (17.7, 21.2)
    if normalized == "payload":
        return (17.7, 21.2) if function == "Tx" else (27.5, 31.0)

    return None


def _function_matches(component_function: str, wanted: str) -> bool:
    normalized = component_function.lower()
    if "integrated fem" in normalized or "trx" in normalized or wanted in normalized:
        return True
    return any(keyword in normalized for keyword in FUNCTION_KEYWORDS[wanted])


def _frequency_range(component: Component):
    if component.category.upper() == "MIXER":
        return component.value("rf_min_ghz"), component.value("rf_max_ghz")
    if component.category.upper() == "PLL":
        return component.value("output_freq_min_ghz"), component.value("output_freq_max_ghz")
    if component.category.upper() in {"ADC", "DAC", "CONVERTER"}:
        bandwidth = component.value("analog_bandwidth_ghz")
        return component.freq_min_ghz or 0.0, component.freq_max_ghz or bandwidth
    return component.freq_min_ghz, component.freq_max_ghz


def check_application(component: Component, requirement: LinkRequirement) -> CheckResult:
    application = component.application.strip().lower()
    wanted      = requirement.application.strip().lower()
    if application in {"common", "t/p", ""} or application == wanted:
        return CheckResult("application", Status.PASS, f"{component.application} 적용 대상을 지원합니다")
    return CheckResult(
        "application", Status.FAIL, f"필요 적용 대상은 {requirement.application}이지만 부품 적용 대상은 {component.application}입니다"
    )


def check_function(component: Component, requirement: LinkRequirement) -> CheckResult:
    category = component.category.upper()
    if category in {"PLL", "SWITCH"}:
        return CheckResult(rule="function", status=Status.PASS, message="방향에 영향을 받지 않는 단계입니다")
    wanted   = required_function(requirement).lower()
    function = component.function.lower()
    if not function:
        return CheckResult(rule="function", status=Status.UNKNOWN, message="기능 정보가 없습니다")
    if _function_matches(function, wanted):
        return CheckResult(
            rule="function",
            status=Status.PASS,
            message=f"{component.function} 기능이 필요한 방향과 일치합니다",
        )
    return CheckResult(
        rule="function",
        status=Status.FAIL,
        message=f"필요 방향 {wanted.upper()}과 {component.function} 기능이 일치하지 않습니다",
    )


def check_frequency(component: Component, requirement: LinkRequirement) -> CheckResult:
    low, high = _frequency_range(component)
    if component.category.upper() in {"ADC", "DAC", "CONVERTER"} and requirement.if_freq_ghz is not None:
        # Channel edges[GHz] = center frequency[GHz] +/- bandwidth[MHz]/2000.
        required_low  = requirement.if_freq_ghz - requirement.channel_bw_mhz / 2000.0
        required_high = requirement.if_freq_ghz + requirement.channel_bw_mhz / 2000.0
        label         = "IF"
    else:
        required_low  = requirement.required_low_ghz
        required_high = requirement.required_high_ghz
        label         = "RF"
    details = {
        "required_low_ghz": required_low,
        "required_high_ghz": required_high,
        "supported_low_ghz": low,
        "supported_high_ghz": high
    }
    if low is None or high is None:
        return CheckResult("frequency", Status.UNKNOWN, "주파수 범위 정보가 없습니다", details)
    if low <= required_low and high >= required_high:
        edge_margin = min(required_low - low, high - required_high)
        status      = Status.WARN if edge_margin < requirement.channel_bw_mhz / 1000.0 else Status.PASS
        return CheckResult(
            "frequency", status, f"필요 {label} 범위 {required_low:.4f}~{required_high:.4f} GHz를 지원합니다", {
                **details, "edge_margin_ghz": edge_margin
            }
        )
    return CheckResult(
        "frequency", Status.FAIL,
        f"필요 {label} 범위는 {required_low:.4f}~{required_high:.4f} GHz이고 지원 범위는 {low:g}~{high:g} GHz입니다", details
    )


def check_bandwidth(component: Component, requirement: LinkRequirement) -> CheckResult:
    bandwidth = component.value("channel_bandwidth_ghz", "analog_bandwidth_ghz")
    if bandwidth is None:
        return CheckResult("bandwidth", Status.UNKNOWN, "대역폭 정보가 없습니다")
    required = requirement.channel_bw_mhz / 1000.0
    if bandwidth >= required:
        margin = bandwidth - required
        return CheckResult(
            "bandwidth", Status.PASS if margin >= required * 0.1 else Status.WARN, f"대역폭 마진은 {margin:.3f} GHz입니다",
            {"margin_ghz": margin}
        )
    return CheckResult("bandwidth", Status.FAIL, f"필요 대역폭은 {required:.3f} GHz이고 지원 대역폭은 {bandwidth:.3f} GHz입니다")


def check_beams(component: Component, requirement: LinkRequirement) -> CheckResult:
    if component.category.upper() != "BFIC":
        return CheckResult("beams", Status.PASS, "빔 수 검사가 필요하지 않은 부품입니다")
    beams = component.value("number_beams")
    if beams is None:
        return CheckResult("beams", Status.UNKNOWN, "빔 수 정보가 없습니다")
    if beams >= requirement.num_beams:
        return CheckResult("beams", Status.PASS, f"{int(beams)}개 빔을 지원합니다")
    return CheckResult("beams", Status.FAIL, f"{requirement.num_beams}개 빔이 필요하지만 {int(beams)}개를 지원합니다")


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
        # Estimated IP1dB[dBm] = OP1dB[dBm] - power gain[dB].
        pa_ip1    = pa_op1 - pa_gain
        estimated = True
    if bfic_limit is None or pa_gain is None or pa_op1 is None or pa_ip1 is None:
        return CheckResult("bfic_pa_power", Status.UNKNOWN, "BFIC 또는 PA의 P1dB/이득 정보가 부족합니다")
    # Required PA input[dBm] = OP1dB-OBO-Gpa.
    required_input = pa_op1 - backoff_db - pa_gain
    available      = bfic_limit
    margin         = available - required_input
    if margin < 0:
        status, message = Status.FAIL, f"BFIC 선형 출력이 권장 PA 입력보다 {-margin:.2f} dB 낮습니다"
    elif margin < 1:
        status, message = Status.WARN, f"PA 구동 마진이 {margin:.2f} dB로 낮습니다"
    else:
        status, message = Status.PASS, f"PA 구동 마진은 {margin:.2f} dB입니다"
    return CheckResult(
        "bfic_pa_power", status, message, {
            "required_input_dbm": required_input,
            "available_dbm": available,
            "pa_ip1db_dbm": pa_ip1,
            "margin_db": margin
        }, estimated
    )


def check_pll_mixer(
    pll: Component,
    mixer: Component,
    rf_freq_ghz: float,
    if_freq_ghz: Optional[float],
    routing_loss_db: float = 1.0
) -> CheckResult:
    if if_freq_ghz is None:
        return CheckResult("pll_mixer", Status.UNKNOWN, "IF 주파수 정보가 없습니다")
    mixer_lo_min, mixer_lo_max = mixer.value("lo_min_ghz"), mixer.value("lo_max_ghz")
    pll_min, pll_max           = pll.value("output_freq_min_ghz"), pll.value("output_freq_max_ghz")
    if None in (mixer_lo_min, mixer_lo_max, pll_min, pll_max):
        return CheckResult("pll_mixer", Status.UNKNOWN, "PLL 또는 믹서의 LO 주파수 범위 정보가 부족합니다")
    multiplier = mixer.value("lo_multiplier") or 1.0
    # Mixer relation: internal LO = |RF-IF| or RF+IF; external LO divides by the internal multiplier.
    internal_candidates = sorted({abs(rf_freq_ghz - if_freq_ghz), rf_freq_ghz + if_freq_ghz})
    candidates          = [(internal, internal / multiplier) for internal in internal_candidates]
    valid = [
        (internal, lo_input) for internal, lo_input in candidates
        if mixer_lo_min <= lo_input <= mixer_lo_max and pll_min <= lo_input <= pll_max
    ]
    if not valid:
        return CheckResult(
            "pll_mixer", Status.FAIL, f"LO 입력 후보 {[round(x[1], 6) for x in candidates]} GHz가 믹서와 PLL의 공통 범위를 벗어납니다", {
                "internal_lo_candidates_ghz": internal_candidates,
                "lo_input_candidates_ghz": [x[1] for x in candidates],
                "lo_multiplier": multiplier
            }
        )
    output    = pll.value("output_power_dbm")
    drive_min = mixer.value("lo_drive_min_dbm")
    if output is None or drive_min is None:
        return CheckResult(
            "pll_mixer", Status.UNKNOWN, f"LO 입력 {valid[0][1]:g} GHz(내부 LO {valid[0][0]:g} GHz)는 유효하지만 LO 전력 정보가 없습니다",
            {
                "selected_lo_ghz": valid[0][1],
                "selected_internal_lo_ghz": valid[0][0],
                "lo_multiplier": multiplier
            }
        )
    # Delivered LO power and drive margin account for routing loss in dB.
    delivered = output - routing_loss_db
    margin    = delivered - drive_min
    status    = Status.FAIL if margin < 0 else Status.WARN if margin < 1 else Status.PASS
    return CheckResult(
        "pll_mixer", status, f"LO 입력 {valid[0][1]:g} GHz(내부 LO {valid[0][0]:g} GHz), 구동 마진 {margin:.2f} dB", {
            "selected_lo_ghz": valid[0][1],
            "selected_internal_lo_ghz": valid[0][0],
            "lo_multiplier": multiplier,
            "delivered_dbm": delivered,
            "margin_db": margin
        }
    )
