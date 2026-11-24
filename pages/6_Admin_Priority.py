"""Admin priority: ranked list of where fixing Wi-Fi helps the most people."""
from __future__ import annotations

from datetime import date
from io import BytesIO
from urllib.parse import urlencode

import plotly.graph_objects as go
import streamlit as st

from core import config
from core.poster import poster_svg
from core.scoring import location_stats, priority_table, trend_table
from core.ui import page_setup, require_admin, require_data, style_fig

df = page_setup("Admin priority", ":material/build:")
st.title("What to fix first")
st.caption("We rank places by three things: how bad the Wi-Fi is, how many students reported it, and how often it is bad. The higher the score, the sooner it should be fixed.")
require_admin()
require_data(df)

with st.sidebar:
    st.header("Adjust")
    thr = st.slider("Poor Wi-Fi score below", 5, 80, config.DEFAULT_DEAD_ZONE_THRESHOLD)
    min_n = st.slider("Readings needed", 1, 30, 3)

prio = priority_table(location_stats(df, thr), min_n)
prio = prio[prio["priority_score"] > 0]
if prio.empty:
    st.success("Nothing to fix with these settings. No place has poor readings.", icon=":material/check_circle:")
    st.stop()
top = prio.head(10).reset_index(drop=True)
top.insert(0, "rank", top.index + 1)

fig = go.Figure(go.Bar(
    x=top["priority_score"][::-1], y=(top["rank"].astype(str) + ". " + top["location"])[::-1], orientation="h",
    marker_color=config.COLOR_WEAK, text=top["priority_score"][::-1].round(0).astype(int), textposition="outside",
    hovertemplate="%{y}<br>Priority %{x:.0f}<extra></extra>",
))
fig.update_xaxes(title="Priority (top place = 100)", range=[0, 112])
st.plotly_chart(style_fig(fig, 420), width="stretch")

show = top.rename(columns={
    "rank": "#", "location": "Place", "priority_score": "Priority", "median_quality": "Wi-Fi score", "readings": "Readings",
    "share_weak": "Poor readings", "worst_time": "Slowest time", "action": "Suggested action",
})[["#", "Place", "Priority", "Wi-Fi score", "Readings", "Poor readings", "Slowest time", "Suggested action"]]
cfg = {
    "Priority": st.column_config.NumberColumn(format="%.0f"), "Wi-Fi score": st.column_config.NumberColumn(format="%.0f"),
    "Poor readings": st.column_config.NumberColumn(format="percent"),
}
st.dataframe(show, hide_index=True, width="stretch", column_config=cfg)
st.download_button(
    "Download this list (CSV)", show.to_csv(index=False).encode("utf-8"), file_name="wifi_fix_priority.csv",
    mime="text/csv", icon=":material/download:",
)

# ---- Progress ----------------------------------------------------------------------------
st.subheader("Progress: the last 2 weeks vs the 2 weeks before")
tt = trend_table(df)
if tt.empty:
    st.caption("Not enough readings in both periods yet. Check back after more students have shared.")
else:
    better, worse = tt[tt["direction"] == "better"], tt[tt["direction"] == "worse"]
    p1, p2, p3 = st.columns(3)
    p1.metric("Getting better", len(better))
    p2.metric("Getting worse", len(worse))
    p3.metric("About the same", int((tt["direction"] == "steady").sum()))
    if len(better) or len(worse):
        g1, g2 = st.columns(2)
        with g1.container(border=True):
            st.markdown("**Good news**")
            for _, r in better.sort_values("delta", ascending=False).head(3).iterrows():
                st.markdown(f"- {r['location']}: up {r['delta']:.0f} points")
            if better.empty:
                st.caption("Nothing has clearly improved yet.")
        with g2.container(border=True):
            st.markdown("**Keep an eye on**")
            for _, r in worse.sort_values("delta").head(3).iterrows():
                st.markdown(f"- {r['location']}: down {abs(r['delta']):.0f} points")
            if worse.empty:
                st.caption("Nothing has clearly got worse.")
    st.caption("After a fix, come back in two weeks: the place should show up under Good news.")

