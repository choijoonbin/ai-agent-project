from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def format_to_kst(iso_ts: str | None, fmt: str = "%Y-%m-%d %H:%M") -> str:
    """
    Convert an ISO timestamp string (UTC or local) to formatted KST string.
    Returns "-" when parsing fails or input missing.
    """
    if not iso_ts:
        return "-"
    try:
        # Support timestamps ending with Z by normalizing to +00:00
        normalized = iso_ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        return dt.astimezone(KST).strftime(fmt)
    except Exception:
        return iso_ts

