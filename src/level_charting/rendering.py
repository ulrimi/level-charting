"""Unmarked model inputs and full/recent planning charts from the same data."""

import io

from matplotlib import rc_context, rcParamsDefault
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.collections import LineCollection
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle
from matplotlib.ticker import FuncFormatter, MaxNLocator
from matplotlib.transforms import Bbox

from . import labels
from .data import ET
from .models import Packet, Proposal
from .validation import validate

BG, INK, MUTED = "#101721", "#e8edf4", "#a6b3c3"
LATEST, OLDER = "#fff0a6", "#aeb7c5"


def _candles(ax, bars, volume=None, *, dark=True):
    rising, falling = ("#22ba9c", "#ee626c") if dark else ("#158473", "#ca555f")
    shades = {
        "premarket": "#192a3c" if dark else "#edf2f6",
        "after_hours": "#332b25" if dark else "#f6eee2",
    }
    wicks, colors, ticks, dates = [], [], [], []
    for i, bar in enumerate(bars):
        if i == 0 or bar.session != bars[i - 1].session:
            ticks.append(i)
            dates.append(bar.start.astimezone(ET).strftime("%b %d"))
            ax.axvline(i - 0.5, color="#8e9aac", lw=0.55, alpha=0.2)
        if shade := shades.get(bar.segment):
            ax.axvspan(i - 0.5, i + 0.5, color=shade, lw=0, zorder=0)
            if volume is not None:
                volume.axvspan(i - 0.5, i + 0.5, color=shade, lw=0, zorder=0)
        color = rising if bar.close >= bar.open else falling
        colors.append(color)
        wicks.append([(i, float(bar.low)), (i, float(bar.high))])
        ax.add_patch(
            Rectangle(
                (i - 0.31, float(bar.body_bottom)),
                0.62,
                max(0.0001, float(bar.body_top - bar.body_bottom)),
                facecolor=color,
                edgecolor=color,
                linewidth=0.25,
                zorder=3,
            )
        )
    ax.add_collection(LineCollection(wicks, colors=colors, linewidths=0.75, zorder=2))
    if volume is not None:
        volume.bar(
            range(len(bars)),
            [float(b.volume) for b in bars],
            width=0.66,
            color=colors,
            alpha=0.75,
        )
        volume.set_xticks(ticks, dates, ha="left")
    else:
        if len(ticks) == 1:
            ticks = list(range(0, len(bars), max(1, len(bars) // 8)))
            dates = [bars[i].start.astimezone(ET).strftime("%H:%M") for i in ticks]
        ax.set_xticks(ticks, dates, ha="left")


def _png(fig):
    output = io.BytesIO()
    fig.savefig(output, dpi=fig.dpi, facecolor=fig.get_facecolor())
    return output.getvalue()


def input_images(packet: Packet) -> dict[str, bytes]:
    views = [("overview.png", packet.sessions), ("recent.png", packet.sessions[-5:])]
    views += [(f"day-{day}.png", (day,)) for day in packet.sessions[-3:]]
    result = {}
    with rc_context(rcParamsDefault):
        for name, days in views:
            bars = tuple(b for b in packet.bars if b.session in days)
            fig = Figure(figsize=(15, 5.6), dpi=140)
            FigureCanvasAgg(fig)
            try:
                ax = fig.add_subplot()
                _candles(ax, bars, dark=False)
                lo, hi = (
                    min(float(b.low) for b in bars),
                    max(float(b.high) for b in bars),
                )
                margin = max((hi - lo) * 0.055, 0.01)
                ax.set_ylim(lo - margin, hi + margin)
                ax.set_xlim(-1, len(bars) + 1)
                ax.set_title(
                    f"{packet.symbol} | {days[0]}–{days[-1]} | 30-minute candles | through {packet.cutoff.astimezone(ET):%b %d %H:%M} ET",
                    loc="left",
                    fontsize=12,
                )
                ax.set_ylabel("Underlying price")
                ax.spines[["top", "right"]].set_visible(False)
                ax.grid(axis="y", alpha=0.14)
                fig.text(
                    0.055,
                    0.015,
                    "ET bar starts; pale blue = premarket, beige = after-hours. Observed buckets only; gaps compressed. No selected levels.",
                    fontsize=8,
                )
                fig.subplots_adjust(left=0.06, right=0.98, bottom=0.14, top=0.91)
                result[name] = _png(fig)
            finally:
                fig.clear()
    return result


def _cards(fig, packet):
    day = packet.sessions[-1]
    refs = {r.kind: r for r in packet.references if r.session == day}
    cards = (
        ("Previous day · provider daily", "provider_daily"),
        ("Premarket · observed", "observed_premarket"),
        ("Postmarket · observed", "observed_after_hours"),
    )
    for i, (title, kind) in enumerate(cards):
        left = 0.045 + i * 0.308
        fig.add_artist(
            Rectangle(
                (left, 0.820),
                0.294,
                0.081,
                transform=fig.transFigure,
                facecolor="#18222e",
                edgecolor="#34414f",
                lw=0.6,
            )
        )
        fig.text(
            left + 0.009,
            0.883,
            f"{title} / {day:%b %d}",
            color=LATEST,
            fontsize=11,
            weight="bold",
        )
        ref = refs.get(kind)
        if ref is None:
            fig.text(left + 0.009, 0.850, "Not supplied", color=MUTED, fontsize=11)
            continue
        values = [
            format(getattr(ref, field), ".4f").rstrip("0").rstrip(".")
            for field in ("open", "high", "low", "close")
        ]
        fig.text(
            left + 0.009,
            0.858,
            f"Open {values[0]}    High {values[1]}",
            color=INK,
            fontsize=11,
        )
        fig.text(
            left + 0.009,
            0.834,
            f"Low   {values[2]}    Close {values[3]}",
            color=INK,
            fontsize=11,
        )


def _inline(ax, bars, levels, summaries):
    candles = []
    for i, bar in enumerate(bars):
        (x0, y0), (x1, y1) = ax.transData.transform(
            [(i - 0.35, float(bar.low)), (i + 0.35, float(bar.high))]
        )
        candles.append(Bbox.from_extents(x0 - 5, y0 - 7, x1 + 5, y1 + 7))
    placed, occupied = [], []
    for level in sorted(levels, key=lambda level: level.price, reverse=True):
        info = summaries[level.level_id]
        text = ax.text(
            0,
            float(level.price),
            f"{level.price:.2f}  ·  {level.short_name}  ·  {info['reactions']}R / {len(info['pivot_dates'])}D",
            color=LATEST if info["latest"] else OLDER,
            fontsize=11,
            fontweight="bold" if level.priority == "main" else "normal",
            va="center",
            ha="left",
            zorder=7,
            bbox={"facecolor": BG, "edgecolor": "none", "pad": 1.6, "alpha": 0.96},
        )
        labels.place(ax, text, candles, occupied)
        placed.append((level, text))
    ax.figure.canvas.draw()
    result = []
    for i, (level, text) in enumerate(placed):
        _, measured = labels.verify(ax, text, candles, occupied[:i] + occupied[i + 1 :])
        result.append(
            {
                "level_id": level.level_id,
                "price": str(level.price),
                "text": text.get_text(),
                **measured,
            }
        )
    return result


def _map(packet, proposal, report, view, width):
    days = packet.sessions[-3:] if view == "recent" else packet.sessions
    bars = tuple(b for b in packet.bars if b.session in days)
    observed_low, observed_high = min(b.low for b in bars), max(b.high for b in bars)
    selected = tuple(
        level
        for level in proposal.levels
        if view == "full" or observed_low <= level.price <= observed_high
    )
    lo, hi = float(observed_low), float(observed_high)
    if view == "full":
        lo = min(
            [lo]
            + [
                float(level.band.low if level.band else level.price)
                for level in selected
            ]
        )
        hi = max(
            [hi]
            + [
                float(level.band.high if level.band else level.price)
                for level in selected
            ]
        )
    margin = max((hi - lo) * 0.09, 0.01)
    fig = Figure(figsize=(width, 11), dpi=150, facecolor=BG)
    FigureCanvasAgg(fig)
    try:
        ax = fig.add_axes([0.045, 0.255, 0.91, 0.54])
        vol = fig.add_axes([0.045, 0.135, 0.91, 0.10], sharex=ax)
        for axis in (ax, vol):
            axis.set_facecolor(BG)
            axis.tick_params(colors=MUTED, labelsize=9)
            axis.spines[["top", "left"]].set_visible(False)
            for spine in axis.spines.values():
                spine.set_color("#34414f")
            axis.yaxis.tick_right()
            axis.grid(axis="y", color="#778698", alpha=0.12)
        _candles(ax, bars, vol)
        for level in selected:
            color = LATEST if report["levels"][level.level_id]["latest"] else OLDER
            if level.band:
                ax.axhspan(
                    float(level.band.low),
                    float(level.band.high),
                    color=color,
                    alpha=0.145 if color == LATEST else 0.12,
                    zorder=1,
                )
            ax.axhline(
                float(level.price),
                color=color,
                lw=1.15 if level.priority == "main" else 0.7,
                zorder=4,
            )
        ax.set_ylim(lo - margin, hi + margin)
        ax.set_xlim(-1, len(bars) + 1)
        ax.yaxis.set_major_locator(MaxNLocator(nbins=10))
        ax.tick_params(axis="x", labelbottom=False)
        vol.yaxis.set_major_formatter(FuncFormatter(lambda n, _: f"{n / 1e6:.1f}M"))
        vol.yaxis.set_major_locator(MaxNLocator(nbins=3))
        vol.text(
            0, 1.05, "CANDLE VOLUME", transform=vol.transAxes, color=MUTED, fontsize=9
        )
        title = "Recent detail" if view == "recent" else f"{len(days)}-session map"
        fig.text(
            0.045,
            0.956,
            f"{packet.symbol} / {title} / {days[0]:%b %d}–{days[-1]:%b %d}",
            color=INK,
            fontsize=23,
            weight="bold",
        )
        fig.text(
            0.045,
            0.924,
            f"Prepared for {packet.target_session} | Through {packet.cutoff.astimezone(ET):%b %d, %Y %H:%M} ET | Last {packet.bars[-1].close:.2f} | 30-minute planning references",
            color=MUTED,
            fontsize=11,
        )
        _cards(fig, packet)
        fig.text(
            0.045,
            0.088,
            f"Yellow: {packet.sessions[-1]:%b %d} references / reviewed responses     Gray: older structure     Bold: Main",
            color=LATEST,
            fontsize=10.5,
        )
        fig.text(
            0.045,
            0.063,
            "R = curated reactions · D = distinct pivot dates · Counts use the full packet, including initial turns; not total touches or strength.",
            color=MUTED,
            fontsize=10,
        )
        fig.text(
            0.045,
            0.038,
            f"Provisional areas · Human review pending · {len(packet.coverage.missing_buckets)} missing half-hour buckets · {len(proposal.levels) - len(selected)} selected areas outside this view",
            color=MUTED,
            fontsize=9,
        )
        fig.canvas.draw()
        measured = _inline(ax, bars, selected, report["levels"])
        facts = {
            "view": view,
            "sessions": [str(d) for d in days],
            "bar_count": len(bars),
            "displayed": [x.level_id for x in selected],
            "off_view": [x.level_id for x in proposal.levels if x not in selected],
            "labels": measured,
            "pixel_dimensions": list(fig.canvas.get_width_height()),
        }
        return _png(fig), facts
    finally:
        fig.clear()


def render(
    packet: Packet, proposal: Proposal, *, width: float = 22
) -> tuple[dict[str, bytes], dict]:
    if not 12 <= width <= 40:
        raise ValueError("Choose a chart width between 12 and 40 inches")
    report = validate(packet, proposal)
    if not proposal.levels:
        raise ValueError(
            "No supported map was selected; retain the proposal and its explanation"
        )
    files, charts = {}, []
    with rc_context(rcParamsDefault):
        for view, filename in (("full", "map.png"), ("recent", "recent-map.png")):
            files[filename], facts = _map(packet, proposal, report, view, width)
            charts.append(facts)
    return files, {**report, "layout_validation": "passed", "charts": charts}
