"""Place comments along their exact price, with measured candle clearance."""

from matplotlib.transforms import Bbox


def measure(ax, text, candles, occupied):
    renderer = ax.figure.canvas.get_renderer()
    text.update_bbox_position_size(renderer)
    box = text.get_bbox_patch().get_window_extent(renderer)
    return box, {
        "inside_plot": bool(
            ax.bbox.contains(box.x0, box.y0) and ax.bbox.contains(box.x1, box.y1)
        ),
        "candle_overlaps": int(sum(box.overlaps(other) for other in candles)),
        "label_overlaps": int(sum(box.overlaps(other) for other in occupied)),
        "bbox_pixels": [round(float(v), 3) for v in box.bounds],
    }


def verify(ax, text, candles, occupied):
    box, facts = measure(ax, text, candles, occupied)
    if not facts["inside_plot"] or facts["candle_overlaps"] or facts["label_overlaps"]:
        raise ValueError("A chart label covers a candle/label or leaves the plot")
    return box, facts


def place(ax, text, candles, occupied):
    original = text.get_window_extent(ax.figure.canvas.get_renderer())
    pad = 4.0
    width, height = original.width + 2 * pad, original.height + 2 * pad
    y = ax.transData.transform((0, text.get_position()[1]))[1]
    left, right = ax.bbox.x0 + 10, ax.bbox.x1 - width - 10
    if right <= left:
        raise ValueError("Label is too wide; shorten short_name or increase --width")
    relevant = [b for b in candles if b.y0 <= y + height / 2 and b.y1 >= y - height / 2]
    candidates = []
    steps = max(1, int((right - left) / 5))
    for i in range(steps + 1):
        x = left + (right - left) * i / steps
        box = Bbox.from_bounds(x, y - height / 2, width, height)
        if box.y0 < ax.bbox.y0 + 4 or box.y1 > ax.bbox.y1 - 4:
            continue
        if any(box.overlaps(b) for b in relevant + occupied):
            continue
        clearance = min(
            (max(b.x0 - box.x1, box.x0 - b.x1, 0) for b in relevant), default=80
        )
        score = min(clearance, 45) / 45 + 0.65 * (x - left) / max(1, right - left)
        candidates.append((score, x))
    if not candidates:
        raise ValueError(
            "No clear inline label position; shorten short_name or increase --width. Preserve prices and bands."
        )
    _, x = max(candidates)
    text.set_x(ax.transData.inverted().transform((x + pad, y))[0])
    box, facts = verify(ax, text, candles, occupied)
    occupied.append(box.padded(2))
    return facts
