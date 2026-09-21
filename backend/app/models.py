from __future__ import annotations

from dataclasses import dataclass, field, fields
from enum import Enum
from typing import Any, Mapping


class Status(str, Enum):
    PASS    = "PASS"
    WARN    = "WARN"
    FAIL    = "FAIL"
    UNKNOWN = "UNKNOWN"


STATUS_PRIORITY = {Status.PASS: 0, Status.WARN: 1, Status.UNKNOWN: 2, Status.FAIL: 3}


@dataclass
class CheckResult:
    rule: str
    status: Status
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    estimated: bool         = False


@dataclass
class ComponentSpec:
    number_channels: float | None       = None
    number_beams: float | None          = None
    gain_db: float | None               = None
    channel_bandwidth_ghz: float | None = None
    output_p1db_dbm: float | None       = None
    psat_dbm: float | None              = None
    oip3_dbm: float | None              = None
    noise_figure_db: float | None       = None
    input_p1db_dbm: float | None        = None
    rms_phase_error_deg: float | None   = None
    rms_gain_error_db: float | None     = None
    evm_percent: float | None           = None
    pa_gain_db: float | None            = None
    pa_pae_percent: float | None        = None
    lna_gain_db: float | None           = None
    lna_iip3_dbm: float | None          = None
    insertion_loss_db: float | None     = None
    isolation_db: float | None          = None
    power_handling_dbm: float | None    = None
    rf_min_ghz: float | None            = None
    rf_max_ghz: float | None            = None
    if_min_ghz: float | None            = None
    if_max_ghz: float | None            = None
    lo_min_ghz: float | None            = None
    lo_max_ghz: float | None            = None
    lo_multiplier: float | None         = None
    conversion_gain_db: float | None    = None
    lo_drive_min_dbm: float | None      = None
    lo_drive_max_dbm: float | None      = None
    output_freq_min_ghz: float | None   = None
    output_freq_max_ghz: float | None   = None
    output_power_dbm: float | None      = None
    phase_noise_1khz: float | None      = None
    phase_noise_10khz: float | None     = None
    phase_noise_100khz: float | None    = None
    phase_noise_1mhz: float | None      = None
    resolution_bit: float | None        = None
    sample_rate_gsps: float | None      = None
    analog_bandwidth_ghz: float | None  = None
    snr_db: float | None                = None
    sinad_db: float | None              = None
    enob_bit: float | None              = None
    sfdr_dbc: float | None              = None
    digital_interface: str | None       = None

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> ComponentSpec:
        allowed = {item.name for item in fields(cls)}
        unknown = set(values) - allowed
        if unknown: raise ValueError(f"Unsupported component specifications: {', '.join(sorted(unknown))}")
        return cls(**values)

    def get(self, key: str, default: Any = None) -> Any:
        value = getattr(self, key, None)
        return default if value is None else value


@dataclass
class Component:
    component_id: int | None
    category: str
    manufacturer: str
    part_no: str
    application: str                   = "Common"
    function: str                      = ""
    process: str | None                = None
    freq_min_ghz: float | None         = None
    freq_max_ghz: float | None         = None
    supply_voltage_v: float | None     = None
    power_consumption_w: float | None  = None
    package: str | None                = None
    operating_temp_min_c: float | None = None
    operating_temp_max_c: float | None = None
    product_url: str | None            = None
    datasheet_url: str | None          = None
    datasheet_revision: str | None     = None
    datasheet_page: str | None         = None
    source_file: str | None            = None
    source_date: str | None            = None
    extraction_method: str | None      = None
    extraction_evidence: str | None    = None
    note: str | None                   = None
    grade: str                         = "Commercial-grade"
    specs: ComponentSpec               = field(default_factory=ComponentSpec)

    def __post_init__(self) -> None:
        if isinstance(self.specs, Mapping): self.specs = ComponentSpec.from_mapping(self.specs)

    def value(self, *keys: str, default: Any = None) -> Any:
        for key in keys:
            value = self.specs.get(key)
            if value is not None: return value
        return default


