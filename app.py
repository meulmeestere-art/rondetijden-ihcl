"""Rondetijden IHCL en Shorttrack Academy.

Live dashboard met rondetijden uit de MYLAPS Speedhive trainingsdata van
IJshal De Vliet in Leiden. Bedoeld voor een TV of tablet langs de ijsbaan.
"""

from __future__ import annotations

import hmac
import html
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st
import urllib3

# ---------------------------------------------------------------------------
# Instellingen
# ---------------------------------------------------------------------------
APP_TITLE = "Rondetijden IHCL en Shorttrack Academy"
LOCATION_NAME = "IJshal De Vliet, Leiden"

LOCATION_ID = "208259692"
API_BASE = "https://practice-api.speedhive.com/api/v1"
ACTIVITIES_URL = f"{API_BASE}/locations/{LOCATION_ID}/activities"
ACTIVITIES_COUNT = 30

REFRESH_SECONDS = 3  # verversing van het scherm en levensduur van de cache
REQUEST_TIMEOUT = 5
MAX_WORKERS = 10

# Rondes buiten deze grenzen tellen niet mee (rondje stilstaan, meting mist een passage)
MIN_LAP_SECONDS = 9.0
MAX_LAP_SECONDS = 18.0

ACTIVE_SECONDS = 60  # rijders die korter geleden passeerden worden gemarkeerd
ONLY_LATEST_DAY = True  # alleen de meest recente trainingsdag tonen
TIMEZONE = ZoneInfo("Europe/Amsterdam")

# SSL-controle staat standaard aan. Alleen uitzetten bij certificaatproblemen op
# een lokale Mac: VERIFY_SSL=0 streamlit run app.py
VERIFY_SSL = os.getenv("VERIFY_SSL", "1") != "0"
if not VERIFY_SSL:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://sporthive.com/",
    "Origin": "https://sporthive.com",
}

st.set_page_config(page_title=APP_TITLE, page_icon="⛸️", layout="wide")


# ---------------------------------------------------------------------------
# Toegang (optioneel)
# ---------------------------------------------------------------------------
def require_access() -> None:
    """Vraagt een toegangscode als ACCESS_CODE in de Streamlit-secrets staat."""
    try:
        expected = str(st.secrets.get("ACCESS_CODE", ""))
    except Exception:
        expected = ""
    if not expected or st.session_state.get("access_ok"):
        return

    code = st.text_input("Toegangscode", type="password")
    if code:
        if hmac.compare_digest(code.encode(), expected.encode()):
            st.session_state["access_ok"] = True
            st.rerun()
        else:
            st.error("Deze code klopt niet.")
    st.stop()


