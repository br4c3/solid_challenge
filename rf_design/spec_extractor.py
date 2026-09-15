from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class SpecMatch:
    field    : str
    value    : float
    unit     : str
    evidence : str


NUMBER       = r"[-+]?\d+(?:\.\d+)?"
FREQUENCY    = rf"(?P<value>{NUMBER})\s*(?P<unit>[GMK]?Hz)"
RANGE_JOINER = r"(?:to|through|[-–—])"

FIELD_BOUNDS = {
    "freq_min_ghz": (0.0,300.0),
    "freq_max_ghz": (0.0,300.0),
    "rf_min_ghz": (0.0,300.0),
    "rf_max_ghz": (0.0,300.0),
    "if_min_ghz": (0.0,300.0),
    "if_max_ghz": (0.0,300.0),
    "lo_min_ghz": (0.0,300.0),
    "lo_max_ghz": (0.0,300.0),
    "output_freq_min_ghz": (0.0,300.0),
    "output_freq_max_ghz": (0.0,300.0),
    "gain_db": (-60.0,100.0),
    "pa_gain_db": (-60.0,100.0),
    "lna_gain_db": (-60.0,100.0),
    "conversion_gain_db": (-60.0,100.0),
    "noise_figure_db": (0.0,50.0),
    "output_p1db_dbm": (-100.0,100.0),
    "psat_dbm": (-100.0,100.0),
    "output_power_dbm": (-100.0,100.0),
    "lo_drive_min_dbm": (-100.0,50.0),
    "pae_percent": (0.0,100.0),
    "pa_pae_percent": (0.0,100.0),
    "phase_noise_100khz": (-250.0,0.0),
}


def normalize_text(text: str) -> str:
    text = (text or "").replace("−", "-").replace("–", "-").replace("—", "-")
    return " ".join(text.split())


def frequency_to_ghz(value: float, unit: str) -> float:
    factors = {"khz": 1e-6, "mhz": 1e-3, "ghz": 1.0, "hz": 1e-9}
    return value * factors[unit.lower()]


def valid_value(field: str, value: float) -> bool:
    bounds = FIELD_BOUNDS.get(field)
    return bounds is None or bounds[0] <= value <= bounds[1]


def _frequency_candidates(text: str, labels: Sequence[Tuple[str,int]]) -> List[Tuple[float,float,int,str]]:
    candidates = []
    for label,priority in labels:
        patterns = [
            rf"(?:{label})[^\d]{{0,45}}(?P<low>{NUMBER})\s*(?P<low_unit>[GMK]?Hz)\s*{RANGE_JOINER}\s*(?P<high>{NUMBER})\s*(?P<high_unit>[GMK]?Hz)",
            rf"(?P<low>{NUMBER})\s*(?P<low_unit>[GMK]?Hz)\s*{RANGE_JOINER}\s*(?P<high>{NUMBER})\s*(?P<high_unit>[GMK]?Hz)[^.;]{{0,35}}(?:{label})",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.I):
                low  = frequency_to_ghz(float(match.group("low")), match.group("low_unit"))
                high = frequency_to_ghz(float(match.group("high")), match.group("high_unit"))
                low,high = sorted((low,high))
                candidates.append((low,high,priority,match.group(0)))
    return candidates


def _best_range(text: str, labels: Sequence[Tuple[str,int]]) -> Optional[Tuple[float,float,str]]:
    candidates = _frequency_candidates(text, labels)
    if not candidates: return None
    low,high,_,evidence = max(candidates, key=lambda row: (row[2],row[1]-row[0]))
    return low,high,evidence


def extract_frequency_specs(text: str, category: str = "") -> List[SpecMatch]:
    category = category.upper()
    output   = []
    groups: List[Tuple[str,str,Sequence[Tuple[str,int]]]] = []

    if category == "MIXER":
        groups = [
            ("rf_min_ghz","rf_max_ghz",[(r"RF(?: input)? frequency(?: range)?",100),(r"RF range",95)]),
            ("if_min_ghz","if_max_ghz",[(r"IF(?: input| output)? frequency(?: range)?",100),(r"IF range",95)]),
            ("lo_min_ghz","lo_max_ghz",[(r"LO(?: input)? frequency(?: range)?",100),(r"LO range",95)]),
        ]
    elif category == "PLL":
        groups = [
            (
                "output_freq_min_ghz",
                "output_freq_max_ghz",
                [
                    (r"output frequency(?: range)?",110),
                    (r"wide\s*band frequency synthesizer",105),
                    (r"frequency synthesizer",90),
                ],
            ),
        ]
    elif category not in {"ADC","DAC"}:
        generic_labels = [(r"(?:)",10)] if not category else []
        groups = [
            (
                "freq_min_ghz",
                "freq_max_ghz",
                [
                    (r"operating frequency(?: range)?",110),
                    (r"RF frequency(?: range)?",105),
                    (r"frequency range",100),
                    (r"operating(?: from)?",90),
                    (r"operation",85),
                ]+generic_labels,
            ),
        ]

    for low_field,high_field,labels in groups:
        result = _best_range(text, labels)
        if not result: continue
        low,high,evidence = result
        if valid_value(low_field, low): output.append(SpecMatch(low_field, low, "GHz", evidence))
        if valid_value(high_field, high): output.append(SpecMatch(high_field, high, "GHz", evidence))
    return output


