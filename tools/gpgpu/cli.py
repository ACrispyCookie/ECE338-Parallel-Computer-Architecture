from __future__ import annotations

import argparse
import sys

from .config import ConfigError, ConfigResolver
from .planner import PlanError, Planner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gpgpu", description="GPGPU goal planner foundation")
    sub = parser.add_subparsers(dest="command", required=True)

    list_parser = sub.add_parser("list", help="List public goals")
    list_parser.add_argument("--internal", action="store_true", help="Include internal goals")

    for name in ("plan", "explain"):
        p = sub.add_parser(name, help=f"{name.capitalize()} a goal graph")
        p.add_argument("goal")
        p.add_argument("--profile", default=None)
        p.add_argument("--set", dest="set_values", action="append", default=[])

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "list":
            config = ConfigResolver().resolve()
            planner = Planner(config)
            for goal in planner.list_goals(include_internal=args.internal):
                visibility = "public" if goal.public else "internal"
                print(f"{goal.goal_id:<24} {goal.kind:<8} {visibility:<8} {goal.description}")
            return 0

        config = ConfigResolver().resolve(profile=args.profile, set_values=args.set_values)
        plan = Planner(config).plan(args.goal)

        if args.command == "plan":
            print(plan.format_plan())
            return 0

        if args.command == "explain":
            print(plan.format_explain(config))
            return 0

        parser.error(f"Unknown command: {args.command}")
        return 2

    except (ConfigError, PlanError) as exc:
        print(f"gpgpu: error: {exc}", file=sys.stderr)
        return 2
