from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.main import availability_segments


def test_availability_segments_show_explicit_outage_between_heartbeats() -> None:
    start = datetime(2026, 7, 28, tzinfo=UTC)
    end = start + timedelta(hours=1)
    events = [
        SimpleNamespace(received_at=start + timedelta(minutes=5)),
        SimpleNamespace(received_at=start + timedelta(minutes=45)),
    ]

    segments, up_seconds = availability_segments(events, start, end, 180)

    assert [segment["status"] for segment in segments] == [
        "down",
        "up",
        "down",
        "up",
        "down",
    ]
    assert up_seconds == 360


def test_availability_without_events_is_unknown_not_false_outage() -> None:
    start = datetime(2026, 7, 28, tzinfo=UTC)
    end = start + timedelta(days=1)

    segments, up_seconds = availability_segments([], start, end)

    assert segments == [{"status": "unknown", "from": start, "to": end}]
    assert up_seconds == 0
