"""Self-play harness for Track A of docs/week-6.md.

Plays persona.py against itself, at one or more strengths, and reports which
style heuristics actually fire and how often -- data to calibrate `WEIGHTS`
and the margin table with, instead of guessing.

Not part of src/ or pytest: it deliberately plays full games against a real
Stockfish process, which is exactly what CLAUDE.md's testing rule keeps out
of persona.py's own unit tests. Run it directly, e.g.:

    python3 -m tools.self_play --style carlsen \\
        --strengths 800 1200 1600 2000 2400 2800 --games 30

Requires Stockfish on PATH (or STOCKFISH_PATH set), same as the app itself.
"""

import argparse
import json
import os
import sys
from collections import Counter
from dataclasses import dataclass, field

from src.engine import Engine, EngineUnavailable
from src.game import Game
from src.persona import WEIGHTS, choose

# A self-play game that runs this long without ending is cut off rather than
# left to run indefinitely -- style comparison doesn't need a natural mate,
# and pathological drawn-out lines aren't informative either way.
_PLY_CAP = 200

# Same shape and interpolation as persona._MARGIN_TABLE and
# server._ANALYSIS_TIME_TABLE. Duplicated on purpose rather than importing
# server.py, which would pull in FastAPI for a standalone script that has
# nothing to do with HTTP.
_MOVETIME_TABLE = [
    (800, 50),
    (1200, 100),
    (1600, 200),
    (2000, 400),
    (2400, 800),
    (2800, 800),
]


def _movetime_ms(strength: int) -> int:
    table = _MOVETIME_TABLE
    if strength <= table[0][0]:
        return table[0][1]
    if strength >= table[-1][0]:
        return table[-1][1]
    for (lo_strength, lo_time), (hi_strength, hi_time) in zip(table, table[1:]):
        if lo_strength <= strength <= hi_strength:
            t = (strength - lo_strength) / (hi_strength - lo_strength)
            return round(lo_time + t * (hi_time - lo_time))
    raise AssertionError("unreachable: strength is clamped to the table's range above")


def _avoid_chaos_is_decisive(fen: str, candidates: list, style: str, strength: int, baseline_move: str) -> bool:
    """Whether avoid_chaos's penalty actually changed the winning candidate,
    found by temporarily zeroing its weight and re-choosing -- a real
    A/B comparison through persona.py's own public choose(), not a
    reimplementation of its scoring loop. choose() is pure and doesn't touch
    the engine, so this costs no extra Stockfish time."""
    original = WEIGHTS["avoid_chaos"]
    WEIGHTS["avoid_chaos"] = 0.0
    try:
        without = choose(fen, candidates, style=style, strength=strength)
    finally:
        WEIGHTS["avoid_chaos"] = original
    return without.move != baseline_move


@dataclass
class GameReport:
    plies: int = 0
    outcome: str | None = None
    cut_off: bool = False
    tag_counts: Counter = field(default_factory=Counter)
    no_tag_plies: int = 0
    avoid_chaos_fired: int = 0
    avoid_chaos_decisive: int = 0


def play_one_game(engine: Engine, style: str, strength: int) -> GameReport:
    game = Game(user_color="white")
    report = GameReport()

    while not game.is_over() and report.plies < _PLY_CAP:
        analysis = engine.analyse(game.fen, _movetime_ms(strength))
        if not analysis.candidates:
            break  # no legal moves -- is_over() should already have caught this; defensive only
        result = choose(game.fen, analysis.candidates, style=style, strength=strength)

        if result.tags:
            report.tag_counts.update(result.tags)
        else:
            report.no_tag_plies += 1
        if "avoid_chaos" in result.tags:
            report.avoid_chaos_fired += 1
            if _avoid_chaos_is_decisive(game.fen, analysis.candidates, style, strength, result.move):
                report.avoid_chaos_decisive += 1

        game.push(result.move)
        report.plies += 1
    else:
        report.cut_off = report.plies >= _PLY_CAP

    report.outcome = game.outcome()
    return report


