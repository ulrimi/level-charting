import argparse
import json
from datetime import date, datetime
from pathlib import Path

from .data import prepare
from .demo import demo
from .models import Proposal
from .pipeline import analyze, load_packet, prepare_package, render_package
from .storage import read_model
from .validation import validate


def parser():
    root = argparse.ArgumentParser(
        description="Prepare evidence and draw contextual price-area maps."
    )
    commands = root.add_subparsers(dest="command", required=True)
    example = commands.add_parser(
        "demo", help="Draw a fictional example without credentials"
    )
    example.add_argument("--out", type=Path, required=True)
    prep = commands.add_parser(
        "prepare", help="Build a cutoff-bounded packet from your CSV exports"
    )
    prep.add_argument("--bars", type=Path, required=True)
    prep.add_argument("--daily", type=Path)
    prep.add_argument("--symbol", required=True)
    prep.add_argument("--target", type=date.fromisoformat, required=True)
    prep.add_argument("--cutoff", type=datetime.fromisoformat, required=True)
    prep.add_argument("--sessions", type=int, default=10)
    prep.add_argument("--input-minutes", type=int, choices=(1, 30), default=1)
    prep.add_argument(
        "--price-basis", default="User-supplied prices; adjustment basis unspecified"
    )
    prep.add_argument("--source", default="User-supplied CSV")
    prep.add_argument("--out", type=Path, required=True)
    for name in ("validate", "render"):
        command = commands.add_parser(
            name, help=f"{name.capitalize()} an authored proposal against its packet"
        )
        command.add_argument("packet", type=Path)
        command.add_argument("proposal", type=Path)
        if name == "render":
            command.add_argument("--out", type=Path, required=True)
            command.add_argument("--width", type=float, default=22)
    author = commands.add_parser(
        "analyze", help="Call your own installed model adapter; preserve its proposal"
    )
    author.add_argument("packet", type=Path)
    author.add_argument("--adapter", required=True)
    author.add_argument("--out", type=Path, required=True)
    return root


def main(argv=None):
    command = parser()
    args = command.parse_args(argv)
    try:
        if args.command == "demo":
            result = demo(args.out)
        elif args.command == "prepare":
            packet = prepare(
                args.bars,
                daily_path=args.daily,
                symbol=args.symbol,
                target=args.target,
                cutoff=args.cutoff,
                sessions=args.sessions,
                input_minutes=args.input_minutes,
                price_basis=args.price_basis,
                source=args.source,
            )
            prepare_package(packet, args.out)
            result = {
                "packet": str(args.out),
                "sessions": len(packet.sessions),
                "bars": len(packet.bars),
                "missing_buckets": len(packet.coverage.missing_buckets),
            }
        elif args.command == "validate":
            result = validate(
                load_packet(args.packet), read_model(Proposal, args.proposal)
            )
        elif args.command == "render":
            result = render_package(
                args.packet, args.proposal, args.out, width=args.width
            )
        else:
            result = analyze(args.packet, args.adapter, args.out)
    except (ValueError, OSError, ImportError, AttributeError, KeyError) as error:
        command.exit(1, f"level-charting: {error}\n")
    print(json.dumps(result, indent=2))
    return 0
