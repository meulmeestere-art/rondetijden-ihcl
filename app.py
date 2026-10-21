"""Rondetijden IHCL en Shorttrack Academy.

Live dashboard met rondetijden uit de MYLAPS Speedhive trainingsdata van
IJshal De Vliet in Leiden. Bedoeld voor een TV of tablet langs de ijsbaan.
"""

from __future__ import annotations

import base64
import hmac
import html
import io
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st
from PIL import Image
import urllib3
from urllib3.util.retry import Retry

# ---------------------------------------------------------------------------
# Instellingen
# ---------------------------------------------------------------------------
APP_TITLE = "Rondetijden IHCL en Shorttrack Academy"
LOCATION_NAME = "IJshal De Vliet, Leiden"

LOCATION_ID = "208259692"
API_BASE = "https://practice-api.speedhive.com/api/v1"
ACTIVITIES_URL = f"{API_BASE}/locations/{LOCATION_ID}/activities"
ACTIVITIES_COUNT = 100  # genoeg voor alle rijders van een drukke dag

REFRESH_SECONDS = 3  # verversing van het scherm en levensduur van de cache
REQUEST_TIMEOUT = 5
MAX_WORKERS = 10

# Rondes buiten deze grenzen tellen niet mee (rondje stilstaan, meting mist een passage)
MIN_LAP_SECONDS = 9.0
MAX_LAP_SECONDS = 18.0

COMPACT_TOP = "1.1rem"  # ruimte boven de kop in de compacte weergave
COMPACT_ROWS = 12  # aantal rijders in de compacte weergave (768 bij 512)
STALE_MAX_SECONDS = 600  # zo lang tonen we oude gegevens als Speedhive niet antwoordt
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

log = logging.getLogger("rondetijden")

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
    if not isinstance(data, dict):
        raise ValueError("onverwacht antwoord")

    laps = []  # (sorteersleutel, passeertijd, duur, ruwe ronde)
    for sess in data.get("sessions") or []:
        if not isinstance(sess, dict):
            continue
        for lap in sess.get("laps") or []:
            if not isinstance(lap, dict):
                continue
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

    best = min(item[2] for item in laps)

    def status_of(index: int) -> str:
        """Eigen status op basis van de gefilterde rondes.

        De status van Speedhive rekent ook mee met rondes buiten de grenzen,
        waardoor een echte beste ronde soms geen PR krijgt. PR geldt hier alleen
        voor de ronde die gelijk is aan de dag beste.
        """
        duration = laps[index][2]
        if duration == best:
            return "REPORTBEST"
        if index == 0:
            return "NONE"
        previous = laps[index - 1][2]
        if duration < previous:
            return "FASTER"
        if duration > previous:
            return "SLOWER"
        return "NONE"

    def nth_last(n: int) -> tuple[float | None, str]:
        if len(laps) < n:
            return None, ""
        return laps[-n][2], status_of(len(laps) - n)

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
        "best": best,
    }


@st.cache_resource
def get_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    retry = Retry(
        total=2,
        backoff_factor=0.4,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        raise_on_status=False,
    )
    adapter = requests.adapters.HTTPAdapter(pool_maxsize=MAX_WORKERS, max_retries=retry)
    session.mount("https://", adapter)
    return session


@st.cache_resource
def get_state() -> dict:
    """Onthoudt de laatste gelukte gegevens, voor als Speedhive even niet antwoordt."""
    return {"df": None, "meta": None, "ok_at": None, "rows": {}}


def describe_error(exc: Exception) -> str:
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        return f"Speedhive geeft foutcode {exc.response.status_code}"
    if isinstance(exc, requests.Timeout):
        return "Speedhive reageert niet op tijd"
    if isinstance(exc, requests.ConnectionError):
        return "geen verbinding met Speedhive"
    return "onverwacht antwoord van Speedhive"


def fetch_activities(session: requests.Session) -> list:
    resp = session.get(
        ACTIVITIES_URL,
        params={"count": ACTIVITIES_COUNT, "offset": 0},
        timeout=REQUEST_TIMEOUT,
        verify=VERIFY_SSL,
    )
    resp.raise_for_status()
    data = resp.json()
    activities = data.get("activities", []) if isinstance(data, dict) else None
    if not isinstance(activities, list):
        raise ValueError("onverwacht antwoord")
    return [a for a in activities if isinstance(a, dict)]


