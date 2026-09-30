"""
Deterministic parsing helpers for operator intelligence questions.

Everything here is a pure function: no database, no model, no clock of its own
(``now`` is always injected). That keeps the two operator capabilities the
assistant needs -- "show me the alerts from 1-5 pm" and "was there anyone inside
this region I marked" -- testable without a running pipeline, and keeps the
assistant's answers reproducible for the same question and the same records.

Two things live here:

1. Time-range extraction. The assistant previously understood only
   ``last N minutes|hours|seconds``. An operator asking for "1-5 pm" got their
   time range silently dropped and received the most recent alerts instead --
   a wrong answer presented with full confidence, which is the one failure mode
   a grounded assistant must not have.
2. Region geometry. When the operator marks a shape on the video, the question
   becomes "which recorded detections fall inside this polygon", which is
   point-in-polygon plus a box-overlap test.
"""
from dataclasses import dataclass
from datetime import datetime, time as dt_time, timedelta, timezone
import re
from typing import List, Optional, Sequence, Tuple

Point = Tuple[float, float]

# Operator shorthand for parts of the day, as (start_hour, end_hour) in local
# wall-clock terms. Deliberately coarse: these are search windows, not claims
# about when "evening" begins.
_DAY_PARTS = {
    "morning": (6, 12),
    "afternoon": (12, 17),
    "evening": (17, 21),
    "night": (21, 24),
}

_CLOCK = r"(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?"

# "from 1-5 pm", "between 1 and 5 pm", "1 to 5pm", "13:00-17:00".
# The separator must not swallow a date-like "1/5" or a decimal.
_RANGE_PATTERNS = [
    re.compile(r"\bbetween\s+" + _CLOCK + r"\s+(?:and|to|-|–)\s+" + _CLOCK, re.IGNORECASE),
    re.compile(r"\bfrom\s+" + _CLOCK + r"\s*(?:to|until|till|-|–)\s*" + _CLOCK, re.IGNORECASE),
    re.compile(r"\b" + _CLOCK + r"\s*(?:to|until|till|-|–)\s*" + _CLOCK, re.IGNORECASE),
]

_SINGLE_TIME = re.compile(r"\b(?:at|around|about)\s+" + _CLOCK, re.IGNORECASE)
_RELATIVE = re.compile(r"\blast\s+(\d+)\s+(minute|min|hour|hr|second|sec|day)s?\b", re.IGNORECASE)


@dataclass
class TimeRange:
    """A resolved UTC query window plus how it was derived, for explainability."""

    start: datetime
    end: datetime
    kind: str  # "relative" | "absolute" | "day_part" | "day"
    text: str  # the phrase this came from, echoed back to the operator

    def describe(self) -> str:
        return f"{self.start.isoformat()} to {self.end.isoformat()} (from \"{self.text}\")"


def _tzinfo(tz_offset_minutes: Optional[int]) -> timezone:
    """
    Resolve the timezone the operator's wall-clock words refer to.

    An operator saying "1-5 pm" means their own clock, but events are stored in
    UTC. When the caller knows the operator's offset (a browser can send
    ``-new Date().getTimezoneOffset()``) we use it; otherwise we fall back to the
    server's local offset, which is right for a single-site deployment and is
    the best available guess for anything else.
    """
    if tz_offset_minutes is not None:
        # Clamp to the real range of UTC offsets so a malformed value cannot
        # push the window into a nonsensical part of the timeline.
        clamped = max(-14 * 60, min(14 * 60, int(tz_offset_minutes)))
        return timezone(timedelta(minutes=clamped))
    local = datetime.now().astimezone().utcoffset() or timedelta(0)
    return timezone(local)


def _to_hour_24(hour: int, minute: int, meridiem: Optional[str]) -> Optional[Tuple[int, int]]:
    """Normalize a parsed clock reading to 24-hour form, or None if impossible."""
    if minute > 59:
        return None
    mer = (meridiem or "").replace(".", "").lower()
    if mer == "pm":
        if hour < 1 or hour > 12:
            return None
        return (hour % 12) + 12, minute
    if mer == "am":
        if hour < 1 or hour > 12:
            return None
        return hour % 12, minute
    if hour > 23:
        return None
    return hour, minute


