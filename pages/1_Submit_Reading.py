"""Submit a Wi-Fi reading (manual entry or in-browser quick test)."""
from __future__ import annotations

import re
import time
from datetime import datetime

import numpy as np
import streamlit as st
import streamlit.components.v1 as components

from core import config
from core.db import delete_reading, insert_reading, load_readings
from core.scoring import quality_score, reading_warnings, score_label, speed_meaning
from core.ui import page_setup

df_all = page_setup("Submit a reading", ":material/add_circle:")
S = st.session_state

# JavaScript quick test. Uses Cloudflare's public speed-test endpoints (CORS-enabled).
_JS_TEST = """
<div style="font-family:system-ui,sans-serif;border:1px solid #2a323f;border-radius:14px;padding:14px;max-width:560px;background:#18202b;color:#e8edf3">
  <button id="go" style="min-height:44px;padding:0 18px;border-radius:10px;border:0;background:#6aa9ff;color:#0e131a;font-weight:600;font-size:15px;cursor:pointer">Run quick test</button>
  <div id="st" style="margin:10px 0;color:#b6c0cc;font-size:14px">Takes about 10-20 seconds and uses up to ~10 MB of data.</div>
  <div id="out" style="display:none">
    <input id="res" readonly style="width:100%;box-sizing:border-box;padding:10px;font-size:15px;border:1px solid #3a4452;border-radius:8px;background:#0e131a;color:#e8edf3">
    <button id="cp" style="margin-top:8px;min-height:44px;padding:0 16px;border-radius:10px;border:1px solid #6aa9ff;background:transparent;color:#6aa9ff;font-size:15px;cursor:pointer">Copy result</button>
  </div>
</div>
<script>
const BASE = "https://speed.cloudflare.com";
const $ = id => document.getElementById(id);
const bust = () => "&r=" + Math.random().toString(36).slice(2);
const median = a => { const s=[...a].sort((x,y)=>x-y); return s[Math.floor(s.length/2)]; };
async function latency() {
  const t = [];
  for (let i = 0; i < 7; i++) {
    const s = performance.now();
    await fetch(BASE + "/__down?bytes=0" + bust(), {cache: "no-store"});
    t.push(performance.now() - s);
  }
  t.shift();  // drop the connection-setup sample
  return median(t);
}
async function download(bytes) {
  const s = performance.now();
  const r = await fetch(BASE + "/__down?bytes=" + bytes + bust(), {cache: "no-store"});
  const b = await r.arrayBuffer();
  return {mbps: b.byteLength * 8 / ((performance.now() - s) / 1000) / 1e6, secs: (performance.now() - s) / 1000};
}
async function upload() {
  const body = new Uint8Array(1000000);
  const s = performance.now();
  await fetch(BASE + "/__up", {method: "POST", body, cache: "no-store"});
  return body.length * 8 / ((performance.now() - s) / 1000) / 1e6;
}
$("go").onclick = async () => {
  $("go").disabled = true; $("out").style.display = "none";
  try {
    $("st").textContent = "Measuring latency...";
    const lat = await latency();
    $("st").textContent = "Measuring download...";
    let d = await download(2000000);
    if (d.secs < 2) { const d2 = await download(10000000); if (d2.mbps > d.mbps) d = d2; }
    let ul = null;
    try { $("st").textContent = "Measuring upload..."; ul = await upload(); } catch (e) {}
    const parts = ["DL " + d.mbps.toFixed(1)];
    if (ul !== null) parts.push("UL " + ul.toFixed(1));
    parts.push("LAT " + Math.round(lat));
    $("res").value = parts.join(" | ");
    $("out").style.display = "block";
    $("st").textContent = "Done. Copy the line below and paste it into the box under this test.";
  } catch (e) {
    $("st").textContent = "The test was blocked by your browser or network. Please use Manual entry instead.";
  }
  $("go").disabled = false;
};
$("cp").onclick = async () => {
  try { await navigator.clipboard.writeText($("res").value); $("cp").textContent = "Copied"; }
  catch (e) { $("res").select(); document.execCommand("copy"); $("cp").textContent = "Copied"; }
};
</script>
"""


def _parse_paste() -> None:
    """on_change callback: read 'DL x | UL y | LAT z' into the number inputs."""
    text = S.get("paste_box", "")
    num = lambda tag: re.search(rf"{tag}\s*[:=]?\s*(\d+(?:\.\d+)?)", text, re.I)  # noqa: E731
    dl, ul, lat = num("DL"), num("UL"), num("LAT")
    if dl:
        S["in_down"] = min(float(dl.group(1)), config.LIMITS["download_mbps"][1])
        if ul:
            S["in_up"] = min(float(ul.group(1)), config.LIMITS["upload_mbps"][1])
        if lat:
            S["in_lat"] = max(float(lat.group(1)), config.LIMITS["latency_ms"][0])
        S["browser_parsed"] = True
    else:
        S["browser_parsed"] = False


