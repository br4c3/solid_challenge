#!/usr/bin/env python3
"""Crawl product pages, download datasheets, extract specs, and write CSV."""
from __future__ import annotations

import csv
import argparse
import json
import os
import re
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

from backend.config import PipelineConfig, load_config
from backend.app.catalog.datasheet import extract_fields_from_pages, extract_pdf_pages
from backend.app.catalog.importer import component_from_csv_row, import_components, import_mcs
from backend.app.catalog.repository import ComponentRepository

SEED_CSV            = ROOT / "data/catalog/manufacturer_product_seeds.csv"
PDF_DIR             = ROOT / "data/pdfs"
QORVO_DOWNLOAD_LOCK = threading.Lock()

MANUFACTURER_DOMAINS = {
    "Qorvo": ("qorvo.com", ),
    "Anokiwave": ("anokiwave.com", ),
    "Analog Devices": ("analog.com", ),
    "Texas Instruments": ("ti.com", ),
    "Renesas": ("renesas.com", "axiro.com"),
}

DIRECT_DATASHEETS = {
    "HMC517-DIE": "https://www.analog.com/media/en/technical-documentation/data-sheets/hmc517chips.pdf",
    "HMC751": "https://www.analog.com/media/en/technical-documentation/data-sheets/hmc751.pdf",
    "ADRF5024": "https://www.analog.com/media/en/technical-documentation/data-sheets/adrf5024.pdf",
    "ADMV1013S": "https://www.analog.com/media/en/technical-documentation/data-sheets/admv1013s-csl.pdf",
    "ADMV1014": "https://www.analog.com/media/en/technical-documentation/data-sheets/admv1014.pdf",
    "HMC798A": "https://www.analog.com/media/en/technical-documentation/data-sheets/hmc798a.pdf",
    "HMC8191": "https://www.analog.com/media/en/technical-documentation/data-sheets/hmc8191.pdf",
    "HMC8192": "https://www.analog.com/media/en/technical-documentation/data-sheets/hmc8192.pdf",
    "HMC519-DIE": "https://www.analog.com/media/en/technical-documentation/data-sheets/hmc519chips.pdf",
    "HMC263-DIE": "https://www.analog.com/media/en/technical-documentation/data-sheets/hmc263chips.pdf",
    "HMC1049LP5E": "https://www.analog.com/media/en/technical-documentation/data-sheets/hmc1049lp5e.pdf",
    "ADF4371": "https://www.analog.com/media/en/technical-documentation/data-sheets/adf4371.pdf",
    "AD9207": "https://www.analog.com/media/en/technical-documentation/data-sheets/ad9207.pdf",
    "AD9176": "https://www.analog.com/media/en/technical-documentation/data-sheets/ad9176.pdf",
}

DISCOVERY_PAGES = (
    "https://www.qorvo.com/products",
    "https://www.qorvo.com/products/amplifiers",
    "https://www.qorvo.com/products/switches/rf-switches",
)

KA_CENTERS_GHZ    = (19.5, 30.0)
ANOKIWAVE_CATALOG = "https://www.anokiwave.com/products/aero_index_all.html"

