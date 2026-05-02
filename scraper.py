from __future__ import annotations

import re
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup

MONEY_RE = re.compile(
    r"(?i)(?:\$|USD\s*)\s?([0-9]{1,3}(?:,[0-9]{3})*(?:\.\d+)?|[0-9]+(?:\.\d+)?)\s*([kKmM]?)"
)

CASH_FLOW_TERMS = [
    "cash flow",
    "sde",
    "seller discretionary earnings",
    "seller's discretionary earnings",
    "discretionary earnings",
    "owner benefit",
    "owner cash flow",
    "ebitda",
    "adjusted ebitda",
]

ASKING_TERMS = [
    "asking price",
    "asking",
    "price",
    "listing price",
    "purchase price",
]


@dataclass
class Deal:
    refresh_date: str
    source: str
    title: str
    url: str
    asking_price: float | None
    cash_flow: float | None
    multiple: float | None
    annual_debt_service: float | None
    dscr: float | None
    max_supportable_price: float | None
    pricing_gap: float | None
    status: str
    notes: str


def normalize_money(raw: str | None):
    if not raw:
        return None

    m = MONEY_RE.search(raw)

    if not m:
        return None

    value = float(m.group(1).replace(",", ""))
    suffix = m.group(2).lower()

    if suffix == "k":
        value *= 1_000
    elif suffix == "m":
        value *= 1_000_000

    return value


def debt_constant(rate: float, years: int):
    monthly_rate = rate / 12
    n = years * 12

    return (
        monthly_rate * (1 + monthly_rate) ** n
        / ((1 + monthly_rate) ** n - 1)
    ) * 12


def clean_text(text: str):
    return re.sub(r"\s+", " ", text or "").strip()


def fetch_url(url: str):
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; SBADealFinderCloud/1.0; personal-use)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    try:
        response = requests.get(url, headers=headers, timeout=25)

        if response.status_code >= 400:
            return None, f"HTTP {response.status_code}"

        return response.text, None

    except Exception as exc:
        return None, str(exc)


def likely_listing_link(href: str, text: str):
    combined = f"{href} {text}".lower()

    positive = [
        "business-for-sale",
        "businesses-for-sale",
        "listing",
        "listings",
        "opportunity",
        "active-business-listings",
        "buy-a-business",
    ]

    negative = [
        "sold",
        "sell",
        "selling",
        "how-to",
        "blog",
        "article",
        "industry",
        "industries",
        "location",
        "locations",
        "about",
        "contact",
        "valuation",
        "privacy",
        "terms",
        "franchise",
        "login",
        "register",
        "facebook",
        "linkedin",
        "instagram",
        "mailto:",
        "tel:",
        "award",
        "brokers",
    ]

    if any(n in combined for n in negative):
        return False

    return any(p in combined for p in positive)
    combined = f"{href} {text}".lower()

    positive = [
        "listing",
        "listings",
        "business",
        "businesses",
        "for-sale",
        "buy-a-business",
        "opportunity",
        "business-for-sale",
    ]

    negative = [
        "contact",
        "about",
        "sell-a-business",
        "valuation",
        "privacy",
        "terms",
        "franchise",
        "blog",
        "login",
        "register",
        "facebook",
        "linkedin",
        "instagram",
        "mailto:",
        "tel:",
    ]

    return any(p in combined for p in positive) and not any(
        n in combined for n in negative
    )


def find_candidate_links(html: str, base_url: str, max_links: int):
    soup = BeautifulSoup(html, "lxml")
    links = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a.get("href")
        text = clean_text(a.get_text(" "))
        full = urljoin(base_url, href).split("#")[0]
        parsed = urlparse(full)

        if parsed.scheme not in ("http", "https"):
            continue

        if full in seen:
            continue

        if likely_listing_link(href, text):
            seen.add(full)
            links.append(full)

    if base_url not in seen:
        links.insert(0, base_url)

    return links[:max_links]


def extract_title(soup: BeautifulSoup, url: str):
    for selector in ["h1", "h2"]:
        tag = soup.find(selector)

        if tag and clean_text(tag.get_text(" ")):
            return clean_text(tag.get_text(" "))[:180]

    if soup.title:
        return clean_text(soup.title.get_text(" "))[:180]

    return url