def _recent_submissions() -> list[float]:
    now = time.time()
    S["submit_times"] = [t for t in S.get("submit_times", []) if now - t < config.RATE_LIMIT_WINDOW_S]
    return S["submit_times"]


st.title("Share your Wi-Fi reading")
st.caption("It takes about 30 seconds. Your reading helps everyone find where the Wi-Fi is weak.")
st.info(
    "**Your privacy is safe.** We never ask for your name, email or device ID. "
    "We only save where you were, your speeds and signal, and an optional note. Please keep the note free of personal details.",
    icon=":material/lock:",
)

# ---- 1. Where are you? -----------------------------------------------------
st.subheader("Step 1: Where are you right now?")
def _prefill_from_link() -> None:
    """Pre-pick the place from a QR link like ?block=Library%20Block&floor=2&area=library (once per visit)."""
    if S.get("_prefilled"):
        return
    S["_prefilled"] = True
    qp = st.query_params
    b = qp.get("block")
    if b not in config.block_names():
        return
    S["sub_block"] = b
    f = str(qp.get("floor", ""))
    if f.isdigit() and int(f) in config.floors_for(b):
        S["sub_floor"] = int(f)
        a = qp.get("area")
        if a in config.area_types_for(b, int(f)):
            S["sub_area"] = a
    S["_from_link"] = b


_prefill_from_link()
if S.get("_from_link"):
    st.caption(f"We picked **{S['_from_link']}** from your QR code. Change it below if you are somewhere else.")
blocks = config.block_names()
c1, c2, c3 = st.columns(3)
block = c1.selectbox("Block", blocks, key="sub_block")
floors = config.floors_for(block)
floor = c2.selectbox("Floor", floors, format_func=lambda f: "Ground" if f == 0 else f"Floor {f}", key="sub_floor")
areas = config.area_types_for(block, floor) or config.load_locations()["area_types"]
area = c3.selectbox("Area type", areas, key="sub_area")

c4, c5 = st.columns(2)
networks = config.load_locations()["networks"] + ["Other"]
network = c4.selectbox("Network name (SSID)", networks, key="sub_net")
if network == "Other":
    network = c4.text_input("Network name", max_chars=40, key="sub_net_other").strip() or "Other"
device = c5.selectbox("Device type", config.load_locations()["devices"], key="sub_dev")

c6, c7 = st.columns(2)
bars = c6.slider("Signal bars on your phone (1 = almost none, 5 = full)", 1, 5, 3, key="sub_bars")
dbm = c7.number_input(
    "Signal in dBm (optional)", min_value=config.LIMITS["dbm"][0], max_value=config.LIMITS["dbm"][1],
    value=None, step=1.0, placeholder="e.g. -62", key="sub_dbm",
    help="Only if your device shows it. If given, it is used instead of the bars.",
)

# ---- 2. Speed --------------------------------------------------------------
st.subheader("Step 2: How is your Wi-Fi?")
mode = st.radio("How would you like to measure?", ["Type it in", "Quick test here"], horizontal=True, key="sub_mode")
if mode == "Quick test here":
    st.caption(
        "Press the button, wait a few seconds, then copy the result line into the box under it. The test is a **rough estimate**. "
        "If your network blocks it, choose \"Type it in\" instead."
    )
    if hasattr(st, "iframe"):  # st.components.v1.html is deprecated in recent Streamlit
        st.iframe(_JS_TEST, height=250)
    else:
        components.html(_JS_TEST, height=250)
    st.text_input("Paste your test result here", key="paste_box", on_change=_parse_paste, placeholder="DL 45.2 | UL 12.1 | LAT 38")
    if S.get("browser_parsed") is False:
        st.warning("Hmm, we could not read that. It should look like: DL 45.2 | UL 12.1 | LAT 38")
    elif S.get("browser_parsed"):
        st.success("Got it! Your numbers are filled in below. Have a quick look, then send.")
else:
    st.caption("Open any speed-test app (Speedtest, fast.com...) where you are, then type the numbers here.")

