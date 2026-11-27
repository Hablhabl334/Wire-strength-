"""
Self-healing publishAt computation for The Strength Test channel.

Drop-in module: import from upload.py as
    from compute_publish_at import compute_publish_at

Mode selected by PUBLISH_MODE env var (set by the GitHub Actions workflow):

  - 'next-day' (option B, LOCKED): publishAt = tomorrow's 13:00 UTC.
    Robust against late runs; first video publishes 24h after first run.
    Structurally impossible for the ep-4-early incident to recur.

  - 'same-day' (option A, available if ever needed): publishAt = today's
    13:00 UTC if >30 min ahead, else tomorrow's 13:00 UTC.

Both modes guarantee publishAt is at least 30 minutes in the future,
so YouTube never receives a past publishAt (the ep-4-early root cause).

NO subtitles / caption pipeline here — that is permanently off the table
for this channel. Emphasis-phrase text synced to voice is the format rule.
"""
import os
from datetime import datetime, timedelta, timezone

_SAFETY_BUFFER = timedelta(minutes=30)
_PUBLISH_HOUR = 13  # 13:00 UTC = 15:00 Cairo local


def compute_publish_at(now: datetime | None = None) -> datetime:
    """Return a 13:00 UTC timestamp strictly in the future.

    Args:
        now: Override for "current time" (UTC). Defaults to datetime.now(timezone.utc).
             Useful for testing.

    Returns:
        A timezone-aware datetime in UTC, at 13:00 on today or tomorrow,
        guaranteed to be at least 30 minutes in the future.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    mode = os.environ.get("PUBLISH_MODE", "next-day").strip().lower()

    today_13 = now.replace(hour=_PUBLISH_HOUR, minute=0, second=0, microsecond=0)
    tomorrow_13 = today_13 + timedelta(days=1)

    if mode == "same-day":
        # Option A: prefer today's 13:00 UTC if there's >30 min headroom.
        if today_13 - now > _SAFETY_BUFFER:
            return today_13
        return tomorrow_13

    # Option B (default, LOCKED): always tomorrow's 13:00 UTC.
    # Tomorrow's 13:00 is ~24h ahead, so the safety buffer is essentially
    # always satisfied. The check is defensive against the pathological case
    # where now is somehow within 30 min of tomorrow's 13:00 (e.g., script
    # runs at 12:45 UTC — tomorrow's 13:00 is 24h15m away, well within buffer).
    if tomorrow_13 - now < _SAFETY_BUFFER:
        return tomorrow_13 + timedelta(days=1)
    return tomorrow_13


# --- Standalone test (does NOT run when imported by upload.py) ---
if __name__ == "__main__":
    test_cases = [
        ("00:00 UTC (midnight)", datetime(2026, 11, 27, 0, 0, tzinfo=timezone.utc)),
        ("11:00 UTC (pre-publish)", datetime(2026, 11, 27, 11, 0, tzinfo=timezone.utc)),
        ("12:55 UTC (close to publish)", datetime(2026, 11, 27, 12, 55, tzinfo=timezone.utc)),
        ("13:30 UTC (just after publish)", datetime(2026, 11, 27, 13, 30, tzinfo=timezone.utc)),
        ("23:59 UTC (end of day)", datetime(2026, 11, 27, 23, 59, tzinfo=timezone.utc)),
    ]
    for mode in ("next-day", "same-day"):
        os.environ["PUBLISH_MODE"] = mode
        print(f"\n=== PUBLISH_MODE={mode} ===")
        for label, now in test_cases:
            pa = compute_publish_at(now)
            print(f"  now={label:30s}  publishAt={pa.isoformat()}")
