from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo


DEFAULT_DISPLAY_TIMEZONE = "Asia/Seoul"


def format_utc_timestamp(
    value: object,
    *,
    timezone_name: str = DEFAULT_DISPLAY_TIMEZONE,
    include_zone: bool = False,
) -> str:
    """Format a persisted UTC timestamp in the requested display timezone.

    SQLite CURRENT_TIMESTAMP stores UTC in the form:
        YYYY-MM-DD HH:MM:SS

    Naive datetime strings are therefore interpreted as UTC. ISO-8601 values
    with `Z` or an explicit offset are also supported.

    Persisted data is never changed; conversion happens only at the presentation
    boundary.
    """
    if value is None:
        return "-"

    raw = str(value).strip()
    if not raw:
        return "-"

    normalized = raw
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        # Preserve unexpected timestamp values rather than hiding them.
        return raw

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    local = parsed.astimezone(ZoneInfo(timezone_name))
    suffix = f" {local.tzname()}" if include_zone else ""
    return local.strftime("%Y-%m-%d %H:%M:%S") + suffix
