from decimal import Decimal

import pytest
from pydantic import ValidationError

from level_charting.models import Alias, Band, Citation, Proposal
from level_charting.validation import validate


def replace_level(proposal, level, index=0):
    items = list(proposal.levels)
    items[index] = level
    return proposal.model_copy(update={"levels": tuple(items)})


def test_demo_records_scope_and_zero_reaction_alias(packet, proposal):
    report = validate(packet, proposal)
    assert report["numeric_validation"] == "passed"
    assert report["human_review"] == "pending"
    assert report["levels"]["L3"]["reactions"] == 0
    assert report["levels"]["L3"]["latest"]


def test_exact_citation_not_rounded_tolerance(packet, proposal):
    level = proposal.levels[0]
    citation = level.evidence[0].model_copy(
        update={"value": level.evidence[0].value + Decimal("0.0000001")}
    )
    changed = replace_level(
        proposal, level.model_copy(update={"evidence": (citation,)})
    )
    with pytest.raises(ValueError, match="Exact citation"):
        validate(packet, changed)


def test_packet_identity_is_required(packet, proposal):
    with pytest.raises(ValueError, match="different packet"):
        validate(packet, proposal.model_copy(update={"packet_sha256": "a" * 64}))


def test_shape_disallows_padding_without_enclosed_price(proposal):
    original = proposal.model_dump()
    original["levels"][0]["band"] = dict(low="1", high="2", justification="Wrong range")
    with pytest.raises(ValidationError, match="inside"):
        Proposal.model_validate(original)
    with pytest.raises(ValidationError, match="ordered"):
        Band(low="100", high="100", justification="No actual width")


def test_reaction_needs_departure_and_nonoverlap(packet, proposal):
    level = proposal.levels[0]
    opposite = level.reactions[0].model_copy(update={"direction": "down"})
    with pytest.raises(ValueError, match="depart"):
        validate(
            packet,
            replace_level(
                proposal, level.model_copy(update={"reactions": (opposite,)})
            ),
        )
    with pytest.raises(ValueError, match="overlap"):
        validate(
            packet,
            replace_level(
                proposal, level.model_copy(update={"reactions": level.reactions * 2})
            ),
        )


def test_wick_alias_requires_the_same_session_record_citation(packet, proposal):
    level = proposal.levels[0]
    pivot = next(b for b in packet.bars if b.record_id == level.reactions[0].pivot_bar)
    ref = next(
        r
        for r in packet.references
        if r.session == pivot.session and r.kind == f"observed_{pivot.segment}"
    )
    alias = Alias(
        record_id=ref.record_id,
        field="low",
        value=ref.low,
        label="Session wick",
        relation="outside_wick",
    )
    changed = level.model_copy(update={"aliases": (alias,)})
    with pytest.raises(ValueError, match="exact cited session"):
        validate(packet, replace_level(proposal, changed))
    citation = Citation(
        record_id=ref.record_id,
        field="low",
        value=ref.low,
        interpretation="Outside supporting wick, distinct from the body band.",
    )
    changed = changed.model_copy(update={"evidence": (*level.evidence, citation)})
    assert (
        validate(packet, replace_level(proposal, changed))["numeric_validation"]
        == "passed"
    )


def test_duplicate_ids_and_missing_recency_fail(packet, proposal):
    with pytest.raises(ValueError, match="unique"):
        validate(packet, proposal.model_copy(update={"levels": proposal.levels * 2}))
    level = proposal.levels[0].model_copy(update={"reactions": (), "aliases": ()})
    with pytest.raises(ValueError, match="Recency"):
        validate(packet, replace_level(proposal, level))


def test_no_ten_line_cap_or_minimum_reaction_gate(packet, proposal):
    levels = tuple(
        proposal.levels[2].model_copy(update={"level_id": f"L{i}"}) for i in range(12)
    )
    report = validate(packet, proposal.model_copy(update={"levels": levels}))
    assert report["selected"] == 12
    assert all(item["reactions"] == 0 for item in report["levels"].values())
