
import json
from io import BytesIO

import pandas as pd
import streamlit as st

from scraper import scrape_all

st.set_page_config(page_title="SBA Deal Finder", layout="wide")

st.title("SBA Deal Finder")
st.caption("Cloud-ready dashboard: click Refresh Listings to pull public listings and score them by SBA DSCR.")

with open("config.json", "r", encoding="utf-8") as f:
    config = json.load(f)

assumptions = config["assumptions"]

with st.sidebar:
    st.header("Screening Assumptions")
    assumptions["target_dscr"] = st.number_input("Target DSCR", 1.0, 3.0, float(assumptions["target_dscr"]), 0.05)
    assumptions["sba_interest_rate"] = st.number_input("SBA Interest Rate", 0.01, 0.20, float(assumptions["sba_interest_rate"]), 0.005, format="%.3f")
    assumptions["loan_years"] = st.number_input("Loan Years", 5, 25, int(assumptions["loan_years"]), 1)
    assumptions["min_cash_flow"] = st.number_input("Min Cash Flow", 0, 5000000, int(assumptions["min_cash_flow"]), 25000)
    assumptions["max_cash_flow"] = st.number_input("Max Cash Flow", 0, 5000000, int(assumptions["max_cash_flow"]), 25000)
    assumptions["max_multiple_green"] = st.number_input("Max Multiple for GREEN", 1.0, 10.0, float(assumptions["max_multiple_green"]), 0.1)
    assumptions["yellow_min_dscr"] = st.number_input("Yellow Min DSCR", 1.0, 3.0, float(assumptions["yellow_min_dscr"]), 0.05)

    st.divider()
    st.header("Sources")
    for source in config["sources"]:
        source["enabled"] = st.checkbox(source["name"], value=bool(source.get("enabled", True)))

progress = st.empty()

if st.button("🔄 Refresh Listings", type="primary"):
    with st.spinner("Pulling listings and scoring deals..."):
        df = scrape_all(config, progress_callback=lambda msg: progress.info(msg))
        st.session_state["deals"] = df
        progress.success("Refresh complete.")

df = st.session_state.get("deals", pd.DataFrame())

if df.empty:
    st.info("Click Refresh Listings to pull current public listings.")
else:
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Deals Pulled", len(df))
    col2.metric("GREEN", int((df["status"] == "GREEN").sum()))
    col3.metric("YELLOW", int((df["status"] == "YELLOW").sum()))
    col4.metric("REVIEW", int((df["status"] == "REVIEW").sum()))

    statuses = st.multiselect(
    "Status",
    ["GREEN", "YELLOW", "REVIEW - HIGH POTENTIAL", "REVIEW - DATA MISSING", "REVIEW", "RED"],
    default=["GREEN", "YELLOW", "REVIEW - HIGH POTENTIAL", "REVIEW - DATA MISSING"]
)
    sources = st.multiselect("Source", sorted(df["source"].unique()), default=sorted(df["source"].unique()))
    filtered = df[df["status"].isin(statuses) & df["source"].isin(sources)].copy()

    cols = ["status", "source", "title", "asking_price", "cash_flow", "multiple", "dscr", "max_supportable_price", "pricing_gap", "url", "notes", "refresh_date"]
    cols = [c for c in cols if c in filtered.columns]

    st.dataframe(
        filtered[cols].style.format({
            "asking_price": "${:,.0f}",
            "cash_flow": "${:,.0f}",
            "multiple": "{:.2f}x",
            "dscr": "{:.2f}x",
            "max_supportable_price": "${:,.0f}",
            "pricing_gap": "${:,.0f}",
        }, na_rep=""),
        use_container_width=True,
        height=600
    )

    st.download_button("Download CSV", filtered.to_csv(index=False).encode("utf-8"), "sba_deal_results.csv", "text/csv")

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        filtered.to_excel(writer, index=False, sheet_name="Deal Results")
    st.download_button("Download Excel", buffer.getvalue(), "sba_deal_results.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

st.caption("Note: Some sites hide financials behind NDA/login pages or block automated scraping. Those listings may show as REVIEW.")
