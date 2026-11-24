"""Helpers for turning a weak spot into a message to the IT team."""
from __future__ import annotations

from urllib.parse import quote


def build_report(place: str, score: float, label: str, mbps: float, share_weak: float, readings: int, worst_time: str) -> tuple[str, str]:
    """Return (subject, body) for a polite, factual message about one weak spot."""
    when = f" It is slowest in the {worst_time.split(' (')[0].lower()}." if worst_time and worst_time != "n/a" else ""
    subject = f"Wi-Fi problem: {place}"
    body = (
        "Hello IT team,\n\n"
        f"Students are reporting weak Wi-Fi at {place}.\n\n"
        f"- Wi-Fi score: {score:.0f}/100 ({label})\n"
        f"- Typical download: about {mbps:.0f} Mbps\n"
        f"- Poor readings: {share_weak:.0%} of {readings} readings.{when}\n\n"
        "Could you please take a look at this spot?\n\n"
        "Thank you!"
    )
    return subject, body


def mailto(email: str, subject: str, body: str) -> str:
    """A mailto: link that opens the user's own email app with the message filled in (nothing is sent)."""
    return f"mailto:{quote(email, safe='@')}?subject={quote(subject)}&body={quote(body)}"
