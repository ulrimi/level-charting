"""Fictional, deterministic observations for the offline demo and tests."""

import csv
import io
import math
from datetime import date
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from .data import evening, expected_buckets, prepare, session_window
from .models import (
    Alias,
    Band,
    Citation,
    Deferred,
    Encounter,
    Level,
    Proposal,
    Reaction,
)
from .pipeline import packet_files
from .rendering import render
from .storage import digest, json_bytes, publish, sha256

TARGET = date(2025, 1, 21)


def synthetic_csv() -> tuple[bytes, bytes]:
    days = session_window(TARGET)
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
    last = Decimal("100")
    sessions = {}
    for i, stamp in enumerate(expected_buckets(days)):
        close = Decimal(
            str(100 + 5 * math.sin(i * math.pi / 64) + 1.2 * math.sin(i * math.pi / 7))
        ).quantize(Decimal(".01"))
        high, low = max(last, close) + Decimal(".24"), min(last, close) - Decimal(".20")
        writer.writerow(
            [stamp.isoformat(), last, high, low, close, 100000 + (i % 13) * 8000]
        )
        if (stamp.hour, stamp.minute) >= (9, 30) and stamp.hour < 16:
            sessions.setdefault(stamp.date(), []).append((last, high, low, close))
        last = close
    daily = io.StringIO(newline="")
    writer = csv.writer(daily, lineterminator="\n")
    writer.writerow(["date", "open", "high", "low", "close"])
    for day, rows in sessions.items():
        writer.writerow(
            [
                day,
                rows[0][0],
                max(r[1] for r in rows),
                min(r[2] for r in rows),
                rows[-1][3] + Decimal(".01"),
            ]
        )
    return buffer.getvalue().encode(), daily.getvalue().encode()


def synthetic_packet():
    bars, daily = synthetic_csv()
    with TemporaryDirectory(prefix="level-charting-demo-") as temporary:
        root = Path(temporary)
        (root / "bars.csv").write_bytes(bars)
        (root / "daily.csv").write_bytes(daily)
        return prepare(
            root / "bars.csv",
            daily_path=root / "daily.csv",
            symbol="DEMO",
            target=TARGET,
            cutoff=evening(session_window(TARGET)[-1]),
            input_minutes=30,
            price_basis="Fictional, consistent units",
            source="Synthetic arithmetic fixture; not market data",
        )


def synthetic_proposal(packet) -> Proposal:
    """Exercise the contracts with known synthetic turns; not a real-data selector."""
    levels = []
    for identity, pivot, direction, name in (
        ("L1", min(packet.bars, key=lambda b: b.low), "up", "Lower body turn"),
        ("L2", max(packet.bars, key=lambda b: b.high), "down", "Upper body turn"),
    ):
        index = packet.bars.index(pivot)
        cluster = packet.bars[max(0, index - 1) : index + 2]
        lower = min(cluster, key=lambda bar: bar.body_bottom)
        upper = max(cluster, key=lambda bar: bar.body_top)
        band = Band(
            low=lower.body_bottom,
            high=upper.body_top,
            justification="Exact outer body edges of three adjacent synthetic turning candles.",
        )
        end = next(
            b
            for b in packet.bars[index + 1 :]
            if (b.close > band.high if direction == "up" else b.close < band.low)
        )
        levels.append(
            Level(
                level_id=identity,
                price=pivot.body_bottom if direction == "up" else pivot.body_top,
                band=band,
                short_name=name,
                priority="main",
                basis="body",
                structural_purpose="An outer turning area in the fictional range.",
                current_role="Historical planning reference; future response unknown.",
                rationale="A deliberately constructed turn supplies a simple demonstrator.",
                placement_reason="The turning candle's outer body edge represents the cited cluster.",
                uncertainty="Synthetic fixture only; not a model interpretation or market result.",
                evidence=tuple(
                    Citation(
                        record_id=bar.record_id,
                        field=field,
                        value=getattr(bar, field),
                        interpretation="Exact synthetic body boundary.",
                    )
                    for bar, field in ((lower, "body_bottom"), (upper, "body_top"))
                ),
                encounters=(
                    Encounter(
                        start_bar=cluster[0].record_id,
                        end_bar=end.record_id,
                        interpretation="One continuous turning episode.",
                    ),
                ),
                reactions=(
                    Reaction(
                        start_bar=cluster[0].record_id,
                        pivot_bar=pivot.record_id,
                        end_bar=end.record_id,
                        direction=direction,
                        note="The next qualifying close departs beyond this synthetic body band.",
                    ),
                ),
                aliases=(),
            )
        )
    last = packet.bars[-1]
    reference = next(
        r
        for r in packet.references
        if r.session == last.session and r.kind == "observed_after_hours"
    )
    levels.append(
        Level(
            level_id="L3",
            price=reference.close,
            band=None,
            short_name="Close",
            priority="secondary",
            basis="session_reference",
            structural_purpose="Locate the latest closing observation within the fictional range.",
            current_role="Unresolved closing reference.",
            rationale="A recent session landmark for orientation.",
            placement_reason="Use the observed close exactly; no supported width is asserted.",
            uncertainty="No completed departure is claimed after the cutoff.",
            evidence=(
                Citation(
                    record_id=reference.record_id,
                    field="close",
                    value=reference.close,
                    interpretation="The observed evening close.",
                ),
            ),
            encounters=(
                Encounter(
                    start_bar=last.record_id,
                    end_bar=last.record_id,
                    interpretation="Final observed candle; response unresolved.",
                ),
            ),
            reactions=(),
            aliases=(
                Alias(
                    record_id=reference.record_id,
                    field="close",
                    value=reference.close,
                    label="Postmarket close",
                    relation="inside",
                ),
            ),
        )
    )
    pivot = min(packet.bars, key=lambda b: b.low)
    return Proposal(
        packet_sha256=digest(packet),
        interpretation="Fictional oscillating price history. Two body turns and a final closing reference demonstrate the pipeline. These choices are fixture construction, not automatic market-level detection.",
        author="Synthetic demo fixture",
        reference_exposure="Only generated fictional observations; no research or real-market examples.",
        levels=tuple(levels),
        deferred=(
            Deferred(
                candidate_id="D1",
                price=pivot.low,
                band=None,
                support="supported",
                reason="The outer wick is retained separately as a supported alternative to the displayed body area.",
                evidence=(
                    Citation(
                        record_id=pivot.record_id,
                        field="low",
                        value=pivot.low,
                        interpretation="Synthetic outer wick; not the body boundary.",
                    ),
                ),
            ),
        ),
    )


def demo(output: Path) -> dict:
    packet = synthetic_packet()
    proposal = synthetic_proposal(packet)
    inputs = packet_files(packet)
    inputs["manifest.json"] = json_bytes(
        {"files": {name: sha256(data) for name, data in sorted(inputs.items())}}
    )
    images, report = render(packet, proposal)
    bars, daily = synthetic_csv()
    files = {f"packet/{name}": value for name, value in inputs.items()}
    files.update({f"charts/{name}": value for name, value in images.items()})
    files.update(
        {
            "input/bars.csv": bars,
            "input/daily.csv": daily,
            "proposal.json": json_bytes(proposal),
            "charts/report.json": json_bytes(report),
        }
    )
    publish(output, files)
    return report
