from __future__ import annotations

import itertools
from typing import Dict, Iterable, List, Sequence, Tuple

from .compatibility import check_bfic_pa, check_component, check_pll_mixer, overall_status, required_function
from .link_budget import calculate_link_budget, calculate_peak_eirp
from .noise_figure import calculate_receiver_nf
from .power_chain import calculate_tx_chain
from ..models import STATUS_PRIORITY, CheckResult, Component, LinkRequirement, MCS, RxCandidate, Status, TxCandidate
from ..preferences import ComponentKey, Preferences
from ..formulas import FormulaEngine, default_profile


def filter_components(components: Iterable[Component],
                      requirement: LinkRequirement) -> Tuple[List[Component], Dict[int, List[CheckResult]]]:
    accepted, results = [], {}
    for component in components:
        checks                                           = check_component(component, requirement)
        results[component.component_id or id(component)] = checks
        if overall_status(checks) != Status.FAIL:
            accepted.append(component)
    return accepted, results


def _by_category(components: Iterable[Component]) -> Dict[str, List[Component]]:
    groups: Dict[str, List[Component]] = {}
    for component in components:
        groups.setdefault(component.category.upper(), []).append(component)
        if component.category.upper() == "FEM":
            groups.setdefault("PA", []).append(component)
            groups.setdefault("LNA", []).append(component)
    return groups


def _total_power(components: Sequence[Component]):
    values = [component.power_consumption_w for component in components]
    return sum(value for value in values if value is not None) if any(value is not None for value in values) else None


def _commercial_count(components: Sequence[Component]) -> int:
    return sum(component.grade != "Space-grade" for component in components)


def _restrict_components(
    components: Sequence[Component],
    pinned_components: Sequence[ComponentKey],
    categories: set[str],
) -> List[Component]:
    relevant = [item for item in pinned_components if item.category.upper() in categories]
    if not relevant: return list(components)
    return [component for component in components if any(item.matches(component) for item in relevant)]


def _incompatible_pins(
    accepted: Sequence[Component],
    pinned_components: Sequence[ComponentKey],
) -> List[ComponentKey]:
    return [item for item in pinned_components if not any(item.matches(component) for component in accepted)]


def _pin_warning(component: ComponentKey) -> str:
    return f"고정 부품 {component.manufacturer} {component.part_no}이(가) 요구사항과 호환되지 않습니다."


def generate_tx_candidates(
    requirement: LinkRequirement,
    components: Iterable[Component],
    mcs_table: Iterable[MCS],
    limit: int = 5000,
    preferences: Preferences | None = None,
    pinned_components: Sequence[ComponentKey] = (),
    formula_engine: FormulaEngine | None = None,
) -> Tuple[List[TxCandidate], List[str]]:
    engine       = formula_engine or FormulaEngine(default_profile())
    mcs_table    = list(mcs_table)
    accepted, _  = filter_components(components, requirement)
    incompatible = _incompatible_pins(accepted, pinned_components)
    if incompatible: return [], [_pin_warning(item) for item in incompatible]
    groups          = _by_category(accepted)
    groups["MIXER"] = _restrict_components(groups.get("MIXER", []), pinned_components, {"MIXER"})
    groups["PLL"]   = _restrict_components(groups.get("PLL", []), pinned_components, {"PLL"})
    groups["BFIC"]  = _restrict_components(groups.get("BFIC", []), pinned_components, {"BFIC"})
    groups["PA"]    = _restrict_components(groups.get("PA", []), pinned_components, {"PA", "FEM"})
    required        = ["MIXER", "PLL", "BFIC", "PA"]
    missing         = [category for category in required if not groups.get(category)]
    if missing: return [], [f"사용 가능한 {category} 후보가 없습니다." for category in missing]
    switch_items = _restrict_components(groups.get("SWITCH", []), pinned_components, {"SWITCH"})
    switches = switch_items if any(item.category.upper() == "SWITCH"
                                   for item in pinned_components) else [None] + switch_items
    converter_items               = groups.get("DAC", []) + groups.get("CONVERTER", [])
    converter_items               = _restrict_components(converter_items, pinned_components, {"DAC", "CONVERTER"})
    converters                    = converter_items or [None]
    candidates: List[TxCandidate] = []
    combinations                  = itertools.product(converters, groups["MIXER"], groups["PLL"], groups["BFIC"], groups["PA"], switches)
    for index, (converter, mixer, pll, bfic, pa, switch) in enumerate(combinations):
        if index >= limit: break
        pair_checks = [
            check_pll_mixer(
                pll, mixer, requirement.center_freq_ghz, requirement.if_freq_ghz, requirement.lo_routing_loss_db
            ),
            check_bfic_pa(bfic, pa, requirement.output_backoff_db),
        ]
        if any(check.status == Status.FAIL for check in pair_checks): continue
        chain = [component for component in (converter, mixer, bfic, pa, switch) if component is not None]
        power = calculate_tx_chain(
            chain,
            requirement.tx_input_power_dbm,
            requirement.output_backoff_db,
            automatic_level_control=True,
            formula_engine=engine,
        )
        peak_eirp = calculate_peak_eirp(
            power.output_dbm + requirement.output_backoff_db,
            requirement.antenna_gain_db,
            requirement.feed_loss_db,
            engine,
        )
        link      = calculate_link_budget(requirement, peak_eirp, mcs_table, formula_engine=engine)
        eirp      = link.linear_eirp_per_beam_dbw
        candidate = TxCandidate(chain + [pll], pair_checks, power, eirp, link, _total_power(chain + [pll]))
        candidate.preference_score, candidate.preference_matches = (preferences
                                                                    or Preferences()).score(candidate.components)
        candidates.append(candidate)
    candidates.sort(
        key=lambda item: engine.ranking_key(
            "Tx", {
                "status_priority":
                STATUS_PRIORITY[item.status],
                "commercial_count":
                _commercial_count(item.components),
                "application_is_payload":
                float(requirement.application.lower() == "payload"),
                "preference_score":
                item.preference_score,
                "link_margin_db":
                item.link_budget.link_margin_db
                if item.link_budget and item.link_budget.link_margin_db is not None else -9999,
                "throughput_margin_mbps":
                item.link_budget.throughput_margin_mbps if item.link_budget else -9999,
                "total_power_w":
                item.total_power_w if item.total_power_w is not None else 9999,
                "component_count":
                len(item.components),
                "total_nf_db":
                9999,
                "total_gain_db":
                -9999,
            }
        )
    )
    for candidate in candidates[:50]:
        trace            = []
        power_components = [item for item in candidate.components if item.category.upper() != "PLL"]
        power = calculate_tx_chain(
            power_components,
            requirement.tx_input_power_dbm,
            requirement.output_backoff_db,
            automatic_level_control=True,
            formula_engine=engine,
            calculation_trace=trace,
        )
        peak_eirp = calculate_peak_eirp(
            power.output_dbm + requirement.output_backoff_db,
            requirement.antenna_gain_db,
            requirement.feed_loss_db,
            engine,
            trace,
        )
        calculate_link_budget(
            requirement,
            peak_eirp,
            mcs_table,
            formula_engine=engine,
            calculation_trace=trace,
        )
        candidate.calculation_trace = trace
    if not candidates: return [], ["LO 및 출력 제약을 만족하는 송신 조합이 없습니다."]
    return candidates, []


