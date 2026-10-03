# Price area charting method

Prepare a readable map of historical areas for a person monitoring price. The analyst
or language model selects the areas; deterministic code prepares evidence, validates
claims and renders the result. These maps do not define entries, position sizes or
trade execution.

Read `work-order.json`, `packet.json`, `bars.csv`, `session-references.json`, the
unmarked overview, recent detail and individual-day images. Use `proposal.schema.json`
for the output contract. The packet normally contains ten completed exchange sessions
of 30-minute candles with extended hours. Its explicit history and cutoff govern this
run. Missing buckets remain absent. Daily provider OHLC and observed session OHLC have
different definitions; never substitute the final regular-session bar for a supplied
provider daily close. The packet states its price basis and availability limitations.

Inspect the whole chart before choosing lines. Discover places where price stopped,
struggled, reversed, returned after separation, or changed support/resistance role.
Consider dominant range boundaries, important session references, prominent extremes
and meaningful internal structure. A continuous balance can be a single encounter
despite containing many candles. Do not limit discovery to a mechanical pivot list.

Prefer coherent body boundaries when supported. Wicks provide rejection evidence;
a significant outer extreme may deserve its own reference. Explain alternate placement
when a coherent body boundary is unavailable. A representative price summarizes an
interpreted area; exact cited OHLC values remain separate evidence. Justify both band
bounds with the candle history, or leave `band` null. Do not apply uniform padding.

After broad discovery, select areas with distinct structural and planning purposes.
For each displayed area, explain what meaningful structure would be lost if omitted.
Keep credible smaller alternatives with evidence and omission reasons in `deferred`.
Supported but omitted does not mean invalid. Review former ceilings that became floors
and other meaningful omissions before finalizing. Preserve useful nearby distinctions;
do not widen unrelated areas together merely to reduce clutter. Do not fill every gap.
There is no fixed line quota, minimum spacing, required touch count, automatic strength
score or automatic age/distance filter. Main/secondary expresses contextual priority.

Record chronological encounters, including failures, crossings and contrary behavior.
Historical significance and the latest observed role are different claims. A wick
outside a band is not a body boundary or an in-band retest. A crossing need not erase
an older area. Observable price behavior does not establish participant identity,
intent or remaining orders. Ordinary candle volume is available; volume-at-price,
volume weighting, dwell/TPO qualification and options context are outside this method.

All evidence must exist in this packet by its cutoff. If older context or a missing
reference is needed, state a specific `data_requests` item. A human can prepare a new
packet with additional completed sessions and rerun the interpretation. Do not invent
data, use later observations, or treat a historical replay as originally published
real-time information. Preserve the evening map when subsequently developing a morning
or intraday extension; this starter implements completed-session evening maps.

Return a Proposal JSON object, with the exact packet hash from `work-order.json`.
Prices may be decimal strings to preserve all digits. Every selected level needs its
price, optional justified band, compact label, priority, basis, distinct purpose,
current role, rationale, placement reason, uncertainty, exact citations and chronological
encounters. Citations identify `record_id`, `field`, `value` and interpretation. Body
fields belong to candles; session references expose open/high/low/close. Supported
deferred areas require exact evidence; unresolved alternatives must not claim a band.
An empty selected set is valid when no map is supported; explain it honestly.

Curate reactions explicitly rather than counting all touches. Each reaction identifies
start, pivot and response-end candles, direction and a note. The pivot range must
intersect the proposed band or bandless line; the response-end close must depart beyond
the boundary in the stated direction. Use separated chronological episodes with no
overlap within an area. Initial turns and modest responses can count. One event may
inform multiple areas, but their counts are not independent confirmations.

Session aliases cite exact supplied reference values. An `inside` alias must fall
inside the band or equal a bandless line exactly. An `outside_wick` alias must identify
an explicitly cited high/low of that same session reference outside a supported band.
Do not turn aliases for the same event into additional reactions. Every selected area
needs a reviewed reaction or dated alias for recency; zero reactions is valid when an
alias supplies the date. Code derives R as curated episodes and D as distinct pivot
dates. These counts are not probabilities, performance or automatic strength.

The renderer shows shaded bands and compact comments at the exact line price, in open
chart space. Main references are bold. Light yellow means an alias or reviewed response
in the latest completed session; gray means older structure. Recency and priority are
independent. Full and recent charts use the same selected geometry; recent detail may
crop out distant areas. All counts use the full packet. Ordinary candle volume remains
visible. Source dates and full reasoning stay in the JSON ledger.

Before delivery, validate citations and inspect both rendered charts. Separately review
the prose for open/close and body/wick confusion, claimed band contacts, whether price
held or merely touched, current-role claims, duplicated encounters, clutter and missing
structure. Numerical/layout validation does not perform that semantic review. Shorten
labels or widen the canvas when needed; never move prices or pad bands to fit text.
Save the first proposal and charts, record human feedback, and version later changes.
State the actual author/model identity when known and disclose reference exposure.
