"""Small public contracts, independent of data providers and model SDKs."""

from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

Price = Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]
Text = Annotated[str, Field(min_length=1)]
PriceField = Literal["open", "high", "low", "close", "body_top", "body_bottom"]


class Value(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class OHLC(Value):
    open: Price
    high: Price
    low: Price
    close: Price

    @model_validator(mode="after")
    def valid_range(self):
        if (
            not self.low
            <= min(self.open, self.close)
            <= max(self.open, self.close)
            <= self.high
        ):
            raise ValueError("OHLC prices contradict the candle range")
        return self

    @property
    def body_top(self) -> Decimal:
        return max(self.open, self.close)

    @property
    def body_bottom(self) -> Decimal:
        return min(self.open, self.close)


class Candle(OHLC):
    record_id: Text
    start: AwareDatetime
    end: AwareDatetime
    session: date
    segment: Literal["premarket", "regular", "after_hours"]
    volume: Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]
    source_bars: Annotated[int, Field(ge=1, le=30)]

    @model_validator(mode="after")
    def half_hour(self):
        if self.end - self.start != timedelta(minutes=30):
            raise ValueError("Chart candles must span exactly 30 minutes")
        return self


class Reference(OHLC):
    record_id: Text
    session: date
    kind: Literal[
        "provider_daily",
        "observed_premarket",
        "observed_regular",
        "observed_after_hours",
    ]
    known_at: AwareDatetime


class Coverage(Value):
    expected_buckets: int
    observed_buckets: int
    missing_buckets: tuple[AwareDatetime, ...]
    input_minutes: Literal[1, 30]


class Packet(Value):
    schema_version: Literal["1"] = "1"
    symbol: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,15}$")]
    target_session: date
    cutoff: AwareDatetime
    sessions: Annotated[tuple[date, ...], Field(min_length=1)]
    price_basis: Text
    source: Text
    availability_note: Text
    input_hashes: dict[str, str]
    bars: Annotated[tuple[Candle, ...], Field(min_length=1)]
    references: tuple[Reference, ...]
    coverage: Coverage


class Citation(Value):
    record_id: Text
    field: PriceField
    value: Price
    interpretation: Text


class Band(Value):
    low: Price
    high: Price
    justification: Text

    @model_validator(mode="after")
    def ordered(self):
        if self.low >= self.high:
            raise ValueError("A band needs distinct, ordered bounds")
        return self


class Encounter(Value):
    start_bar: Text
    end_bar: Text
    interpretation: Text


class Reaction(Value):
    start_bar: Text
    pivot_bar: Text
    end_bar: Text
    direction: Literal["up", "down"]
    note: Text


class Alias(Value):
    record_id: Text
    field: Literal["open", "high", "low", "close"]
    value: Price
    label: Text
    relation: Literal["inside", "outside_wick"]


class Level(Value):
    level_id: Text
    price: Price
    band: Band | None
    short_name: Annotated[str, Field(min_length=1, max_length=80)]
    priority: Literal["main", "secondary"]
    basis: Literal["body", "wick", "mixed", "session_reference"]
    structural_purpose: Text
    current_role: Text
    rationale: Text
    placement_reason: Text
    uncertainty: Text
    evidence: Annotated[tuple[Citation, ...], Field(min_length=1)]
    encounters: Annotated[tuple[Encounter, ...], Field(min_length=1)]
    reactions: tuple[Reaction, ...]
    aliases: tuple[Alias, ...]

    @model_validator(mode="after")
    def supported_geometry(self):
        if self.band and not self.band.low <= self.price <= self.band.high:
            raise ValueError("Representative price must lie inside its band")
        return self


class Deferred(Value):
    candidate_id: Text
    price: Price | None = None
    band: Band | None = None
    support: Literal["supported", "unresolved"]
    reason: Text
    evidence: tuple[Citation, ...]

    @model_validator(mode="after")
    def geometry(self):
        if self.support == "supported" and not self.evidence:
            raise ValueError("Supported alternatives need exact evidence")
        if self.band and (
            self.support != "supported"
            or self.price is None
            or not self.band.low <= self.price <= self.band.high
        ):
            raise ValueError(
                "Deferred bounds require supported evidence and an enclosed price"
            )
        return self


class Proposal(Value):
    schema_version: Literal["1"] = "1"
    packet_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    interpretation: Text
    author: Text
    model: str | None = None
    reasoning_effort: str | None = None
    reference_exposure: Text
    levels: tuple[Level, ...]
    deferred: tuple[Deferred, ...]
    data_requests: tuple[str, ...] = ()
