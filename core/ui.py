"""Shared Streamlit helpers: page setup, banners, empty states and grid heatmaps."""
from __future__ import annotations

import hmac
import os
import re

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import config
from core.db import backend_info, load_readings
from core.scoring import score_label

_CSS = """
<style>
:root{--ccm-surface:#18202b;--ccm-border:#2a323f;--ccm-muted:#a3afbf;--ccm-accent:#6aa9ff;--ccm-radius:16px}
.block-container{padding-top:2rem;max-width:1200px}
@media (max-width:640px){.block-container{padding-left:1rem;padding-right:1rem}}
h1,h2,h3{letter-spacing:-.02em}
div[data-testid="stMetric"]{background:var(--ccm-surface);border:1px solid var(--ccm-border);border-radius:var(--ccm-radius);padding:1rem 1.1rem;transition:border-color .18s ease}
div[data-testid="stMetric"]:hover{border-color:var(--ccm-accent)}
div[data-testid="stMetricValue"]{font-weight:700;font-size:clamp(1.3rem,2.6vw,1.9rem)}
div[data-testid="stMetricLabel"]{color:var(--ccm-muted)}
div[data-testid="stVerticalBlockBorderWrapper"]{border-radius:var(--ccm-radius)}
.stButton>button,.stDownloadButton>button{min-height:44px;border-radius:12px;font-weight:600}
a[data-testid="stPageLink-NavLink"]{min-height:44px;border:1px solid var(--ccm-accent);border-radius:12px;padding:.5rem 1rem;font-weight:600;width:fit-content}
a[data-testid="stPageLink-NavLink"]:hover{background:rgba(106,169,255,.12)}
.ccm-hero{background:linear-gradient(135deg,#1c2d4a 0%,#16202e 65%);border:1px solid #2c3f5e;border-radius:24px;padding:2rem 2.2rem;margin-bottom:1.4rem}
.ccm-hero h1{margin:.4rem 0 .6rem;font-size:2.4rem;padding:0}
.ccm-eyebrow{display:inline-block;background:rgba(106,169,255,.16);color:#a9cbff;border-radius:999px;padding:.2rem .8rem;font-size:.82rem;font-weight:600}
.ccm-lead{font-size:1.2rem;font-weight:600;margin:0 0 .3rem}
.ccm-sub{color:var(--ccm-muted);margin:0}
@media (max-width:640px){.ccm-hero{padding:1.4rem 1.2rem}.ccm-hero h1{font-size:1.8rem}}
@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
</style>
"""


_BADGE_COLOR = {"Great": "green", "Good": "green", "Okay": "orange", "Poor": "red", "Barely usable": "red"}


def score_badge(score: float) -> str:
    """Markdown badge for a 0-100 score. The word is shown, so colour is never the only signal."""
    label = score_label(score)
    return f":{_BADGE_COLOR[label]}-badge[{label}]"


def page_setup(title: str, icon: str) -> pd.DataFrame:
    """Configure the page, draw the sidebar toggle and demo banner, return readings."""
    st.set_page_config(page_title=f"{title} | {config.APP_NAME}", page_icon=icon, layout="wide")
    st.markdown(_CSS, unsafe_allow_html=True)
    with st.sidebar:
        st.toggle(
            "Include demo data", value=True, key="include_demo",
            help="Synthetic readings shipped with the app so the charts are not empty.",
        )
        try:
            b = backend_info()
            tag = ":green-badge[MySQL]" if b.kind == "mysql" else ":orange-badge[Local file]"
            st.markdown(f"**Database** {tag}")
            if b.note:
                st.caption(b.note)
        except Exception:  # noqa: BLE001  (strict mode with MySQL down)
            st.markdown("**Database** :red-badge[Not connected]")
        st.caption("Made by students, for students. We never collect names, emails or device IDs.")
    include = bool(st.session_state.get("include_demo", True))
    try:
        df = load_readings(include)
    except Exception as e:  # noqa: BLE001
        st.error(f"Could not read the database: {e}. Open the Database page for help.", icon=":material/error:")
        st.stop()
    if include and (df["method"] == "seeded").any():
        st.warning("**Demo data: synthetic readings included.** These are made-up numbers so you can explore. Switch them off in the sidebar to see only real student readings.", icon=":material/science:")
    elif not include:
        st.caption("Demo data hidden: showing real student submissions only.")
    return df


def require_data(df: pd.DataFrame, message: str = "Nothing here yet.") -> None:
    """Show a friendly empty state and stop the page when there is nothing to analyse."""
    if df.empty:
        st.info(f"{message} Add the first one, or turn demo data on in the sidebar to look around.", icon=":material/inbox:")
        st.page_link("pages/1_Submit_Reading.py", label="Submit a reading", icon=":material/add_circle:")
        st.stop()