GAIN_PATTERNS = (
    rf"(?:small.signal gain|gain)\s*(?:of|is|:|=)\s*(?P<value>{NUMBER})\s*dB",
    rf"(?P<value>{NUMBER})\s*dB\s+(?:of\s+)?small.signal gain",
)

LABELED_PATTERNS: Dict[str,Tuple[str,Sequence[str]]] = {
    "gain_db": ("dB",GAIN_PATTERNS),
    "output_p1db_dbm": (
        "dBm",
        (rf"(?:output\s+)?(?:OP1dB|P1dB)(?: output power)?\s*(?:of|is|:|=)\s*(?P<value>{NUMBER})\s*dBm",),
    ),
    "psat_dbm": (
        "dBm",
        (rf"(?:P[_ ]?sat|saturated output power)\s*(?:is\s+)?(?:greater than|>|≥)?\s*(?P<value>{NUMBER})\s*dBm",),
    ),
    "noise_figure_db": ("dB",(rf"noise figure\s*(?:of|is|:|=)\s*(?P<value>{NUMBER})\s*dB",)),
    "oip3_dbm": ("dBm",(rf"OIP3\s*(?:of|is|:|=)\s*(?P<value>{NUMBER})\s*dBm",)),
    "insertion_loss_db": ("dB",(rf"insertion loss[^\d+-]{{0,30}}(?P<value>{NUMBER})\s*dB",)),
    "isolation_db": ("dB",(rf"isolation\s*(?:of|is|:|=)\s*(?P<value>{NUMBER})\s*dB",)),
    "lo_drive_min_dbm": ("dBm",(rf"LO\s*(?:drive|power)(?: level)?\s*(?:of|is|:|=)\s*(?P<value>{NUMBER})\s*dBm",)),
    "pa_pae_percent": ("%",(rf"(?:PAE|power.added efficiency)\s*(?:of|is|:|=)\s*(?P<value>{NUMBER})\s*%",)),
    "pae_percent": ("%",(rf"(?:PAE|power.added efficiency)\s*(?:of|is|:|=)\s*(?P<value>{NUMBER})\s*%",)),
    "phase_noise_100khz": ("dBc/Hz",(rf"(?P<value>{NUMBER})\s*dBc/Hz[^\d+-]{{0,30}}100\s*kHz",)),
}


def extract_labeled_specs(text: str, category: str = "") -> List[SpecMatch]:
    text     = normalize_text(text)
    category = category.upper()
    output   = extract_frequency_specs(text, category)
    allowed = {
        "BFIC": {"gain_db","output_p1db_dbm","noise_figure_db","oip3_dbm","pae_percent"},
        "PA": {"output_p1db_dbm","psat_dbm","pa_pae_percent"},
        "LNA": {"output_p1db_dbm","noise_figure_db","oip3_dbm"},
        "SWITCH": {"output_p1db_dbm","insertion_loss_db","isolation_db"},
        "MIXER": {"noise_figure_db","insertion_loss_db","isolation_db","lo_drive_min_dbm"},
        "PLL": {"phase_noise_100khz"},
        "ADC": set(),
        "DAC": set(),
    }.get(category, set(LABELED_PATTERNS))
    patterns = {key:value for key,value in LABELED_PATTERNS.items() if key in allowed}

    if category == "PA":
        patterns["pa_gain_db"] = ("dB",GAIN_PATTERNS)
    elif category == "LNA":
        patterns["lna_gain_db"] = ("dB",GAIN_PATTERNS)
    elif category == "MIXER":
        patterns["conversion_gain_db"] = ("dB",(
            rf"conversion gain\s*(?:of|is|:|=)\s*(?P<value>{NUMBER})\s*dB",
            rf"(?P<value>{NUMBER})\s*dB\s+conversion gain",
        ))
    elif category in {"ADC","DAC"}:
        patterns["resolution_bit"]   = ("bit",(rf"(?P<value>{NUMBER})\s*[- ]?bit",))
        patterns["sample_rate_gsps"] = ("GSPS",(rf"(?P<value>{NUMBER})\s*GSPS",))
        if category == "ADC": patterns["analog_bandwidth_ghz"] = ("GHz",(rf"analog(?: input)? bandwidth\s*(?:of|is|:|=|to)?\s*(?P<value>{NUMBER})\s*GHz",))

    seen = {item.field for item in output}
    for field,(unit,field_patterns) in patterns.items():
        if field in seen: continue
        match = next((result for pattern in field_patterns if (result := re.search(pattern, text, re.I))), None)
        if not match: continue
        value = float(match.group("value"))
        if valid_value(field, value): output.append(SpecMatch(field, value, unit, match.group(0)))
    return output
