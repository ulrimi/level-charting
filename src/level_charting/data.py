"""CSV observations into an explicit exchange-session evidence window."""

import csv
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

import exchange_calendars
from pydantic import AwareDatetime, Field

from .models import OHLC, Candle, Coverage, Packet, Reference
from .storage import sha256

ET = ZoneInfo("America/New_York")
HALF_HOUR = timedelta(minutes=30)


@lru_cache(maxsize=1)
def calendar():
    return exchange_calendars.get_calendar("XNYS")


def session_window(target: date, count: int = 10) -> tuple[date, ...]:
    if not 1 <= count <= 120:
        raise ValueError("Choose between 1 and 120 completed sessions")
    cal = calendar()
    if not cal.is_session(target):
        raise ValueError("Target date must be an XNYS trading session")
    days = cal.sessions_in_range(
        target - timedelta(days=count * 3 + 14), target - timedelta(days=1)
    )
    if len(days) < count:
        raise ValueError("The calendar does not cover the requested history")
    return tuple(day.date() for day in days[-count:])


def evening(day: date) -> datetime:
    return datetime.combine(day, time(20), ET)


def segments(day: date) -> dict[str, tuple[datetime, datetime]]:
    cal = calendar()
    opening = cal.session_open(day).to_pydatetime().astimezone(ET)
    closing = cal.session_close(day).to_pydatetime().astimezone(ET)
    return {
        "premarket": (datetime.combine(day, time(4), ET), opening),
        "regular": (opening, closing),
        "after_hours": (closing, min(closing + timedelta(hours=4), evening(day))),
    }


def segment_for(stamp: datetime) -> str | None:
    local = stamp.astimezone(ET)
    if not calendar().is_session(local.date()):
        return None
    return next(
        (
            kind
            for kind, (start, end) in segments(local.date()).items()
            if start <= local < end
        ),
        None,
    )


def bucket(stamp: datetime) -> datetime:
    local = stamp.astimezone(ET)
    return local.replace(minute=local.minute // 30 * 30, second=0, microsecond=0)


def expected_buckets(days: tuple[date, ...]) -> tuple[datetime, ...]:
    result = []
    for day in days:
        start = segments(day)["premarket"][0]
        end = segments(day)["after_hours"][1]
        while start < end:
            result.append(start)
            start += HALF_HOUR
    return tuple(result)


class Observation(OHLC):
    timestamp: AwareDatetime
    volume: Decimal = Field(ge=0, allow_inf_nan=False)


def _observations(path: Path, input_minutes: int) -> list[Observation]:
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"timestamp", "open", "high", "low", "close", "volume"}
        if not required <= set(reader.fieldnames or ()):
            raise ValueError("Bars CSV requires timestamp,open,high,low,close,volume")
        rows = [
            Observation.model_validate({key: row[key] for key in required})
            for row in reader
        ]
    seen = set()
    for row in rows:
        stamp = row.timestamp
        if stamp in seen:
            raise ValueError(f"Duplicate source timestamp: {stamp.isoformat()}")
        if stamp.second or stamp.microsecond or stamp.minute % input_minutes:
            raise ValueError(
                f"Timestamp is not on the {input_minutes}-minute grid: {stamp}"
            )
        seen.add(stamp)
    return sorted(rows, key=lambda row: row.timestamp)


def _ohlc(rows):
    return dict(
        open=rows[0].open,
        high=max(r.high for r in rows),
        low=min(r.low for r in rows),
        close=rows[-1].close,
    )


def _daily(path: Path | None, days: tuple[date, ...]) -> list[Reference]:
    if path is None:
        return []
    result, seen = [], set()
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        if not {"date", "open", "high", "low", "close"} <= set(reader.fieldnames or ()):
            raise ValueError("Daily CSV requires date,open,high,low,close")
        for row in reader:
            day = date.fromisoformat(row["date"])
            if day in seen:
                raise ValueError(f"Duplicate provider daily date: {day}")
            seen.add(day)
            if day in days:
                result.append(
                    Reference(
                        record_id=f"D-{day}",
                        session=day,
                        kind="provider_daily",
                        known_at=segments(day)["regular"][1],
                        **{
                            field: row[field]
                            for field in ("open", "high", "low", "close")
                        },
                    )
                )
    return result