@dataclass
class LinkRequirement:
    application: str
    direction: str
    center_freq_ghz: float
    channel_bw_mhz: float
    target_throughput_mbps: float
    altitude_km: float
    elevation_deg: float
    num_beams: int                    = 1
    antenna_gain_db: float            = 34.0
    sky_temperature_k: float          = 30.0
    atmospheric_loss_db: float        = 1.0
    rain_loss_db: float               = 0.0
    scintillation_loss_db: float      = 0.0
    control_overhead: float           = 0.18
    fill_factor: float                = 0.88704
    feed_loss_db: float               = 0.0
    bf_error_db: float                = 0.5
    coherent_gain_db: float           = 28.5
    receiver_nf_db: float | None      = 2.0
    if_freq_ghz: float | None         = 4.0
    lo_routing_loss_db: float         = 1.0
    tx_input_power_dbm: float         = -20.0
    output_backoff_db: float          = 3.0
    nonlinear_snr_db: float           = 28.0
    max_slant_nonlinear_snr_db: float = 28.0
    peak_eirp_dbw: float | None       = None

    def validate(self) -> None:
        if self.center_freq_ghz <= 0: raise ValueError("Center frequency must be greater than zero.")
        if self.channel_bw_mhz <= 0: raise ValueError("Channel bandwidth must be greater than zero.")
        if self.target_throughput_mbps < 0: raise ValueError("Target throughput must be non-negative.")
        if self.altitude_km <= 0: raise ValueError("Altitude must be greater than zero.")
        if not 0 <= self.elevation_deg <= 90: raise ValueError("Elevation must be between 0 and 90 degrees.")
        if self.num_beams < 1: raise ValueError("Number of beams must be at least one.")
        if not 0 <= self.control_overhead < 1: raise ValueError("Control overhead must be in the range [0, 1).")
        if self.fill_factor <= 0: raise ValueError("Fill factor must be greater than zero.")

    @property
    def required_low_ghz(self) -> float:
        # Lower channel edge[GHz] = center[GHz] - bandwidth[MHz]/2000.
        return self.center_freq_ghz - self.channel_bw_mhz / 2000.0

    @property
    def required_high_ghz(self) -> float:
        # Upper channel edge[GHz] = center[GHz] + bandwidth[MHz]/2000.
        return self.center_freq_ghz + self.channel_bw_mhz / 2000.0


@dataclass
class PowerStageResult:
    stage: str
    part_no: str
    input_dbm: float
    gain_db: float
    output_dbm: float
    limit_dbm: float | None
    status: Status
    message: str


@dataclass
class PowerChainResult:
    stages: list[PowerStageResult]
    output_dbm: float
    status: Status
    checks: list[CheckResult] = field(default_factory=list)


@dataclass
class MCS:
    index: int
    modulation_order: int
    min_snr_db: float
    max_snr_db: float
    spectral_efficiency: float
    target_code_rate: float | None = None

    @property
    def modulation(self) -> str:
        return {
            2: "QPSK",
            4: "16QAM",
            6: "64QAM",
            8: "256QAM"
        }.get(self.modulation_order, f"Qm={self.modulation_order}")


@dataclass
class LinkBudgetResult:
    slant_range_km: float
    fspl_db: float
    system_noise_temperature_k: float
    gt_db_per_k: float
    eis_dbm: float
    snr_noise_db: float
    snr_total_db: float
    mcs: MCS | None
    throughput_mbps: float
    throughput_margin_mbps: float
    result: Status
    link_margin_db: float | None
    boresight_range_km: float
    peak_eirp_dbw: float
    peak_eirp_per_beam_dbw: float
    composite_eirp_backoff_dbw: float
    linear_eirp_per_beam_dbw: float
    boresight_path_loss_db: float
    max_slant_path_loss_db: float
    boresight_noise_snr_db: float
    boresight_nonlinear_snr_db: float
    boresight_total_snr_db: float
    max_slant_noise_snr_db: float
    max_slant_nonlinear_snr_db: float
    max_slant_total_snr_db: float
    max_mcs: MCS | None
    min_mcs: MCS | None
    max_throughput_mbps: float
    min_throughput_mbps: float


@dataclass
class TxCandidate:
    components: list[Component]
    checks: list[CheckResult]
    power_chain: PowerChainResult | None = None
    eirp_dbw: float | None               = None
    link_budget: LinkBudgetResult | None = None
    total_power_w: float | None          = None

    @property
    def status(self) -> Status:
        statuses = [check.status for check in self.checks]
        if self.power_chain: statuses.append(self.power_chain.status)
        if self.link_budget: statuses.append(self.link_budget.result)
        return max(statuses, key=STATUS_PRIORITY.get) if statuses else Status.UNKNOWN


@dataclass
class RxCandidate:
    components: list[Component]
    checks: list[CheckResult]
    total_gain_db: float
    total_nf_db: float
    total_power_w: float | None
