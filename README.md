# level-charting

A small Python starter for drawing evidence-backed price-area maps. A human or language
model interprets the chart and selects areas; code prepares the data, verifies numerical
claims and renders full/recent charts with shaded zones and inline labels.

The default is ten completed US equity sessions, 30-minute candles, extended hours and
an explicit evening cutoff. Selection is contextual: coherent body boundaries, wick
rejections, role changes and meaningful extremes. There is no fixed line quota, touch
threshold or automatic strength score. The executable [method prompt](src/level_charting/method.md)
contains the complete selection and presentation instructions.

## Try it

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```sh
git clone https://github.com/ulrimi/level-charting.git
cd level-charting
uv sync --locked
uv run level-charting demo --out output/demo
```

Open `output/demo/charts/map.png` and `recent-map.png`. The demo generates fictional
prices, an example proposal and the full evidence packet locally. It needs no account,
API key or model call. Its fixture selections are for demonstrating the contracts.

## Data sources

`prepare` reads local CSV files. Market-data acquisition is a separate step; this
repository does not download prices or load provider credentials.

| Source | Role | Included here |
| --- | --- | --- |
| Synthetic demo | Fictional observations for testing the complete workflow | Generator and example proposal |
| Massive (formerly Polygon.io) | Historical stock bars and separately captured daily OHLC | CSV ingestion only; no Massive API client or downloader |
| Schwab | An optional source for a separately implemented data exporter | No Schwab interface, OAuth flow, token storage/refresh, streaming or trading integration |

[Massive is the renamed Polygon.io](https://www.massive.com/blog/polygon-is-now-massive).
To prepare compatible exports, use its
[custom bars endpoint](https://massive.com/docs/rest/stocks/aggregates/custom-bars)
for one-minute or 30-minute OHLCV, including extended hours. Convert the `t` bar-start
timestamp from Unix milliseconds to an offset-aware ISO timestamp, and map
`o,h,l,c,v` to `open,high,low,close,volume`. Retrieve all pages for the requested window;
leave absent bars absent. Choose the split-adjustment setting explicitly and keep it
consistent across intraday and daily inputs.

For the optional daily CSV, obtain `open,high,low,close` separately from Massive's
[daily ticker summary](https://massive.com/docs/rest/stocks/aggregates/daily-ticker-summary),
using its `from` date. Its `preMarket` and `afterHours` prices are not session high/low
ranges; this starter derives extended-session OHLC from the intraday observations.
Access and available history depend on your provider account. Keep acquisition code
and credentials under your own control, then supply the CSVs described below.

Record provenance with `--source "Massive historical CSV export"` and an accurate
`--price-basis`. These flags label the supplied data; they do not fetch it. A future
Schwab exporter can target the same CSV contract. The `analyze --adapter` hook below
is for model authoring and does not provide a market-data connection.

## Use your data

Export one-minute or 30-minute bars to CSV. Timestamps are **bar starts** with an explicit
UTC offset. Include extended hours; absent buckets are recorded, never filled. Supply
at least some observations for every requested session. Keep prices on one consistent
share/adjustment basis; this starter does not reconcile splits or provider corrections.

```csv
timestamp,open,high,low,close,volume
2025-01-03T04:00:00-05:00,100.00,100.20,99.90,100.10,1200
```

Optional provider daily CSV uses `date,open,high,low,close`. It remains distinct from
OHLC reconstructed from the intraday export; missing daily references display as
unavailable. These CSVs are historical replay inputs, not verified live captures.

```sh
uv run level-charting prepare \
  --bars data/bars.csv --daily data/daily.csv --symbol EXAMPLE \
  --target 2025-01-21 --cutoff 2025-01-17T20:00:00-05:00 \
  --input-minutes 1 --price-basis unadjusted \
  --out output/packet-v1
```

Replace the symbol and dates with your export. `--daily` is optional. Use
`--input-minutes 30` for existing half-hour bars. `--sessions 20` expands the completed
history when justified. The XNYS calendar handles holidays, DST and early closes; the
cutoff is 20:00 New York time on the session immediately before the target.

Give your chosen model or analyst the packet's `method.md`, `work-order.json`, exact
records, all unmarked images and `proposal.schema.json`. Have them return a proposal
using the packet hash in the work order. The demo's `proposal.json` illustrates the
format. Use decimal strings for prices when possible. Selected areas require exact
citations; bands need their own justification; supported alternatives stay in `deferred`.

```sh
uv run level-charting validate output/packet-v1 output/proposal-v1.json
uv run level-charting render output/packet-v1 output/proposal-v1.json \
  --out output/map-v1
```

Inspect both PNGs and the reasoning before relying on a map. Validation checks numbers,
cutoffs, reaction geometry and label placement; it does not judge omissions or prove
that an interpretation is useful. R/D counts are curated reactions and distinct pivot
dates, not total touches, probabilities or strength. Charts are planning references.

Output includes the submitted proposal, packet, method, validation/layout report and
file hashes. Commands refuse to overwrite output. Keep feedback separately and use new
paths for revisions. If a label cannot fit, shorten `short_name` or increase
`render --width 28`; prices and bands are never adjusted for typography.

## Adapt it

| Module | Responsibility |
| --- | --- |
| `models.py` | Provider-neutral packet, proposal, evidence and zone contracts |
| `data.py` | CSV normalization, exchange windows, half-hour aggregation and session references |
| `method.md` | Contextual area-selection instructions for the analyst/model |
| `validation.py` | Exact evidence, chronology, band membership and curated reactions |
| `rendering.py`, `labels.py` | Unmarked inputs, full/recent charts and measured inline labels |
| `pipeline.py`, `cli.py` | File packages, integrity checks and a replaceable model adapter |

Start by adapting CSV exports, the method prompt or chart styling. No provider/model
SDK, database, broker login or hosting service is required. To automate authoring,
implement an importable Python callable with the `Analyzer` contract:

```python
from pathlib import Path
from level_charting.models import Proposal


def analyze(packet_directory: Path) -> Proposal:
    # Read the packet and images, call your chosen model, and parse its response.
    ...
```

Run `uv run level-charting analyze output/packet-v1 --adapter your_package:analyze
--out output/proposal-v1.json` on one line. Your adapter owns authentication, model/effort
selection and transport; declare those in the proposal. The first parsed proposal is
saved even if numerical validation then fails. Rendering and human review follow as
separate steps. Additional data requests require a newly prepared packet.

```sh
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

MIT licensed. Only fictional examples are included. Keep your exports and generated
maps under the ignored `data/` and `output/` directories.