def generate_rx_candidates(
    requirement: LinkRequirement,
    components: Iterable[Component],
    limit: int = 5000,
    preferences: Preferences | None = None,
    pinned_components: Sequence[ComponentKey] = (),
    formula_engine: FormulaEngine | None = None,
) -> Tuple[List[RxCandidate], List[str]]:
    engine       = formula_engine or FormulaEngine(default_profile())
    accepted, _  = filter_components(components, requirement)
    incompatible = _incompatible_pins(accepted, pinned_components)
    if incompatible: return [], [_pin_warning(item) for item in incompatible]
    groups          = _by_category(accepted)
    groups["LNA"]   = _restrict_components(groups.get("LNA", []), pinned_components, {"LNA", "FEM"})
    groups["BFIC"]  = _restrict_components(groups.get("BFIC", []), pinned_components, {"BFIC"})
    groups["MIXER"] = _restrict_components(groups.get("MIXER", []), pinned_components, {"MIXER"})
    groups["PLL"]   = _restrict_components(groups.get("PLL", []), pinned_components, {"PLL"})
    required        = ["LNA", "BFIC", "MIXER", "PLL"]
    missing         = [category for category in required if not groups.get(category)]
    if missing: return [], [f"사용 가능한 {category} 후보가 없습니다." for category in missing]
    switch_items    = _restrict_components(groups.get("SWITCH", []), pinned_components, {"SWITCH"})
    switches        = switch_items or [None]
    converter_items = groups.get("ADC", []) + groups.get("CONVERTER", [])
    converter_items = _restrict_components(converter_items, pinned_components, {"ADC", "CONVERTER"})
    converters      = converter_items or [None]
    results         = []
    combinations = itertools.product(
        switches, groups["LNA"], groups["BFIC"], groups["MIXER"], converters, groups["PLL"]
    )
    for index, (switch, lna, bfic, mixer, converter, pll) in enumerate(combinations):
        if index >= limit: break
        lo_check = check_pll_mixer(
            pll, mixer, requirement.center_freq_ghz, requirement.if_freq_ghz, requirement.lo_routing_loss_db
        )
        if lo_check.status == Status.FAIL: continue
        rf_chain = [component for component in (switch, lna, bfic, mixer) if component is not None]
        try:
            gain, nf = calculate_receiver_nf(rf_chain, engine)
        except ValueError:
            continue
        chain     = rf_chain + [component for component in (converter, pll) if component is not None]
        candidate = RxCandidate(chain, [lo_check], gain, nf, _total_power(chain))
        candidate.preference_score, candidate.preference_matches = (preferences
                                                                    or Preferences()).score(candidate.components)
        results.append(candidate)
    results.sort(
        key=lambda item: engine.ranking_key(
            "Rx", {
                "status_priority": 0,
                "commercial_count": _commercial_count(item.components),
                "application_is_payload": float(requirement.application.lower() == "payload"),
                "preference_score": item.preference_score,
                "link_margin_db": -9999,
                "throughput_margin_mbps": -9999,
                "total_power_w": item.total_power_w if item.total_power_w is not None else 9999,
                "component_count": len(item.components),
                "total_nf_db": item.total_nf_db,
                "total_gain_db": item.total_gain_db,
            }
        )
    )
    for candidate in results[:50]:
        trace = []
        rf_chain = [
            item for item in candidate.components if item.category.upper() in {"SWITCH", "LNA", "BFIC", "MIXER", "FEM"}
        ]
        calculate_receiver_nf(rf_chain, engine, trace)
        candidate.calculation_trace = trace
    if not results: return [], ["LO, 이득 및 잡음 지수 제약을 만족하는 수신 조합이 없습니다."]
    return results, []