def prepare(
    bars_path: Path,
    *,
    symbol: str,
    target: date,
    cutoff: datetime,
    daily_path: Path | None = None,
    sessions: int = 10,
    input_minutes: int = 1,
    price_basis: str = "User-supplied prices; adjustment basis unspecified",
    source: str = "User-supplied CSV",
) -> Packet:
    if input_minutes not in (1, 30):
        raise ValueError("CSV bar interval must be 1 or 30 minutes")
    days = session_window(target, sessions)
    if (
        cutoff.tzinfo is None
        or cutoff.utcoffset() is None
        or cutoff != evening(days[-1])
    ):
        raise ValueError(
            "Use an explicit 20:00 ET cutoff on the last completed session"
        )
    source_span = timedelta(minutes=input_minutes)
    groups, session_rows = defaultdict(list), defaultdict(list)
    for row in _observations(bars_path, input_minutes):
        stamp = row.timestamp.astimezone(ET)
        if stamp.date() not in days or stamp + source_span > cutoff:
            continue
        segment = segment_for(stamp)
        if segment is None or stamp + source_span > segments(stamp.date())[segment][1]:
            continue
        groups[bucket(stamp)].append(row)
        session_rows[(stamp.date(), segment)].append(row)
    bars = tuple(
        Candle(
            record_id=f"B{i:04d}",
            start=start,
            end=start + HALF_HOUR,
            session=start.date(),
            segment=segment_for(start),
            source_bars=len(rows),
            volume=sum((r.volume for r in rows), Decimal(0)),
            **_ohlc(rows),
        )
        for i, (start, rows) in enumerate(sorted(groups.items()), 1)
    )
    references = _daily(daily_path, days)
    references += [
        Reference(
            record_id=f"S-{day}-{kind}",
            session=day,
            kind=f"observed_{kind}",
            known_at=rows[-1].timestamp + source_span,
            **_ohlc(rows),
        )
        for (day, kind), rows in sorted(session_rows.items())
    ]
    expected = expected_buckets(days)
    observed = {bar.start for bar in bars}
    hashes = {"bars_csv": sha256(bars_path.read_bytes())}
    if daily_path:
        hashes["daily_csv"] = sha256(daily_path.read_bytes())
    packet = Packet(
        symbol=symbol.upper(),
        target_session=target,
        cutoff=cutoff,
        sessions=days,
        price_basis=price_basis,
        source=source,
        availability_note="Historical CSV replay. Original provider publication and revision times are not established. Daily known_at uses the completed-session close convention.",
        input_hashes=hashes,
        bars=bars,
        references=tuple(sorted(references, key=lambda r: r.record_id)),
        coverage=Coverage(
            expected_buckets=len(expected),
            observed_buckets=len(bars),
            missing_buckets=tuple(t for t in expected if t not in observed),
            input_minutes=input_minutes,
        ),
    )
    check_packet(packet)
    return packet


def check_packet(packet: Packet) -> None:
    if packet.sessions != session_window(packet.target_session, len(packet.sessions)):
        raise ValueError(
            "Packet history must contain the completed exchange sessions before its target"
        )
    if packet.cutoff != evening(packet.sessions[-1]):
        raise ValueError("Packet cutoff must be the final completed session's 20:00 ET")
    if {bar.session for bar in packet.bars} != set(packet.sessions):
        raise ValueError(
            "An entire requested session is missing; supply complete session coverage"
        )
    ids = [r.record_id for r in (*packet.bars, *packet.references)]
    if len(ids) != len(set(ids)):
        raise ValueError("Evidence record IDs must be unique")
    starts = tuple(bar.start for bar in packet.bars)
    if tuple(sorted(set(starts))) != starts:
        raise ValueError("Candles must be distinct and chronological")
    expected = expected_buckets(packet.sessions)
    for bar in packet.bars:
        if (
            bar.start not in expected
            or bar.session != bar.start.astimezone(ET).date()
            or bar.segment != segment_for(bar.start)
            or bar.end > packet.cutoff
        ):
            raise ValueError(
                f"Candle contradicts the declared session or cutoff: {bar.record_id}"
            )
        if bar.source_bars > 30 // packet.coverage.input_minutes:
            raise ValueError("Observed source count exceeds its candle capacity")
    for ref in packet.references:
        if ref.session not in packet.sessions or ref.known_at > packet.cutoff:
            raise ValueError(
                f"Reference lies outside the history/cutoff: {ref.record_id}"
            )
        if ref.known_at.astimezone(ET).date() != ref.session:
            raise ValueError(
                f"Reference availability and session disagree: {ref.record_id}"
            )
    missing = tuple(t for t in expected if t not in set(starts))
    if (
        packet.coverage.expected_buckets != len(expected)
        or packet.coverage.observed_buckets != len(starts)
        or packet.coverage.missing_buckets != missing
    ):
        raise ValueError("Coverage summary contradicts the observed candles")
