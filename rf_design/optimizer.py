from __future__ import annotations

import itertools
from typing import Dict, Iterable, List, Sequence, Tuple

from .engine.compatibility import check_bfic_pa, check_component, check_pll_mixer, overall_status, required_function
from .engine.link_budget import calculate_eirp, calculate_link_budget
from .engine.noise_figure import calculate_receiver_nf
from .engine.power_chain import calculate_tx_chain
from .models import CheckResult, Component, DesignCandidate, LinkRequirement, MCS, Status


def filter_components(components: Iterable[Component], requirement: LinkRequirement) -> Tuple[List[Component], Dict[int, List[CheckResult]]]:
    accepted,results = [],{}
    for component in components:
        checks = check_component(component, requirement)
        results[component.component_id or id(component)] = checks
        if overall_status(checks) != Status.FAIL:
            accepted.append(component)
    return accepted,results


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


def generate_tx_candidates(requirement: LinkRequirement, components: Iterable[Component], mcs_table: Iterable[MCS], limit: int = 5000) -> Tuple[List[DesignCandidate], List[str]]:
    accepted,_ = filter_components(components, requirement)
    groups     = _by_category(accepted)
    required   = ["MIXER","PLL","BFIC","PA"]
    missing    = [category for category in required if not groups.get(category)]
    if missing: return [],[f"{category} 후보가 없습니다." for category in missing]
    switches   = [None]+groups.get("SWITCH", [])
    converters = groups.get("DAC") or groups.get("CONVERTER") or [None]
    candidates: List[DesignCandidate] = []
    combinations = itertools.product(converters, groups["MIXER"], groups["PLL"], groups["BFIC"], groups["PA"], switches)
    for index,(converter,mixer,pll,bfic,pa,switch) in enumerate(combinations):
        if index >= limit: break
        pair_checks = [
            check_pll_mixer(pll, mixer, requirement.center_freq_ghz, requirement.if_freq_ghz, requirement.lo_routing_loss_db),
            check_bfic_pa(bfic, pa, requirement.output_backoff_db),
        ]
        if any(check.status == Status.FAIL for check in pair_checks): continue
        chain = [component for component in (converter,mixer,bfic,pa,switch) if component is not None]
        power = calculate_tx_chain(
            chain,
            requirement.tx_input_power_dbm,
            requirement.output_backoff_db,
            automatic_level_control=True,
        )
        eirp  = calculate_eirp(power.output_dbm, requirement.antenna_gain_db, requirement.feed_loss_db, requirement.num_beams)
        link  = calculate_link_budget(requirement, eirp, mcs_table)
        candidates.append(DesignCandidate(chain+[pll], pair_checks, power, eirp, link, _total_power(chain+[pll])))
    candidates.sort(key=lambda item: (
        item.status != Status.PASS,
        -(item.link_budget.link_margin_db if item.link_budget and item.link_budget.link_margin_db is not None else -9999),
        -(item.link_budget.throughput_margin_mbps if item.link_budget else -9999),
        item.total_power_w if item.total_power_w is not None else 9999,
        len(item.components),
    ))
    if not candidates: return [],["부품 간 LO 또는 출력 조건을 만족하는 Tx 조합이 없습니다."]
    return candidates,[]


def generate_rx_candidates(requirement: LinkRequirement, components: Iterable[Component], limit: int = 5000) -> Tuple[List[dict], List[str]]:
    accepted,_ = filter_components(components, requirement)
    groups     = _by_category(accepted)
    required   = ["LNA","BFIC","MIXER","PLL"]
    missing    = [category for category in required if not groups.get(category)]
    if missing: return [],[f"{category} 후보가 없습니다." for category in missing]
    switches   = groups.get("SWITCH") or [None]
    converters = groups.get("ADC") or groups.get("CONVERTER") or [None]
    results    = []
    combinations = itertools.product(switches, groups["LNA"], groups["BFIC"], groups["MIXER"], converters, groups["PLL"])
    for index,(switch,lna,bfic,mixer,converter,pll) in enumerate(combinations):
        if index >= limit: break
        lo_check = check_pll_mixer(pll, mixer, requirement.center_freq_ghz, requirement.if_freq_ghz, requirement.lo_routing_loss_db)
        if lo_check.status == Status.FAIL: continue
        rf_chain = [component for component in (switch,lna,bfic,mixer) if component is not None]
        try:
            gain,nf = calculate_receiver_nf(rf_chain)
        except ValueError:
            continue
        chain = rf_chain+[component for component in (converter,pll) if component is not None]
        results.append({"components": chain, "checks": [lo_check], "total_gain_db": gain, "total_nf_db": nf, "total_power_w": _total_power(chain)})
    results.sort(key=lambda item: (item["total_nf_db"], -item["total_gain_db"], item["total_power_w"] or 9999))
    if not results: return [],["부품 간 LO 조건과 수신 이득/NF 조건을 만족하는 Rx 조합이 없습니다."]
    return results,[]