# ---------------------------------------------------------------------------
# Data ophalen
# ---------------------------------------------------------------------------
def parse_ts(value: str | None) -> datetime | None:
    """Leest een ISO-tijdstempel en geeft die terug in Nederlandse tijd."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=TIMEZONE)
    return dt.astimezone(TIMEZONE)


def fetch_skater(session: requests.Session, activity: dict) -> dict | None:
    """Haalt de sessies van een rijder op en bouwt een tabelrij.

    Rondes buiten MIN_LAP_SECONDS en MAX_LAP_SECONDS worden genegeerd. Dag beste
    en aantal rondes komen uit deze gefilterde lijst.
    """
    url = f"{API_BASE}/training/activities/{activity.get('id')}/sessions"
    resp = session.get(url, timeout=REQUEST_TIMEOUT, verify=VERIFY_SSL)
    resp.raise_for_status()
    data = resp.json()

    laps = []  # (sorteersleutel, passeertijd, duur, ruwe ronde)
    for sess in data.get("sessions", []):
        for lap in sess.get("laps", []):
            try:
                duration = float(lap.get("duration"))
            except (TypeError, ValueError):
                continue
            if MIN_LAP_SECONDS <= duration <= MAX_LAP_SECONDS:
                start = parse_ts(lap.get("dateTimeStart"))
                # dateTimeStart is het begin van de ronde. De passering over de
                # lijn is het einde: start plus rondetijd.
                passed = start + timedelta(seconds=duration) if start else None
                laps.append((passed.timestamp() if passed else 0.0, passed, duration, lap))

    if not laps:
        return None

    laps.sort(key=lambda item: item[0])
    last = laps[-1]
    speed = (last[3].get("speed") or {}).get("kph") or 0.0

    def nth_last(n: int) -> tuple[float | None, str]:
        if len(laps) < n:
            return None, ""
        _, _, duration, raw = laps[-n]
        return duration, raw.get("status") or ""

    lap1, st1 = nth_last(1)
    lap2, st2 = nth_last(2)
    lap3, st3 = nth_last(3)
    return {
        "_ts": last[0],
        "passed": last[1],
        "rider": activity.get("chipLabel") or "Onbekend",
        "lap1": lap1,
        "st1": st1,
        "lap2": lap2,
        "st2": st2,
        "lap3": lap3,
        "st3": st3,
        "kph": speed or None,
        "best": min(item[2] for item in laps),
        "laps": len(laps),
        "chip": activity.get("chipCode") or "-",
    }


@st.cache_resource
def get_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    adapter = requests.adapters.HTTPAdapter(pool_maxsize=MAX_WORKERS)
    session.mount("https://", adapter)
    return session


@st.cache_data(ttl=REFRESH_SECONDS, show_spinner=False)
def load_live_data(only_latest_day: bool) -> tuple[pd.DataFrame, dict]:
    """Geeft de tabel en metadata terug. Wordt gedeeld tussen alle kijkers.

    Dankzij de korte cache doet het aantal schermen geen extra verzoeken aan
    de Speedhive API.
    """
    meta: dict = {"date": None, "errors": 0, "message": None}
    session = get_session()

    try:
        resp = session.get(
            ACTIVITIES_URL,
            params={"count": ACTIVITIES_COUNT, "offset": 0},
            timeout=REQUEST_TIMEOUT,
            verify=VERIFY_SSL,
        )
        resp.raise_for_status()
        activities = resp.json().get("activities", [])
    except (requests.RequestException, ValueError) as exc:
        meta["message"] = f"⚠️ Geen verbinding met MYLAPS Speedhive: {exc}"
        return pd.DataFrame(), meta

    if not activities:
        meta["message"] = "Geen activiteiten gevonden op deze locatie."
        return pd.DataFrame(), meta

    dated = [(parse_ts(a.get("startTime")), a) for a in activities]
    dated = [(dt, a) for dt, a in dated if dt is not None]
    if only_latest_day and dated:
        latest_day = max(dt.date() for dt, _ in dated)
        selected = [a for dt, a in dated if dt.date() == latest_day]
        meta["date"] = latest_day.strftime("%d-%m-%Y")
    else:
        selected = activities[:15]

    rows = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(fetch_skater, session, a) for a in selected]
        for future in futures:
            try:
                row = future.result()
            except (requests.RequestException, ValueError):
                meta["errors"] += 1
                continue
            if row is not None:
                rows.append(row)

    if not rows:
        meta["message"] = "Geen actieve sessies met rondetijden gevonden."
        return pd.DataFrame(), meta

    df = (
        pd.DataFrame(rows)
        .sort_values("_ts", ascending=False)
        .drop(columns="_ts")
        .reset_index(drop=True)
    )
    return df, meta


# ---------------------------------------------------------------------------
# Opmaak
# ---------------------------------------------------------------------------
CSS = """
<style>
:root{--ink:#111827;--muted:#6b7280;--line:#e5e7eb;--soft:#f3f4f6;
--accent:#0a5ca8;--pr:#6f2dbd;--fast:#1a7f37;--slow:#c62828;}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin:.4rem 0 1rem;}
.kpi{border:1px solid var(--line);border-radius:14px;padding:12px 18px;background:#fff;}
.kpi .l{font-size:.78rem;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);}
.kpi .v{font-size:2rem;font-weight:700;color:var(--ink);line-height:1.25;font-variant-numeric:tabular-nums;}
.kpi .s{font-size:.95rem;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.live{display:inline-block;width:.65em;height:.65em;border-radius:50%;background:var(--fast);margin-right:.4em;animation:pulse 1.6s infinite;}
@keyframes pulse{0%{opacity:1}50%{opacity:.3}100%{opacity:1}}
.wrap{overflow-x:auto;border:1px solid var(--line);border-radius:14px;}
table.laps{width:100%;border-collapse:collapse;font-size:1.2rem;font-variant-numeric:tabular-nums;color:var(--ink);}
table.laps th{position:sticky;top:0;background:var(--ink);color:#fff;font-size:.8rem;font-weight:600;
text-transform:uppercase;letter-spacing:.07em;padding:12px 14px;text-align:right;white-space:nowrap;}
table.laps th.l,table.laps td.l{text-align:left;}
table.laps td{padding:11px 14px;text-align:right;border-top:1px solid var(--line);white-space:nowrap;}
table.laps tbody tr:nth-child(even){background:#fafafa;}
table.laps tr.now td{background:#e8f1fb;}
table.laps tr.now td:first-child{box-shadow:inset 5px 0 0 var(--accent);}
td.rider{font-weight:700;}
td.muted,.muted{color:var(--muted);font-size:.95rem;}
.lap{display:inline-block;min-width:5.2em;padding:3px 10px;border-radius:999px;}
.lap.first{font-weight:700;font-size:1.3rem;}
.lap.pr{background:var(--pr);color:#fff;font-weight:700;}
.lap.fast{color:var(--fast);font-weight:600;}
.lap.slow{color:var(--slow);font-weight:600;}
.lap.none{color:var(--muted);}
.best{font-weight:700;}
.star{color:var(--pr);margin-left:.3em;}
.legend{margin:.7rem 0 0;color:var(--muted);font-size:.9rem;}
.empty{padding:2.5rem;text-align:center;color:var(--muted);border:1px dashed var(--line);border-radius:14px;font-size:1.2rem;}
@media (max-width:900px){table.laps{font-size:1rem;}.kpi .v{font-size:1.5rem;}}
</style>
"""

MARKS = {"REPORTBEST": ("pr", " PR"), "FASTER": ("fast", " ▼"), "SLOWER": ("slow", " ▲")}


def fmt_lap(value, status: str, first: bool = False) -> str:
    if value is None or pd.isna(value):
        return '<span class="muted">-</span>'
    css, mark = MARKS.get(status, ("none", ""))
    extra = " first" if first else ""
    return f'<span class="lap {css}{extra}">{value:.3f}{mark}</span>'


def build_table(df: pd.DataFrame, now: datetime) -> str:
    fastest = df["best"].min()
    rows = []
    for r in df.itertuples():
        passed = r.passed
        active = passed is not None and (now - passed).total_seconds() <= ACTIVE_SECONDS
        time_txt = passed.strftime("%H:%M:%S") if passed is not None else "-"
        star = '<span class="star">★</span>' if r.best == fastest else ""
        kph = f"{r.kph:.1f}" if r.kph and not pd.isna(r.kph) else "-"
        rows.append(
            f'<tr class="{"now" if active else ""}">'
            f'<td class="l">{"● " if active else ""}{time_txt}</td>'
            f'<td class="l rider">{html.escape(str(r.rider))}</td>'
            f"<td>{fmt_lap(r.lap1, r.st1, first=True)}</td>"
            f"<td>{fmt_lap(r.lap2, r.st2)}</td>"
            f"<td>{fmt_lap(r.lap3, r.st3)}</td>"
            f"<td>{kph}</td>"
            f'<td class="best">{r.best:.3f}{star}</td>'
            f"<td>{r.laps}</td>"
            f'<td class="muted">{html.escape(str(r.chip))}</td>'
            "</tr>"
        )
    head = (
        '<th class="l">Passering</th><th class="l">Rijder</th><th>Laatste ronde</th>'
        "<th>Ronde -2</th><th>Ronde -3</th><th>km/u</th><th>Dag beste</th>"
        "<th>Rondes</th><th>Transponder</th>"
    )
    return f'<div class="wrap"><table class="laps"><thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'


def build_kpis(df: pd.DataFrame, meta: dict, now: datetime) -> str:
    fastest_row = df.loc[df["best"].idxmin()]
    cards = [
        ("Op het ijs", f'<span class="live"></span>{len(df)}', f"Trainingsdag {meta['date']}" if meta["date"] else "Rijders met tijden"),
        ("Snelste ronde", f"{fastest_row['best']:.3f}", html.escape(str(fastest_row["rider"]))),
        ("Rondes totaal", f"{int(df['laps'].sum())}", "binnen 9 tot 18 seconden"),
        ("Laatste controle", now.strftime("%H:%M:%S"), f"ververst elke {REFRESH_SECONDS} seconden"),
    ]
    inner = "".join(
        f'<div class="kpi"><div class="l">{label}</div><div class="v">{value}</div><div class="s">{sub}</div></div>'
        for label, value, sub in cards
    )
    return f'<div class="kpis">{inner}</div>'


LEGEND_HTML = (
    '<div class="legend"><b>PR</b> beste dagtijd van de rijder | <span style="color:var(--fast)">▼</span> sneller dan vorige ronde | '
    '<span style="color:var(--slow)">▲</span> langzamer dan vorige ronde | ★ snelste van de dag | '
    '<span style="color:var(--accent)">●</span> net gepasseerd</div>'
)


# ---------------------------------------------------------------------------
# Scherm
# ---------------------------------------------------------------------------
st.html(CSS)

ASSETS = Path(__file__).parent / "assets"
col_ihcl, col_title, col_academy = st.columns([1, 6, 1], vertical_alignment="center")
with col_ihcl:
    if (ASSETS / "logo_ihcl.png").exists():
        st.image(str(ASSETS / "logo_ihcl.png"), width=120)
with col_title:
    st.title(f"⛸️ {APP_TITLE}")
    st.markdown(f"**Locatie:** {LOCATION_NAME}")
with col_academy:
    if (ASSETS / "logo_academy.png").exists():
        st.image(str(ASSETS / "logo_academy.png"), width=120)

require_access()


@st.fragment(run_every=REFRESH_SECONDS)
def live_view() -> None:
    """Ververst alleen dit blok, de rest van de pagina blijft staan."""
    df, meta = load_live_data(ONLY_LATEST_DAY)
    now = datetime.now(TIMEZONE)

    if df.empty:
        st.html(f'<div class="empty">{html.escape(meta["message"] or "Geen data.")}<br>Wachten op doorkomsten van rijders...</div>')
        return

    warn = f'<div class="legend">⚠️ {meta["errors"]} rijder(s) niet opgehaald</div>' if meta["errors"] else ""
    st.html(build_kpis(df, meta, now) + build_table(df, now) + LEGEND_HTML + warn)


live_view()