RESEARCHED_PRODUCT_ROWS = (
    {
        "category": "BFIC",
        "slot": "researched_official",
        "manufacturer": "Analog Devices",
        "part_no": "ADAR3000S",
        "application": "Payload",
        "function": "Tx",
        "freq_min_ghz": 17.0,
        "freq_max_ghz": 22.0,
        "number_channels": 16,
        "number_beams": 4,
        "channel_bandwidth_ghz": 5.0,
        "power_consumption_w": 0.192,
        "package": "311-ball CSPBGA",
        "product_url": "https://www.analog.com/en/products/adar3000s.html",
        "grade": "Space-grade",
        "data_origin": "official_product_research",
        "review_status": "MANUFACTURER_SOURCE_REVIEWED",
        "note": "Commercial-space BFIC for payload Tx; detailed RF specifications require an NDA",
    },
    {
        "category": "BFIC",
        "slot": "researched_official",
        "manufacturer": "Analog Devices",
        "part_no": "ADAR3001S",
        "application": "Payload",
        "function": "Rx",
        "freq_min_ghz": 27.5,
        "freq_max_ghz": 31.0,
        "number_channels": 16,
        "number_beams": 4,
        "channel_bandwidth_ghz": 3.5,
        "power_consumption_w": 0.192,
        "package": "311-ball CSPBGA",
        "product_url": "https://www.analog.com/en/products/adar3001s.html",
        "grade": "Space-grade",
        "data_origin": "official_product_research",
        "review_status": "MANUFACTURER_SOURCE_REVIEWED",
        "note": "Commercial-space BFIC for payload Rx; detailed RF specifications require an NDA",
    },
    {
        "category": "BFIC",
        "slot": "researched_official",
        "manufacturer": "Analog Devices",
        "part_no": "ADAR3000",
        "application": "Payload",
        "function": "Tx",
        "freq_min_ghz": 17.0,
        "freq_max_ghz": 22.0,
        "number_channels": 16,
        "number_beams": 4,
        "channel_bandwidth_ghz": 5.0,
        "power_consumption_w": 0.192,
        "package": "311-ball CSPBGA",
        "product_url": "https://www.analog.com/en/products/adar3000.html",
        "grade": "Commercial-grade",
        "data_origin": "official_product_research",
        "review_status": "MANUFACTURER_SOURCE_REVIEWED",
        "note": "Commercial BFIC for payload Tx; detailed RF specifications require an NDA",
    },
    {
        "category": "BFIC",
        "slot": "researched_official",
        "manufacturer": "Analog Devices",
        "part_no": "ADAR3001",
        "application": "Payload",
        "function": "Rx",
        "freq_min_ghz": 27.5,
        "freq_max_ghz": 31.0,
        "number_channels": 16,
        "number_beams": 4,
        "channel_bandwidth_ghz": 3.5,
        "power_consumption_w": 0.192,
        "package": "311-ball CSPBGA",
        "product_url": "https://www.analog.com/en/products/adar3001.html",
        "grade": "Commercial-grade",
        "data_origin": "official_product_research",
        "review_status": "MANUFACTURER_SOURCE_REVIEWED",
        "note": "Commercial BFIC for payload Rx; detailed RF specifications require an NDA",
    },
    {
        "category": "PA",
        "slot": "researched_official",
        "manufacturer": "Qorvo",
        "part_no": "QPA2211",
        "application": "Common",
        "function": "PA",
        "process": "GaN",
        "freq_min_ghz": 27.5,
        "freq_max_ghz": 31.0,
        "product_url": "https://www.qorvo.com/products/p/QPA2211",
        "data_origin": "official_product_research",
        "review_status": "REVIEW_REQUIRED",
    },
    {
        "category": "MIXER",
        "slot": "researched_official",
        "manufacturer": "Qorvo",
        "part_no": "QPC4510",
        "application": "Common",
        "function": "Upconverter",
        "process": "pHEMT",
        "freq_min_ghz": 17.7,
        "freq_max_ghz": 26.5,
        "rf_min_ghz": 17.7,
        "rf_max_ghz": 26.5,
        "if_min_ghz": 0,
        "if_max_ghz": 4.0,
        "lo_min_ghz": 6.85,
        "lo_max_ghz": 15.25,
        "conversion_gain_db": 13,
        "lo_drive_min_dbm": 3,
        "lo_drive_max_dbm": 9,
        "supply_voltage_v": 5,
        "power_consumption_w": 1.8,
        "product_url": "https://www.qorvo.com/products/p/QPC4510",
        "data_origin": "official_product_research",
        "review_status": "REVIEW_REQUIRED",
    },
    {
        "category": "MIXER",
        "slot": "researched_official",
        "manufacturer": "Qorvo",
        "part_no": "QPC4610",
        "application": "Common",
        "function": "Downconverter",
        "process": "pHEMT",
        "freq_min_ghz": 17.0,
        "freq_max_ghz": 27.0,
        "rf_min_ghz": 17.0,
        "rf_max_ghz": 27.0,
        "if_min_ghz": 0,
        "if_max_ghz": 4.0,
        "lo_min_ghz": 6.5,
        "lo_max_ghz": 15.5,
        "conversion_gain_db": 15,
        "noise_figure_db": 2.5,
        "lo_drive_min_dbm": 2,
        "lo_drive_max_dbm": 9,
        "supply_voltage_v": 3,
        "power_consumption_w": 0.684,
        "product_url": "https://www.qorvo.com/products/p/QPC4610",
        "data_origin": "official_product_research",
        "review_status": "REVIEW_REQUIRED",
    },
    {
        "category": "LNA",
        "slot": "researched_official",
        "manufacturer": "Analog Devices",
        "part_no": "HMC519-DIE",
        "application": "Common",
        "function": "LNA",
        "process": "GaAs pHEMT",
        "freq_min_ghz": 18.0,
        "freq_max_ghz": 32.0,
        "noise_figure_db": 2.8,
        "lna_gain_db": 15,
        "oip3_dbm": 23,
        "supply_voltage_v": 3,
        "power_consumption_w": 0.195,
        "product_url": "https://www.analog.com/en/products/hmc519-die.html",
        "data_origin": "official_product_research",
        "review_status": "REVIEW_REQUIRED",
    },
    {
        "category": "LNA",
        "slot": "researched_official",
        "manufacturer": "Analog Devices",
        "part_no": "HMC263-DIE",
        "application": "Common",
        "function": "LNA",
        "process": "GaAs pHEMT",
        "freq_min_ghz": 24.0,
        "freq_max_ghz": 36.0,
        "noise_figure_db": 2.0,
        "lna_gain_db": 22,
        "supply_voltage_v": 3,
        "power_consumption_w": 0.174,
        "product_url": "https://www.analog.com/en/products/hmc263-die.html",
        "data_origin": "official_product_research",
        "review_status": "REVIEW_REQUIRED",
    },
    {
        "category": "LNA",
        "slot": "researched_official",
        "manufacturer": "Analog Devices",
        "part_no": "HMC1049LP5E",
        "application": "Common",
        "function": "LNA",
        "process": "GaAs pHEMT",
        "freq_min_ghz": 0.3,
        "freq_max_ghz": 20.0,
        "output_p1db_dbm": 14.5,
        "noise_figure_db": 1.8,
        "oip3_dbm": 29,
        "lna_gain_db": 15,
        "supply_voltage_v": 7,
        "power_consumption_w": 0.49,
        "product_url": "https://www.analog.com/en/products/hmc1049lp5e.html",
        "data_origin": "official_product_research",
        "review_status": "REVIEW_REQUIRED",
    },
    {
        "category": "MIXER",
        "slot": "researched_official",
        "manufacturer": "Analog Devices",
        "part_no": "HMC8192",
        "application": "Common",
        "function": "Upconverter / Downconverter",
        "process": "GaAs",
        "freq_min_ghz": 20.0,
        "freq_max_ghz": 42.0,
        "rf_min_ghz": 20.0,
        "rf_max_ghz": 42.0,
        "if_min_ghz": 0,
        "if_max_ghz": 5.0,
        "lo_min_ghz": 20.0,
        "lo_max_ghz": 42.0,
        "conversion_gain_db": -9,
        "noise_figure_db": 12,
        "product_url": "https://www.analog.com/en/products/hmc8192.html",
        "data_origin": "official_product_research",
        "review_status": "REVIEW_REQUIRED",
    },
    {
        "category": "PLL",
        "slot": "researched_official",
        "manufacturer": "Analog Devices",
        "part_no": "ADF4371",
        "application": "Common",
        "function": "PLL/Synthesizer",
        "freq_min_ghz": 0.0625,
        "freq_max_ghz": 32.0,
        "output_freq_min_ghz": 0.0625,
        "output_freq_max_ghz": 32.0,
        "supply_voltage_v": 3.3,
        "product_url": "https://www.analog.com/en/products/adf4371.html",
        "data_origin": "official_product_research",
        "review_status": "REVIEW_REQUIRED",
    },
    {
        "category": "PLL",
        "slot": "researched_official",
        "manufacturer": "Texas Instruments",
        "part_no": "LMX2595",
        "application": "Common",
        "function": "PLL/Synthesizer",
        "freq_min_ghz": 0.01,
        "freq_max_ghz": 20.0,
        "output_freq_min_ghz": 0.01,
        "output_freq_max_ghz": 20.0,
        "output_power_dbm": 7,
        "phase_noise_100khz": -110,
        "supply_voltage_v": 3.3,
        "product_url": "https://www.ti.com/product/LMX2595",
        "datasheet_url": "https://www.ti.com/lit/ds/symlink/lmx2595.pdf",
        "data_origin": "official_product_research",
        "review_status": "REVIEW_REQUIRED",
    },
)