def _summarize(strength: int, reports: list[GameReport]) -> dict:
    total_plies = sum(r.plies for r in reports)
    tag_totals: Counter = Counter()
    for r in reports:
        tag_totals.update(r.tag_counts)
    outcomes: Counter = Counter(r.outcome or "cut_off" for r in reports)
    no_tag = sum(r.no_tag_plies for r in reports)
    avoid_chaos_fired = sum(r.avoid_chaos_fired for r in reports)
    avoid_chaos_decisive = sum(r.avoid_chaos_decisive for r in reports)

    return {
        "strength": strength,
        "games": len(reports),
        "total_plies": total_plies,
        "avg_plies": round(total_plies / len(reports), 1) if reports else 0,
        "outcomes": dict(outcomes),
        "tag_frequency_pct": {
            tag: round(100 * count / total_plies, 1) for tag, count in sorted(tag_totals.items())
        }
        if total_plies
        else {},
        "no_tag_ply_pct": round(100 * no_tag / total_plies, 1) if total_plies else 0,
        "avoid_chaos_fired": avoid_chaos_fired,
        "avoid_chaos_decisive": avoid_chaos_decisive,
        "avoid_chaos_decisive_pct": round(100 * avoid_chaos_decisive / avoid_chaos_fired, 1) if avoid_chaos_fired else None,
    }


def _print_summary(summary: dict) -> None:
    print(f"\n== strength {summary['strength']} ({summary['games']} games) ==")
    print(f"  avg plies: {summary['avg_plies']}  outcomes: {summary['outcomes']}")
    if summary["tag_frequency_pct"]:
        # A single ply's winning move can carry more than one tag (every
        # heuristic that fired on it contributes), so these percentages are
        # independent, not a breakdown that sums to 100%.
        print("  tag frequency (% of all plies, not mutually exclusive):")
        for tag, pct in summary["tag_frequency_pct"].items():
            print(f"    {tag:>22}: {pct}%")
    else:
        print("  tag frequency: no tags fired at all")
    print(f"  no heuristic fired: {summary['no_tag_ply_pct']}% of plies")
    if summary["avoid_chaos_fired"]:
        print(
            f"  avoid_chaos fired {summary['avoid_chaos_fired']} times, "
            f"changed the winning move {summary['avoid_chaos_decisive']} times "
            f"({summary['avoid_chaos_decisive_pct']}%)"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--style", default="carlsen", choices=["carlsen", "raw"])  # mirrors persona._STYLES
    parser.add_argument("--strengths", type=int, nargs="+", default=[800, 1200, 1600, 2000, 2400, 2800])
    parser.add_argument("--games", type=int, default=20, help="games per strength")
    parser.add_argument("--stockfish-path", default=os.environ.get("STOCKFISH_PATH", "stockfish"))
    parser.add_argument("--output", help="optional path to also write the summaries as JSON")
    parser.add_argument(
        "--weight",
        action="append",
        default=[],
        metavar="TAG=VALUE",
        help="override one WEIGHTS entry for this run only, e.g. --weight avoid_chaos=3.0 "
        "-- for exploring a calibration candidate before committing it to persona.py",
    )
    args = parser.parse_args()

    for override in args.weight:
        tag, _, value = override.partition("=")
        if tag not in WEIGHTS:
            print(f"error: unknown weight tag {tag!r}", file=sys.stderr)
            return 1
        WEIGHTS[tag] = float(value)

    try:
        engine = Engine(path=args.stockfish_path)
    except EngineUnavailable as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    summaries = []
    try:
        for strength in args.strengths:
            reports = [play_one_game(engine, args.style, strength) for _ in range(args.games)]
            summary = _summarize(strength, reports)
            summaries.append(summary)
            _print_summary(summary)
    finally:
        engine.close()

    if args.output:
        with open(args.output, "w") as f:
            json.dump(summaries, f, indent=2)
        print(f"\nwrote {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
