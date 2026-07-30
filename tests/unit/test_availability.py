from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.main import availability_days, availability_segments


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


def test_availability_days_split_intervals_at_local_midnight() -> None:
    start = datetime(2026, 7, 28, 20, 30, tzinfo=UTC)
    end = datetime(2026, 7, 29, 2, 0, tzinfo=UTC)
    segments = [
        {"status": "up", "from": start, "to": start + timedelta(hours=1)},
        {
            "status": "down",
            "from": start + timedelta(hours=1),
            "to": end,
        },
    ]

    days = availability_days(segments, start, end, -180)

    assert [day["date"] for day in days] == ["2026-07-28", "2026-07-29"]
    assert days[0]["uptime_seconds"] == 1800
    assert days[0]["downtime_seconds"] == 0
    assert days[1]["uptime_seconds"] == 1800
    assert days[1]["downtime_seconds"] == 4 * 3600 + 1800
    assert days[0]["intervals"][-1]["to"] == datetime(
        2026, 7, 28, 21, tzinfo=UTC
    )
