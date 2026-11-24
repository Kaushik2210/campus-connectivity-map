"""Print-ready A4 poster (SVG) with a QR code that opens the Submit page for one block."""
from __future__ import annotations

from xml.sax.saxutils import escape

import segno


def poster_svg(block: str, link: str) -> str:
    """Return an A4 portrait SVG poster. Open it in a browser and print, or send it to a print shop."""
    qr = segno.make(link, error="m")
    uri = qr.svg_data_uri(scale=10, border=2, dark="#0b1220", light="#ffffff")
    href = escape(uri, {'"': "&quot;"})
    name = escape(block)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 794 1123" width="210mm" height="297mm" font-family="Segoe UI, Helvetica, Arial, sans-serif">
  <rect width="794" height="1123" fill="#ffffff"/>
  <rect width="794" height="250" fill="#1d4ed8"/>
  <text x="397" y="120" text-anchor="middle" font-size="64" font-weight="700" fill="#ffffff">Is the Wi-Fi bad here?</text>
  <text x="397" y="185" text-anchor="middle" font-size="30" fill="#dbeafe">Tell us in 30 seconds and help get it fixed.</text>
  <text x="397" y="340" text-anchor="middle" font-size="34" fill="#0b1220">1. Scan this code with your phone camera</text>
  <image x="177" y="380" width="440" height="440" href="{href}" style="image-rendering:crisp-edges"/>
  <text x="397" y="890" text-anchor="middle" font-size="34" fill="#0b1220">2. Share your speed and where you are sitting</text>
  <text x="397" y="960" text-anchor="middle" font-size="46" font-weight="700" fill="#1d4ed8">{name}</text>
  <text x="397" y="1050" text-anchor="middle" font-size="24" fill="#475569">We never collect names, emails or device IDs.</text>
  <text x="397" y="1085" text-anchor="middle" font-size="22" fill="#475569">CampusConnectivity Map: made by students, for students.</text>
</svg>
"""
