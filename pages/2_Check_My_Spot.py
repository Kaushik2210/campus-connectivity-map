"""Check my spot: 'Is it just me?' for one place, in plain words."""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from core import config
from core.scoring import (
    daypart_mask, location_stats, place_name, score_label, speed_meaning, time_ago, trend,
)
from core.report import build_report, mailto
from core.ui import block_order, it_email, page_setup, require_data, score_badge, style_fig

df = page_setup("Check my spot", ":material/pin_drop:")
st.title("Is it just me?")
st.caption("Pick the place where you sit and see how its Wi-Fi really is, and how it compares with the rest of campus.")
require_data(df)

c1, c2, c3 = st.columns(3)
block = c1.selectbox("Block", block_order(df["block"].unique()))
floors = sorted(df.loc[df["block"] == block, "floor"].unique())
floor = c2.selectbox("Floor", floors, format_func=lambda f: "Ground" if f == 0 else f"Floor {f}")
areas = sorted(df[(df["block"] == block) & (df["floor"] == floor)]["area_type"].unique())
area = c3.selectbox("What kind of place?", areas)

here = df[(df["block"] == block) & (df["floor"] == floor) & (df["area_type"] == area)]
stats = location_stats(df, config.DEFAULT_DEAD_ZONE_THRESHOLD)
me = stats[(stats["block"] == block) & (stats["floor"] == floor) & (stats["area_type"] == area)].iloc[0]
campus = float(df["download_mbps"].median())
q, d = me["median_quality"], me["median_download"]

with st.container(border=True):
    st.markdown(f"### {place_name(block, floor, area)}  {score_badge(q)}")
    ratio = d / campus - 1 if campus else 0
    versus = (
        "That is about the same as the rest of campus."
        if abs(ratio) < 0.1
        else f"That is {abs(ratio):.0%} {'faster' if ratio > 0 else 'slower'} than the campus typical ({campus:.0f} Mbps)."
    )
    st.write(f"Students here usually get about **{d:.0f} Mbps**, which is {speed_meaning(d)}. {versus}")
    if me["share_weak"] >= 0.6:
        st.markdown("**Is it just me?** No. Most readings from here are poor, so it is not you or your phone. This is a weak spot.")
    elif me["share_weak"] <= 0.2:
        st.markdown("**Is it just me?** Maybe. Most readings from here are fine, so a slow moment may be a one-off or something on your device.")
    else:
        st.markdown("**Is it just me?** Not really. It is hit and miss here: some readings are fine, some are not.")
    tr = trend(here)
    if tr:
        words = {
            "better": f"**Lately:** getting better (up {tr['delta']:.0f} points on the two weeks before).",
            "worse": f"**Lately:** getting worse (down {abs(tr['delta']):.0f} points on the two weeks before).",
            "steady": "**Lately:** about the same as the two weeks before.",
        }
        st.markdown(words[tr["direction"]])
    if me["readings"] < config.DEFAULT_MIN_READINGS:
        st.caption(f"Only {me['readings']} readings so far, so take this with a pinch of salt. Add yours to help!")

m1, m2, m3, m4 = st.columns(4)
m1.metric("Wi-Fi score", f"{q:.0f} / 100", score_label(q), delta_color="off")
m2.metric("Download", f"{d:.0f} Mbps")
m3.metric("Latency", f"{me['median_latency']:.0f} ms", help="Lower is better. It is the delay before things start loading.")
m4.metric("Readings", int(me["readings"]), me["confidence"] + " confidence", delta_color="off")

# ---- Tell IT -----------------------------------------------------------------------------
if q < 55:
    with st.expander("Want this fixed? Tell IT"):
        subject, body = build_report(
            place_name(block, floor, area), q, score_label(q), d, me["share_weak"], int(me["readings"]), me["worst_time"],
        )
        st.caption("Copy this message, or open it in your email app. Nothing is sent until you press send yourself.")
        st.code(body, language=None)
        email = it_email()
        if email:
            st.link_button("Open an email to IT", mailto(email, subject, body), icon=":material/mail:")
        else:
            st.caption("Ask an admin to set the IT address (`CCM_IT_EMAIL`) so this button can open an email for you.")

# ---- Through the day -------------------------------------------------------------------
parts = []
for name in config.DAYPARTS:
    if name == "All day":
        continue
    sub = here[daypart_mask(here["hour"], name)]
    if len(sub) >= 2:
        parts.append((name, float(sub["download_mbps"].median()), len(sub)))
if len(parts) >= 2:
    st.subheader("Best and worst times here")
    best, worst = max(parts, key=lambda p: p[1]), min(parts, key=lambda p: p[1])
    st.write(f"Best in the **{best[0].split(' (')[0].lower()}** (about {best[1]:.0f} Mbps). Slowest in the **{worst[0].split(' (')[0].lower()}** (about {worst[1]:.0f} Mbps).")
    fig = go.Figure(go.Bar(
        x=[p[0] for p in parts], y=[p[1] for p in parts], customdata=[p[2] for p in parts],
        marker=dict(color=[p[1] for p in parts], colorscale=config.COLORSCALE, cmin=0, cmax=config.DOWNLOAD_GOOD_MBPS),
        text=[f"{p[1]:.0f}" for p in parts], textposition="outside",
        hovertemplate="%{x}<br>%{y:.1f} Mbps<br>%{customdata} readings<extra></extra>",
    ))
    fig.update_yaxes(title="Typical download (Mbps)", rangemode="tozero")
    st.plotly_chart(style_fig(fig, 320), width="stretch")

# ---- A better place nearby? ------------------------------------------------------------
others = stats[
    (stats["block"] == block) & ~((stats["floor"] == floor) & (stats["area_type"] == area))
    & (stats["readings"] >= config.DEFAULT_MIN_READINGS)
].sort_values("median_quality", ascending=False)
if not others.empty and others.iloc[0]["median_quality"] >= q + 10:
    o = others.iloc[0]
    st.info(
        f"**Tip:** {place_name(o['block'], o['floor'], o['area_type'])} is doing better "
        f"({score_label(o['median_quality'])}, about {o['median_download']:.0f} Mbps). Worth a try if you can move.",
        icon=":material/lightbulb:",
    )

# ---- What people said ------------------------------------------------------------------
notes = here[here["note"].notna() & (here["note"].astype(str).str.strip() != "")].sort_values("timestamp").tail(3).iloc[::-1]
if not notes.empty:
    st.subheader("What students said here")
    for _, n in notes.iterrows():
        st.markdown(f"> “{n['note']}”  \n> {time_ago(n['timestamp'])}")

st.page_link("pages/1_Submit_Reading.py", label="Add my reading for this spot", icon=":material/add_circle:")
