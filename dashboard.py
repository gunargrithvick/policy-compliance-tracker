import html
import json
import os
from datetime import datetime, timedelta

import streamlit as st

from compliance_agent import analyze_regulation
from config import REGULATION_DIR, TRACKER_PRIORITY_VALUES, TRACKER_STATUS_VALUES
from exports import (
    analysis_to_csv,
    analysis_to_json,
    analysis_to_markdown,
    analysis_to_pdf,
    analysis_to_text,
    analysis_to_xlsx,
    tracker_entries_to_csv,
    tracker_entries_to_pdf,
    tracker_entries_to_xlsx,
)
from rag_eval import evaluate_retrieval_quality
from regulation_monitor import clean_title, detect_regulator, scan_regulation_directory
from regulatory_feeds import DEFAULT_FEEDS, ingest_feeds
from tracker_store import (
    consolidate_duplicate_trackers,
    fetch_audit_trail,
    fetch_notifications,
    fetch_processing_history,
    fetch_rag_evaluations,
    fetch_tracker_entries,
    init_db,
    mark_all_notifications_read,
    mark_notification_read,
    tracker_summary_counts,
    update_tracker_status,
)


SAMPLES = {
    "RBI MFA threshold": (
        "RBI requires multi-factor authentication for transactions above INR 10,000. "
        "Banks must implement the requirement immediately for all high-value digital transactions."
    ),
    "GDPR breach notice": (
        "Under GDPR Article 33, controllers must notify the supervisory authority of a "
        "personal data breach within 72 hours of becoming aware of it."
    ),
    "Security logging": (
        "The regulator requires regulated entities to maintain audit logging, monitor "
        "security events, and investigate suspicious activity."
    ),
}


