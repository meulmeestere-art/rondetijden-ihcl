"""Rondetijden IHCL en Shorttrack Academy.

Live dashboard met rondetijden uit de MYLAPS Speedhive trainingsdata van
IJshal De Vliet in Leiden. Bedoeld voor een TV of tablet langs de ijsbaan.
"""

from __future__ import annotations

import hmac
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
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

STATUS_ICONS = {
    "REPORTBEST": "🟣 PR",
    "SESSIONBEST": "",
    "FASTER": "🟢",
    "SLOWER": "🔴",
    "NONE": "⚪",
}

LEGEND = "🟣 PR = beste dagtijd | 🟢 = sneller dan vorige ronde | 🔴 = langzamer dan vorige ronde"

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


def lap_label(duration: float, status: str | None) -> str:
    return f"{duration:.3f} {STATUS_ICONS.get(status or '', '')}".strip()


def fetch_skater(session: requests.Session, activity: dict) -> dict | None:
    """Haalt de sessies van een rijder op en bouwt een tabelrij.

    Rondes buiten MIN_LAP_SECONDS en MAX_LAP_SECONDS worden genegeerd. Dag beste
    en aantal rondes komen uit deze gefilterde lijst.
    """
    url = f"{API_BASE}/training/activities/{activity.get('id')}/sessions"
    resp = session.get(url, timeout=REQUEST_TIMEOUT, verify=VERIFY_SSL)
    resp.raise_for_status()
    data = resp.json()

    laps = []  # (sorteersleutel, starttijd, duur, ruwe ronde)
    for sess in data.get("sessions", []):
        for lap in sess.get("laps", []):
            try:
                duration = float(lap.get("duration"))
            except (TypeError, ValueError):
                continue
            if MIN_LAP_SECONDS <= duration <= MAX_LAP_SECONDS:
                start = parse_ts(lap.get("dateTimeStart"))
                laps.append((start.timestamp() if start else 0.0, start, duration, lap))

    if not laps:
        return None

    laps.sort(key=lambda item: item[0])
    last = laps[-1]
    speed = (last[3].get("speed") or {}).get("kph") or 0.0

    def nth_last(n: int) -> str:
        if len(laps) < n:
            return "-"
        _, _, duration, raw = laps[-n]
        return lap_label(duration, raw.get("status"))

    return {
        "_ts": last[0],
        "Laatste Passering": last[1].strftime("%H:%M:%S") if last[1] else "-",
        "Rijder": activity.get("chipLabel") or "Onbekend",
        "Laatste Ronde (-1)": nth_last(1),
        "Ronde (-2)": nth_last(2),
        "Ronde (-3)": nth_last(3),
        "Snelheid (-1)": f"{speed:.1f} km/u" if speed else "-",
        "Dag Beste (PR)": f"{min(item[2] for item in laps):.3f}",
        "Totaal Ronden": len(laps),
        "Transponder": activity.get("chipCode") or "-",
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
# Scherm
# ---------------------------------------------------------------------------
col_logo, col_title = st.columns([1, 8])
with col_logo:
    logo = Path(__file__).parent / "logo.png"
    if logo.exists():
        st.image(str(logo), width=110)
with col_title:
    st.title(f"⛸️ {APP_TITLE}")
    st.markdown(f"**Locatie:** {LOCATION_NAME}")

require_access()


@st.fragment(run_every=REFRESH_SECONDS)
def live_view() -> None:
    """Ververst alleen dit blok, de rest van de pagina blijft staan."""
    df, meta = load_live_data(ONLY_LATEST_DAY)
    now = datetime.now(TIMEZONE).strftime("%H:%M:%S")

    if df.empty:
        st.markdown(meta["message"] or "Geen data.")
        st.warning("Wachten op doorkomsten van rijders...")
        return

    status = f"🟢 **LIVE** | Laatste controle: {now}"
    if meta["date"]:
        status += f" | Trainingsdatum: {meta['date']}"
    status += f" | Rijders op het ijs: {len(df)}"
    if meta["errors"]:
        status += f" | ⚠️ {meta['errors']} rijder(s) niet opgehaald"
    st.markdown(f"{status}  \n*Legenda: {LEGEND}*")

    st.dataframe(
        df,
        width="stretch",
        height=min(60 + 36 * len(df), 800),
        hide_index=True,
        column_config={
            "Totaal Ronden": st.column_config.NumberColumn("Totaal Ronden", format="%d")
        },
    )


live_view()