def _local_day_bounds(now_local: datetime, days_back: int = 0) -> Tuple[datetime, datetime]:
    day = (now_local - timedelta(days=days_back)).date()
    start = datetime.combine(day, dt_time.min, tzinfo=now_local.tzinfo)
    return start, start + timedelta(days=1)


def parse_time_range(
    query: str,
    now: Optional[datetime] = None,
    tz_offset_minutes: Optional[int] = None,
) -> Optional[TimeRange]:
    """
    Extract a UTC time window from an operator question, or None if it names no time.

    Returning None is meaningful: it tells the assistant the operator did not ask
    for a window, so it must not invent one.
    """
    if not query:
        return None

    tz = _tzinfo(tz_offset_minutes)
    now_utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    now_local = now_utc.astimezone(tz)

    def utc(dt: datetime) -> datetime:
        return dt.astimezone(timezone.utc)

    # 1. Relative windows ("last 30 minutes") -- unambiguous, so check first.
    m = _RELATIVE.search(query)
    if m:
        qty, unit = int(m.group(1)), m.group(2).lower()
        delta = {
            "hour": timedelta(hours=qty),
            "hr": timedelta(hours=qty),
            "min": timedelta(minutes=qty),
            "minute": timedelta(minutes=qty),
            "sec": timedelta(seconds=qty),
            "second": timedelta(seconds=qty),
            "day": timedelta(days=qty),
        }[unit]
        return TimeRange(start=now_utc - delta, end=now_utc, kind="relative", text=m.group(0).strip())

    lower = query.lower()

    # 2. Explicit clock ranges ("1-5 pm", "between 11am and 2pm").
    for pattern in _RANGE_PATTERNS:
        m = pattern.search(query)
        if not m:
            continue
        h1, m1, mer1, h2, m2, mer2 = m.groups()
        # "1-5 pm" states the meridiem once, at the end, and means it for both.
        eff_mer1 = mer1 or mer2
        eff_mer2 = mer2 or mer1
        start_hm = _to_hour_24(int(h1), int(m1 or 0), eff_mer1)
        end_hm = _to_hour_24(int(h2), int(m2 or 0), eff_mer2)
        if start_hm is None or end_hm is None:
            continue

        day_start, _ = _local_day_bounds(now_local)
        start_local = day_start.replace(hour=start_hm[0], minute=start_hm[1])
        end_local = day_start.replace(hour=end_hm[0], minute=end_hm[1])
        if end_local <= start_local:
            # "11 pm - 2 am" crosses midnight; a bare "5-1" does too.
            end_local += timedelta(days=1)
        if "yesterday" in lower:
            start_local -= timedelta(days=1)
            end_local -= timedelta(days=1)
        return TimeRange(start=utc(start_local), end=utc(end_local), kind="absolute", text=m.group(0).strip())

    # 3. A single stated time ("at 3 pm") -- take the hour it names.
    m = _SINGLE_TIME.search(query)
    if m:
        hm = _to_hour_24(int(m.group(1)), int(m.group(2) or 0), m.group(3))
        if hm is not None:
            day_start, _ = _local_day_bounds(now_local, 1 if "yesterday" in lower else 0)
            start_local = day_start.replace(hour=hm[0], minute=hm[1])
            return TimeRange(
                start=utc(start_local),
                end=utc(start_local + timedelta(hours=1)),
                kind="absolute",
                text=m.group(0).strip(),
            )

    # 4. Named parts of a day ("yesterday evening", "this morning").
    for name, (h_start, h_end) in _DAY_PARTS.items():
        if name not in lower:
            continue
        days_back = 1 if ("yesterday" in lower or (name == "night" and "last night" in lower)) else 0
        day_start, _ = _local_day_bounds(now_local, days_back)
        start_local = day_start.replace(hour=h_start)
        end_local = day_start + timedelta(days=1) if h_end == 24 else day_start.replace(hour=h_end)
        phrase = f"yesterday {name}" if days_back else name
        return TimeRange(start=utc(start_local), end=utc(end_local), kind="day_part", text=phrase)

    # 5. Whole days.
    if "yesterday" in lower:
        start_local, end_local = _local_day_bounds(now_local, 1)
        return TimeRange(start=utc(start_local), end=utc(end_local), kind="day", text="yesterday")
    if "today" in lower:
        start_local, _ = _local_day_bounds(now_local)
        return TimeRange(start=utc(start_local), end=now_utc, kind="day", text="today")

    return None


