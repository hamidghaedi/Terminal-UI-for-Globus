"""Formatting helpers that mimic what the Globus web app shows."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

_UNITS = ["B", "KB", "MB", "GB", "TB", "PB"]


def human_bytes(n: Optional[int]) -> str:
    """Decimal units, two decimals, like the web app (353.07 GB)."""
    if n is None:
        return "n/a"
    n = float(n)
    for unit in _UNITS:
        if n < 1000 or unit == _UNITS[-1]:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.2f} {unit}"
        n /= 1000
    return f"{n:.2f} PB"


def human_rate(bps: Optional[int]) -> str:
    if not bps:
        return "0.00 MB/s"
    return f"{bps / 1e6:.2f} MB/s"


def parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        try:
            dt = datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def local_dt(s: Optional[str], fmt: str = "%m/%d/%Y, %I:%M %p") -> str:
    dt = parse_iso(s)
    if dt is None:
        return "-"
    return dt.astimezone().strftime(fmt)


def local_time(s: Optional[str]) -> str:
    return local_dt(s, "%m/%d/%Y, %I:%M:%S %p")


def duration(start: Optional[str], end: Optional[str] = None) -> str:
    a = parse_iso(start)
    if a is None:
        return "-"
    b = parse_iso(end) or datetime.now(timezone.utc)
    secs = int((b - a).total_seconds())
    if secs < 0:
        secs = 0
    d, rem = divmod(secs, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    parts = []
    if d:
        parts.append(f"{d} day{'s' if d != 1 else ''}")
    if h:
        parts.append(f"{h} hour{'s' if h != 1 else ''}")
    if m:
        parts.append(f"{m} minute{'s' if m != 1 else ''}")
    parts.append(f"{s} second{'s' if s != 1 else ''}")
    return " ".join(parts[:3])


def countdown(secs: int) -> str:
    m, s = divmod(max(0, secs), 60)
    return f"{m}:{s:02d}"


def progress_fraction(task: dict) -> Optional[float]:
    """0..1 fraction, or None when nothing can be estimated yet."""
    if task.get("status") == "SUCCEEDED":
        return 1.0
    total = task.get("total_estimated_bytes") or 0
    done = task.get("bytes_transferred") or 0
    if total > 0:
        return min(1.0, done / total)
    st = task.get("subtasks_total") or 0
    if st > 0:
        return min(1.0, (task.get("subtasks_succeeded") or 0) / st)
    return None


def status_message(task: dict) -> str:
    """The short line under each task label in the Activity list."""
    kind = "delete" if task.get("type") == "DELETE" else "transfer"
    if task.get("sync_level") is not None and kind == "transfer":
        kind = "sync transfer"
    status = task.get("status")
    if status == "SUCCEEDED":
        return f"{kind} completed"
    if status == "FAILED":
        err = task.get("fatal_error") or {}
        code = (err.get("code") or "failed").lower()
        return f"{kind} {code}"
    if status == "INACTIVE":
        return f"{kind} inactive ({task.get('nice_status') or 'needs attention'})"
    nice = task.get("nice_status") or "OK"
    if nice == "Queued":
        return f"{kind} queued"
    if nice not in ("OK", "Queued"):
        return f"{kind} started ({task.get('nice_status_short_description') or nice})"
    if task.get("is_paused"):
        return f"{kind} paused"
    return f"{kind} started"


def transfer_settings(task: dict) -> list[str]:
    out = []
    if task.get("type") == "DELETE":
        return ["delete task"]
    if task.get("verify_checksum"):
        out.append("verify file integrity after transfer")
    if task.get("encrypt_data"):
        out.append("transfer encrypted")
    sl = task.get("sync_level")
    if sl is None:
        out.append("overwriting all files on destination")
    else:
        out.append(
            {
                0: "sync: copy files that do not exist at destination",
                1: "sync: copy files where size differs",
                2: "sync: copy files where source is newer",
                3: "sync: copy files where checksum differs",
            }.get(sl, f"sync level {sl}")
        )
    if task.get("preserve_timestamp"):
        out.append("preserving source modification times")
    if task.get("delete_destination_extra"):
        out.append("deleting extra files on destination")
    if task.get("skip_source_errors"):
        out.append("skipping files with source errors")
    if task.get("fail_on_quota_errors"):
        out.append("quota errors prevent transfer retry")
    return out
