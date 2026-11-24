# CampusConnectivity Map

A crowdsourced Wi-Fi quality tracker for Christ University, Bengaluru. Students submit a quick speed and signal reading from where they are sitting. The app turns those readings into heatmaps, flags dead zones and peak congestion hours, and ranks where the administration should fix Wi-Fi first.

> **Screenshots:** _add images to `docs/` and link them here (home, heatmap, peak hours, dead zones, admin one-pager)._

## Run it

```bash
pip install -r requirements.txt
streamlit run app.py
```

Python 3.11+ is required. The first run creates `data/readings.db` and fills it with ~1,500 **synthetic** readings (`method = "seeded"`) so every page has something to show. Run the tests with `python -m pytest`.

Useful switches:

| What | How |
| --- | --- |
| Hide demo data | "Include demo data" toggle in the sidebar |
| Regenerate demo rows | `python -m core.seed` (real submissions are untouched) |
| Start with an empty database | `CCM_AUTO_SEED=0 streamlit run app.py` (set before the first run) |
| Use another database file | `CCM_DB_PATH=/path/to/file.db` |

## Deploying online (Streamlit Community Cloud)

1. Put the project in a GitHub repository (private is fine). `.streamlit/secrets.toml` and `data/readings.db` are git-ignored, so neither is uploaded.
2. On Streamlit Community Cloud choose the repository and `app.py` as the main file. It installs everything in `requirements.txt` by itself.
3. In the app's **Settings > Secrets**, paste the same `[mysql]` block (and optional `[admin]` PIN) you use locally.
4. The MySQL server must be reachable from the internet. `localhost` only works on your own computer, so use a hosted MySQL service and put its address in `host`.
5. Do not rely on the local SQLite file online: cloud hosts can reset local files, which would delete readings. With MySQL configured, the Database page and the sidebar badge show **MySQL** when it works.
6. Open the **Admin Priority** page, paste the live address under "Poster QR codes", and print the posters.

## Using MySQL

By default readings live in a local SQLite file. To use MySQL instead:

1. Create a database and user (or let the app create the database if your user may):
   ```sql
   CREATE DATABASE IF NOT EXISTS campus_wifi CHARACTER SET utf8mb4;
   CREATE USER 'campus'@'localhost' IDENTIFIED BY 'pick-a-strong-password';
   GRANT ALL PRIVILEGES ON campus_wifi.* TO 'campus'@'localhost';
   ```
2. Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and fill in your values (the file is git-ignored). Environment variables `CCM_MYSQL_HOST`, `CCM_MYSQL_PORT`, `CCM_MYSQL_USER`, `CCM_MYSQL_PASSWORD`, `CCM_MYSQL_DATABASE` work too.
3. Restart the app. The sidebar shows **MySQL** when connected, and tables are created automatically.

If MySQL cannot be reached the app falls back to SQLite and says why. Set `CCM_BACKEND=mysql` to fail loudly instead, or `CCM_BACKEND=sqlite` to ignore MySQL settings. On first connection to an empty database about 1,500 demo rows are added; set `CCM_AUTO_SEED=0` to skip them. The Database page in the app explains all of this.

## Admin PIN (optional)

Set `CCM_ADMIN_PIN` (or `[admin] pin` in `.streamlit/secrets.toml`) and the Admin Priority and Database pages ask for it first. Without a PIN they are open. The PIN is a light gate for a shared link, not strong security.

## Telling IT (optional)

On **Check My Spot**, places with a weak score offer a ready-made message to IT. Set `CCM_IT_EMAIL` (or `[contact] it_email` in `.streamlit/secrets.toml`) and a button opens a pre-filled email in the student's own email app. The app never sends email itself.

## Pages