m1, m2, m3 = st.columns(3)
down = m1.number_input("Download (Mbps)", min_value=0.0, max_value=config.LIMITS["download_mbps"][1], value=None, step=0.5, key="in_down")
up = m2.number_input("Upload (Mbps, optional)", min_value=0.0, max_value=config.LIMITS["upload_mbps"][1], value=None, step=0.5, key="in_up")
lat = m3.number_input("Latency (ms)", min_value=config.LIMITS["latency_ms"][0], max_value=config.LIMITS["latency_ms"][1], value=None, step=1.0, key="in_lat")
issues = st.pills(
    "What was going wrong? (optional, pick any)",
    ["Pages will not load", "Video call dropped", "Keeps disconnecting", "Slow downloads", "Works fine"],
    selection_mode="multi", key="sub_issues",
)
note_text = st.text_input("Anything else we should know? (optional)", max_chars=150, key="sub_note", placeholder="e.g. drops near the stairwell").strip()
note = "; ".join([*(issues or []), *([note_text] if note_text else [])])[:200]

# ---- Submit ----------------------------------------------------------------
warn = reading_warnings(down, up, lat)
confirmed = True
if warn:
    for w in warn:
        st.warning(w, icon=":material/help:")
    confirmed = st.checkbox("These numbers are right", key="sub_confirm")
recent = _recent_submissions()
left = config.RATE_LIMIT_MAX - len(recent)
if left <= 0:
    wait = int(config.RATE_LIMIT_WINDOW_S - (time.time() - min(recent))) // 60 + 1
    st.error(f"That is the limit of {config.RATE_LIMIT_MAX} readings per {config.RATE_LIMIT_WINDOW_S // 60} minutes. Please come back in about {wait} min.")

if st.button("Send my reading", type="primary", disabled=left <= 0 or not confirmed, width="stretch"):
    errors = []
    if down is None or down <= 0:
        errors.append("Please add your download speed (it must be above 0 Mbps).")
    if lat is None:
        errors.append("Please add the latency (ms). Speed-test apps call it 'ping' or 'latency'.")
    if errors:
        for e in errors:
            st.error(e)
    else:
        include = bool(S.get("include_demo", True))
        pool = load_readings(include)
        pool = pool[pool["block"] == block]
        sig = float(dbm) if dbm is not None else float(bars)
        q = quality_score(down, up if up is not None else np.nan, lat, sig)
        method = "in_browser_test" if mode == "Quick test here" and S.get("browser_parsed") else "manual"
        new_id = insert_reading(
            {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "block": block, "floor": int(floor),
                "area_type": area, "download_mbps": float(down), "upload_mbps": None if up is None else float(up),
                "latency_ms": float(lat), "signal_strength": sig, "device_type": device,
                "network_name": network, "method": method, "note": note or None,
            }
        )
        st.cache_data.clear()
        recent.append(time.time())
        S["last_result"] = {
            "id": new_id, "block": block, "down": float(down), "quality": q, "n": len(pool),
            "avg_down": float(pool["download_mbps"].median()) if len(pool) else None,
            "avg_q": float(pool["quality_score"].median()) if len(pool) else None,
        }

r = S.get("last_result")
if r and st.button("I made a typo: remove this reading", key="undo_last", icon=":material/undo:"):
    if delete_reading(r["id"]):
        st.cache_data.clear()
        S["submit_times"] = S.get("submit_times", [])[:-1]  # give the allowance back
        S.pop("last_result", None)
        st.toast("Removed. You can send a corrected one.")
        st.rerun()
r = S.get("last_result")
if r:
    st.success("Thank you! Your reading is on the map now. You just helped every student who sits near you.", icon=":material/check_circle:")
    st.markdown(f"**In plain words:** your Wi-Fi here is **{score_label(r['quality'])}**. At {r['down']:.0f} Mbps it is {speed_meaning(r['down'])}.")
    a, b = st.columns(2)
    if r["avg_down"]:
        pct = (r["down"] - r["avg_down"]) / r["avg_down"] * 100
        a.metric("Your download", f"{r['down']:.1f} Mbps", f"{pct:+.0f}% vs {r['block']} median ({r['avg_down']:.1f})")
        b.metric("Your Wi-Fi score", f"{r['quality']:.0f} / 100", f"{r['quality'] - r['avg_q']:+.0f} vs block median ({r['avg_q']:.0f})")
    else:
        a.metric("Your download", f"{r['down']:.1f} Mbps")
        b.metric("Your Wi-Fi score", f"{r['quality']:.0f} / 100")
        st.caption(f"You are the first to report from {r['block']}, so there is nothing to compare with yet.")
st.caption(f"You can send {max(config.RATE_LIMIT_MAX - len(_recent_submissions()), 0)} more in the next 10 minutes.")
