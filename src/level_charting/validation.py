"""Verify claimed facts; never select or score the chart's areas."""

from .data import ET, check_packet
from .models import Candle, Level, Packet, Proposal, Reference
from .storage import digest


def bounds(level: Level):
    return (
        (level.band.low, level.band.high) if level.band else (level.price, level.price)
    )


def validate(packet: Packet, proposal: Proposal) -> dict:
    check_packet(packet)
    if proposal.packet_sha256 != digest(packet):
        raise ValueError("Proposal was authored against a different packet")
    records = {r.record_id: r for r in (*packet.bars, *packet.references)}
    ids = [level.level_id for level in proposal.levels] + [
        c.candidate_id for c in proposal.deferred
    ]
    if len(ids) != len(set(ids)):
        raise ValueError("Selected and deferred IDs must be unique")

    def resolve(identity, kind=None):
        record = records.get(identity)
        if record is None or (kind is not None and not isinstance(record, kind)):
            raise ValueError(
                f"Unknown or incorrectly typed evidence record: {identity}"
            )
        return record

    claims = 0
    for area in (*proposal.levels, *proposal.deferred):
        for citation in area.evidence:
            record = resolve(citation.record_id)
            if isinstance(record, Reference) and citation.field.startswith("body_"):
                raise ValueError(
                    "Session references expose OHLC; cite a candle for body edges"
                )
            if getattr(record, citation.field) != citation.value:
                raise ValueError(
                    f"Exact citation mismatch: {citation.record_id}.{citation.field}"
                )
            claims += 1

    summaries = {}
    for level in proposal.levels:
        low, high = bounds(level)
        dates, pivots, previous_end = [], set(), None
        encounter_start = None
        for encounter in level.encounters:
            start, end = (
                resolve(x, Candle) for x in (encounter.start_bar, encounter.end_bar)
            )
            if start.start > end.start or (
                encounter_start and start.start < encounter_start
            ):
                raise ValueError(f"Encounter order is invalid: {level.level_id}")
            encounter_start = start.start
        for reaction in level.reactions:
            start, pivot, end = (
                resolve(x, Candle)
                for x in (reaction.start_bar, reaction.pivot_bar, reaction.end_bar)
            )
            if not start.start <= pivot.start <= end.start:
                raise ValueError(f"Reaction order is invalid: {level.level_id}")
            if previous_end and start.start < previous_end:
                raise ValueError(f"Reaction episodes overlap: {level.level_id}")
            if pivot.low > high or pivot.high < low:
                raise ValueError(
                    f"Reaction pivot never contacted the area: {level.level_id}"
                )
            if (reaction.direction == "up" and end.close <= high) or (
                reaction.direction == "down" and end.close >= low
            ):
                raise ValueError(
                    f"Reaction endpoint does not depart beyond the band: {level.level_id}"
                )
            previous_end = end.end
            dates.append(end.end.astimezone(ET).date())
            pivots.add(pivot.session)
        seen_aliases = set()
        evidence = {(c.record_id, c.field, c.value) for c in level.evidence}
        for alias in level.aliases:
            record = resolve(alias.record_id, Reference)
            key = (alias.record_id, alias.field)
            if key in seen_aliases or getattr(record, alias.field) != alias.value:
                raise ValueError(
                    f"Duplicate or incorrect session alias: {level.level_id}"
                )
            seen_aliases.add(key)
            inside = low <= alias.value <= high
            if alias.relation == "inside" and not inside:
                raise ValueError(
                    f"Session alias is outside the submitted band: {level.level_id}"
                )
            if alias.relation == "outside_wick" and (
                inside
                or level.band is None
                or alias.field not in ("high", "low")
                or (alias.record_id, alias.field, alias.value) not in evidence
            ):
                raise ValueError(
                    f"Outside wick needs its own exact cited session evidence: {level.level_id}"
                )
            dates.append(record.session)
        if not dates:
            raise ValueError(
                f"Recency needs a reviewed response or session alias: {level.level_id}"
            )
        summaries[level.level_id] = {
            "reactions": len(level.reactions),
            "pivot_dates": sorted(str(d) for d in pivots),
            "recency_date": str(max(dates)),
            "latest": max(dates) == packet.sessions[-1],
        }
    return {
        "packet_sha256": digest(packet),
        "proposal_sha256": digest(proposal),
        "numeric_validation": "passed",
        "human_review": "pending",
        "semantic_review": "Requires review of reasoning, omissions, band placement and final charts",
        "selected": len(proposal.levels),
        "deferred": len(proposal.deferred),
        "citations": claims,
        "levels": summaries,
        "count_policy": "Curated episodes and distinct pivot dates; not exhaustive touches, strength or probabilities",
    }
