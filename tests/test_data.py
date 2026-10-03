import csv
from datetime import date, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from level_charting.data import (
    ET,
    check_packet,
    evening,
    expected_buckets,
    prepare,
    segment_for,
    session_window,
)
from level_charting.demo import TARGET, synthetic_csv


def write_csv(tmp_path, raw):
    path = tmp_path / "bars.csv"
    path.write_bytes(raw)
    return path


def prepare_demo(path, **kwargs):
    return prepare(
        path,
        symbol="TEST",
        target=TARGET,
        cutoff=evening(session_window(TARGET)[-1]),
        input_minutes=30,
        **kwargs,
    )


def test_separate_daily_and_intraday_definitions(packet):
    day = packet.sessions[-1]
    refs = {r.kind: r for r in packet.references if r.session == day}
    assert refs["provider_daily"].close - refs["observed_regular"].close == Decimal(
        ".01"
    )
    assert packet.coverage.observed_buckets == packet.coverage.expected_buckets == 320


def test_missing_buckets_are_not_filled(tmp_path):
    lines = synthetic_csv()[0].splitlines(keepends=True)
    omitted = lines.pop(12).decode().split(",")[0]
    packet = prepare_demo(write_csv(tmp_path, b"".join(lines)))
    assert len(packet.bars) == 319
    assert [d.isoformat() for d in packet.coverage.missing_buckets] == [omitted]
    assert all(b.start.isoformat() != omitted for b in packet.bars)


def test_future_rows_never_enter_the_packet(tmp_path):
    original = synthetic_csv()[0]
    baseline = prepare_demo(write_csv(tmp_path, original))
    later = original + b"2025-01-21T09:30:00-05:00,999,1000,998,999,10\n"
    bounded = prepare_demo(write_csv(tmp_path, later))
    assert bounded.bars == baseline.bars
    assert bounded.references == baseline.references
    assert bounded.input_hashes != baseline.input_hashes


@pytest.mark.parametrize(
    "bad",
    [
        b"2025-01-03T04:00:00,100,101,99,100,1\n",
        b"2025-01-03T04:15:00-05:00,100,101,99,100,1\n",
        b"2025-01-03T04:00:00-05:00,100,99,98,100,1\n",
        b"2025-01-03T04:00:00-05:00,100,101,99,100,-1\n",
    ],
)
def test_invalid_source_observations_fail(tmp_path, bad):
    with pytest.raises((ValueError, ValidationError)):
        prepare_demo(
            write_csv(tmp_path, b"timestamp,open,high,low,close,volume\n" + bad)
        )


def test_duplicate_timestamps_fail(tmp_path):
    raw = synthetic_csv()[0]
    with pytest.raises(ValueError, match="Duplicate"):
        prepare_demo(write_csv(tmp_path, raw + raw.splitlines(keepends=True)[1]))


def test_minute_aggregation_preserves_observed_prices_and_volume(tmp_path):
    days = session_window(TARGET)
    path = tmp_path / "minutes.csv"
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        for day in days:
            start = expected_buckets((day,))[0]
            writer.writerow(
                [start.isoformat(), "100.123456789", "102", "99", "101", "10"]
            )
            writer.writerow(
                [
                    (start + timedelta(minutes=1)).isoformat(),
                    "101",
                    "103",
                    "100",
                    "102",
                    "15",
                ]
            )
    packet = prepare(path, symbol="TEST", target=TARGET, cutoff=evening(days[-1]))
    first = packet.bars[0]
    assert (
        first.open,
        first.high,
        first.low,
        first.close,
        first.volume,
        first.source_bars,
    ) == (
        Decimal("100.123456789"),
        Decimal(103),
        Decimal(99),
        Decimal(102),
        Decimal(25),
        2,
    )
    assert len(packet.coverage.missing_buckets) == 310


def test_calendar_early_close_and_holiday():
    slots = expected_buckets((date(2025, 11, 28),))
    assert len(slots) == 26
    assert slots[-1].astimezone(ET).strftime("%H:%M") == "16:30"
    assert segment_for(slots[18]) == "after_hours"
    with pytest.raises(ValueError, match="trading session"):
        session_window(date(2025, 11, 27))


def test_window_can_expand_without_a_new_selection_rule():
    days = session_window(TARGET, 44)
    assert len(days) == 44
    assert days[-10:] == session_window(TARGET)


def test_forged_coverage_and_future_candle_fail(packet):
    bad = packet.model_copy(
        update={"coverage": packet.coverage.model_copy(update={"observed_buckets": 1})}
    )
    with pytest.raises(ValueError, match="Coverage"):
        check_packet(bad)
    bad_bar = packet.bars[-1].model_copy(
        update={"end": packet.cutoff + timedelta(minutes=30)}
    )
    with pytest.raises(ValueError, match="cutoff"):
        check_packet(packet.model_copy(update={"bars": (*packet.bars[:-1], bad_bar)}))
