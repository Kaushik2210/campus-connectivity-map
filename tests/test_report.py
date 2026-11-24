from core.report import build_report, mailto


def test_report_mentions_the_facts():
    subject, body = build_report("Library Block, floor 3 (library)", 13.0, "Poor", 2.0, 1.0, 50, "Late morning (10-13)")
    assert subject == "Wi-Fi problem: Library Block, floor 3 (library)"
    for piece in ("13/100", "Poor", "2 Mbps", "100%", "50 readings", "late morning"):
        assert piece in body


def test_report_without_worst_time():
    _, body = build_report("X", 30.0, "Poor", 5.0, 0.5, 10, "n/a")
    assert "slowest" not in body


def test_mailto_is_url_encoded():
    link = mailto("it@uni.edu", "Wi-Fi problem: A & B", "Line one\nLine two")
    assert link.startswith("mailto:it@uni.edu?subject=")
    assert " " not in link and "\n" not in link and "&body=" in link
    assert "A%20%26%20B" in link
