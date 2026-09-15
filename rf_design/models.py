from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class Status(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


@dataclass
class CheckResult:
    rule      : str
    status    : Status
    message   : str
    details   : Dict[str, Any] = field(default_factory=dict)
    estimated : bool           = False


@dataclass
class Component:
    component_id         : Optional[int]
    category             : str
    manufacturer         : str
    part_no              : str
    application          : str            = "Common"
    function             : str            = ""
    process              : Optional[str]  = None
    freq_min_ghz         : Optional[float] = None
    freq_max_ghz         : Optional[float] = None
    supply_voltage_v     : Optional[float] = None
    power_consumption_w  : Optional[float] = None
    package              : Optional[str]  = None
    operating_temp_min_c : Optional[float] = None
    operating_temp_max_c : Optional[float] = None
    product_url          : Optional[str]  = None
    datasheet_url        : Optional[str]  = None
    datasheet_revision   : Optional[str]  = None
    datasheet_page       : Optional[str]  = None
    source_file          : Optional[str]  = None
    source_date          : Optional[str]  = None
    extraction_method    : Optional[str]  = None
    extraction_evidence  : Optional[str]  = None
    note                 : Optional[str]  = None
    specs                : Dict[str, Any] = field(default_factory=dict)

    def value(self, *keys: str, default: Any = None) -> Any:
        for key in keys:
            value = self.specs.get(key)
            if value is not None:
                return value
        return default


@dataclass
class LinkRequirement:
    application            : str
    direction              : str
    center_freq_ghz        : float
    channel_bw_mhz         : float
    target_throughput_mbps : float
    altitude_km            : float
    elevation_deg          : float
    num_beams              : int             = 1
    antenna_gain_db        : float           = 34.0
    sky_temperature_k      : float           = 30.0
    atmospheric_loss_db    : float           = 1.0
    rain_loss_db           : float           = 0.0
    scintillation_loss_db  : float           = 0.0
    control_overhead       : float           = 0.18
    fill_factor            : float           = 0.88704
    feed_loss_db           : float           = 0.0
    bf_error_db            : float           = 0.5
    coherent_gain_db       : float           = 28.5
    receiver_nf_db         : Optional[float] = 2.0
    if_freq_ghz            : Optional[float] = 4.0
    lo_routing_loss_db     : float           = 1.0
    tx_input_power_dbm     : float           = -20.0
    output_backoff_db      : float           = 3.0
    nonlinear_snr_db       : float           = 28.0

    @property
    def required_low_ghz(self) -> float:
        return self.center_freq_ghz-self.channel_bw_mhz / 2000.0

    @property
    def required_high_ghz(self) -> float:
        return self.center_freq_ghz+self.channel_bw_mhz / 2000.0


@dataclass
class PowerStageResult:
    stage      : str
    part_no    : str
    input_dbm  : float
    gain_db    : float
    output_dbm : float
    limit_dbm  : Optional[float]
    status     : Status
    message    : str


@dataclass
class PowerChainResult:
    stages     : List[PowerStageResult]
    output_dbm : float
    status     : Status
    checks     : List[CheckResult] = field(default_factory=list)


@dataclass
class MCS:
    index               : int
    modulation_order    : int
    min_snr_db          : float
    max_snr_db          : float
    spectral_efficiency : float
    target_code_rate    : Optional[float] = None

    @property
    def modulation(self) -> str:
        return {2: "QPSK", 4: "16QAM", 6: "64QAM", 8: "256QAM"}.get(
            self.modulation_order, f"Qm={self.modulation_order}"
        )


@dataclass
class LinkBudgetResult:
    slant_range_km            : float
    fspl_db                   : float
    system_noise_temperature_k : float
    gt_db_per_k               : float
    eis_dbm                   : float
    snr_noise_db              : float
    snr_total_db              : float
    mcs                       : Optional[MCS]
    throughput_mbps           : float
    throughput_margin_mbps    : float
    result                    : Status
    link_margin_db            : Optional[float]


@dataclass
class DesignCandidate:
    components    : List[Component]
    checks        : List[CheckResult]
    power_chain   : Optional[PowerChainResult] = None
    eirp_dbw      : Optional[float]            = None
    link_budget   : Optional[LinkBudgetResult] = None
    total_power_w : Optional[float]            = None

    @property
    def status(self) -> Status:
        statuses = [check.status for check in self.checks]
        if self.power_chain:
            statuses.append(self.power_chain.status)
        if self.link_budget:
            statuses.append(self.link_budget.result)
        priority = {Status.PASS: 0, Status.WARN: 1, Status.UNKNOWN: 2, Status.FAIL: 3}
        return max(statuses, key=priority.get) if statuses else Status.UNKNOWN
