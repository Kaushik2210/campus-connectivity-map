"""Dead zones: locations with consistently poor quality."""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from core import config
from core.scoring import location_stats, speed_meaning
from core.ui import page_setup, require_data, score_badge, style_fig

df = page_setup("Dead zones", ":material/signal_wifi_off:")
st.title("Dead zones")
st.caption("A dead zone is a place where the Wi-Fi is poor almost every time someone checks. You can change what counts as poor on the left.")
require_data(df)

with st.sidebar:
    st.header("What counts as a dead zone?")
    thr = st.slider("Wi-Fi score below", 5, 80, config.DEFAULT_DEAD_ZONE_THRESHOLD)
    min_n = st.slider("Readings needed before we judge", 1, 30, config.DEFAULT_MIN_READINGS)

stats = location_stats(df, thr)
eligible = stats[stats["readings"] >= min_n]
dead = eligible[eligible["median_quality"] < thr].sort_values("median_quality").reset_index(drop=True)

a, b, c = st.columns(3)
a.metric("Dead zones", len(dead))
b.metric("Places checked", len(eligible))
c.metric("Not enough readings yet", len(stats) - len(eligible), help=f"Spots with fewer than {min_n} readings are not judged.")

if dead.empty:
    st.success("No dead zones right now. Nice! Raise the score on the left to see the weakest places anyway.", icon=":material/check_circle:")
    st.stop()

top = dead.head(15).iloc[::-1]
fig = go.Figure(go.Bar(
    x=top["median_quality"], y=top["location"], orientation="h",
    marker=dict(color=top["median_quality"], colorscale=config.COLORSCALE, cmin=0, cmax=100),
    text=top["median_quality"].round(0).astype(int), textposition="outside",
    customdata=top[["readings", "confidence", "median_download"]],
    hovertemplate="%{y}<br>Wi-Fi score %{x:.0f}<br>%{customdata[0]} readings (%{customdata[1]} confidence)<br>Typical download %{customdata[2]:.1f} Mbps<extra></extra>",
))
fig.add_vline(x=thr, line_dash="dash", line_color="#6b7280", annotation_text=f"dead zone below {thr}")
fig.update_xaxes(title="Wi-Fi score (0-100)", range=[0, max(100, thr + 5)])
st.plotly_chart(style_fig(fig, max(300, 38 * len(top) + 80)), width="stretch")

st.subheader("The worst places, in plain words")
for _, r in dead.head(3).iterrows():
    with st.container(border=True):
        st.markdown(f"**{r['location']}**  {score_badge(r['median_quality'])}")
        when = f" It is slowest in the {r['worst_time'].split(' (')[0].lower()}." if r["worst_time"] != "n/a" else ""
        st.write(
            f"Students here usually get about {r['median_download']:.0f} Mbps, which is {speed_meaning(r['median_download'])}.{when}"
        )
        st.caption(f"Based on {r['readings']} readings ({r['confidence'].lower()} confidence).")

st.subheader("The full list")
table = dead.rename(columns={
    "location": "Place", "median_quality": "Wi-Fi score", "median_download": "Download (Mbps)", "median_latency": "Latency (ms)",
    "readings": "Readings", "confidence": "Confidence", "worst_time": "Worst time of day", "share_weak": "Poor readings",
})[["Place", "Wi-Fi score", "Download (Mbps)", "Latency (ms)", "Readings", "Confidence", "Worst time of day", "Poor readings"]]
st.dataframe(
    table, hide_index=True, width="stretch",
    column_config={
        "Wi-Fi score": st.column_config.NumberColumn(format="%.0f"),
        "Download (Mbps)": st.column_config.NumberColumn(format="%.1f"),
        "Latency (ms)": st.column_config.NumberColumn(format="%.0f"),
        "Poor readings": st.column_config.NumberColumn(format="percent"),
    },
)
st.caption("How sure are we? High = 15 or more readings, Medium = 6 to 14, Low = 5 or fewer. 'Worst time of day' is when that place is slowest.")