def extract_money_near_terms(text: str, terms: list[str]):
    lower = text.lower()
    candidates = []

    for term in terms:
        for match in re.finditer(re.escape(term), lower):
            window = text[
                max(0, match.start() - 120) : min(len(text), match.end() + 240)
            ]

            for number, suffix in MONEY_RE.findall(window):
                candidate = normalize_money(f"${number}{suffix}")

                if candidate and candidate >= 50_000:
                    candidates.append(candidate)

    if not candidates:
        return None

    candidates = sorted(candidates)

    return candidates[len(candidates) // 2]


def score_deal(source, title, url, asking, cash_flow, assumptions, notes=""):
    dc = debt_constant(
        assumptions["sba_interest_rate"],
        assumptions["loan_years"],
    )

    target_dscr = assumptions["target_dscr"]

    multiple = None
    annual_ds = None
    dscr = None
    max_supportable = None
    pricing_gap = None

    status = "REVIEW"
    note_list = [notes] if notes else []

    if cash_flow:
        max_supportable = cash_flow / target_dscr / dc

    if asking and cash_flow:
        multiple = asking / cash_flow
        annual_ds = asking * dc
        dscr = cash_flow / annual_ds if annual_ds else None
        pricing_gap = asking - max_supportable if max_supportable else None

        if (
            assumptions["min_cash_flow"] <= cash_flow <= assumptions["max_cash_flow"]
            and dscr >= target_dscr
            and multiple <= assumptions["max_multiple_green"]
        ):
            status = "GREEN"

        elif (
            assumptions["min_cash_flow"] <= cash_flow <= assumptions["max_cash_flow"]
            and dscr >= assumptions["yellow_min_dscr"]
        ):
            status = "YELLOW"

        else:
            status = "RED"

    else:
        premium_sources = [
            "quiet light",
            "website closers",
            "transworld",
            "inbar",
        ]

        source_lower = source.lower()

        if any(p in source_lower for p in premium_sources):
            status = "REVIEW - HIGH POTENTIAL"
        else:
            status = "REVIEW - DATA MISSING"

        if not asking:
            note_list.append("Asking price not visible/extracted")

        if not cash_flow:
            note_list.append("Cash flow/SDE/EBITDA not visible/extracted")

    return Deal(
        refresh_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        source=source,
        title=title,
        url=url,
        asking_price=asking,
        cash_flow=cash_flow,
        multiple=multiple,
        annual_debt_service=annual_ds,
        dscr=dscr,
        max_supportable_price=max_supportable,
        pricing_gap=pricing_gap,
        status=status,
        notes="; ".join(note_list),
    )


def scrape_all(config: dict, progress_callback=None):
    assumptions = config["assumptions"]
    deals = []
    seen_urls = set()

    enabled_sources = [
        s for s in config["sources"] if s.get("enabled", True)
    ]

    for idx, source in enumerate(enabled_sources, 1):
        source_name = source["name"]
        source_url = source["url"]
        max_links = int(source.get("max_links", 25))

        if progress_callback:
            progress_callback(
                f"Searching {source_name} ({idx}/{len(enabled_sources)})"
            )

        html, err = fetch_url(source_url)

        if err or not html:
            deals.append(
                score_deal(
                    source_name,
                    f"Source could not be fetched: {source_name}",
                    source_url,
                    None,
                    None,
                    assumptions,
                    notes=err or "Unknown fetch error",
                )
            )
            continue

        candidate_links = find_candidate_links(html, source_url, max_links)

        for link in candidate_links:
            if link in seen_urls:
                continue

            seen_urls.add(link)

            page_html, page_err = fetch_url(link)

            if not page_html:
                continue

            soup = BeautifulSoup(page_html, "lxml")
            title = extract_title(soup, link)
            text = clean_text(soup.get_text(" "))

            asking = extract_money_near_terms(text, ASKING_TERMS)
            cash_flow = extract_money_near_terms(text, CASH_FLOW_TERMS)

            deal = score_deal(
                source_name,
                title,
                link,
                asking,
                cash_flow,
                assumptions,
            )

            keep_review_terms = config.get("review_sources_keep_all", [])

            keep_review_source = any(
                term.lower() in source_name.lower()
                for term in keep_review_terms
            )

            if (
                deal.status in [
                    "GREEN",
                    "YELLOW",
                    "REVIEW - HIGH POTENTIAL",
                    "REVIEW - DATA MISSING",
                ]
                or (
                    deal.cash_flow
                    and assumptions["min_cash_flow"]
                    <= deal.cash_flow
                    <= assumptions["max_cash_flow"]
                )
                or (deal.asking_price and deal.cash_flow)
                or keep_review_source
            ):
                deals.append(deal)

            time.sleep(0.25)

    df = pd.DataFrame([asdict(d) for d in deals])

    if not df.empty:
        status_order = {
            "GREEN": 0,
            "YELLOW": 1,
            "REVIEW - HIGH POTENTIAL": 2,
            "REVIEW - DATA MISSING": 3,
            "REVIEW": 4,
            "RED": 5,
        }

        df["_rank"] = df["status"].map(status_order).fillna(9)

        df = (
            df.sort_values(
                ["_rank", "dscr", "multiple"],
                ascending=[True, False, True],
            )
            .drop(columns=["_rank"])
        )

    return df