def _admin_pin() -> str:
    pin = os.environ.get("CCM_ADMIN_PIN", "")
    if not pin:
        try:
            pin = str(st.secrets.get("admin", {}).get("pin", ""))
        except Exception:  # noqa: BLE001  (no secrets file)
            pin = ""
    return pin


def require_admin() -> None:
    """Ask for the admin PIN when one is set (CCM_ADMIN_PIN or secrets [admin] pin); otherwise open."""
    pin = _admin_pin()
    if not pin or st.session_state.get("_admin_ok"):
        return
    tries = st.session_state.get("_pin_tries", 0)
    st.info("This page is for admins. Please enter the PIN.", icon=":material/lock:")
    if tries >= 5:
        st.error("Too many wrong tries. Please reload the page and try again later.")
        st.stop()
    entered = st.text_input("Admin PIN", type="password", key="admin_pin_input")
    if entered:
        if hmac.compare_digest(entered.encode(), pin.encode()):
            st.session_state["_admin_ok"] = True
            st.rerun()
        st.session_state["_pin_tries"] = tries + 1
        st.error("That PIN is not right.")
    st.stop()


def it_email() -> str:
    """IT team address from CCM_IT_EMAIL or secrets [contact] it_email ('' if missing or invalid)."""
    mail = os.environ.get("CCM_IT_EMAIL", "")
    if not mail:
        try:
            mail = str(st.secrets.get("contact", {}).get("it_email", ""))
        except Exception:  # noqa: BLE001  (no secrets file)
            mail = ""
    return mail if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", mail) else ""


def block_order(blocks) -> list[str]:
    """Order block names as in locations.json, unknown ones last."""
    known = config.block_names()
    return sorted(set(blocks), key=lambda b: (known.index(b) if b in known else 999, b))


def style_fig(fig: go.Figure, height: int = 420) -> go.Figure:
    """Apply the shared chart style."""
    fig.update_layout(
        template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=height, margin=dict(l=10, r=10, t=30, b=10),
        font=dict(size=13), legend=dict(orientation="h", y=-0.2),
    )
    return fig


def grid_heatmap(
    frame: pd.DataFrame, row_keys, col_keys, row_labels, col_labels, *,
    value_col: str, count_col: str, min_n: int, zmin: float, zmax: float,
    cbar_title: str, reverse: bool = False, show_text: bool = True,
    x_title: str = "", y_title: str = "", height: int = 420,
) -> go.Figure:
    """Heatmap of a (row, col)-indexed frame; cells with < min_n readings are grey.

    ``reverse=True`` is for metrics where lower is better (latency), so red still means weak.
    """
    idx = pd.MultiIndex.from_product([row_keys, col_keys])
    agg = frame.reindex(idx)
    n = agg[count_col].fillna(0).astype(int)
    val = agg[value_col].where(n >= min_n)
    z = val.to_numpy(dtype=float).reshape(len(row_keys), len(col_keys))
    nn = n.to_numpy().reshape(len(row_keys), len(col_keys))
    text = np.empty(z.shape, dtype=object)
    for i in range(z.shape[0]):
        for j in range(z.shape[1]):
            if nn[i, j] == 0:
                text[i, j] = ""
            elif nn[i, j] < min_n:
                text[i, j] = f"n={nn[i, j]}<br>too few"
            else:
                text[i, j] = f"{z[i, j]:.0f}<br>n={nn[i, j]}"
    fig = go.Figure(
        go.Heatmap(
            z=z, x=list(col_labels), y=list(row_labels), customdata=nn,
            text=text if show_text else None, texttemplate="%{text}" if show_text else None,
            colorscale=config.COLORSCALE, reversescale=reverse, zmin=zmin, zmax=zmax,
            xgap=2, ygap=2, hoverongaps=False,
            hovertemplate="%{y} / %{x}<br>" + cbar_title + ": %{z:.1f}<br>Readings: %{customdata}<extra></extra>",
            colorbar=dict(title=dict(text=cbar_title, side="top"), orientation="h", thickness=10, len=0.9, y=-0.22, yanchor="top"),
        )
    )
    fig.update_xaxes(type="category", title=x_title, side="bottom")
    fig.update_yaxes(type="category", title=y_title)
    fig.update_layout(plot_bgcolor=config.COLOR_NODATA)
    style_fig(fig, height)
    fig.update_layout(margin=dict(l=10, r=10, t=30, b=90))
    return fig

