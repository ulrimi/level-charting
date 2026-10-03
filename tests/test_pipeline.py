import io
import json
import sys
from types import SimpleNamespace

import pytest
from PIL import Image

from level_charting.pipeline import (
    analyze,
    load_packet,
    prepare_package,
    render_package,
)
from level_charting.rendering import render
from level_charting.storage import digest, json_bytes


def test_rendered_geometry_and_inline_clearance(packet, proposal):
    before = digest(proposal)
    files, report = render(packet, proposal)
    assert digest(proposal) == before
    assert set(files) == {"map.png", "recent-map.png"}
    assert len(report["charts"][0]["sessions"]) == 10
    assert len(report["charts"][1]["sessions"]) == 3
    prices = {level.level_id: str(level.price) for level in proposal.levels}
    for chart in report["charts"]:
        for label in chart["labels"]:
            assert label["price"] == prices[label["level_id"]]
            assert label["inside_plot"]
            assert label["candle_overlaps"] == label["label_overlaps"] == 0
    for data in files.values():
        assert Image.open(io.BytesIO(data)).size == (3300, 1650)


def test_packet_tampering_and_output_preservation(tmp_path, packet, proposal):
    directory = tmp_path / "packet"
    prepare_package(packet, directory)
    assert load_packet(directory) == packet
    assert json.loads((directory / "work-order.json").read_bytes())[
        "packet_sha256"
    ] == digest(packet)
    with pytest.raises(FileExistsError):
        prepare_package(packet, directory)
    first = (directory / "packet.json").read_bytes()
    (directory / "bars.csv").write_text("changed")
    with pytest.raises(ValueError, match="changed"):
        load_packet(directory)
    assert (directory / "packet.json").read_bytes() == first


def test_complete_package_round_trip(tmp_path, packet, proposal):
    directory = tmp_path / "packet"
    prepare_package(packet, directory)
    source = tmp_path / "proposal.json"
    source.write_bytes(json_bytes(proposal))
    destination = tmp_path / "rendered"
    report = render_package(directory, source, destination)
    assert report["layout_validation"] == "passed"
    assert (destination / "proposal.json").read_bytes() == source.read_bytes()
    assert (destination / "manifest.json").is_file()
    with pytest.raises(FileExistsError):
        render_package(directory, source, destination)


def test_adapter_preserves_first_invalid_numeric_submission(
    tmp_path, monkeypatch, packet, proposal
):
    directory = tmp_path / "packet"
    prepare_package(packet, directory)
    bad = proposal.model_copy(update={"packet_sha256": "b" * 64})
    monkeypatch.setitem(
        sys.modules, "test_adapter", SimpleNamespace(analyze=lambda _: bad)
    )
    output = tmp_path / "proposal.json"
    with pytest.raises(ValueError, match="different packet"):
        analyze(directory, "test_adapter:analyze", output)
    assert output.read_bytes() == json_bytes(bad)
    with pytest.raises(FileExistsError):
        analyze(directory, "test_adapter:analyze", output)