def launch_chromium(playwright):
    """Launch Chrome locally or the bundled Chromium when no channel is configured."""
    browser_channel                        = os.environ.get("PLAYWRIGHT_BROWSER_CHANNEL", "chrome").strip()
    options                                = {"headless": True}
    if browser_channel: options["channel"] = browser_channel
    return playwright.chromium.launch(**options)


def read_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")


def discovered_row(label: str, product_url: str) -> dict | None:
    text  = " ".join(label.split())
    match = re.search(r"(?P<low>\d+(?:\.\d+)?)\s*(?:-|–|—|to)\s*(?P<high>\d+(?:\.\d+)?)\s*GHz", text, re.I)
    if not match: return None
    low, high = float(match.group("low")), float(match.group("high"))
    if not any(low <= center <= high for center in KA_CENTERS_GHZ): return None

    lower = text.lower()
    if "sspa" in lower or "transistor" in lower: return None
    if "low noise" in lower:
        category, function = "LNA", "LNA"
    elif "switch" in lower:
        category, function = "SWITCH", "Switch"
    elif any(word in lower for word in ("mixer", "downconverter", "upconverter")):
        category = "MIXER"
        function = "Downconverter" if "downconverter" in lower else "Upconverter" if "upconverter" in lower else "Mixer"
    elif "power amplifier" in lower or "watt" in lower:
        category, function = "PA", "PA"
    else:
        return None

    part_no = product_url.rstrip("/").rsplit("/", 1)[-1]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", part_no): return None
    row = {
        "category": category,
        "slot": "auto_discovered",
        "manufacturer": "Qorvo",
        "part_no": part_no,
        "application": "Common",
        "function": function,
        "freq_min_ghz": low,
        "freq_max_ghz": high,
        "product_url": product_url,
        "data_origin": "official_catalog_discovery",
        "review_status": "REVIEW_REQUIRED",
        "note": f"Automatically discovered in the official Qorvo catalog: {text}",
    }
    if category == "MIXER": row.update({"rf_min_ghz": low, "rf_max_ghz": high})
    return row