@st.cache_data(ttl=REFRESH_SECONDS, show_spinner=False)
def load_live_data(only_latest_day: bool) -> tuple[pd.DataFrame, dict]:
    """Geeft de tabel en metadata terug. Wordt gedeeld tussen alle kijkers.

    Dankzij de korte cache doet het aantal schermen geen extra verzoeken aan
    de Speedhive API. Bij een storing blijven de laatste gelukte gegevens
    zichtbaar, met een melding.
    """
    meta: dict = {"date": None, "errors": 0, "message": None, "stale_at": None, "reason": None}
    session = get_session()
    state = get_state()
    now = datetime.now(TIMEZONE)

    try:
        activities = fetch_activities(session)
    except (requests.RequestException, ValueError) as exc:
        reason = describe_error(exc)
        log.warning("Activiteiten ophalen mislukt: %s", exc)
        ok_at = state["ok_at"]
        if state["df"] is not None and ok_at and (now - ok_at).total_seconds() <= STALE_MAX_SECONDS:
            stale = dict(state["meta"])
            stale.update(stale_at=ok_at, reason=reason)
            return state["df"], stale
        meta["message"] = f"⚠️ {reason[0].upper()}{reason[1:]}. Een nieuwe poging volgt automatisch."
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
        futures = [(a, executor.submit(fetch_skater, session, a)) for a in selected]
        for activity, future in futures:
            key = activity.get("id")
            try:
                row = future.result()
            except (requests.RequestException, ValueError) as exc:
                log.warning("Rijder %s ophalen mislukt: %s", key, exc)
                meta["errors"] += 1
                row = state["rows"].get(key)  # vorige gelukte waarde blijft staan
                if row is not None:
                    rows.append(row)
                continue
            if row is not None:
                state["rows"][key] = row
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
    state.update(df=df, meta=dict(meta), ok_at=now)
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
td.rider{font-weight:700;max-width:12em;overflow:hidden;text-overflow:ellipsis;}
table.laps th.fit,table.laps td.fit{width:1%;white-space:nowrap;}
td.muted,.muted{color:var(--muted);font-size:.95rem;}
.lap{display:inline-block;min-width:5.2em;padding:3px 10px;border-radius:999px;}
.lap.first{font-weight:700;font-size:1.3rem;}
.lap.pr{background:var(--pr);color:#fff;font-weight:700;}
.lap.fast{color:var(--fast);font-weight:600;}
.lap.slow{color:var(--slow);font-weight:600;}
.lap.none{color:var(--muted);}
.best{font-weight:700;}
.star{color:var(--pr);margin-left:.3em;}
.notice{margin:0 0 .8rem;padding:10px 16px;border-radius:12px;background:#fff7e0;border:1px solid #f0d98a;color:#7a5b00;}
.legend{margin:.7rem 0 0;color:var(--muted);font-size:.9rem;}
.empty{padding:2.5rem;text-align:center;color:var(--muted);border:1px dashed var(--line);border-radius:14px;font-size:1.2rem;}
.more{display:none;}
.head{display:flex;align-items:center;gap:1.2rem;margin:.2rem 0 .8rem;}
.head img{height:96px;width:auto;flex:none;}
.head .ttl{flex:1;min-width:0;}
.head h1{margin:0!important;padding:0!important;font-size:2.4rem!important;line-height:1.15!important;font-weight:700;color:var(--ink);}
.head .loc{color:var(--muted);margin-top:.3rem;}
@media (max-width:900px){table.laps{font-size:1rem;}table.laps th{padding:10px 8px;}table.laps td{padding:8px 8px;}.lap{min-width:4.4em;padding:2px 6px;}.lap.first{font-size:1.1rem;}}
@media (max-width:700px){.head img{height:56px;}.head h1{font-size:1.5rem!important;}}
</style>
"""

# Compacte weergave voor kleine schermen, zoals 768 bij 512 pixels. Staat aan
# via de browser zodra het scherm lager is dan 600 pixels, of via ?scherm=klein.
COMPACT_RULES = f"""
[data-testid="stHeader"],[data-testid="stToolbar"]{{display:none!important;}}
[data-testid="stMainBlockContainer"],.block-container{{padding:{COMPACT_TOP} .7rem .3rem!important;max-width:100%!important;}}
[data-testid="stVerticalBlock"]{{gap:.35rem!important;}}
.head{{gap:.6rem;margin:0 0 .15rem;}}
.head img{{height:36px;}}
.head h1{{font-size:1.15rem!important;}}
.head .loc{{font-size:.72rem;margin-top:.05rem;}}
.kpis{{grid-template-columns:repeat(4,1fr);gap:6px;margin:.25rem 0 .35rem;}}
.kpi{{padding:5px 9px;border-radius:9px;}}
.kpi .l{{font-size:.58rem;letter-spacing:.05em;}}
.kpi{{overflow:hidden;white-space:nowrap;}}
.kpi .v{{font-size:1.15rem;line-height:1.2;display:inline;}}
.kpi .s{{font-size:.66rem;display:inline;margin-left:.45rem;}}
.kpi:nth-child(1) .s,.kpi:nth-child(3) .s,.kpi:nth-child(4) .s{{display:none;}}
.wrap{{border-radius:9px;}}
table.laps{{font-size:1rem;}}
table.laps td.rider{{max-width:11em;overflow:hidden;text-overflow:ellipsis;}}
table.laps th{{font-size:.58rem;padding:5px 7px;letter-spacing:.04em;}}
table.laps td{{padding:1px 7px;line-height:1.25;}}
table.laps tbody tr:nth-child(n+{COMPACT_ROWS + 1}){{display:none;}}
.lap{{min-width:4.6em;padding:0 7px;line-height:1.3;vertical-align:middle;}}
.lap.first{{font-size:1.12rem;}}
.star{{margin-left:.15em;}}
table.laps tr.now td:first-child{{box-shadow:inset 3px 0 0 var(--accent);}}
.notice{{margin:0 0 .3rem;padding:4px 10px;font-size:.72rem;border-radius:8px;}}
.legend{{margin:.3rem 0 0;font-size:.62rem;}}
.more{{display:inline;}}
.empty{{padding:1rem;font-size:.9rem;}}
"""
CSS += "<style>@media (max-height:600px){" + COMPACT_RULES + "}</style>"

ASSETS = Path(__file__).parent / "assets"


@st.cache_resource
def logo_data_uri(name: str) -> str:
    """Verkleint het logo eenmalig en geeft het terug als ingebed plaatje."""
    path = ASSETS / name
    if not path.exists():
        return ""
    with Image.open(path) as im:
        im.thumbnail((300, 300))
        buf = io.BytesIO()
        im.save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def build_header() -> str:
    def img(name: str, alt: str) -> str:
        uri = logo_data_uri(name)
        return f'<img src="{uri}" alt="{alt}">' if uri else "<span></span>"

    return (
        '<div class="head">'
        + img("logo_ihcl.png", "IHCL Leiden")
        + f'<div class="ttl"><h1>⛸️ {html.escape(APP_TITLE)}</h1>'
        + f'<div class="loc">Locatie: {html.escape(LOCATION_NAME)}</div></div>'
        + img("logo_academy.png", "Shorttrack Academy Leiden")
        + "</div>"
    )


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
            f'<td class="l fit">{"● " if active else ""}{time_txt}</td>'
            f'<td class="l fit rider">{html.escape(str(r.rider))}</td>'
            f"<td>{fmt_lap(r.lap1, r.st1, first=True)}</td>"
            f"<td>{fmt_lap(r.lap2, r.st2)}</td>"
            f"<td>{fmt_lap(r.lap3, r.st3)}</td>"
            f"<td>{kph}</td>"
            f'<td class="best">{r.best:.3f}{star}</td>'
            "</tr>"
        )
    head = (
        '<th class="l fit">Passering</th><th class="l fit">Rijder</th><th>Laatste ronde</th>'
        "<th>Ronde -2</th><th>Ronde -3</th><th>km/u</th><th>Dag beste</th>"
    )
    return f'<div class="wrap"><table class="laps"><thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'


def ago_text(seconds: float) -> str:
    seconds = max(int(seconds), 0)
    if seconds < 60:
        return "zojuist"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} min geleden"
    return f"{minutes // 60} u {minutes % 60} min geleden"


def build_legend(df: pd.DataFrame) -> str:
    hidden = len(df) - COMPACT_ROWS
    more = f'<span class="more"> | nog {hidden} rijder(s) op het ijs</span>' if hidden > 0 else ""
    return LEGEND_HTML[:-6] + more + "</div>"


def build_kpis(df: pd.DataFrame, meta: dict, now: datetime) -> str:
    fastest_row = df.loc[df["best"].idxmin()]
    last_pass = df["passed"].dropna().max() if df["passed"].notna().any() else None
    last_pass_txt = last_pass.strftime("%H:%M:%S") if last_pass is not None else "-"
    last_pass_ago = ago_text((now - last_pass).total_seconds()) if last_pass is not None else ""
    cards = [
        ("Op het ijs", f'<span class="live"></span>{len(df)}', f"Trainingsdag {meta['date']}" if meta["date"] else "Rijders met tijden"),
        ("Snelste ronde", f"{fastest_row['best']:.3f}", html.escape(str(fastest_row["rider"]))),
        ("Laatste passering", last_pass_txt, last_pass_ago),
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
forced = "<style>" + COMPACT_RULES + "</style>" if st.query_params.get("scherm") == "klein" else ""
st.html(CSS + forced + build_header())

require_access()


@st.fragment(run_every=REFRESH_SECONDS)
def live_view() -> None:
    """Ververst alleen dit blok, de rest van de pagina blijft staan."""
    try:
        df, meta = load_live_data(ONLY_LATEST_DAY)
        now = datetime.now(TIMEZONE)

        if df.empty:
            msg = html.escape(meta["message"] or "Geen data.")
            st.html(f'<div class="empty">{msg}<br>Wachten op doorkomsten van rijders...</div>')
            return

        notices = ""
        if meta.get("stale_at"):
            notices += (
                f'<div class="notice">⚠️ {html.escape(meta["reason"] or "Speedhive reageert even niet")}. '
                f'Je ziet de gegevens van {meta["stale_at"].strftime("%H:%M:%S")}. '
                "Een nieuwe poging volgt automatisch.</div>"
            )
        elif meta["errors"]:
            notices += f'<div class="notice">⚠️ {meta["errors"]} rijder(s) niet ververst, de vorige waarde blijft staan.</div>'
        st.html(notices + build_kpis(df, meta, now) + build_table(df, now) + build_legend(df))
    except Exception:  # nooit een foutmelding met traceback aan de baan tonen
        log.exception("Weergave mislukt")
        st.html('<div class="empty">Even geen gegevens. Een nieuwe poging volgt automatisch.</div>')


live_view()