# ---- One-page summary (screenshot this) ----------------------------------------------
st.subheader("One-page summary (take a screenshot and share it)")
demo = bool((df["method"] == "seeded").any())
with st.container(border=True):
    st.markdown(f"### Wi-Fi fix priorities: {config.CAMPUS}")
    st.caption(
        f"{date.today():%d %b %Y} | {len(df):,} readings across {df[['block', 'floor', 'area_type']].drop_duplicates().shape[0]} spots"
        + (" | INCLUDES SYNTHETIC DEMO DATA" if demo else "")
    )
    m1, m2, m3 = st.columns(3)
    m1.metric("Places needing work", len(prio))
    m2.metric("Worst Wi-Fi score", f"{top.loc[0, 'median_quality']:.0f} / 100")
    m3.metric("Typical campus download", f"{df['download_mbps'].median():.0f} Mbps")
    st.markdown("**Start with these three**")
    for _, r in top.head(3).iterrows():
        st.markdown(
            f"{int(r['rank'])}. **{r['location']}**: quality {r['median_quality']:.0f}, {r['share_weak']:.0%} of readings weak, "
            f"{r['readings']} readings. {r['action']}."
        )
    st.markdown("**Top 10 places**")
    st.dataframe(show.drop(columns=["Suggested action"]), hide_index=True, width="stretch", column_config=cfg)
    st.caption("These come from student readings, so treat this as a shortlist to check on site, not a final report.")

st.subheader("Need to tell IT? Here is a message you can copy")
lines = "\n".join(
    f"{int(r['rank'])}. {r['location']} (about {r['median_download']:.0f} Mbps, {r['share_weak']:.0%} of readings poor)"
    for _, r in top.head(5).iterrows()
)
demo_note = "\n(Note: this draft was made with demo data, so please replace it with real numbers.)\n" if demo else ""
st.code(
    "Hello IT team,\n\n"
    "Students have shared Wi-Fi readings through CampusConnectivity Map. These places need attention first:\n\n"
    f"{lines}\n{demo_note}\n"
    "Could we arrange a site survey for them? I am happy to share the full data.\n\nThank you!",
    language=None,
)

st.subheader("Poster QR codes")
st.caption("One poster per block. Scanning it opens the Submit page with that block already picked. Open the poster file in your browser and press Ctrl+P to print it.")
base = st.text_input("Your app's public address", key="poster_base", placeholder="https://your-app.streamlit.app").strip().rstrip("/")
if not base:
    st.info("Paste the address where the app is deployed and the QR codes will appear here.", icon=":material/qr_code_2:")
elif not base.startswith(("http://", "https://")):
    st.warning("The address should start with https:// (or http:// for a test on your own network).")
else:
    try:
        import segno
    except ImportError:
        st.warning("Install the QR library with: pip install segno")
    else:
        cols = st.columns(3)
        for i, b in enumerate(config.block_names()):
            link = f"{base}/Submit_Reading?{urlencode({'block': b})}"
            qr = segno.make(link, error="m")
            png, svg = BytesIO(), BytesIO()
            qr.save(png, kind="png", scale=10, border=3)
            qr.save(svg, kind="svg", scale=10, border=3)
            with cols[i % 3].container(border=True):
                st.image(png.getvalue(), width=170)
                st.markdown(f"**{b}**")
                st.caption("Scan to share your Wi-Fi reading")
                st.download_button("Download poster (SVG, ready to print)", poster_svg(b, link), file_name=f"poster_{b.replace(' ', '_')}.svg", mime="image/svg+xml", key=f"poster_{i}", type="primary")
                st.download_button("Download PNG", png.getvalue(), file_name=f"qr_{b.replace(' ', '_')}.png", mime="image/png", key=f"qrpng_{i}")
                st.download_button("Download SVG", svg.getvalue(), file_name=f"qr_{b.replace(' ', '_')}.svg", mime="image/svg+xml", key=f"qrsvg_{i}")
        with st.expander("See what a poster looks like"):
            first = config.block_names()[0]
            st.image(poster_svg(first, f"{base}/Submit_Reading?{urlencode({'block': first})}"), width=380)
