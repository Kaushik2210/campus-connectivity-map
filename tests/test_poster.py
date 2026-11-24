import xml.etree.ElementTree as ET

from core.poster import poster_svg


def test_poster_is_valid_svg_with_block_name_and_qr():
    svg = poster_svg("Block & Co <1>", "https://example.streamlit.app/Submit_Reading?block=Block")
    root = ET.fromstring(svg)  # must be well-formed XML even with odd characters in the name
    assert root.tag.endswith("svg")
    assert "Block &amp; Co &lt;1&gt;" in svg
    assert "data:image/svg+xml" in svg and "Is the Wi-Fi bad here?" in svg