| Page | What it does |
| --- | --- |
| Home | Headline KPIs, how it works, CSV export of all readings |
| Submit Reading | Block / floor / area / network / device / signal bars, manual or in-browser quick test; validation, 5 submissions per 10 minutes per session, comparison with the block average |
| Check My Spot | "Is it just me?": pick where you sit and see its score in plain words, how it compares with campus, best and worst times, a better spot nearby and what students said |
| Heatmap | Floor x block map of median download, latency or quality; filters for time of day, weekday/weekend, area type, network; cells with fewer than 3 readings are grey |
| Peak Hours | Weekday x hour and block x hour heatmaps, speed-vs-hour line with a congestion band, and cards for each congestion window |
| Dead Zones | Spots below a quality threshold (sidebar) with at least N readings; confidence level and worst time of day |
| Admin Priority | Top 10 places to fix, CSV download, and a one-page summary to screenshot |

Block, floor, area-type, network and device lists live in `data/locations.json`. The block and SSID names shipped there are placeholders: edit them to match the real campus.

## Scoring

Quality score (0-100) is a weighted blend of four normalised components. Weights live in `core/config.py`.

```
quality = 100 x ( 0.50 x download + 0.15 x upload + 0.20 x latency + 0.15 x signal )
```

| Component | Normalised to 0-1 as |
| --- | --- |
| download | `min(Mbps / 50, 1)` |
| upload | `min(Mbps / 20, 1)` |
| latency | `1 - (ms - 20) / (250 - 20)`, clipped (lower is better) |
| signal | bars: `(bars - 1) / 4`; dBm: `(dBm + 90) / 40`, clipped |

If a component is missing (for example no upload value) it is left out and the remaining weights are renormalised, so partial readings are not punished.

**Congestion window:** an hour whose median download is 30%+ below that block's own median (default; adjustable) with at least 3 readings. Consecutive hours are merged into one window.

**Priority score:** `(100 - median quality) / 100 x readings x share of readings below the weak threshold`, rescaled so the top spot is 100. Reading volume is only a proxy for how many people are affected.

## Data collection plan

1. Deploy the app to Streamlit Community Cloud and note the public link.
2. Open the **Admin Priority** page, paste the link under "Poster QR codes" and download a print-ready poster per block (or just the QR code as PNG or SVG). Each code opens the Submit page with that block already picked. Put posters in each block's lobby, the library, the food court and the hostels ("Is the Wi-Fi bad here? Tell us in 30 seconds").
3. Run a short campaign (for example one week, with different classes assigned different blocks) so every floor reaches at least 5 readings at different times of day.
4. Check the Dead Zones page for spots marked "Low" confidence and ask for more readings there.
5. Before the first real analysis, switch off demo data.

Note: Streamlit Cloud storage is ephemeral. For a long-running deployment, point `CCM_DB_PATH` at persistent storage or swap `core/db.py` for a hosted database.

## Privacy

No names, emails, MAC addresses or device identifiers are collected. Stored fields: time, block, floor, area type, speeds, latency, signal, device *type* (for example "iPhone"), network name and an optional free-text note. The Submit page tells users not to put personal details in notes.

## Limitations

- Readings are crowdsourced and partly self-reported (signal bars, location). Expect noise and some wrong entries.
- The in-browser speed test is approximate: it downloads a small file from Cloudflare's public test endpoint over your current connection, so it measures the path to that server, not only the campus Wi-Fi. It cannot fill the form on its own, so the user copies the result line into a box. If a network blocks it, use manual entry.
- The spam limit is per browser session, so it deters casual repeats but is not secure against determined abuse.
- Coverage is uneven: popular spots get more readings. Low-sample cells are greyed or labelled with low confidence rather than guessed.
- The demo data is synthetic and says nothing about the real campus.

## Future work

- Floor-plan overlay with readings placed on the actual map
- Access-point-level data from the IT department to separate coverage gaps from capacity problems
- Trend tracking after fixes (before/after comparison per spot)
- Moderation tools and outlier detection for suspicious submissions
- Persistent hosted database and an admin login for the priority page

## Project layout

```
app.py                      home page
pages/                      the five Streamlit pages
core/config.py              paths, weights, thresholds, location lookups
core/scoring.py             quality score, congestion windows, priority
core/db.py                  SQLite init, writes, cached reads
core/seed.py                synthetic demo data generator
core/ui.py                  shared page setup and heatmap helper
data/locations.json         editable blocks, floors, area types
tests/                      unit tests and headless page smoke tests
```
