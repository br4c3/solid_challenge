from __future__ import annotations

from typing import Iterable, List, Optional

from ..models import STATUS_PRIORITY, CheckResult, Component, LinkRequirement, Status


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
    if application.strip().lower() == "terminal": return (27.5, 31.0) if function == "Tx" else (17.7, 21.2)
    if application.strip().lower() == "payload": return (17.7, 21.2) if function == "Tx" else (27.5, 31.0)

    return None


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
        return CheckResult("application", Status.PASS, f"{component.application} application is supported")
    return CheckResult(
        "application", Status.FAIL,
        f"Required application is {requirement.application}; component application is {component.application}"
    )


def check_function(component: Component, requirement: LinkRequirement) -> CheckResult:
    category = component.category.upper()
    if category in {"PLL", "SWITCH"}:
        return CheckResult("function", Status.PASS, "Direction-independent stage")
    wanted   = required_function(requirement).lower()
    function = component.function.lower()
    if not function:
        return CheckResult("function", Status.UNKNOWN, "Function information is unavailable")
    if "integrated fem" in function:
        return CheckResult("function", Status.PASS, "Integrated FEM supports Tx and Rx paths")
    if "trx" in function or wanted in function or (wanted == "tx" and any(
        x in function for x in ("pa", "up", "dac")
    )) or (wanted == "rx" and any(x in function for x in ("lna", "down", "adc"))):
        return CheckResult("function", Status.PASS, f"{component.function} matches the required direction")
    return CheckResult(
        "function", Status.FAIL, f"Required direction {wanted.upper()} does not match {component.function}"
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
        return CheckResult("frequency", Status.UNKNOWN, "Frequency range is unavailable", details)
    if low <= required_low and high >= required_high:
        edge_margin = min(required_low - low, high - required_high)
        status      = Status.WARN if edge_margin < requirement.channel_bw_mhz / 1000.0 else Status.PASS
        return CheckResult(
            "frequency", status, f"Required {label} range {required_low:.4f}~{required_high:.4f} GHz is supported", {
                **details, "edge_margin_ghz": edge_margin
            }
        )
    return CheckResult(
        "frequency", Status.FAIL,
        f"Required {label} range is {required_low:.4f}~{required_high:.4f} GHz; supported range is {low:g}~{high:g} GHz",
        details
    )


def check_bandwidth(component: Component, requirement: LinkRequirement) -> CheckResult:
    bandwidth = component.value("channel_bandwidth_ghz", "analog_bandwidth_ghz")
    if bandwidth is None:
        return CheckResult("bandwidth", Status.UNKNOWN, "Bandwidth is unavailable")
    required = requirement.channel_bw_mhz / 1000.0
    if bandwidth >= required:
        margin = bandwidth - required
        return CheckResult(
            "bandwidth", Status.PASS if margin >= required * 0.1 else Status.WARN,
            f"Bandwidth margin is {margin:.3f} GHz", {"margin_ghz": margin}
        )
    return CheckResult(
        "bandwidth", Status.FAIL,
        f"Required bandwidth is {required:.3f} GHz; supported bandwidth is {bandwidth:.3f} GHz"
    )


def check_beams(component: Component, requirement: LinkRequirement) -> CheckResult:
    if component.category.upper() != "BFIC":
        return CheckResult("beams", Status.PASS, "Beam-count check is not applicable")
    beams = component.value("number_beams")
    if beams is None:
        return CheckResult("beams", Status.UNKNOWN, "Beam-count information is unavailable")
    if beams >= requirement.num_beams:
        return CheckResult("beams", Status.PASS, f"Supports {int(beams)} beams")
    return CheckResult("beams", Status.FAIL, f"Requires {requirement.num_beams} beams; supports {int(beams)}")


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
        return CheckResult("bfic_pa_power", Status.UNKNOWN, "BFIC or PA P1dB/gain information is incomplete")
    # Required PA input[dBm] = OP1dB-OBO-Gpa.
    required_input = pa_op1 - backoff_db - pa_gain
    available      = bfic_limit
    margin         = available - required_input
    if margin < 0:
        status, message = Status.FAIL, f"BFIC linear output is {-margin:.2f} dB below the recommended PA input"
    elif margin < 1:
        status, message = Status.WARN, f"PA drive margin is low at {margin:.2f} dB"
    else:
        status, message = Status.PASS, f"PA drive margin is {margin:.2f} dB"
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
        return CheckResult("pll_mixer", Status.UNKNOWN, "IF frequency is unavailable")
    mixer_lo_min, mixer_lo_max = mixer.value("lo_min_ghz"), mixer.value("lo_max_ghz")
    pll_min, pll_max           = pll.value("output_freq_min_ghz"), pll.value("output_freq_max_ghz")
    if None in (mixer_lo_min, mixer_lo_max, pll_min, pll_max):
        return CheckResult("pll_mixer", Status.UNKNOWN, "PLL or mixer LO frequency range is incomplete")
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
            "pll_mixer", Status.FAIL,
            f"LO input candidates {[round(x[1], 6) for x in candidates]} GHz are outside the common mixer/PLL range", {
                "internal_lo_candidates_ghz": internal_candidates,
                "lo_input_candidates_ghz": [x[1] for x in candidates],
                "lo_multiplier": multiplier
            }
        )
    output    = pll.value("output_power_dbm")
    drive_min = mixer.value("lo_drive_min_dbm")
    if output is None or drive_min is None:
        return CheckResult(
            "pll_mixer", Status.UNKNOWN,
            f"LO input {valid[0][1]:g} GHz (internal LO {valid[0][0]:g} GHz) is valid, but LO power is unavailable", {
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
        "pll_mixer", status,
        f"LO input {valid[0][1]:g} GHz (internal LO {valid[0][0]:g} GHz), drive margin {margin:.2f} dB", {
            "selected_lo_ghz": valid[0][1],
            "selected_internal_lo_ghz": valid[0][0],
            "lo_multiplier": multiplier,
            "delivered_dbm": delivered,
            "margin_db": margin
        }
    )
