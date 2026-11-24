"""Database status and a step-by-step guide to connect MySQL."""
from __future__ import annotations

import streamlit as st

from core.db import backend_info, count_by_method, recheck
from core.ui import page_setup, require_admin

page_setup("Database", ":material/database:")
st.title("Database")
st.caption("Where your readings are stored, and how to connect MySQL.")

require_admin()
b = backend_info()
if b.kind == "mysql":
    st.success(f"Connected to **{b.label}**. New readings are saved there.", icon=":material/check_circle:")
else:
    st.info(
        "Readings are saved in a **local file (SQLite)** for now. That is fine for trying things out. "
        "Connect MySQL when you want one shared database.",
        icon=":material/storage:",
    )
    if b.note:
        st.warning(b.note, icon=":material/link_off:")

counts = count_by_method()
real = sum(n for m, n in counts.items() if m != "seeded")
c1, c2, c3 = st.columns(3)
c1.metric("Readings stored", f"{sum(counts.values()):,}")
c2.metric("From students", f"{real:,}")
c3.metric("Demo rows", f"{counts.get('seeded', 0):,}")

if st.button("Check the connection again", icon=":material/refresh:"):
    recheck()
    st.rerun()

st.subheader("Connect to MySQL in 3 steps")
with st.container(border=True):
    st.markdown("**1. Make a database and a user.** Run this once in MySQL Workbench or the `mysql` command line.")
    st.code(
        "CREATE DATABASE IF NOT EXISTS campus_wifi CHARACTER SET utf8mb4;\n"
        "CREATE USER 'campus'@'localhost' IDENTIFIED BY 'pick-a-strong-password';\n"
        "GRANT ALL PRIVILEGES ON campus_wifi.* TO 'campus'@'localhost';",
        language="sql",
    )
    st.caption("Already have a user? Skip this. The app can also create the database itself if your user is allowed to.")
with st.container(border=True):
    st.markdown("**2. Tell the app how to connect.** Create the file `.streamlit/secrets.toml` in the project folder:")
    st.code(
        '[mysql]\nhost = "localhost"\nport = 3306\nuser = "campus"\npassword = "pick-a-strong-password"\ndatabase = "campus_wifi"',
        language="toml",
    )
    st.caption("This file is git-ignored, so your password stays on your computer. Never share it or post it.")
with st.container(border=True):
    st.markdown("**3. Restart the app.** The sidebar will say **MySQL** when it works. The tables are created automatically.")

st.subheader("Good to know")
st.markdown(
    "- The first time the app connects to an empty database it adds about 1,500 **demo rows** (marked `seeded`). "
    "Turn them off with the sidebar switch, or start the app with `CCM_AUTO_SEED=0` to skip them.\n"
    "- If MySQL cannot be reached, the app keeps working with the local file and tells you why in the sidebar.\n"
    "- Prefer environment variables? Use `CCM_MYSQL_HOST`, `CCM_MYSQL_PORT`, `CCM_MYSQL_USER`, "
    "`CCM_MYSQL_PASSWORD` and `CCM_MYSQL_DATABASE`.\n"
    "- Set `CCM_BACKEND=mysql` to refuse the local file and show an error instead.\n"
    "- Putting the app online? `localhost` will not work from there. Use a MySQL server that is reachable from the internet, "
    "and keep local files out of it: online hosts often reset local files, so MySQL is the safe place for real readings."
)