st.set_page_config(
    page_title="Regulatory Impact Tracker",
    page_icon="R",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
<style>
    :root {
        --bg: #edf4f1;
        --bg-top: #f8fbfa;
        --panel: #ffffff;
        --panel-soft: #f8fbfa;
        --ink: #1f2937;
        --muted: #627184;
        --line: #d8e2e8;
        --line-strong: #c5d3dc;
        --brand: #123047;
        --brand-strong: #0d2538;
        --teal: #117a72;
        --teal-soft: #e4f3f0;
        --ok: #2f7d5f;
        --warn: #b86b19;
        --bad: #b74444;
        --blue: #456b8c;
        --amber-soft: #fff5e6;
        --soft-blue: #eef6f8;
        --soft-red: #fff0ef;
        --shadow: 0 12px 32px rgba(18, 48, 71, .08);
    }
    .stApp {
        background: linear-gradient(180deg, var(--bg-top) 0, var(--bg) 34rem);
        color: var(--ink);
    }
    .block-container { max-width: 1480px; padding-top: 1.25rem; padding-bottom: 4rem; }
    [data-testid="stHeader"] { background: transparent; }
    [data-testid="stSidebar"] { background: var(--brand-strong); border-right: 1px solid #1b4961; }
    [data-testid="stSidebar"] * { color: #e8f0f7; }
    [data-testid="stSidebar"] hr { border-color: #2b4d6e; }
    [data-testid="stSidebar"] .stCaption { color: #a9bfd2; }
    [data-testid="stSidebar"] .stButton button { background: #e8f0f7; border-color: #e8f0f7; color: #0b2343 !important; }
    [data-testid="stSidebar"] .stButton button * { color: #0b2343 !important; }
    [data-testid="stSidebar"] .stButton button:hover { background: #ffffff; border-color: #ffffff; color: #0b2343 !important; }
    h1, h2, h3 { letter-spacing: 0; }
    .topbar-shell {
        position: relative;
        overflow: hidden;
        background: var(--panel);
        color: var(--ink);
        border: 1px solid var(--line);
        border-radius: 12px;
        padding: 1.25rem 1.35rem 1.1rem 1.55rem;
        margin-bottom: .9rem;
        box-shadow: var(--shadow);
    }
    .topbar-shell::before {
        content: "";
        position: absolute;
        inset: 0 auto 0 0;
        width: .42rem;
        background: linear-gradient(180deg, var(--teal), var(--warn));
    }
    .topbar {
        display: flex; align-items: flex-start; justify-content: space-between;
        gap: 1.25rem;
    }
    .eyebrow {
        color: var(--teal);
        font-size: .7rem;
        font-weight: 800;
        letter-spacing: .12em;
        text-transform: uppercase;
        margin-bottom: .45rem;
    }
    .title h1 { margin: 0; color: var(--ink); font-size: 2rem; line-height: 1.1; }
    .title p { margin: .45rem 0 0; color: var(--muted); max-width: 760px; }
    .health-pill {
        display: inline-flex; align-items: center; gap: .45rem;
        border: 1px solid #bee1db; background: var(--teal-soft);
        border-radius: 999px; padding: .48rem .75rem; color: #0f5f58;
        font-size: .8rem; white-space: nowrap;
    }
    .health-dot { width: .45rem; height: .45rem; border-radius: 50%; background: var(--ok); }
    .hero-meta {
        display: flex; flex-wrap: wrap; gap: 1rem; margin-top: 1.15rem;
        color: var(--muted); font-size: .78rem;
    }
    .metric-row {
        display: grid; grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: .75rem; margin-bottom: 1rem;
    }
    .metric-card {
        background: var(--panel); border: 1px solid var(--line);
        border-radius: 10px; padding: .95rem 1rem .85rem;
        min-height: 96px;
        box-shadow: 0 8px 22px rgba(18, 48, 71, .055);
    }
    .metric-card .label {
        color: var(--muted); font-size: .75rem; text-transform: uppercase;
        letter-spacing: .08em; font-weight: 700;
    }
    .metric-card .value { color: var(--ink); font-size: 1.75rem; font-weight: 800; margin-top: .3rem; }
    .metric-card .detail { color: var(--muted); font-size: .75rem; margin-top: .15rem; }
    .metric-card.teal { border-top: 3px solid var(--teal); }
    .metric-card.orange { border-top: 3px solid var(--warn); }
    .metric-card.red { border-top: 3px solid var(--bad); }
    .metric-card.blue { border-top: 3px solid var(--blue); }
    .section-heading {
        display: flex; align-items: center; justify-content: space-between;
        gap: .75rem; margin: 0 0 1rem; padding-bottom: .8rem;
        border-bottom: 1px solid var(--line);
    }
    .section-heading h2, .section-heading h3 { margin: 0; color: var(--ink); white-space: normal; }
    .section-heading h2 { font-size: 1.15rem; }
    .section-heading h3 { font-size: .92rem; }
    .section-heading span { color: var(--muted); font-size: .74rem; text-align: right; line-height: 1.4; }
    .view-intro {
        display: flex; align-items: center; justify-content: space-between; gap: 1rem;
        padding: 1rem 1.15rem; margin: 1.1rem 0 .95rem;
        background: var(--panel); border: 1px solid var(--line);
        border-left: 5px solid var(--teal); border-radius: 10px;
        box-shadow: 0 8px 22px rgba(18, 48, 71, .055);
    }
    .view-intro.orange { border-left-color: var(--warn); }
    .view-intro.blue { border-left-color: var(--blue); }
    .view-intro.red { border-left-color: var(--bad); }
    .view-kicker {
        color: var(--teal); font-size: .68rem; font-weight: 800;
        letter-spacing: .1em; text-transform: uppercase; margin-bottom: .25rem;
    }
    .view-intro.orange .view-kicker { color: var(--warn); }
    .view-intro.blue .view-kicker { color: var(--blue); }
    .view-intro.red .view-kicker { color: var(--bad); }
    .view-intro h2 { color: var(--ink); font-size: 1.18rem; margin: 0; }
    .view-intro p { color: var(--muted); font-size: .8rem; margin: .3rem 0 0; }
    .view-tag {
        flex: 0 0 auto; color: var(--brand); background: var(--soft-blue);
        border: 1px solid #d3e2ed; border-radius: 999px;
        font-size: .72rem; font-weight: 700; padding: .42rem .62rem;
    }
    .tool-panel {
        background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
        padding: 1rem; box-shadow: 0 8px 22px rgba(18, 48, 71, .055);
    }
    .tool-panel + .tool-panel { margin-top: .9rem; }
    .tool-panel-title {
        display: flex; align-items: center; justify-content: space-between; gap: .75rem;
        border-bottom: 1px solid var(--line); padding-bottom: .72rem; margin-bottom: .95rem;
    }
    .tool-panel-title h3 { color: var(--ink); font-size: .92rem; margin: 0; white-space: normal; }
    .tool-panel-title span { color: var(--muted); font-size: .72rem; text-align: right; line-height: 1.35; }
    .tool-panel-title a, .section-heading a, .panel-heading a { display: none !important; }
    .empty-state {
        display: flex; align-items: center; min-height: 108px; box-sizing: border-box; padding: .95rem 1rem;
        color: var(--muted); background: var(--panel-soft); border: 1px dashed #bdd0da;
        border-radius: 8px; font-size: .82rem; line-height: 1.5; margin-top: .15rem;
    }
    .action-note {
        color: var(--muted); background: var(--soft-blue); border: 1px solid #d8e8ec; border-radius: 8px;
        display: flex; align-items: center; min-height: 3.2rem; box-sizing: border-box;
        padding: .72rem .85rem; font-size: .78rem; line-height: 1.5; margin: .15rem 0 .85rem;
    }
    .monitor-note { min-height: 4.25rem; }
    .control-spacer { height: 1.65rem; }
    .result-surface {
        background: var(--panel-soft); border: 1px solid var(--line); border-radius: 8px;
        padding: .85rem 1rem; margin-bottom: .75rem;
    }
    .result-surface h4 { color: var(--ink); font-size: .86rem; margin: 0 0 .45rem; }
    div[data-testid="stTextArea"] textarea { background: var(--panel-soft); border-color: #cbd8e4; border-radius: 8px; }
    div[data-testid="stTextArea"] textarea:focus { border-color: var(--teal); box-shadow: 0 0 0 1px var(--teal); }
    div[data-testid="stAlert"] { border-radius: 7px; }
    .overview-panel {
        min-height: 238px;
        height: 100%;
        box-sizing: border-box;
        background: var(--panel);
        border: 1px solid var(--line);
        border-radius: 10px;
        padding: 1rem 1.1rem;
        box-shadow: 0 8px 22px rgba(18, 48, 71, .055);
    }
    .overview-grid {
        display: grid;
        grid-template-columns: minmax(0, 1.45fr) minmax(0, 1fr);
        gap: 1.15rem;
        align-items: stretch;
        margin: 1.15rem 0 1.15rem;
    }
    .panel-heading {
        display: flex; align-items: center; justify-content: space-between;
        gap: .75rem; margin-bottom: .7rem;
    }
    .panel-heading h2, .panel-heading h3 { margin: 0; color: var(--ink); }
    .panel-heading h2 { font-size: 1.05rem; }
    .panel-heading h3 { font-size: .95rem; }
    .panel-heading span { color: var(--muted); font-size: .75rem; text-align: right; line-height: 1.35; }
    .panel-meta { color: var(--muted); font-size: .76rem; margin: 0 0 .65rem; }
    .overview-table { width: 100%; border-collapse: collapse; table-layout: fixed; font-size: .76rem; }
    .overview-table th {
        color: var(--muted); font-size: .68rem; font-weight: 800; letter-spacing: .04em;
        text-align: left; text-transform: uppercase; padding: .42rem .35rem;
        border-bottom: 1px solid var(--line);
    }
    .overview-table td { color: var(--ink); padding: .58rem .35rem; border-bottom: 1px solid #edf1f5; vertical-align: top; }
    .overview-table tr:last-child td { border-bottom: 0; }
    .overview-table th:nth-child(1), .overview-table td:nth-child(1) { width: 16%; }
    .overview-table th:nth-child(2), .overview-table td:nth-child(2) { width: 29%; }
    .overview-table th:nth-child(3), .overview-table td:nth-child(3) { width: 31%; }
    .overview-table th:nth-child(4), .overview-table td:nth-child(4) { width: 24%; }
    .overview-table td:nth-child(2), .overview-table td:nth-child(3), .overview-table td:nth-child(4) { overflow-wrap: anywhere; }
    .mini-priority { font-weight: 800; white-space: nowrap; }
    .mini-priority.critical, .mini-priority.high { color: var(--bad); }
    .mini-priority.medium { color: var(--warn); }
    .mini-priority.low { color: var(--ok); }
    .overview-empty { color: var(--muted); font-size: .8rem; line-height: 1.5; padding: 2.2rem .2rem 1rem; }
    .overview-activity { padding: .68rem 0; border-bottom: 1px solid var(--line); }
    .overview-activity:last-child { border-bottom: 0; }
    .overview-activity strong { color: var(--ink); font-size: .82rem; }
    .overview-activity p { color: var(--muted); font-size: .76rem; line-height: 1.45; margin: .28rem 0 0; }
    .overview-activity p.message { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
    .activity-scroll {
        max-height: 260px;
        overflow-y: auto;
        padding-right: .35rem;
    }
    .alert-card {
        border: 1px solid var(--line);
        border-left: 5px solid var(--brand);
        border-radius: 8px;
        padding: .85rem .95rem;
        background: var(--panel);
        margin-bottom: .75rem;
        box-shadow: 0 8px 22px rgba(18, 48, 71, .045);
    }
    .alert-card.unread { border-left-color: var(--bad); background: #fffafa; }
    .alert-card strong { display: block; color: var(--ink); font-size: .92rem; margin-bottom: .22rem; }
    .alert-card .meta { color: var(--muted); font-size: .74rem; margin-bottom: .35rem; }
    .alert-card .message { color: var(--muted); font-size: .82rem; line-height: 1.45; margin: 0; overflow-wrap: anywhere; }
    .section-card {
        background: var(--panel); border: 1px solid var(--line);
        border-radius: 10px; padding: 1rem; margin-bottom: 1rem;
        box-shadow: 0 8px 22px rgba(18, 48, 71, .055);
    }
    .section-card h3 { margin-top: 0; font-size: 1rem; }
    .alert-strip {
        display: flex; align-items: center; gap: .75rem;
        background: var(--soft-red); border: 1px solid #efcac8;
        border-left: 5px solid var(--bad); border-radius: 8px;
        padding: .7rem .85rem; margin-bottom: 1rem; color: #71302c;
        font-size: .85rem;
    }
    .alert-strip strong { color: #60241f; }
    .queue-summary {
        display: flex; gap: 1.25rem; flex-wrap: wrap;
        color: var(--muted); font-size: .78rem; margin-bottom: .65rem;
    }
    .queue-summary strong { color: var(--ink); }
    .activity-item {
        padding: .65rem 0; border-bottom: 1px solid var(--line);
    }
    .activity-item:last-child { border-bottom: 0; padding-bottom: 0; }
    .activity-item strong { color: var(--ink); font-size: .85rem; }
    .activity-item p { color: var(--muted); font-size: .77rem; margin: .18rem 0 0; }
    .status-tag {
        display: inline-block; border-radius: 999px; padding: .18rem .48rem;
        font-size: .7rem; font-weight: 800; letter-spacing: .02em;
        background: var(--soft-blue); color: var(--brand);
    }
    .status-tag.red { background: var(--soft-red); color: var(--bad); }
    .status-tag.teal { background: var(--soft-teal); color: var(--ok); }
    .small { color: var(--muted); font-size: .8rem; }
    .muted-panel {
        background: var(--panel-soft); border: 1px dashed #c8d6e2; border-radius: 8px;
        padding: .8rem; color: var(--muted); font-size: .82rem;
    }
    .inline-action-title {
        color: var(--ink);
        font-size: .84rem;
        font-weight: 800;
        margin: .95rem 0 .1rem;
    }
    .inline-action-caption {
        color: var(--muted);
        font-size: .74rem;
        margin: 0 0 .45rem;
    }
    .source-panel {
        background: var(--panel-soft);
        border: 1px solid var(--line);
        border-radius: 10px;
        padding: .9rem;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: .25rem; padding: .3rem; background: rgba(255, 255, 255, .72);
        border: 1px solid var(--line); border-radius: 10px;
        box-shadow: 0 8px 20px rgba(18, 48, 71, .045);
    }
    .stTabs [data-baseweb="tab"] {
        padding: .62rem .92rem; color: var(--muted); border-radius: 8px;
        font-weight: 700;
    }
    .stTabs [aria-selected="true"] { color: #ffffff; background: var(--brand); }
    .stTabs [aria-selected="true"] * { color: #ffffff !important; }
    .stTabs [data-baseweb="tab-highlight"] { background: transparent; }
    .stButton button, .stDownloadButton button {
        border-radius: 8px; min-height: 2.45rem; font-weight: 750;
        color: var(--brand); background: #ffffff; border-color: #b7c8d2;
        box-shadow: none;
    }
    .stButton button:hover, .stDownloadButton button:hover {
        color: var(--brand-strong); border-color: #8da8b7; background: var(--panel-soft);
    }
    .stButton button[kind="primary"], .stButton button[kind="primary"] * {
        background: var(--brand); border-color: var(--brand); color: #ffffff !important;
    }
    .stButton button[kind="primary"]:hover, .stButton button[kind="primary"]:hover * {
        background: var(--brand-strong); border-color: var(--brand-strong); color: #ffffff !important;
    }
    .stButton button[kind="primary"]:disabled, .stButton button[kind="primary"]:disabled * {
        background: #dfe8e7; border-color: #dfe8e7; color: #71818a !important;
        opacity: 1;
    }
    div[data-testid="stMetric"] {
        background: var(--panel); border: 1px solid var(--line);
        border-radius: 8px; padding: .75rem;
    }
    .detail-metric {
        min-height: 72px;
        background: var(--panel-soft);
        border: 1px solid var(--line);
        border-radius: 8px;
        padding: .7rem .8rem;
    }
    .detail-metric .label {
        color: var(--muted); font-size: .72rem; font-weight: 800;
        letter-spacing: .04em; text-transform: uppercase;
    }
    .detail-metric .value {
        color: var(--ink); font-size: 1.12rem; font-weight: 750;
        line-height: 1.25; margin-top: .35rem; overflow-wrap: anywhere;
    }
    [data-testid="stVerticalBlockBorderWrapper"] {
        box-sizing: border-box;
        background: var(--panel);
        border-color: var(--line) !important;
        border-radius: 10px;
        box-shadow: 0 8px 22px rgba(18, 48, 71, .055);
        overflow: visible;
    }
    [data-testid="stVerticalBlockBorderWrapper"] > div {
        padding: 1.15rem 1.25rem !important;
    }
    div[data-testid="stDataFrame"] {
        border: 1px solid var(--line);
        border-radius: 8px;
        overflow: hidden;
        margin-top: .2rem;
    }
    div[data-testid="stExpander"] { border-color: var(--line); border-radius: 8px; }
    .sidebar-brand { padding: .35rem 0 1.25rem; }
    .sidebar-brand .mark { color: #8ed2cb; font-weight: 900; letter-spacing: .12em; font-size: .72rem; }
    .sidebar-brand h2 { color: #ffffff; margin: .35rem 0 .25rem; font-size: 1.15rem; }
    .sidebar-brand p { color: #a9bfd2; font-size: .78rem; line-height: 1.45; margin: 0; }
    .side-status { border: 1px solid #2d5272; border-radius: 7px; padding: .7rem; margin: .8rem 0 1.1rem; background: rgba(255, 255, 255, .04); }
    .side-status strong { color: #ffffff; font-size: .82rem; }
    .side-status span { display: block; color: #a9bfd2; font-size: .72rem; margin-top: .18rem; }
    .source-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: .6rem; }
    .source-chip {
        display: flex; flex-direction: column; align-items: flex-start; justify-content: center; gap: .2rem;
        min-height: 58px; box-sizing: border-box;
        padding: .62rem .7rem; background: #ffffff; border: 1px solid var(--line);
        border-radius: 8px; color: var(--ink); font-size: .8rem; overflow: hidden;
    }
    .source-chip > span { font-weight: 800; line-height: 1.25; }
    .source-chip small { color: var(--muted); font-size: .68rem; line-height: 1.25; overflow-wrap: anywhere; }
    .notice {
        border-left: 4px solid var(--brand); padding: .6rem .8rem;
        background: var(--soft-blue); margin-bottom: .6rem; border-radius: 0 6px 6px 0;
    }
    .notice strong { color: var(--ink); }
    [data-testid="stSidebar"] .notice {
        background: #f8fbff;
        border: 1px solid #c9d8e5;
        border-left: 5px solid #f08a64;
        border-radius: 8px;
        color: #14233a !important;
        line-height: 1.4;
        box-shadow: 0 6px 16px rgba(0, 0, 0, .12);
    }
    [data-testid="stSidebar"] .notice,
    [data-testid="stSidebar"] .notice * {
        color: #14233a !important;
    }
    [data-testid="stSidebar"] .notice strong {
        color: #9f2f2a !important;
        font-size: .78rem;
        letter-spacing: .04em;
        text-transform: uppercase;
    }
    [data-testid="stSidebar"] .notice .small {
        color: #5d7186 !important;
        font-size: .72rem;
    }
    @media (max-width: 850px) {
        .metric-row { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        .topbar { align-items: flex-start; flex-direction: column; }
        .panel-heading { align-items: flex-start; flex-direction: column; gap: .2rem; }
        .panel-heading span { white-space: normal; }
        .section-heading { flex-direction: column; gap: .2rem; }
        .section-heading h2, .section-heading h3, .section-heading span { white-space: normal; text-align: left; }
        .overview-panel { min-height: 0; }
        .overview-grid { grid-template-columns: 1fr; gap: 1rem; }
        .empty-state { min-height: 76px; }
        .overview-table { font-size: .68rem; }
        .overview-table th { font-size: .58rem; }
        .overview-table th:nth-child(1), .overview-table td:nth-child(1) { width: 20%; white-space: nowrap; }
        .overview-table th:nth-child(2), .overview-table td:nth-child(2) { width: 26%; }
        .overview-table th:nth-child(3), .overview-table td:nth-child(3) { width: 30%; }
        .overview-table th:nth-child(4), .overview-table td:nth-child(4) { width: 24%; }
        .block-container { padding-top: 1rem; }
    }
    @media (max-width: 560px) {
        .metric-row { grid-template-columns: 1fr; }
        .title h1 { font-size: 1.55rem; }
        .alert-strip { align-items: flex-start; flex-direction: column; gap: .25rem; }
        .view-intro { align-items: flex-start; flex-direction: column; }
        .view-tag { align-self: flex-start; }
        .stTabs [data-baseweb="tab-list"] { flex-wrap: wrap; }
        .stTabs [data-baseweb="tab"] {
            flex: 1 1 calc(50% - .25rem);
            justify-content: center;
            text-align: center;
        }
        .tool-panel-title { align-items: flex-start; flex-direction: column; gap: .25rem; }
        .tool-panel-title span { text-align: left; }
        [data-testid="stVerticalBlockBorderWrapper"] > div { padding: 1rem !important; }
    }
</style>
""",
    unsafe_allow_html=True,
)


def escape(text):
    if text is None:
        return ""
    return html.escape(str(text))


def distinct(entries, field):
    values = sorted({entry.get(field) for entry in entries if entry.get(field)})
    return ["All"] + values


def tracker_display_rows(entries):
    rows = []
    for entry in entries:
        rows.append(
            {
                "Tracker ID": entry.get("tracker_id"),
                "Status": entry.get("status"),
                "Priority": entry.get("priority"),
                "Owner": entry.get("owner"),
                "Regulator": entry.get("regulator"),
                "Policy change": "Yes" if entry.get("policy_change_required") else "No",
                "Policy": entry.get("impacted_policy"),
                "Updated": display_time(entry.get("updated_at")),
            }
        )
    return rows


def short_path(value):
    if not value:
        return ""
    return os.path.basename(str(value))


def display_time(value):
    if not value:
        return ""
    return str(value).replace("T", " ").replace("Z", "")


def display_label(value):
    if not value:
        return ""
    return str(value).replace("_", " ").replace("-", " ").title()


def format_audit_details(details):
    if not details:
        return "No additional details"

    try:
        parsed = json.loads(details) if isinstance(details, str) else details
    except (TypeError, json.JSONDecodeError):
        return str(details)

    if not isinstance(parsed, dict):
        return str(parsed)

    if {"from", "to"}.issubset(parsed):
        actor = parsed.get("actor") or "Dashboard"
        return f"{actor}: {parsed.get('from')} to {parsed.get('to')}"

    if "priority" in parsed or "owner" in parsed:
        parts = []
        if parsed.get("priority"):
            parts.append(f"Priority {parsed['priority']}")
        if parsed.get("owner"):
            parts.append(f"Owner {parsed['owner']}")
        return ", ".join(parts) or "Tracker updated"

    if parsed.get("file"):
        if parsed.get("url"):
            return f"PDF ingested: {short_path(parsed['file'])}"
        return f"File {short_path(parsed['file'])}"

    if parsed.get("url"):
        return "PDF link recorded from configured source"

    if parsed.get("tracker_id"):
        return f"Tracker {parsed['tracker_id']}"

    return ", ".join(
        f"{key.replace('_', ' ').title()}: {value}"
        for key, value in parsed.items()
        if value is not None and value != ""
    ) or "No additional details"


def audit_display_rows(rows):
    return [
        {
            "Event": row.get("id"),
            "Time": display_time(row.get("created_at")),
            "Type": display_label(row.get("entity_type")),
            "Action": display_label(row.get("action")),
            "Target": row.get("entity_id"),
            "Details": format_audit_details(row.get("details")),
        }
        for row in rows
    ]


def processing_display_rows(rows):
    return [
        {
            "File": row.get("file_name") or short_path(row.get("file_path")),
            "Regulator": row.get("regulator") or row.get("regulator_source") or "Unknown",
            "Status": display_label(row.get("status")),
            "Version": row.get("version"),
            "Detected": display_time(row.get("detected_at")),
            "Processed": display_time(row.get("processed_at")) or "Pending",
        }
        for row in rows
    ]


def scan_display_rows(rows):
    return [
        {
            "File": short_path(row.get("file")),
            "Status": display_label(row.get("status")),
            "Tracker": row.get("tracker_id") or row.get("supersedes") or "",
            "Message": row.get("message") or row.get("change") or "",
        }
        for row in rows
    ]


def feed_display_rows(rows):
    return [
        {
            "Feed": row.get("feed"),
            "Status": display_label(row.get("analysis_status") or row.get("status")),
            "Tracker": row.get("tracker_id") or "",
            "File": short_path(row.get("file")),
            "Message": row.get("message") or "",
        }
        for row in rows
    ]


def percent_value(value):
    if value is None:
        return "Not measured"
    try:
        return f"{float(value):.0%}"
    except (TypeError, ValueError):
        return str(value)


def metric_scope_label(row):
    scope = row.get("metric_scope") or "legacy_multi_source"
    if scope == "selected_evidence":
        return "Selected evidence"
    if scope == "top_1":
        return "Top 1"
    if scope.startswith("top_"):
        return f"Top {scope.split('_', 1)[1]}"
    return "Legacy"


def rag_display_rows(rows):
    return [
        {
            "Run": row.get("id"),
            "Query": row.get("query"),
            "Scope": metric_scope_label(row),
            "Precision": percent_value(row.get("precision")),
            "Recall": percent_value(row.get("recall")),
            "Source overlap": percent_value(row.get("hit_rate")),
            "Relevance": percent_value(row.get("context_relevance")),
        }
        for row in rows
    ]


def notification_display_rows(rows):
    return [
        {
            "Alert": row.get("id"),
            "Status": "Unread" if not row.get("read_at") else "Read",
            "Severity": row.get("severity"),
            "Tracker": row.get("tracker_id") or "",
            "Title": row.get("title"),
            "Created": display_time(row.get("created_at")),
            "Read": display_time(row.get("read_at")),
            "Message": row.get("message"),
        }
        for row in rows
    ]


def priority_rank(value):
    return {
        "Critical": 0,
        "High": 1,
        "Medium": 2,
        "Low": 3,
        "Review": 4,
    }.get(value or "Review", 5)


def open_entries(entries):
    return [
        entry for entry in entries
        if entry.get("status") not in {"Closed", "Validated"}
    ]


def policy_change_entries(entries):
    return [entry for entry in entries if entry.get("policy_change_required")]


def latest_timestamp(entries):
    values = [entry.get("updated_at") for entry in entries if entry.get("updated_at")]
    return max(values) if values else "No tracker activity yet"


def source_count(entries):
    values = {
        entry.get("regulator_source") or entry.get("regulator")
        for entry in entries
        if entry.get("regulator_source") or entry.get("regulator")
    }
    return len(values)


def status_tag(status, tone=""):
    return f'<span class="status-tag {tone}">{escape(status)}</span>'


def find_tracker_record(entries, tracker_id):
    if not tracker_id:
        return None
    return next(
        (
            entry for entry in entries
            if entry.get("tracker_id") == tracker_id
        ),
        None,
    )


def triage_panel_html(entries):
    rows = []
    for entry in entries:
        priority = entry.get("priority") or "Review"
        rows.append(
            "<tr>"
            f'<td><span class="mini-priority {escape(priority.lower())}">{escape(priority)}</span></td>'
            f'<td>{escape(entry.get("regulation_title") or "Untitled update")}</td>'
            f'<td>{escape(entry.get("impacted_policy") or "Policy review needed")}</td>'
            f'<td>{escape(entry.get("owner") or "Unassigned")}</td>'
            "</tr>"
        )

    body = (
        '<table class="overview-table"><thead><tr>'
        "<th>Priority</th><th>Regulatory update</th><th>Policy</th><th>Owner</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
        if rows
        else '<div class="overview-empty">No open policy-impact items. New regulatory findings will appear here after a scan or analysis.</div>'
    )
    return (
        '<div class="overview-panel">'
        '<div class="panel-heading"><h2>Triage queue</h2><span>Policy impact and risk</span></div>'
        f'<div class="panel-meta">{len(entries)} item(s) prioritized for review</div>'
        f"{body}</div>"
    )


def activity_panel_html(notifications):
    items = []
    for note in notifications:
        tone = "red" if note.get("severity") in {"Critical", "High"} else "teal"
        items.append(
            '<div class="overview-activity">'
            f'<strong>{escape(note.get("title"))}</strong>'
            f'<p>{status_tag(note.get("severity") or "Medium", tone)}</p>'
            f'<p class="message">{escape(note.get("message"))}</p>'
            "</div>"
        )
    body = "".join(items) or '<div class="overview-empty">No unread notifications. The queue is clear for now.</div>'
    return (
        '<div class="overview-panel">'
        '<div class="panel-heading"><h2>Attention queue</h2><span>Unread notifications</span></div>'
        f'<div class="panel-meta">{len(notifications)} item(s) need attention</div>'
        f'<div class="activity-scroll">{body}</div></div>'
    )


def detail_metric_html(label, value):
    return (
        '<div class="detail-metric">'
        f'<div class="label">{escape(label)}</div>'
        f'<div class="value">{escape(value)}</div>'
        '</div>'
    )


def view_intro_html(kicker, title, description, tag, tone=""):
    return (
        f'<div class="view-intro {escape(tone)}">'
        "<div>"
        f'<div class="view-kicker">{escape(kicker)}</div>'
        f'<h2>{escape(title)}</h2>'
        f'<p>{escape(description)}</p>'
        "</div>"
        f'<span class="view-tag">{escape(tag)}</span>'
        "</div>"
    )


def result_block(title, text):
    st.markdown(f"#### {escape(title)}")
    st.write(text or "No data available.")


def operation_error_message(action, error):
    detail = str(error) or error.__class__.__name__
    lower_detail = detail.lower()
    if "winerror 10061" in lower_detail or "connection refused" in lower_detail:
        return (
            f"{action} could not complete because the local AI model service is not reachable. "
            "Start Ollama and try again."
        )
    return f"{action} could not complete: {detail[:400]}"


def public_tracker_record(record):
    return {
        key: value
        for key, value in (record or {}).items()
        if key not in {"analysis_json"}
    }


def analysis_metadata(regulation_text):
    return {
        "title": clean_title(regulation_text, "Manual input"),
        "regulator": detect_regulator(regulation_text, "Manual input"),
        "version": 1,
        "source_path": "Manual input",
        "regulator_source": "Manual input",
    }


def run_auto_scan_if_needed():
    if not st.session_state.get("auto_monitor_enabled"):
        return

    last_scan = st.session_state.get("last_auto_scan")
    now = datetime.utcnow()
    if last_scan and now - last_scan < timedelta(seconds=60):
        return

    with st.spinner("Checking regulation folder for new or changed PDFs..."):
        st.session_state.last_scan_results = scan_regulation_directory(REGULATION_DIR)
        st.session_state.last_auto_scan = now


init_db()
consolidate_duplicate_trackers()

if "current_result" not in st.session_state:
    st.session_state.current_result = None
if "manual_text" not in st.session_state:
    st.session_state.manual_text = ""
if "last_scan_results" not in st.session_state:
    st.session_state.last_scan_results = []
if "last_feed_results" not in st.session_state:
    st.session_state.last_feed_results = []
if "auto_monitor_enabled" not in st.session_state:
    st.session_state.auto_monitor_enabled = False

run_auto_scan_if_needed()

summary = tracker_summary_counts()
all_entries = fetch_tracker_entries()
notifications = fetch_notifications(unread_only=True, limit=100)
all_notifications = fetch_notifications(unread_only=False, limit=100)
open_work = open_entries(all_entries)
policy_changes = policy_change_entries(open_work)
critical_items = [entry for entry in open_work if entry.get("priority") == "Critical"]
monitored_sources = source_count(all_entries)
configured_feed_count = len(DEFAULT_FEEDS)

st.markdown(
    f"""
<div class="topbar-shell">
  <div class="topbar">
    <div class="title">
      <div class="eyebrow">PS168 / Legal &amp; Compliance Operations</div>
      <h1>Regulatory Impact Tracker</h1>
      <p>Turn regulatory change into owned policy and control actions.</p>
    </div>
    <div class="health-pill"><span class="health-dot"></span> Local data loaded</div>
  </div>
  <div class="hero-meta">
    <span>Agent focus: Regulatory change mapping</span>
    <span>Tracker source groups: {monitored_sources}</span>
    <span>Configured feeds: {configured_feed_count}</span>
    <span>Last tracker update: {escape(latest_timestamp(all_entries))}</span>
  </div>
</div>
<div class="metric-row">
  <div class="metric-card teal"><div class="label">Policy changes</div><div class="value">{len(policy_changes)}</div><div class="detail">Open policy reviews</div></div>
  <div class="metric-card orange"><div class="label">Open actions</div><div class="value">{len(open_work)}</div><div class="detail">Not yet validated or closed</div></div>
  <div class="metric-card red"><div class="label">Critical items</div><div class="value">{len(critical_items)}</div><div class="detail">Open highest-priority items</div></div>
  <div class="metric-card blue"><div class="label">Unread alerts</div><div class="value">{summary['unread_notifications']}</div><div class="detail">Notifications needing attention</div></div>
</div>
""",
    unsafe_allow_html=True,
)

if critical_items or notifications:
    st.markdown(
        f'<div class="alert-strip"><strong>{len(critical_items)} critical item(s), {summary["unread_notifications"]} unread alert(s)</strong>'
        "Review the listed tracker items and notifications before the next governance check.</div>",
        unsafe_allow_html=True,
    )

with st.sidebar:
    st.markdown(
        """
        <div class="sidebar-brand">
          <div class="mark">PS168</div>
          <h2>Compliance control room</h2>
          <p>Regulatory intelligence, policy impact, and remediation workflow in one place.</p>
        </div>
        <div class="side-status"><strong>Local data loaded</strong><span>Counts and tables come from the local tracker database.</span></div>
        """,
        unsafe_allow_html=True,
    )
    st.header("Monitoring")
    st.session_state.auto_monitor_enabled = st.toggle(
        "Auto-check local PDFs",
        value=st.session_state.auto_monitor_enabled,
        help="Checks for new or modified PDFs about once per minute while the dashboard is open.",
    )
    st.caption("Use the Automation tab to run folder scans, feed checks, and review stored processing history.")

    st.divider()
    st.header("Notifications")
    if notifications:
        st.caption(f"{summary['unread_notifications']} unread alert(s)")
        if st.button("Mark all read", key="sidebar_mark_all_read", width="stretch"):
            mark_all_notifications_read()
            st.rerun()
        for note in notifications:
            st.markdown(
                f"""
                <div class="notice">
                    <strong>{escape(note['severity'])}</strong><br>
                    {escape(note['title'])}<br>
                    <span class="small">{escape(note['created_at'])}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button("Mark read", key=f"read_{note['id']}", width="stretch"):
                mark_notification_read(note["id"])
                st.rerun()
    else:
        st.caption("No unread notifications.")


tab_analyze, tab_tracker, tab_alerts, tab_automation, tab_audit, tab_rag = st.tabs(
    ["Analyze", "Tracker", "Alerts", "Automation", "Audit Trail", "RAG Evaluation"]
)

with tab_tracker:
    triage_entries = sorted(
        policy_changes or open_work,
        key=lambda entry: (priority_rank(entry.get("priority")), entry.get("updated_at") or ""),
    )[:5]
    st.markdown(
        f'<div class="overview-grid">{triage_panel_html(triage_entries)}{activity_panel_html(notifications)}</div>',
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        st.markdown(
            '<div class="section-heading"><h2>Persistent tracker</h2><span>Filter, update, and export the regulatory impact register</span></div>',
            unsafe_allow_html=True,
        )
        filter_cols = st.columns([1, 1, 1, 1, 2])
        with filter_cols[0]:
            status_filter = st.selectbox("Status", ["All"] + TRACKER_STATUS_VALUES)
        with filter_cols[1]:
            owner_filter = st.selectbox("Owner", distinct(all_entries, "owner"))
        with filter_cols[2]:
            priority_filter = st.selectbox("Priority", ["All"] + TRACKER_PRIORITY_VALUES)
        with filter_cols[3]:
            regulator_filter = st.selectbox("Regulator", distinct(all_entries, "regulator"))
        with filter_cols[4]:
            search_filter = st.text_input("Search")

        entries = fetch_tracker_entries(
            {
                "status": status_filter,
                "owner": owner_filter,
                "priority": priority_filter,
                "regulator": regulator_filter,
                "search": search_filter.strip(),
            }
        )

        st.dataframe(tracker_display_rows(entries), width="stretch", hide_index=True)

        st.markdown(
            '<div class="inline-action-title">Download filtered register</div>'
            '<div class="inline-action-caption">Exports use the same filters shown above.</div>',
            unsafe_allow_html=True,
        )
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        download_cols = st.columns([1, 1, 1, 3], gap="small")
        with download_cols[0]:
            st.download_button(
                "CSV",
                tracker_entries_to_csv(entries),
                f"regulatory_tracker_{ts}.csv",
                "text/csv",
                width="stretch",
            )
        with download_cols[1]:
            st.download_button(
                "Excel",
                tracker_entries_to_xlsx(entries),
                f"regulatory_tracker_{ts}.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width="stretch",
            )
        with download_cols[2]:
            st.download_button(
                "PDF",
                tracker_entries_to_pdf(entries),
                f"regulatory_tracker_{ts}.pdf",
                "application/pdf",
                width="stretch",
            )

    with st.container(border=True):
        st.markdown('<div class="section-heading"><h3>Change status</h3><span>Move a selected tracker item forward</span></div>', unsafe_allow_html=True)
        if entries:
            tracker_ids = [entry["tracker_id"] for entry in entries]
            status_cols = st.columns([2, 2, 1], gap="medium")
            with status_cols[0]:
                selected_tracker = st.selectbox("Tracker item", tracker_ids, key="workflow_tracker")
            with status_cols[1]:
                selected_status = st.selectbox("New status", TRACKER_STATUS_VALUES, key="workflow_status")
            with status_cols[2]:
                st.markdown('<div class="control-spacer"></div>', unsafe_allow_html=True)
                if st.button("Update", type="primary", width="stretch"):
                    update_tracker_status(selected_tracker, selected_status)
                    st.success(f"{selected_tracker} moved to {selected_status}.")
                    st.rerun()
        else:
            st.info("No tracker rows match the current filters.")

    if entries:
        with st.container(border=True):
            st.markdown('<div class="section-heading"><h3>Tracker item detail</h3><span>Evidence behind the policy decision</span></div>', unsafe_allow_html=True)
            detail_tracker = st.selectbox(
                "Review tracker item",
                [entry["tracker_id"] for entry in entries],
                key="detail_tracker",
            )
            detail_entry = next(
                entry for entry in entries
                if entry["tracker_id"] == detail_tracker
            )
            detail_cols = st.columns(3)
            detail_cols[0].markdown(
                detail_metric_html(
                    "Policy change",
                    "Required" if detail_entry.get("policy_change_required") else "Not required",
                ),
                unsafe_allow_html=True,
            )
            detail_cols[1].markdown(
                detail_metric_html("Priority", detail_entry.get("priority") or "Review"),
                unsafe_allow_html=True,
            )
            detail_cols[2].markdown(
                detail_metric_html("Owner", detail_entry.get("owner") or "Compliance Team"),
                unsafe_allow_html=True,
            )

            st.markdown("##### Regulation source")
            st.write(detail_entry.get("regulation_title") or "No regulation title available.")
            if detail_entry.get("source_url"):
                st.write(detail_entry.get("source_url"))
            else:
                st.write(detail_entry.get("source_path") or "No source path available.")

            st.markdown("##### Policy impact")
            st.write(detail_entry.get("impacted_policy") or "No impacted policy recorded.")
            st.write(detail_entry.get("policy_change_reason") or "No policy change reason recorded.")
            st.write(detail_entry.get("required_policy_update") or "No required policy update recorded.")

            st.markdown("##### Control and evidence")
            st.write(detail_entry.get("impacted_control") or "No impacted control recorded.")
            st.write(detail_entry.get("control_gap") or "No control gap recorded.")
            st.write(detail_entry.get("evidence") or "No evidence recorded.")


with tab_alerts:
    st.markdown(
        view_intro_html(
            "Attention queue",
            "Alerts and notifications",
            "Review high-impact tracker notifications and clear unread alerts after they have been handled.",
            f"{summary['unread_notifications']} unread",
            "red" if summary["unread_notifications"] else "",
        ),
        unsafe_allow_html=True,
    )

    alert_metric_cols = st.columns(3)
    alert_metric_cols[0].markdown(
        detail_metric_html("Unread alerts", str(summary["unread_notifications"])),
        unsafe_allow_html=True,
    )
    alert_metric_cols[1].markdown(
        detail_metric_html("Total alerts", str(len(all_notifications))),
        unsafe_allow_html=True,
    )
    alert_metric_cols[2].markdown(
        detail_metric_html("Critical alerts", str(len([note for note in all_notifications if note.get("severity") == "Critical"]))),
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        st.markdown(
            '<div class="section-heading"><h3>Unread alerts</h3><span>Current notifications needing attention</span></div>',
            unsafe_allow_html=True,
        )
        if notifications:
            if st.button("Mark all unread alerts as read", type="primary", width="stretch"):
                mark_all_notifications_read()
                st.rerun()

            for note in notifications:
                read_button_col, detail_col = st.columns([1, 5], gap="medium")
                with read_button_col:
                    st.markdown('<div class="control-spacer"></div>', unsafe_allow_html=True)
                    if st.button("Mark read", key=f"alert_read_{note['id']}", width="stretch"):
                        mark_notification_read(note["id"])
                        st.rerun()
                with detail_col:
                    st.markdown(
                        f"""
                        <div class="alert-card unread">
                            <strong>{escape(note.get("title"))}</strong>
                            <div class="meta">{escape(note.get("severity"))} / {escape(note.get("tracker_id") or "No tracker")} / {escape(display_time(note.get("created_at")))}</div>
                            <p class="message">{escape(note.get("message"))}</p>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
        else:
            st.markdown('<div class="empty-state">No unread alerts. All current notifications have been reviewed.</div>', unsafe_allow_html=True)

    with st.container(border=True):
        st.markdown(
            '<div class="section-heading"><h3>Alert history</h3><span>Newest notifications first</span></div>',
            unsafe_allow_html=True,
        )
        if all_notifications:
            st.dataframe(notification_display_rows(all_notifications), width="stretch", hide_index=True)
        else:
            st.markdown('<div class="empty-state">No notification records are available yet.</div>', unsafe_allow_html=True)


with tab_analyze:
    st.markdown(
        view_intro_html(
            "Agent workspace",
            "Analyze a regulatory update",
            "Map obligations to internal policy and control actions, then create a persistent tracker item.",
            "Agent-assisted mapping",
        ),
        unsafe_allow_html=True,
    )
    with st.container(border=True):
        st.markdown(
            '<div class="tool-panel-title"><h3>Regulatory input</h3><span>Paste text or start from a sample</span></div>',
            unsafe_allow_html=True,
        )
        sample_col, sample_action_col = st.columns([3, 1], gap="medium")
        with sample_col:
            sample_name = st.selectbox("Sample library (optional)", ["No sample selected"] + list(SAMPLES.keys()))
        with sample_action_col:
            st.markdown('<div class="control-spacer"></div>', unsafe_allow_html=True)
            if st.button("Load sample", width="stretch", disabled=sample_name == "No sample selected"):
                st.session_state.manual_text = SAMPLES[sample_name]
                st.session_state.current_result = None
                st.rerun()

        manual_text = st.text_area(
            "Regulation text",
            height=220,
            key="manual_text",
        )
        st.markdown(
            '<div class="action-note">The agent will identify obligations, map relevant policies and controls, decide whether policy change is required, and assign a remediation owner.</div>',
            unsafe_allow_html=True,
        )
        if st.button(
            "Analyze and create tracker item",
            type="primary",
            width="stretch",
        ):
            regulation_text = manual_text.strip()
            if not regulation_text:
                st.warning("Paste a regulatory update before running analysis.")
            else:
                with st.spinner("Analyzing regulation and saving tracker item..."):
                    try:
                        result = analyze_regulation(
                            regulation_text,
                            regulation_metadata=analysis_metadata(regulation_text),
                            persist=True,
                        )
                    except Exception as exc:
                        st.session_state.current_result = None
                        st.error(operation_error_message("Analysis", exc))
                    else:
                        st.session_state.current_result = result
                        st.rerun()

    if st.session_state.current_result:
        result = st.session_state.current_result
        record = result.get("tracker_record") or {}
        tracker_id = record.get("tracker_id", "pending")
        stored_record = find_tracker_record(all_entries, tracker_id)
        display_status = (
            (stored_record or {}).get("status")
            or record.get("status")
        )
        if display_status in {"Closed", "Validated"}:
            st.info(
                f"This regulatory update already has a {display_status} "
                f"tracker: {tracker_id}. No new tracker was created."
            )
        elif record.get("matched_existing_tracker"):
            st.warning(
                f"This regulatory update already has an active tracker: "
                f"{tracker_id}. The existing tracker was updated instead of creating a duplicate."
            )
        else:
            st.success(f"Created tracker item {tracker_id}.")
        overview, detail = st.tabs(["Overview", "Details"])
        with overview:
            ts = datetime.now().strftime("%Y%m%d_%H%M")
            export_options = {
                "Text": (
                    analysis_to_text(result),
                    f"impact_report_{ts}.txt",
                    "text/plain",
                ),
                "Markdown": (
                    analysis_to_markdown(result),
                    f"impact_report_{ts}.md",
                    "text/markdown",
                ),
                "JSON": (
                    analysis_to_json(result),
                    f"impact_report_{ts}.json",
                    "application/json",
                ),
                "CSV": (
                    analysis_to_csv(result),
                    f"impact_report_{ts}.csv",
                    "text/csv",
                ),
                "Excel": (
                    analysis_to_xlsx(result),
                    f"impact_report_{ts}.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
                "PDF": (
                    analysis_to_pdf(result),
                    f"impact_report_{ts}.pdf",
                    "application/pdf",
                ),
            }
            export_col, download_col = st.columns([2, 1], gap="small")
            with export_col:
                selected_export = st.selectbox(
                    "Export report",
                    list(export_options.keys()),
                    key="analysis_export_format",
                )
            with download_col:
                st.markdown('<div class="control-spacer"></div>', unsafe_allow_html=True)
                export_data, export_name, export_mime = export_options[selected_export]
                st.download_button(
                    f"Download {selected_export}",
                    export_data,
                    export_name,
                    export_mime,
                    width="stretch",
                )

            result_block("Summary", result.get("summary"))
            result_block("Policy mapping", result.get("mapping"))
            result_block("Control matrix", result.get("control_matrix"))
            result_block("Impact tracker", result.get("impact_tracker"))
        with detail:
            st.json(public_tracker_record(record))

with tab_automation:
    st.markdown(
        view_intro_html(
            "Monitoring operations",
            "Regulation monitoring",
            "Track folder scans, feed ingestion, duplicate detection, and automated tracker creation.",
            "On-demand checks",
            "orange",
        ),
        unsafe_allow_html=True,
    )

    monitor_action_cols = st.columns(2, gap="medium")
    with monitor_action_cols[0]:
        with st.container(border=True):
            st.markdown('<div class="tool-panel-title"><h3>Folder scan</h3><span>Local PDFs</span></div>', unsafe_allow_html=True)
            st.markdown('<div class="action-note monitor-note">Detect new, changed, and exact-duplicate regulation files.</div>', unsafe_allow_html=True)
            if st.button("Run folder scan", type="primary", width="stretch"):
                with st.spinner("Scanning regulations and updating tracker..."):
                    try:
                        st.session_state.last_scan_results = scan_regulation_directory(REGULATION_DIR)
                    except Exception as exc:
                        st.error(operation_error_message("Folder scan", exc))
                    else:
                        st.rerun()
    with monitor_action_cols[1]:
        with st.container(border=True):
            st.markdown('<div class="tool-panel-title"><h3>Feed check</h3><span>Regulatory sources</span></div>', unsafe_allow_html=True)
            st.markdown('<div class="action-note monitor-note">Check the configured regulator feed URLs and analyze newly downloaded PDFs.</div>', unsafe_allow_html=True)
            if st.button("Check configured feeds", type="primary", width="stretch"):
                with st.spinner("Checking configured regulatory feeds..."):
                    try:
                        st.session_state.last_feed_results = ingest_feeds(
                            DEFAULT_FEEDS,
                            analyze_downloads=True,
                        )
                    except Exception as exc:
                        st.error(operation_error_message("Feed check", exc))
                    else:
                        st.rerun()
    with st.container(border=True):
        st.markdown('<div class="tool-panel-title"><h3>Configured feed list</h3><span>URLs stored in app configuration</span></div>', unsafe_allow_html=True)
        source_chips = "".join(
            f'<div class="source-chip"><span>{escape(feed["regulator"])}</span><small>{escape(feed["name"])}</small></div>'
            for feed in DEFAULT_FEEDS
        )
        st.markdown(f'<div class="source-list">{source_chips}</div>', unsafe_allow_html=True)

    scan_cols = st.columns(2)
    with scan_cols[0]:
        with st.container(border=True):
            st.markdown('<div class="tool-panel-title"><h3>Last folder scan</h3><span>Local PDF intake</span></div>', unsafe_allow_html=True)
            if st.session_state.last_scan_results:
                st.dataframe(scan_display_rows(st.session_state.last_scan_results), width="stretch", hide_index=True)
            else:
                st.markdown('<div class="empty-state">No folder scan results are available in this browser session. Run folder scan to create a current result set.</div>', unsafe_allow_html=True)
    with scan_cols[1]:
        with st.container(border=True):
            st.markdown('<div class="tool-panel-title"><h3>Last feed check</h3><span>Regulatory source intake</span></div>', unsafe_allow_html=True)
            if st.session_state.last_feed_results:
                st.dataframe(feed_display_rows(st.session_state.last_feed_results), width="stretch", hide_index=True)
            else:
                st.markdown('<div class="empty-state">No feed check results are available in this browser session. Check configured feeds to create a current result set.</div>', unsafe_allow_html=True)

    with st.container(border=True):
        processing_history = fetch_processing_history()
        st.markdown(
            f'<div class="tool-panel-title"><h3>Processing history</h3><span>{len(processing_history)} recorded file event(s)</span></div>',
            unsafe_allow_html=True,
        )
        if processing_history:
            st.dataframe(processing_display_rows(processing_history), width="stretch", hide_index=True)
        else:
            st.markdown('<div class="empty-state">No stored regulation file events were found.</div>', unsafe_allow_html=True)

with tab_audit:
    st.markdown(
        view_intro_html(
            "Governance record",
            "Audit trail",
            "Review every detection, tracker creation, status update, feed ingestion, and processing outcome.",
            "Traceable activity",
            "blue",
        ),
        unsafe_allow_html=True,
    )
    audit_rows = fetch_audit_trail()
    audit_metrics = st.columns(3)
    audit_metrics[0].markdown(detail_metric_html("Recorded events", len(audit_rows)), unsafe_allow_html=True)
    audit_metrics[1].markdown(
        detail_metric_html("Tracker events", sum(1 for row in audit_rows if row.get("entity_type") == "tracker")),
        unsafe_allow_html=True,
    )
    audit_metrics[2].markdown(
        detail_metric_html("Source events", sum(1 for row in audit_rows if row.get("entity_type") in {"regulation", "regulatory_feed"})),
        unsafe_allow_html=True,
    )
    with st.container(border=True):
        st.markdown('<div class="tool-panel-title"><h3>Event history</h3><span>Newest activity first</span></div>', unsafe_allow_html=True)
        if audit_rows:
            st.dataframe(audit_display_rows(audit_rows), width="stretch", hide_index=True)
        else:
            st.markdown('<div class="empty-state">No audit events have been recorded yet.</div>', unsafe_allow_html=True)

with tab_rag:
    st.markdown(
        view_intro_html(
            "Quality assurance",
            "RAG retrieval evaluation",
            "Measure whether policy and control retrieval is returning the right evidence for the compliance agent.",
            "Retrieval quality",
            "red",
        ),
        unsafe_allow_html=True,
    )
    previous = fetch_rag_evaluations()
    with st.container(border=True):
        st.markdown('<div class="tool-panel-title"><h3>Run quality check</h3><span>Policy and control retrieval</span></div>', unsafe_allow_html=True)
        action_col, note_col = st.columns([1, 2], gap="large")
        with action_col:
            if st.button("Run retrieval evaluation", type="primary", width="stretch"):
                with st.spinner("Evaluating retrieval quality..."):
                    try:
                        results = evaluate_retrieval_quality()
                    except Exception as exc:
                        st.session_state.latest_rag_results = None
                        st.error(operation_error_message("Retrieval evaluation", exc))
                    else:
                        st.session_state.latest_rag_results = results
        with note_col:
            st.markdown('<div class="action-note">The evaluation searches the full policy and control library, selects only strong evidence sources, and scores source overlap so partial or extra-source matches do not appear as perfect hits.</div>', unsafe_allow_html=True)

    latest_rag_results = st.session_state.get("latest_rag_results")
    if latest_rag_results is not None:
        with st.container(border=True):
            st.markdown('<div class="tool-panel-title"><h3>Latest evaluation result</h3><span>Current run</span></div>', unsafe_allow_html=True)
            st.dataframe(rag_display_rows(latest_rag_results), width="stretch", hide_index=True)

    with st.container(border=True):
        st.markdown(f'<div class="tool-panel-title"><h3>Recent evaluation history</h3><span>{len(previous)} recorded run(s)</span></div>', unsafe_allow_html=True)
        if previous:
            st.dataframe(rag_display_rows(previous), width="stretch", hide_index=True)
        else:
            st.markdown('<div class="empty-state">No retrieval evaluation runs recorded yet.</div>', unsafe_allow_html=True)
