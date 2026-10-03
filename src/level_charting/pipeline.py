import csv
import io
from importlib import import_module, resources
from pathlib import Path
from typing import Protocol

from .data import check_packet
from .models import Packet, Proposal
from .rendering import input_images, render
from .storage import digest, json_bytes, publish, read_model, sha256, verify_directory
from .validation import validate


class Analyzer(Protocol):
    def __call__(self, packet_directory: Path) -> Proposal:
        """Read the supplied evidence/images and return an authored proposal."""
        ...


def packet_files(packet: Packet) -> dict[str, bytes]:
    check_packet(packet)
    buffer = io.StringIO(newline="")
    fields = [
        "record_id",
        "start",
        "end",
        "session",
        "segment",
        "open",
        "high",
        "low",
        "close",
        "body_top",
        "body_bottom",
        "volume",
        "source_bars",
    ]
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(fields)
    for bar in packet.bars:
        writer.writerow([getattr(bar, key) for key in fields])
    method = resources.files("level_charting").joinpath("method.md").read_bytes()
    files = {
        "packet.json": json_bytes(packet),
        "bars.csv": buffer.getvalue().encode(),
        "session-references.json": json_bytes(
            [r.model_dump(mode="json") for r in packet.references]
        ),
        "method.md": method,
        "proposal.schema.json": json_bytes(Proposal.model_json_schema()),
        **input_images(packet),
    }
    files["work-order.json"] = json_bytes(
        {
            "method": "level-charting-v1",
            "method_sha256": sha256(method),
            "packet_sha256": digest(packet),
            "symbol": packet.symbol,
            "target_session": str(packet.target_session),
            "cutoff": packet.cutoff.isoformat(),
            "history_sessions": len(packet.sessions),
            "expected_output": "Proposal JSON",
            "instruction": "Read the method, exact records and all unmarked images. Select areas contextually. Preserve unsupported/unresolved claims as such. Do not claim final-chart inspection until you have seen the rendered output.",
        }
    )
    return files


def load_packet(directory: Path) -> Packet:
    verify_directory(directory)
    packet = read_model(Packet, directory / "packet.json")
    check_packet(packet)
    return packet


def prepare_package(packet: Packet, output: Path) -> None:
    publish(output, packet_files(packet))


def render_package(
    directory: Path, proposal_path: Path, output: Path, *, width=22
) -> dict:
    packet = load_packet(directory)
    proposal = read_model(Proposal, proposal_path)
    images, report = render(packet, proposal, width=width)
    publish(
        output,
        {
            **images,
            "report.json": json_bytes(report),
            "packet.json": json_bytes(packet),
            "proposal.json": proposal_path.read_bytes(),
            "method.md": (directory / "method.md").read_bytes(),
            "work-order.json": (directory / "work-order.json").read_bytes(),
        },
    )
    return report


def analyze(directory: Path, adapter: str, output: Path) -> dict:
    packet = load_packet(directory)
    module, separator, name = adapter.partition(":")
    if not separator or not module or not name:
        raise ValueError("Use --adapter importable_module:function")
    analyzer: Analyzer = getattr(import_module(module), name)
    if not callable(analyzer):
        raise ValueError(
            "The adapter must be a callable accepting the packet directory"
        )
    if output.exists():
        raise FileExistsError(f"Preserve the previous proposal: {output}")
    proposal = Proposal.model_validate(analyzer(directory))
    output.parent.mkdir(parents=True, exist_ok=True)
    # Keep the first authored answer even when its numerical claims fail validation.
    with output.open("xb") as handle:
        handle.write(json_bytes(proposal))
    return validate(packet, proposal)