def normalize_polygon(raw: Optional[Sequence[Sequence[float]]]) -> Optional[List[Point]]:
    """
    Validate an operator-marked region into a usable polygon.

    Returns None rather than raising for anything unusable, so a sloppy click
    sequence degrades to "no region" instead of a 500.
    """
    if not raw:
        return None
    points: List[Point] = []
    for item in raw:
        if item is None or len(tuple(item)) < 2:
            continue
        try:
            x, y = float(item[0]), float(item[1])
        except (TypeError, ValueError):
            continue
        points.append((x, y))
    return points if len(points) >= 3 else None


def point_in_polygon(point: Point, polygon: Sequence[Point]) -> bool:
    """
    Ray-casting containment test, matching the convention used by SecurityZone.

    Points exactly on an edge are not guaranteed either way -- that is inherent to
    ray casting and irrelevant at the pixel scale this operates on.
    """
    if not polygon or len(polygon) < 3:
        return False
    x, y = point
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if (yi > y) != (yj > y):
            denom = yj - yi
            if denom != 0 and x < (xj - xi) * (y - yi) / denom + xi:
                inside = not inside
        j = i
    return inside


def polygon_bounds(polygon: Sequence[Point]) -> Tuple[float, float, float, float]:
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    return min(xs), min(ys), max(xs), max(ys)


def box_intersects_polygon(box: Sequence[float], polygon: Sequence[Point]) -> bool:
    """
    Test whether a detection box overlaps an operator-marked polygon.

    A centroid-only test misses the case the operator cares about most: a large
    box whose subject stands inside the marked area while its centre sits outside
    it. So we test the centroid, the foot point (where a person meets the ground,
    the most meaningful single point for "was someone standing there"), the four
    corners, and finally whether any polygon vertex falls inside the box -- which
    catches a small region marked entirely within a large box.
    """
    if box is None or len(tuple(box)) < 4 or not polygon or len(polygon) < 3:
        return False
    try:
        x1, y1, x2, y2 = (float(box[0]), float(box[1]), float(box[2]), float(box[3]))
    except (TypeError, ValueError):
        return False

    x1, x2 = min(x1, x2), max(x1, x2)
    y1, y2 = min(y1, y2), max(y1, y2)

    # Cheap rejection before the per-point work.
    px1, py1, px2, py2 = polygon_bounds(polygon)
    if x2 < px1 or x1 > px2 or y2 < py1 or y1 > py2:
        return False

    cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    candidates = [
        (cx, cy),        # centroid
        (cx, y2),        # foot point
        (x1, y1),
        (x2, y1),
        (x1, y2),
        (x2, y2),
    ]
    if any(point_in_polygon(p, polygon) for p in candidates):
        return True

    return any(x1 <= vx <= x2 and y1 <= vy <= y2 for vx, vy in polygon)


# Object classes the detector actually reports, mapped from the words operators
# use. Anything outside this set must not be silently treated as "person".
_CLASS_SYNONYMS = {
    "person": "person",
    "people": "person",
    "human": "person",
    "man": "person",
    "woman": "person",
    "intruder": "person",
    "someone": "person",
    "anybody": "person",
    "anyone": "person",
    "car": "car",
    "truck": "truck",
    "bus": "bus",
    "motorcycle": "motorcycle",
    "motorbike": "motorcycle",
    "bike": "bicycle",
    "bicycle": "bicycle",
    "cycle": "bicycle",
    "boat": "boat",
    "train": "train",
    "drone": "airplane",
}


def extract_object_class(query: str) -> Optional[str]:
    """Map an operator's noun to a detector class name, or None if none is named."""
    if not query:
        return None
    lower = query.lower()
    if re.search(r"\bvehicles?\b", lower):
        return "vehicle"  # widened by the caller into the vehicle class family
    for word, cls in _CLASS_SYNONYMS.items():
        if re.search(rf"\b{re.escape(word)}\b", lower):
            return cls
    return None


VEHICLE_CLASSES = ("car", "truck", "bus", "motorcycle", "bicycle")
