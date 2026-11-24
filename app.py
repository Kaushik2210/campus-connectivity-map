"""CampusConnectivity Map: home page with headline KPIs."""
from __future__ import annotations

import streamlit as st

from core import config
from core.db import load_readings
from datetime import datetime

from core.scoring import fastest_hour, find_congestion_windows, hour_label, location_stats, merge_windows, place_name, score_label, time_ago
from core.ui import page_setup, score_badge

df = page_setup("Home", ":material/wifi:")

hour_now = datetime.now().hour
greeting = "Good morning" if hour_now < 12 else "Good afternoon" if hour_now < 17 else "Good evening"
st.markdown(
    f"""<div class="ccm-hero"><span class="ccm-eyebrow">{config.CAMPUS}</span>
<h1>CampusConnectivity Map</h1>
<p class="ccm-lead">{greeting}! Is the Wi-Fi bad where you sit? Tell us, and let's fix it together.</p>
<p class="ccm-sub">Students share quick Wi-Fi readings. We turn them into a map of weak spots and busy hours.</p></div>""",
    unsafe_allow_html=True,
)

if df.empty:
    st.info("No readings yet. Be the first to add one and start the map!", icon=":material/inbox:")
else:
    stats = location_stats(df, config.DEFAULT_DEAD_ZONE_THRESHOLD)
    ok = stats[stats["readings"] >= config.DEFAULT_MIN_READINGS]
    dead = int((ok["median_quality"] < config.DEFAULT_DEAD_ZONE_THRESHOLD).sum())
    weak_share = float((df["quality_score"] < config.DEFAULT_DEAD_ZONE_THRESHOLD).mean())
    c1, c2, c3 = st.columns(3)
    c1.metric("Readings", f"{len(df):,}")
    c2.metric("Places covered", f"{len(stats)}", help="Distinct block + floor + area type combinations")
    c3.metric("Median download", f"{df['download_mbps'].median():.0f} Mbps")
    c4, c5, c6 = st.columns(3)
    c4.metric("Median latency", f"{df['latency_ms'].median():.0f} ms")
    c5.metric("Poor readings", f"{weak_share:.0%}", help=f"Quality score below {config.DEFAULT_DEAD_ZONE_THRESHOLD}")
    c6.metric("Dead zones", dead, help=f"Places with almost no usable Wi-Fi: median quality < {config.DEFAULT_DEAD_ZONE_THRESHOLD} and >= {config.DEFAULT_MIN_READINGS} readings")

if not df.empty:
    st.subheader("How campus Wi-Fi feels right now")
    rated = ok.sort_values("median_quality")
    wins = merge_windows(find_congestion_windows(df))
    fast = fastest_hour(df)
    k1, k2, k3 = st.columns(3)
    if not rated.empty:
        best, worst = rated.iloc[-1], rated.iloc[0]
        with k1.container(border=True):
            st.markdown("**Best Wi-Fi**")
            st.markdown(f"#### {best['location']}")
            st.markdown(f"{score_badge(best['median_quality'])} usually about {best['median_download']:.0f} Mbps")
        with k2.container(border=True):
            st.markdown("**Roughest spot**")
            st.markdown(f"#### {worst['location']}")
            st.markdown(f"{score_badge(worst['median_quality'])} usually about {worst['median_download']:.0f} Mbps")
    if not wins.empty:
        w = wins.iloc[0]
        with k3.container(border=True):
            st.markdown("**Busiest time**")
            st.markdown(f"#### {hour_label(w['start_hour'])} to {hour_label(w['end_hour'])}")
            tip = f" Quietest is around {hour_label(fast[0])}." if fast else ""
            st.caption(f"{w['block']} runs about {w['drop']:.0%} slower than usual.{tip}")

if not df.empty:
    notes = df[df["note"].notna() & (df["note"].astype(str).str.strip() != "")].sort_values("timestamp").tail(4).iloc[::-1]
    if not notes.empty:
        st.subheader("What students are saying")
        for _, n in notes.iterrows():
            st.markdown(f"> \u201c{n['note']}\u201d  \n> {place_name(n['block'], n['floor'], n['area_type'])} \u00b7 {time_ago(n['timestamp'])}")

st.page_link("pages/1_Submit_Reading.py", label="Share my Wi-Fi reading (30 seconds)", icon=":material/add_circle:")

st.subheader("How it works, in four steps")
a, b, c, d = st.columns(4)
a.markdown("**1. Test**  \nRun a quick speed test where you are sitting and tell us the block and floor.")
b.markdown("**2. Map**  \nEvery reading adds a colour to the campus map. Grey means we need more readings.")
c.markdown("**3. Spot problems**  \nWe highlight dead zones and the hours when Wi-Fi slows to a crawl.")
d.markdown("**4. Get it fixed**  \nAdmins see a short list of where a fix helps the most students.")

st.subheader("Want the raw data?")
full = load_readings(True)
st.download_button(
    "Export all readings (CSV)", full.drop(columns=["weekday_name", "is_weekend"]).to_csv(index=False).encode("utf-8"),
    file_name="campus_wifi_readings.csv", mime="text/csv", icon=":material/download:",
)
st.caption("The export includes every row in the database; the `method` column marks synthetic demo rows as `seeded`.")
