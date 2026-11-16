"""
Streamlit frontend for the Automated Multi-Platform Posting System.

Connects to the FastAPI backend at http://localhost:4000/posting
and displays a rich, interactive dashboard for composing and publishing
messages to social media platforms.

Run with:
    streamlit run streamlit_app.py
"""

from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Any

import httpx
import streamlit as st

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Multi-Platform Poster",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Constants ─────────────────────────────────────────────────────────────────
API_URL: str = "http://localhost:4000/posting"
HEALTH_URL: str = "http://localhost:4000/health"
MAX_CHARS: int = 200
APP_VERSION: str = "2.0.0"

PLATFORM_INFO: dict[str, dict[str, str]] = {
    "Telegram":  {"icon": "✈️",  "color": "#229ED9", "bg": "rgba(34,158,217,0.12)"},
    "Bluesky":   {"icon": "🦋",  "color": "#0085FF", "bg": "rgba(0,133,255,0.12)"},
    "Mastodon":  {"icon": "🐘",  "color": "#6364FF", "bg": "rgba(99,100,255,0.12)"},
    "LinkedIn":  {"icon": "💼",  "color": "#0A66C2", "bg": "rgba(10,102,194,0.12)"},
    "Reddit":    {"icon": "🤖",  "color": "#FF4500", "bg": "rgba(255,69,0,0.12)"},
}

PLATFORM_ICONS: dict[str, str] = {k: v["icon"] for k, v in PLATFORM_INFO.items()}

STATUS_CONFIG: dict[str, dict[str, str]] = {
    "success":      {"icon": "✅", "color": "#22c55e", "label": "Published"},
    "failed":       {"icon": "❌", "color": "#ef4444", "label": "Failed"},
    "unconfigured": {"icon": "⚙️", "color": "#f59e0b", "label": "Not Configured"},
    "posting":      {"icon": "⏳", "color": "#818cf8", "label": "Posting…"},
}

TIPS: list[str] = [
    "💡 Include exactly ONE URL (http/https) in your message.",
    "💡 Keep messages under 200 characters for all platforms.",
    "💡 Use emojis to boost engagement on social platforms.",
    "💡 Add a call-to-action to increase click-through rates.",
    "💡 Post at peak hours (9–11 AM or 7–9 PM) for best reach.",
]