def discover_qorvo_products() -> list[dict]:
    from playwright.sync_api import sync_playwright

    discovered = {}
    with sync_playwright() as playwright:
        browser = launch_chromium(playwright)
        page    = browser.new_page()
        for catalog_url in DISCOVERY_PAGES:
            try:
                page.goto(catalog_url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(3000)
                links = page.locator('a[href*="/products/p/"]'
                                     ).evaluate_all("elements => elements.map(link => [link.innerText, link.href])")
                for label, product_url in links:
                    row                                        = discovered_row(label, product_url)
                    if row: discovered[row["part_no"].lower()] = row
            except Exception as exc:
                print(f"Discovery warning: {catalog_url}: {type(exc).__name__}: {exc}")
        browser.close()
    return list(discovered.values())


def append_discovered_rows(path: Path, discovered: list[dict]) -> list[dict]:
    rows     = read_rows(path)
    existing = {row.get("part_no", "").lower() for row in rows}
    added    = [row for row in discovered if row.get("part_no", "").lower() not in existing]
    if not added: return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        fields = next(csv.reader(handle))
    with tempfile.NamedTemporaryFile("w", encoding="utf-8-sig", newline="", dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        writer    = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows + added)
    os.replace(temporary, path)
    return added


def anokiwave_rows_from_html(html: bytes, catalog_url: str = ANOKIWAVE_CATALOG) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    pattern = re.compile(
        r"(?P<part>(?:AWMF|AWS)-\d+)\s+(?P<low>\d+(?:\.\d+)?)\s*(?:-|–|—|to)\s*"
        r"(?P<high>\d+(?:\.\d+)?)\s*GHz.*?\b(?P<direction>Tx|Rx)\b",
        re.I,
    )
    for card in soup.select(".productcard"):
        description = card.select_one("p.description")
        if not description: continue
        text  = " ".join(description.get_text(" ", strip=True).split())
        match = pattern.search(text)
        if not match: continue
        low, high = float(match.group("low")), float(match.group("high"))
        if not any(low <= center <= high for center in KA_CENTERS_GHZ): continue
        link = card.find_parent("a", href=True) or card.select_one("a[href]")
        if not link: continue
        part_no   = match.group("part").upper()
        direction = match.group("direction").title()
        channel   = re.search(r"(?P<count>\d+)x\d+", text, re.I)
        rows.append(
            {
                "category": "BFIC",
                "slot": "auto_discovered",
                "manufacturer": "Anokiwave",
                "part_no": part_no,
                "application": "Common",
                "function": direction,
                "freq_min_ghz": low,
                "freq_max_ghz": high,
                "number_channels": int(channel.group("count")) if channel else "",
                "product_url": urljoin(catalog_url, link.get("href", "")),
                "data_origin": "official_catalog_discovery",
                "review_status": "REVIEW_REQUIRED",
                "note": f"Automatically discovered in the official Anokiwave SATCOM catalog: {text}",
            }
        )
    return rows


def discover_anokiwave_products(session: requests.Session) -> list[dict]:
    response = get(session, "Anokiwave", ANOKIWAVE_CATALOG)
    return anokiwave_rows_from_html(response.content, response.url)


def allowed_url(manufacturer: str, url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == domain or host.endswith("." + domain) for domain in MANUFACTURER_DOMAINS.get(manufacturer, ()))


def get(session: requests.Session, manufacturer: str, url: str) -> requests.Response:
    if not allowed_url(manufacturer, url): raise ValueError(f"Manufacturer URL is not allowed: {url}")
    response = session.get(url, timeout=30)
    if response.status_code == 429: raise RuntimeError("Manufacturer site blocked the automated request (HTTP 429)")
    response.raise_for_status()
    if not allowed_url(manufacturer, response.url):
        raise ValueError(f"Request redirected outside the manufacturer domain: {response.url}")
    return response


def find_datasheet_url(manufacturer: str, page_url: str, html: bytes) -> str:
    soup       = BeautifulSoup(html, "html.parser")
    candidates = []
    for anchor in soup.select("a[href]"):
        url   = urljoin(page_url, anchor.get("href", ""))
        label = " ".join(anchor.get_text(" ", strip=True).lower().split())
        path  = urlparse(url).path.lower()
        if not allowed_url(manufacturer, url): continue
        if "datasheet" not in label and "data sheet" not in label and "/data-sheets/" not in path and "/lit/ds/" not in path:
            continue
        score = 3 * int(path.endswith(".pdf")) + 2 * int("datasheet" in label or "data sheet" in label) + int(
            "/data-sheets/" in path or "/lit/ds/" in path
        )
        if score: candidates.append((score, url))
    return max(candidates, default=(0, ""))[1]


def download_qorvo_pdf(product_url: str, pdf_path: Path) -> str:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright

    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = launch_chromium(playwright)
        page    = browser.new_page(accept_downloads=True)
        page.goto(product_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)
        link         = page.locator('a[href*="/products/r/"]').filter(has_text="Product Data Sheet").first
        document_url = urljoin(page.url, link.get_attribute("href") or "")
        if not document_url: raise RuntimeError("Qorvo datasheet link was not found")

        try:
            with page.expect_download(timeout=15000) as event:
                link.click()
            download = event.value
        except PlaywrightTimeoutError:
            body = page.locator("body").inner_text()
            if "Non-Disclosure Agreement" in body or "Resource Request" in body:
                raise PermissionError("Qorvo datasheet requires an NDA and is not publicly downloadable")
            proceed = page.get_by_text("PROCEED", exact=True).first
            if not proceed.is_visible(): raise RuntimeError("Public Qorvo datasheet download link is unavailable")
            try:
                with page.expect_download(timeout=30000) as event:
                    proceed.click()
                download = event.value
            except PlaywrightTimeoutError as exc:
                raise PermissionError("Qorvo preview datasheet is not currently publicly downloadable") from exc

        download.save_as(pdf_path)
        browser.close()
    if not pdf_path.read_bytes().startswith(b"%PDF"): raise RuntimeError("Qorvo response is not a PDF")
    return document_url


def resolve_datasheet_url(row: dict) -> str:
    return row.get("datasheet_url", "").strip() or DIRECT_DATASHEETS.get(row.get("part_no", "").upper(), "")


def apply_extracted_fields(component, fields) -> None:
    for field in fields:
        if field.field == "freq_min_ghz" and component.freq_min_ghz is None: component.freq_min_ghz   = field.value
        elif field.field == "freq_max_ghz" and component.freq_max_ghz is None: component.freq_max_ghz = field.value
        elif field.field not in {"freq_min_ghz", "freq_max_ghz"} and component.specs.get(field.field) is None:
            setattr(component.specs, field.field, field.value)


def process_row(session: requests.Session, row: dict, offline: bool = False):
    component             = component_from_csv_row(row, "manufacturer_product_seeds.csv")
    manufacturer          = component.manufacturer
    product_url           = row.get("product_url", "").strip()
    datasheet_url         = resolve_datasheet_url(row)
    pdf_path              = PDF_DIR / f"{safe_name(component.part_no)}.pdf"
    component.product_url = product_url or None
    product               = None

    try:
        if pdf_path.exists():
            datasheet_url = datasheet_url or component.datasheet_url or ""
        elif offline:
            raise RuntimeError("Cached datasheet PDF is unavailable")
        elif manufacturer == "Qorvo":
            with QORVO_DOWNLOAD_LOCK:
                datasheet_url = download_qorvo_pdf(product_url, pdf_path)
        elif product_url and not datasheet_url:
            product       = get(session, manufacturer, product_url)
            datasheet_url = find_datasheet_url(manufacturer, product.url, product.content)
        if not pdf_path.exists():
            if not datasheet_url and product is not None:
                text                          = BeautifulSoup(product.content, "html.parser").get_text(" ", strip=True)
                fields                        = extract_fields_from_pages([text], component.category)
                evidence                      = [asdict(field) for field in fields]
                component.source_file         = product.url
                component.source_date         = datetime.now(timezone.utc).isoformat()
                component.extraction_method   = "PRODUCT_PAGE"
                component.extraction_evidence = json.dumps(evidence, ensure_ascii=False)
                component.note                = f"Extracted {len(fields)} fields from the official product page; datasheet is private or unavailable"
                apply_extracted_fields(component, fields)
                return component
            if not datasheet_url: raise RuntimeError("Datasheet PDF was not found on the product page")
            pdf = get(session, manufacturer, datasheet_url)
            if "pdf" not in pdf.headers.get("Content-Type", "").lower() and not pdf.content.startswith(b"%PDF"):
                raise RuntimeError("Datasheet response is not a PDF")
            PDF_DIR.mkdir(parents=True, exist_ok=True)
            pdf_path.write_bytes(pdf.content)
            datasheet_url = pdf.url

        content                       = pdf_path.read_bytes()
        pages, method                 = extract_pdf_pages(content)
        fields                        = extract_fields_from_pages(pages, component.category)
        evidence                      = [asdict(field) for field in fields]
        component.datasheet_url       = datasheet_url or component.datasheet_url
        component.datasheet_page      = ",".join(sorted({str(field.page) for field in fields})) or None
        component.source_file         = str(pdf_path.relative_to(ROOT))
        component.source_date         = datetime.now(timezone.utc).isoformat()
        component.extraction_method   = method
        component.extraction_evidence = json.dumps(evidence, ensure_ascii=False)
        component.note                = f"Extracted {len(fields)} fields from the datasheet; review required"
        apply_extracted_fields(component, fields)
    except Exception as exc:
        component.note = f"Extraction failed: {type(exc).__name__}: {exc}"
    return component


def make_session() -> requests.Session:
    retry   = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 KaRFComponentPipeline/1.0"})
    session.mount("https://", adapter)
    return session


def process_rows(rows: list[dict], offline: bool, workers: int) -> list:
    if not rows: return []
    workers    = max(1, min(workers, len(rows)))
    components = [None] * len(rows)

    def task(row: dict):
        session = make_session()
        try:
            return process_row(session, row, offline)
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="rf-pipeline") as executor:
        futures = {executor.submit(task, row): index for index, row in enumerate(rows)}
        for future in as_completed(futures):
            index             = futures[future]
            component         = future.result()
            components[index] = component
            print(
                f"[{index+1}/{len(rows)}] {component.manufacturer} {component.part_no}: {component.extraction_method or component.note}"
            )

    return components


