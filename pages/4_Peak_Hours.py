"""Peak hours: hour x weekday heatmap, speed-vs-hour line and congestion windows."""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from core import config
from core.scoring import fastest_hour, find_congestion_windows, hour_label, merge_windows
from core.ui import block_order, grid_heatmap, page_setup, require_data, style_fig

df = page_setup("Peak hours", ":material/schedule:")
st.title("Busy hours")
st.caption("When does the Wi-Fi get slow? We mark an hour as 'busy' when speeds fall 30% or more below what that block normally gets.")
require_data(df)

with st.sidebar:
    st.header("Adjust")
    drop_pct = st.slider("How big a slowdown counts as busy (%)", 10, 70, int(config.CONGESTION_DROP * 100), step=5)
    min_n = st.slider("Readings needed per square", 1, 10, config.MIN_CELL_READINGS)
drop = drop_pct / 100

blocks = block_order(df["block"].unique())
choice = st.selectbox("Block", ["All blocks"] + blocks)
sub = df if choice == "All blocks" else df[df["block"] == choice]
hours = list(range(int(df["hour"].min()), int(df["hour"].max()) + 1))
hlabels = [f"{h:02d}" for h in hours]

tab1, tab2 = st.tabs(["By day of week", "By block"])
with tab1:
    agg = sub.groupby(["weekday", "hour"]).agg(value=("download_mbps", "median"), n=("id", "size"))
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    st.plotly_chart(
        grid_heatmap(agg, range(7), hours, days, hlabels, value_col="value", count_col="n", min_n=min_n,
                     zmin=0, zmax=config.DOWNLOAD_GOOD_MBPS, cbar_title="Median download (Mbps)",
                     show_text=False, x_title="Hour of the day", y_title="", height=360),
        width="stretch",
    )
    if choice != "All blocks":
        st.caption("One block has fewer readings, so many squares are grey. Pick 'All blocks' to see more.")
with tab2:
    agg2 = df.groupby(["block", "hour"]).agg(value=("download_mbps", "median"), n=("id", "size"))
    st.plotly_chart(
        grid_heatmap(agg2, blocks, hours, blocks, hlabels, value_col="value", count_col="n", min_n=min_n,
                     zmin=0, zmax=config.DOWNLOAD_GOOD_MBPS, cbar_title="Median download (Mbps)",
                     show_text=False, x_title="Hour of the day", height=max(320, 60 * len(blocks) + 120)),
        width="stretch",
    )

# ---- Speed vs hour with congestion band ----------------------------------------
st.subheader(f"Speed through the day: {choice}")
hourly = sub.groupby("hour")["download_mbps"].agg(med="median", q1=lambda s: s.quantile(.25), q3=lambda s: s.quantile(.75), n="size")
hourly = hourly[hourly["n"] >= min_n]
baseline = float(sub["download_mbps"].median())
flag = find_congestion_windows(sub.assign(block=choice), drop, min_n)
wins = merge_windows(flag)
fig = go.Figure()
for _, w in wins.iterrows():
    fig.add_vrect(x0=w["start_hour"] - 0.5, x1=w["end_hour"] - 0.5, fillcolor=config.COLOR_WEAK, opacity=0.13, line_width=0,
                  annotation_text="busy", annotation_position="top left", annotation_font_size=11)
fig.add_trace(go.Scatter(x=hourly.index, y=hourly["q3"], mode="lines", line=dict(width=0), hoverinfo="skip", showlegend=False))
fig.add_trace(go.Scatter(x=hourly.index, y=hourly["q1"], mode="lines", line=dict(width=0), fill="tonexty",
                         fillcolor="rgba(106,169,255,0.18)", name="Most readings fall in this band", hoverinfo="skip"))
fig.add_trace(go.Scatter(x=hourly.index, y=hourly["med"], mode="lines+markers", name="Typical download",
                         line=dict(color="#6aa9ff", width=3), customdata=hourly["n"],
                         hovertemplate="%{x}:00<br>%{y:.1f} Mbps<br>%{customdata} readings<extra></extra>"))
fig.add_hline(y=baseline, line_dash="dot", line_color="#8b96a5", annotation_text=f"normal {baseline:.0f}", annotation_position="bottom right")
fig.add_hline(y=baseline * (1 - drop), line_dash="dash", line_color=config.COLOR_WEAK, annotation_text=f"{drop_pct}% slower", annotation_position="bottom left")
fig.update_xaxes(title="Hour of day", dtick=1)
fig.update_yaxes(title="Download (Mbps)", rangemode="tozero")
st.plotly_chart(style_fig(fig, 400), width="stretch")
with st.expander("See the numbers as a table"):
    st.dataframe(
        hourly.rename(columns={"med": "Typical download (Mbps)", "q1": "Lower quarter", "q3": "Upper quarter", "n": "Readings"})
        .round(1).rename_axis("Hour"),
        width="stretch",
    )

# ---- Insight cards -------------------------------------------------------------
st.subheader("When Wi-Fi slows down")
all_wins = merge_windows(find_congestion_windows(df, drop, min_n))
if all_wins.empty:
    st.success(f"Good news: no block slows down by {drop_pct}% or more (with at least {min_n} readings per hour).", icon=":material/check_circle:")
else:
    top = all_wins.head(9)
    cols = st.columns(3)
    for i, (_, w) in enumerate(top.iterrows()):
        with cols[i % 3].container(border=True):
            st.markdown(f"**{w['block']}**")
            st.markdown(f"### {w['start_hour']:02d}:00 - {w['end_hour']:02d}:00")
            st.markdown(f"About **{w['median_speed']:.0f} Mbps** instead of the usual **{w['baseline']:.0f}**  \n:red[**{w['drop']:.0%} slower**] ({w['readings']} readings)")
    if len(all_wins) > len(top):
        st.caption(f"Showing the {len(top)} biggest of {len(all_wins)} windows.")

fast = fastest_hour(df)
if fast:
    st.info(f"Tip: compared with each block's normal, Wi-Fi is usually at its best around {hour_label(fast[0])}. Got something big to download? Try then.", icon=":material/lightbulb:")