URL_REGEX = re.compile(
    r"https?://"
    r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,}|"
    r"localhost|\d{1,3}(?:\.\d{1,3}){3})"
    r"(?::\d+)?(?:/[^\s]*)?",
    re.IGNORECASE,
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    /* ── Google Font ── */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
        font-size: 16px;
    }

    /* ── Dark gradient background ── */
    .stApp {
        background: linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%);
        min-height: 100vh;
    }

    /* ── Max-width content wrapper ── */
    .block-container {
        max-width: 1280px !important;
        padding-left: 1.5rem !important;
        padding-right: 1.5rem !important;
    }

    /* ── Animated gradient hero header ── */
    .hero-header {
        text-align: center;
        padding: 2.5rem 1.5rem 2rem;
        background: linear-gradient(135deg, rgba(99,102,241,0.18), rgba(168,85,247,0.18));
        border-radius: 24px;
        border: 1px solid rgba(99,102,241,0.35);
        margin-bottom: 2rem;
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        position: relative;
        overflow: hidden;
    }
    .hero-header::before {
        content: '';
        position: absolute;
        inset: 0;
        background: linear-gradient(270deg, #818cf8, #c084fc, #fb7185, #c084fc, #818cf8);
        background-size: 400% 400%;
        animation: gradientShift 8s ease infinite;
        opacity: 0.07;
        border-radius: 24px;
    }
    @keyframes gradientShift {
        0%   { background-position: 0% 50%; }
        50%  { background-position: 100% 50%; }
        100% { background-position: 0% 50%; }
    }
    .hero-header h1 {
        font-size: clamp(1.6rem, 4vw, 2.4rem);
        font-weight: 700;
        background: linear-gradient(90deg, #818cf8, #c084fc, #fb7185);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        margin: 0 0 0.6rem;
        position: relative;
    }
    .hero-header p {
        color: #a5b4fc;
        font-size: clamp(0.9rem, 2vw, 1.05rem);
        margin: 0;
        position: relative;
    }
    .platform-logos-row {
        display: flex;
        justify-content: center;
        gap: 1.2rem;
        margin-top: 1.2rem;
        flex-wrap: wrap;
        position: relative;
    }
    .platform-logo-pill {
        display: flex;
        align-items: center;
        gap: 0.4rem;
        padding: 0.35rem 0.9rem;
        border-radius: 20px;
        font-size: 0.82rem;
        font-weight: 600;
        border: 1px solid rgba(255,255,255,0.12);
        backdrop-filter: blur(6px);
        color: #e2e8f0;
        background: rgba(255,255,255,0.07);
        transition: transform 0.2s, background 0.2s;
    }
    .platform-logo-pill:hover {
        transform: translateY(-2px);
        background: rgba(255,255,255,0.12);
    }

    /* ── Section headings ── */
    .section-heading {
        font-size: 1.1rem;
        font-weight: 600;
        color: #c4b5fd;
        margin-bottom: 0.8rem;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }

    /* ── Compose panel ── */
    .stTextArea textarea {
        background: rgba(255,255,255,0.05) !important;
        border: 1px solid rgba(99,102,241,0.4) !important;
        border-radius: 12px !important;
        color: #e2e8f0 !important;
        font-family: 'Inter', sans-serif !important;
        font-size: 1rem !important;
        min-height: 44px;
        line-height: 1.6;
        resize: vertical;
    }
    .stTextArea textarea:focus {
        border-color: #818cf8 !important;
        box-shadow: 0 0 0 3px rgba(129,140,248,0.2) !important;
    }
    .stTextInput input {
        background: rgba(255,255,255,0.05) !important;
        border: 1px solid rgba(99,102,241,0.4) !important;
        border-radius: 10px !important;
        color: #e2e8f0 !important;
        font-size: 1rem !important;
        min-height: 44px;
    }

    /* ── Character / word count row ── */
    .meta-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-size: 0.82rem;
        margin-top: -0.2rem;
        margin-bottom: 0.6rem;
    }
    .word-count  { color: #94a3b8; }
    .char-ok     { color: #86efac; }
    .char-warn   { color: #fde68a; }
    .char-over   { color: #fca5a5; font-weight: 600; }

    /* ── URL validator feedback ── */
    .url-feedback {
        display: flex;
        align-items: center;
        gap: 0.4rem;
        font-size: 0.84rem;
        margin-bottom: 0.5rem;
        padding: 0.35rem 0.75rem;
        border-radius: 8px;
    }
    .url-valid   { background: rgba(34,197,94,0.12); color: #86efac; }
    .url-invalid { background: rgba(239,68,68,0.12); color: #fca5a5; }
    .url-none    { background: rgba(100,116,139,0.1); color: #94a3b8; }

    /* ── Message preview ── */
    .msg-preview {
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(99,102,241,0.2);
        border-radius: 12px;
        padding: 0.9rem 1.1rem;
        font-size: 0.9rem;
        color: #cbd5e1;
        line-height: 1.65;
        word-break: break-word;
        min-height: 60px;
    }
    .msg-preview .url-span {
        color: #818cf8;
        text-decoration: underline;
    }

    /* ── Platform status tiles (pre-posting) ── */
    .platform-tile {
        border-radius: 14px;
        padding: 1rem 1.1rem;
        margin-bottom: 0.8rem;
        border: 1px solid rgba(255,255,255,0.08);
        display: flex;
        align-items: center;
        gap: 0.9rem;
        backdrop-filter: blur(6px);
    }
    .tile-icon   { font-size: 1.5rem; line-height: 1; }
    .tile-name   { font-size: 1rem; font-weight: 600; color: #e2e8f0; }
    .tile-status { font-size: 0.75rem; color: #94a3b8; margin-top: 0.1rem; }
    .tile-badge  {
        margin-left: auto;
        padding: 0.15rem 0.6rem;
        border-radius: 20px;
        font-size: 0.72rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }
    .badge-online       { background: rgba(34,197,94,0.18); color: #86efac; }
    .badge-offline      { background: rgba(239,68,68,0.18); color: #fca5a5; }
    .badge-unconfigured { background: rgba(245,158,11,0.18); color: #fde68a; }

    /* ── Platform result cards ── */
    .platform-card {
        background: rgba(255,255,255,0.05);
        border-radius: 14px;
        padding: 1.1rem 1.3rem;
        margin-bottom: 0.9rem;
        border-left: 4px solid;
        backdrop-filter: blur(6px);
        transition: transform 0.18s ease, box-shadow 0.18s ease;
    }
    .platform-card:hover {
        transform: translateX(4px);
        box-shadow: 0 4px 20px rgba(0,0,0,0.3);
    }
    .platform-card.success      { border-color: #22c55e; background: rgba(34,197,94,0.07); }
    .platform-card.failed       { border-color: #ef4444; background: rgba(239,68,68,0.07); }
    .platform-card.unconfigured { border-color: #f59e0b; background: rgba(245,158,11,0.07); }
    .platform-card.posting      { border-color: #818cf8; background: rgba(129,140,248,0.07); }

    .card-title {
        font-size: 1.05rem;
        font-weight: 600;
        color: #e2e8f0;
        margin-bottom: 0.4rem;
    }
    .card-status-badge {
        display: inline-block;
        padding: 0.15rem 0.65rem;
        border-radius: 20px;
        font-size: 0.74rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 0.5rem;
    }
    .badge-success      { background: rgba(34,197,94,0.2);  color: #86efac; }
    .badge-failed       { background: rgba(239,68,68,0.2);  color: #fca5a5; }
    .badge-unconfigured { background: rgba(245,158,11,0.2); color: #fde68a; }
    .badge-posting      { background: rgba(129,140,248,0.2); color: #c4b5fd; }

    .card-url a {
        color: #818cf8;
        text-decoration: none;
        word-break: break-all;
        font-size: 0.84rem;
    }
    .card-url a:hover { text-decoration: underline; }
    .card-meta  { color: #94a3b8; font-size: 0.79rem; margin-top: 0.3rem; }
    .card-error { color: #fca5a5; font-size: 0.82rem; margin-top: 0.3rem; font-style: italic; }

    /* ── Summary banners ── */
    .summary-success, .summary-partial, .summary-fail {
        border-radius: 14px;
        padding: 1.1rem 1.5rem;
        text-align: center;
        font-size: 1.05rem;
        font-weight: 600;
        margin-bottom: 1.2rem;
    }
    .summary-success {
        background: linear-gradient(135deg, rgba(34,197,94,0.15), rgba(16,185,129,0.1));
        border: 1px solid rgba(34,197,94,0.4);
        color: #86efac;
    }
    .summary-partial {
        background: linear-gradient(135deg, rgba(245,158,11,0.15), rgba(234,88,12,0.08));
        border: 1px solid rgba(245,158,11,0.4);
        color: #fde68a;
    }
    .summary-fail {
        background: linear-gradient(135deg, rgba(239,68,68,0.15), rgba(220,38,38,0.08));
        border: 1px solid rgba(239,68,68,0.4);
        color: #fca5a5;
    }

    /* ── Sidebar ── */
    section[data-testid="stSidebar"] {
        background: rgba(15,12,41,0.95) !important;
        border-right: 1px solid rgba(99,102,241,0.2);
    }
    section[data-testid="stSidebar"] .stMarkdown { color: #cbd5e1; }

    /* ── History entries (sidebar) ── */
    .history-entry {
        background: rgba(255,255,255,0.04);
        border-radius: 10px;
        padding: 0.75rem 0.9rem;
        margin-bottom: 0.5rem;
        border: 1px solid rgba(99,102,241,0.15);
        font-size: 0.84rem;
        color: #94a3b8;
        cursor: pointer;
        transition: background 0.15s;
    }
    .history-entry:hover { background: rgba(99,102,241,0.1); }
    .history-entry strong { color: #e2e8f0; }
    .history-entry .h-ts  { font-size: 0.75rem; color: #64748b; }

    /* ── Buttons ── */
    .stButton > button {
        min-height: 44px;
        font-size: 1rem;
        font-weight: 600;
        border-radius: 10px;
        border: none;
        cursor: pointer;
        transition: all 0.18s ease;
        letter-spacing: 0.03em;
    }
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #6366f1, #8b5cf6);
        color: white;
        width: 100%;
        padding: 0.75rem 1.5rem;
    }
    .stButton > button[kind="primary"]:hover {
        background: linear-gradient(135deg, #4f46e5, #7c3aed);
        transform: translateY(-2px);
        box-shadow: 0 8px 25px rgba(99,102,241,0.4);
    }
    .stButton > button[kind="secondary"] {
        background: rgba(255,255,255,0.07);
        color: #c4b5fd;
        border: 1px solid rgba(99,102,241,0.3);
        padding: 0.5rem 1rem;
    }
    .stButton > button[kind="secondary"]:hover {
        background: rgba(99,102,241,0.15);
    }

    /* ── Progress bar ── */
    .stProgress > div > div {
        border-radius: 8px;
        background: linear-gradient(90deg, #6366f1, #8b5cf6, #c084fc) !important;
    }

    /* ── Spinner ── */
    .stSpinner { color: #818cf8; }

    /* ── Divider ── */
    hr { border-color: rgba(99,102,241,0.2) !important; }

    /* ── Status dot ── */
    .status-dot {
        display: inline-block;
        width: 9px;
        height: 9px;
        border-radius: 50%;
        margin-right: 6px;
        animation: pulse 2s infinite;
    }
    .dot-green { background: #22c55e; }
    .dot-red   { background: #ef4444; animation: none; }
    @keyframes pulse {
        0%,100% { opacity:1; }
        50% { opacity: 0.4; }
    }

    /* ── Empty state ── */
    .empty-state {
        text-align: center;
        padding: 3.5rem 2rem;
        background: rgba(255,255,255,0.03);
        border-radius: 18px;
        border: 1px dashed rgba(99,102,241,0.3);
        color: #64748b;
    }
    .empty-state .empty-icon {
        font-size: 3.5rem;
        margin-bottom: 0.8rem;
        animation: float 3s ease-in-out infinite;
    }
    .empty-state .empty-title {
        font-size: 1.1rem;
        color: #94a3b8;
        font-weight: 500;
        margin-bottom: 0.4rem;
    }
    .empty-state .empty-tip {
        font-size: 0.88rem;
        color: #64748b;
        margin-top: 0.6rem;
        font-style: italic;
    }
    @keyframes float {
        0%,100% { transform: translateY(0); }
        50% { transform: translateY(-8px); }
    }

    /* ── Footer ── */
    .app-footer {
        text-align: center;
        padding: 1.5rem 1rem;
        margin-top: 3rem;
        border-top: 1px solid rgba(99,102,241,0.2);
        color: #475569;
        font-size: 0.8rem;
    }
    .app-footer a {
        color: #818cf8;
        text-decoration: none;
    }
    .app-footer a:hover { text-decoration: underline; }

    /* ── Tabs ── */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0.5rem;
        background: rgba(255,255,255,0.03);
        border-radius: 10px;
        padding: 0.3rem;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px;
        padding: 0.4rem 1rem;
        font-size: 0.88rem;
        font-weight: 500;
        color: #94a3b8;
        min-height: 36px;
    }
    .stTabs [aria-selected="true"] {
        background: rgba(99,102,241,0.25) !important;
        color: #c4b5fd !important;
    }

    /* ── Clipboard copy button ── */
    .copy-btn {
        display: inline-flex;
        align-items: center;
        gap: 0.3rem;
        padding: 0.2rem 0.6rem;
        font-size: 0.75rem;
        border-radius: 6px;
        background: rgba(129,140,248,0.15);
        color: #818cf8;
        cursor: pointer;
        border: 1px solid rgba(129,140,248,0.3);
        margin-left: 0.5rem;
        text-decoration: none;
        transition: background 0.15s;
    }
    .copy-btn:hover { background: rgba(129,140,248,0.3); }

    /* ── Mobile responsiveness ── */
    @media (max-width: 768px) {
        .block-container {
            padding-left: 0.75rem !important;
            padding-right: 0.75rem !important;
        }
        .hero-header {
            padding: 1.5rem 1rem;
        }
        .hero-header h1 {
            font-size: 1.5rem;
        }
        .platform-logos-row {
            gap: 0.6rem;
        }
        .stButton > button {
            min-height: 48px;
            font-size: 1rem;
            padding: 0.9rem 1rem;
        }
        .stTextArea textarea {
            font-size: 1rem !important;
        }
        html, body, [class*="css"] {
            font-size: 16px !important;
        }
        section[data-testid="stSidebar"] {
            padding: 0.5rem !important;
        }
        .platform-card {
            padding: 0.9rem 1rem;
        }
    }
    @media (max-width: 480px) {
        .hero-header h1 { font-size: 1.3rem; }
        .platform-logo-pill { display: none; }
        .meta-row { flex-direction: column; align-items: flex-start; gap: 0.2rem; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ── Session state ─────────────────────────────────────────────────────────────
if "history" not in st.session_state:
    st.session_state.history: list[dict] = []
if "last_response" not in st.session_state:
    st.session_state.last_response: dict | None = None
if "tip_index" not in st.session_state:
    st.session_state.tip_index: int = 0


# ── Helper functions ──────────────────────────────────────────────────────────

def check_backend_health() -> bool:
    """Return True if the FastAPI backend is reachable."""
    try:
        r = httpx.get(HEALTH_URL, timeout=3.0)
        return r.status_code == 200
    except Exception:
        return False


def get_health_data() -> dict[str, Any]:
    """
    Call GET /health and return the parsed JSON dict, or an empty dict on failure.
    Uses a 3-second timeout to avoid blocking the UI.
    """
    try:
        r = httpx.get(HEALTH_URL, timeout=3.0)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return {}


def post_message(message: str) -> tuple[dict | None, int]:
    """Call the FastAPI /posting endpoint and return (json_response, status_code)."""
    try:
        r = httpx.post(API_URL, json={"message": message}, timeout=60.0)
        return r.json(), r.status_code
    except httpx.TimeoutException:
        return None, 408
    except Exception as e:
        return {"error": str(e)}, 500


def extract_url(text: str) -> str | None:
    """Return the first URL found in *text*, or None."""
    m = URL_REGEX.search(text)
    return m.group(0) if m else None


def count_urls(text: str) -> int:
    """Return the number of URLs found in *text*."""
    return len(URL_REGEX.findall(text))


def render_message_preview(text: str) -> str:
    """Return HTML that shows the message with URLs highlighted."""
    if not text.strip():
        return '<span style="color:#475569;font-style:italic;">Preview will appear here…</span>'
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def _link(m: re.Match) -> str:
        url = m.group(0)
        return f'<span class="url-span">{url}</span>'

    return URL_REGEX.sub(_link, escaped).replace("\n", "<br>")


def render_platform_card(result: dict) -> str:
    """Return HTML for a single platform result card."""
    platform = result.get("platform", "Unknown")
    status = result.get("status", "failed")
    posted_url = result.get("posted_url")
    public_access = result.get("public_access", False)
    date = result.get("date", "")
    time_val = result.get("time", "")
    error = result.get("error")

    icon = PLATFORM_ICONS.get(platform, "🌐")
    cfg = STATUS_CONFIG.get(status, STATUS_CONFIG["failed"])

    url_html = ""
    if posted_url:
        url_html = (
            f'<div class="card-url">🔗 '
            f'<a href="{posted_url}" target="_blank">{posted_url}</a>'
            f'</div>'
        )

    meta_html = ""
    if date and time_val:
        public_label = "🌍 Public" if public_access else "🔒 Private"
        meta_html = (
            f'<div class="card-meta">📅 {date} &nbsp;⏰ {time_val} &nbsp;{public_label}</div>'
        )

    error_html = ""
    if error and status != "success":
        error_html = f'<div class="card-error">⚠️ {error}</div>'

    return f"""
    <div class="platform-card {status}">
        <div class="card-title">{icon} {platform}</div>
        <span class="card-status-badge badge-{status}">{cfg['icon']} {cfg['label']}</span>
        {url_html}
        {meta_html}
        {error_html}
    </div>
    """


def render_platform_tile(
    name: str,
    configured: bool,
    backend_online: bool,
) -> str:
    """Return HTML for a pre-posting platform status tile."""
    info = PLATFORM_INFO.get(name, {"icon": "🌐", "color": "#64748b", "bg": "rgba(100,116,139,0.1)"})
    icon = info["icon"]
    color = info["color"]
    bg = info["bg"]

    if not backend_online:
        badge_class = "badge-offline"
        badge_text = "Offline"
        status_text = "Backend unreachable"
    elif configured:
        badge_class = "badge-online"
        badge_text = "Ready"
        status_text = "Configured & ready to post"
    else:
        badge_class = "badge-unconfigured"
        badge_text = "Not Configured"
        status_text = "API credentials missing"

    return f"""
    <div class="platform-tile" style="background:{bg}; border-color:{color}33;">
        <div class="tile-icon">{icon}</div>
        <div>
            <div class="tile-name">{name}</div>
            <div class="tile-status">{status_text}</div>
        </div>
        <span class="tile-badge {badge_class}">{badge_text}</span>
    </div>
    """


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ System Status")

    is_healthy = check_backend_health()
    if is_healthy:
        st.markdown(
            '<span class="status-dot dot-green"></span> **Backend: Online**',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<span style="color:#94a3b8;font-size:0.78rem;">API: {API_URL}</span>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<span class="status-dot dot-red"></span> **Backend: Offline**',
            unsafe_allow_html=True,
        )
        st.error(
            "FastAPI backend not running.\n\n"
            "Start it with:\n```\nuvicorn app.main:app --host 0.0.0.0 --port 4000\n```"
        )

    st.markdown("---")
    st.markdown("### 📋 Platform Rules")
    st.markdown(
        """
        - ✅ Max **200 characters**
        - ✅ Exactly **1 URL** (http/https)
        - ✅ URL must be **valid**
        - ❌ No FTP / bare domains
        - ❌ No multiple URLs
        - ❌ No empty message
        """
    )

    st.markdown("---")

    # ── History in sidebar ────────────────────────────────────────────────────
    st.markdown("### 🕐 Post History")
    if not st.session_state.history:
        st.markdown(
            '<div style="color:#475569;font-size:0.85rem;font-style:italic;">'
            "No posts yet. Publish a message to see history here."
            "</div>",
            unsafe_allow_html=True,
        )
    else:
        for i, entry in enumerate(st.session_state.history[:10]):
            icon = "✅" if entry["success"] else "⚠️"
            # Expandable history entry
            with st.expander(f"{icon} {entry['ts']} · {entry['elapsed']}", expanded=False):
                st.markdown(f"**Message:** {entry['msg']}")
                if entry.get("success_count") is not None:
                    st.markdown(
                        f"📊 {entry.get('success_count', 0)} published · "
                        f"{entry.get('fail_count', 0)} failed"
                    )
        if st.button("🗑️ Clear History", key="clear_history"):
            st.session_state.history = []
            st.rerun()

    st.markdown("---")
    st.markdown("### 📖 API Docs")
    st.markdown(
        "[Swagger UI](http://localhost:4000/docs) · "
        "[ReDoc](http://localhost:4000/redoc)"
    )


# ── Hero Header ───────────────────────────────────────────────────────────────
logos_html = "".join(
    f'<div class="platform-logo-pill">{info["icon"]} {name}</div>'
    for name, info in PLATFORM_INFO.items()
)

st.markdown(
    f"""
    <div class="hero-header">
        <h1>🚀 Multi-Platform Posting System</h1>
        <p>Compose once · Publish everywhere — reach every audience in one click</p>
        <div class="platform-logos-row">
            {logos_html}
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ── Main two-column layout ────────────────────────────────────────────────────
col_compose, col_results = st.columns([1, 1], gap="large")


# ══════════════════════════════════════════════════════════════════════════════
# LEFT COLUMN — Compose
# ══════════════════════════════════════════════════════════════════════════════
with col_compose:
    st.markdown('<div class="section-heading">✍️ Compose Message</div>', unsafe_allow_html=True)

    message: str = st.text_area(
        label="Your message",
        placeholder=(
            "Write your message here. Include exactly ONE URL (http/https).\n\n"
            "Example:\nCheck out our latest updates and join our growing community! "
            "https://example.com"
        ),
        height=145,
        max_chars=MAX_CHARS,
        label_visibility="collapsed",
        key="message_input",
    )

    # ── Character counter (progress bar + text) ────────────────────────────
    char_count = len(message)
    word_count = len(message.split()) if message.strip() else 0
    pct = min(char_count / MAX_CHARS, 1.0)

    if char_count == 0:
        counter_class = "char-ok"
        counter_text = f"0 / {MAX_CHARS}"
    elif char_count <= 160:
        counter_class = "char-ok"
        counter_text = f"{char_count} / {MAX_CHARS}"
    elif char_count <= MAX_CHARS:
        counter_class = "char-warn"
        counter_text = f"{char_count} / {MAX_CHARS} ⚠️"
    else:
        counter_class = "char-over"
        counter_text = f"{char_count} / {MAX_CHARS} ✗ Too long"

    st.progress(pct)
    st.markdown(
        f"""
        <div class="meta-row">
            <span class="word-count">📝 {word_count} word{'s' if word_count != 1 else ''}</span>
            <span class="{counter_class}">{counter_text}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Real-time URL validator ────────────────────────────────────────────
    url_count = count_urls(message)
    found_url = extract_url(message)
    if not message.strip():
        url_fb_class = "url-none"
        url_fb_text = "🔗 Add one URL (http/https) to your message"
    elif url_count == 0:
        url_fb_class = "url-invalid"
        url_fb_text = "✗ No URL detected — exactly one required"
    elif url_count > 1:
        url_fb_class = "url-invalid"
        url_fb_text = f"✗ {url_count} URLs found — only one allowed"
    else:
        url_fb_class = "url-valid"
        url_fb_text = f"✓ Valid URL: {found_url}"

    st.markdown(
        f'<div class="url-feedback {url_fb_class}">{url_fb_text}</div>',
        unsafe_allow_html=True,
    )

    # ── Message preview ───────────────────────────────────────────────────
    with st.expander("👁️ Message Preview", expanded=bool(message.strip())):
        st.markdown(
            f'<div class="msg-preview">{render_message_preview(message)}</div>',
            unsafe_allow_html=True,
        )

    # ── Quick templates ───────────────────────────────────────────────────
    with st.expander("💡 Message Templates", expanded=False):
        templates = [
            {
                "label": "Business announcement",
                "text": (
                    "🚀 Excited to announce our new platform launch! "
                    "Check it out and join our community. https://example.com"
                ),
            },
            {
                "label": "Product update",
                "text": (
                    "📦 New features just dropped! Faster, smarter, and built for you. "
                    "See what's new: https://example.com/updates"
                ),
            },
            {
                "label": "Community post",
                "text": (
                    "💬 Join thousands of professionals growing their online presence. "
                    "Start for free today: https://example.com"
                ),
            },
        ]
        for t in templates:
            if st.button(f"📝 {t['label']}", key=f"tpl_{t['label']}"):
                st.session_state["_tpl"] = t["text"]
                st.rerun()

    # Apply template if selected
    if "_tpl" in st.session_state:
        message = st.session_state.pop("_tpl")
        st.rerun()

    st.markdown("&nbsp;")

    publish_clicked = st.button(
        "🚀 Publish to All Platforms",
        disabled=not is_healthy or not message.strip(),
        type="primary",
        key="publish_btn",
    )

    if not is_healthy:
        st.warning("⚠️ Backend is offline. Start the FastAPI server first.")
    elif not message.strip():
        st.info("ℹ️ Type your message above to enable publishing.")

    # ── Platform status tiles (pre-posting overview) ───────────────────────
    st.markdown("---")
    st.markdown('<div class="section-heading">🌐 Platform Status</div>', unsafe_allow_html=True)

    # Attempt to get platform configured status from health endpoint
    health_data = get_health_data()
    configured_platforms: set[str] = set()
    if health_data:
        # Accept either {"platforms": {"Telegram": true, ...}} or similar shapes
        plat_map = health_data.get("platforms", health_data.get("configured_platforms", {}))
        if isinstance(plat_map, dict):
            configured_platforms = {k for k, v in plat_map.items() if v}
        elif isinstance(plat_map, list):
            configured_platforms = set(plat_map)
        else:
            # Backend is healthy but no platform granularity — assume all ready
            if is_healthy:
                configured_platforms = set(PLATFORM_INFO.keys())

    tiles_html = "".join(
        render_platform_tile(name, name in configured_platforms, is_healthy)
        for name in PLATFORM_INFO
    )
    st.markdown(tiles_html, unsafe_allow_html=True)

    # ── Publish action ─────────────────────────────────────────────────────
    if publish_clicked and message.strip():
        # Per-platform animated placeholders
        st.markdown("---")
        st.markdown('<div class="section-heading">📡 Publishing…</div>', unsafe_allow_html=True)

        platform_placeholders: dict[str, Any] = {}
        for pname in PLATFORM_INFO:
            platform_placeholders[pname] = st.empty()
            platform_placeholders[pname].markdown(
                f'<div class="platform-card posting">'
                f'<div class="card-title">{PLATFORM_INFO[pname]["icon"]} {pname}</div>'
                f'<span class="card-status-badge badge-posting">⏳ Posting…</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

        start_time = time.time()
        with st.spinner("📡 Sending to all platforms…"):
            response_data, status_code = post_message(message)
        elapsed = time.time() - start_time

        if response_data is None or status_code == 408:
            for ph in platform_placeholders.values():
                ph.empty()
            st.error("⏱️ Request timed out (60 s). Check your network and credentials.")
        elif "error" in response_data and status_code == 500:
            for ph in platform_placeholders.values():
                ph.empty()
            st.error(f"❌ Connection error: {response_data['error']}")
        elif status_code == 422:
            for ph in platform_placeholders.values():
                ph.empty()
            detail = response_data.get("detail", [])
            hint = response_data.get("hint", "")
            if isinstance(detail, list):
                for d in detail:
                    st.error(f"🚫 Validation: {d}")
            else:
                st.error(f"🚫 Validation error: {detail}")
            if hint:
                st.info(f"💡 {hint}")
        else:
            # Animate each card result
            results = response_data.get("results", [])
            result_map = {r.get("platform", ""): r for r in results}
            for pname, ph in platform_placeholders.items():
                r = result_map.get(pname)
                if r:
                    ph.markdown(render_platform_card(r), unsafe_allow_html=True)
                else:
                    ph.empty()

            success_count = sum(1 for r in results if r.get("status") == "success")
            fail_count = sum(1 for r in results if r.get("status") == "failed")

            st.session_state.last_response = response_data
            st.session_state.history.insert(
                0,
                {
                    "ts": datetime.now().strftime("%H:%M:%S"),
                    "msg": message[:60] + ("…" if len(message) > 60 else ""),
                    "success": response_data.get("success", False),
                    "elapsed": f"{elapsed:.1f}s",
                    "success_count": success_count,
                    "fail_count": fail_count,
                },
            )
            st.success(f"✅ Done in {elapsed:.1f}s")
            time.sleep(0.8)  # Brief pause so user sees per-card results before rerun
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# RIGHT COLUMN — Results
# ══════════════════════════════════════════════════════════════════════════════
with col_results:
    st.markdown('<div class="section-heading">📊 Publishing Results</div>', unsafe_allow_html=True)

    if st.session_state.last_response is None:
        # Animated empty state with tips carousel
        tip = TIPS[st.session_state.tip_index % len(TIPS)]
        st.markdown(
            f"""
            <div class="empty-state">
                <div class="empty-icon">📭</div>
                <div class="empty-title">No results yet</div>
                <div style="color:#64748b;font-size:0.9rem;">
                    Compose a message and click <strong style="color:#818cf8">Publish</strong>
                    to post to all platforms.
                </div>
                <div class="empty-tip">{tip}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        # Advance tip carousel
        if st.button("💡 Next Tip", key="next_tip"):
            st.session_state.tip_index += 1
            st.rerun()
    else:
        data = st.session_state.last_response
        results: list[dict] = data.get("results", [])
        overall: bool = data.get("success", False)

        success_count = sum(1 for r in results if r.get("status") == "success")
        fail_count = sum(1 for r in results if r.get("status") == "failed")
        unconf_count = sum(1 for r in results if r.get("status") == "unconfigured")

        # Summary banner
        if overall:
            st.markdown(
                f'<div class="summary-success">🎉 All {success_count} platforms published successfully!</div>',
                unsafe_allow_html=True,
            )
        elif success_count > 0:
            st.markdown(
                f'<div class="summary-partial">'
                f"⚡ Partial success — {success_count} published, {fail_count} failed"
                f"{f', {unconf_count} not configured' if unconf_count else ''}"
                f"</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="summary-fail">💥 Publishing failed on all platforms.</div>',
                unsafe_allow_html=True,
            )

        # Metrics row
        m1, m2, m3 = st.columns(3)
        m1.metric("✅ Published", success_count)
        m2.metric("❌ Failed", fail_count)
        m3.metric("⚙️ Not Configured", unconf_count)

        st.markdown("---")

        # ── Tabbed results view ────────────────────────────────────────────
        tab_all, tab_ok, tab_fail = st.tabs(
            [f"All Platforms ({len(results)})",
             f"✅ Succeeded ({success_count})",
             f"❌ Failed ({fail_count + unconf_count})"]
        )

        def _render_results_list(items: list[dict]) -> None:
            """Render result cards with optional copy-to-clipboard buttons."""
            if not items:
                st.markdown(
                    '<div style="color:#475569;font-size:0.88rem;text-align:center;'
                    'padding:1.5rem;">No results in this category.</div>',
                    unsafe_allow_html=True,
                )
                return
            for res in items:
                posted_url = res.get("posted_url")
                st.markdown(render_platform_card(res), unsafe_allow_html=True)
                if posted_url:
                    # Copy-to-clipboard via HTML anchor trick
                    st.markdown(
                        f'<a class="copy-btn" href="{posted_url}" target="_blank">'
                        f"🔗 Open URL</a>"
                        f'<a class="copy-btn" '
                        f'onclick="navigator.clipboard.writeText(\'{posted_url}\'); '
                        f'this.textContent=\'✅ Copied!\'; '
                        f'setTimeout(()=>this.textContent=\'📋 Copy URL\',1500); return false;" '
                        f'href="#" >📋 Copy URL</a>',
                        unsafe_allow_html=True,
                    )

        with tab_all:
            _render_results_list(results)

        with tab_ok:
            _render_results_list([r for r in results if r.get("status") == "success"])

        with tab_fail:
            _render_results_list(
                [r for r in results if r.get("status") in ("failed", "unconfigured")]
            )

        # ── Raw JSON expander ──────────────────────────────────────────────
        with st.expander("🔍 Raw API Response", expanded=False):
            st.json(data)

        # ── Clear results button ───────────────────────────────────────────
        st.markdown("&nbsp;")
        if st.button("🗑️ Clear Results", key="clear_results"):
            st.session_state.last_response = None
            st.rerun()


# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown(
    f"""
    <div class="app-footer">
        Multi-Platform Posting System &nbsp;·&nbsp; v{APP_VERSION} &nbsp;·&nbsp;
        <a href="http://localhost:4000/docs" target="_blank">Swagger UI</a> &nbsp;·&nbsp;
        <a href="http://localhost:4000/redoc" target="_blank">ReDoc</a> &nbsp;·&nbsp;
        <a href="http://localhost:4000/health" target="_blank">Health Check</a>
        <br>
        <span style="font-size:0.72rem;color:#334155;margin-top:0.3rem;display:block;">
            Powered by Streamlit · FastAPI · httpx
        </span>
    </div>
    """,
    unsafe_allow_html=True,
)