def save_components(repository: ComponentRepository, components: list, replace: bool) -> None:
    previous = {(item.category, item.manufacturer, item.part_no): item for item in repository.list()}
    saved    = []
    for component in components:
        key   = component.category, component.manufacturer, component.part_no
        prior = previous.get(key)
        saved.append(prior if not component.extraction_method and prior and prior.extraction_method else component)
    if replace:
        repository.replace_components(saved)
        return
    for component in saved:
        repository.upsert(component)


def import_reference_components(repository: ComponentRepository) -> tuple[int, list[str]]:
    component_book = next((ROOT / "references").glob("3-*.xlsx"), None)
    if not component_book: return 0, ["Reference component workbook was not found"]
    return import_components(component_book, repository)


def run(config: PipelineConfig) -> ComponentRepository:
    if config.discover and not config.offline and not config.limit and not config.part_no:
        session    = make_session()
        discovered = list(RESEARCHED_PRODUCT_ROWS) + discover_qorvo_products()
        try:
            discovered += discover_anokiwave_products(session)
        except Exception as exc:
            print(f"Discovery warning: {ANOKIWAVE_CATALOG}: {type(exc).__name__}: {exc}")
        added = append_discovered_rows(SEED_CSV, discovered)
        print(
            f"Official catalog discovery: {len(discovered)} candidates, {len(added)} new" +
            (f" ({', '.join(row['part_no'] for row in added)})" if added else "")
        )
    rows     = read_rows(SEED_CSV)
    existing = {row.get("part_no", "").lower() for row in rows}
    rows += [dict(row) for row in RESEARCHED_PRODUCT_ROWS if row["part_no"].lower() not in existing]
    if config.part_no:
        rows = [row for row in rows if row.get("part_no", "").lower() == config.part_no.lower()]
    if config.limit: rows = rows[:config.limit]
    if not rows: raise SystemExit(f"Component was not found in the seed CSV: {config.part_no}")
    components = process_rows(rows, config.offline, config.workers)

    repository   = ComponentRepository()
    full_refresh = not config.limit and not config.part_no
    save_components(repository, components, full_refresh)
    reference_count, warnings = import_reference_components(repository)
    for warning in warnings:
        print(f"Reference component warning: {warning}")
    link_book = next((ROOT / "references").glob("4-*.xlsx"), None)
    if link_book: import_mcs(link_book, repository)
    failed = [component.part_no for component in components if not component.extraction_method]
    print(
        f"Complete: collected {len(components)-len(failed)}/{len(components)} components and imported {reference_count} reference BFICs -> {repository.component_path}"
    )
    if failed: print(f"Failed in this run; previous successful values were preserved: {', '.join(failed)}")
    return repository


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--crawl-only", action="store_true", help="Run the pipeline without starting the web server.")
    arguments = parser.parse_args()
    config    = load_config()
    run(config.pipeline)
    if arguments.crawl_only or not config.server.start_after_pipeline: return 0
    from backend.app import create_app
    create_app().run(host=config.server.host, port=config.server.port, debug=config.server.debug)
    return 0


if __name__ == "__main__": raise SystemExit(main())
