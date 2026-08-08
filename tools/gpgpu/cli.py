from __future__ import annotations

import argparse
import os
import sys

from .config import ConfigError, ConfigResolver
from .executor import ExecuteError, Executor
from .goals import GoalDefinition
from .planner import Plan, PlanError, Planner
from .reporter import InteractiveRunReporter, PlainRunReporter

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
COLORS = {
    "artifact": "\033[36m",
    "action": "\033[33m",
    "service": "\033[35m",
    "check": "\033[32m",
    "public": "\033[32m",
    "internal": "\033[90m",
    "heading": "\033[1;34m",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gpgpu", description="GPGPU goal planner foundation")
    parser.add_argument(
        "--color",
        choices=("auto", "always", "never"),
        default="auto",
        help="Colorize output: auto, always, or never (default: auto)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    list_parser = sub.add_parser("list", help="List public goals")
    list_parser.add_argument("--internal", action="store_true", help="Include internal goals")

    for name in ("plan", "explain"):
        p = sub.add_parser(name, help=f"{name.capitalize()} a goal graph")
        p.add_argument("goal")
        p.add_argument("--profile", default=None)
        p.add_argument("--set", dest="set_values", action="append", default=[])
        p.add_argument("-v", "--verbose", action="store_true", help="Show full explanatory planner metadata")

    run_parser = sub.add_parser("run", help="Run an executable goal through a compatibility adapter")
    run_parser.add_argument("goal")
    run_parser.add_argument("--profile", default=None)
    run_parser.add_argument("--set", dest="set_values", action="append", default=[])
    run_parser.add_argument(
        "--progress",
        choices=("auto", "plain", "tty"),
        default="auto",
        help="Run progress renderer: auto, plain, or tty (default: auto)",
    )

    return parser


def should_color(mode: str) -> bool:
    if mode == "always":
        return True
    if mode == "never" or os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def paint(text: str, color: str, enabled: bool) -> str:
    if not enabled:
        return text
    return f"{color}{text}{RESET}"


def format_goal_list(goals: list[GoalDefinition], *, color: bool) -> str:
    lines = []
    if color:
        lines.append(paint("GPGPU goals", COLORS["heading"], True))
    for goal in goals:
        visibility = "public" if goal.public else "internal"
        kind = paint(f"{goal.kind:<8}", COLORS[goal.kind], color)
        vis = paint(f"{visibility:<8}", COLORS[visibility], color)
        bullet = paint("●", COLORS[goal.kind], color) if color else ""
        prefix = f"{bullet} " if bullet else ""
        desc = paint(goal.description, DIM, color)
        lines.append(f"{prefix}{goal.goal_id:<24} {kind} {vis} {desc}")
    return "\n".join(lines)


def format_plan(plan: Plan, *, color: bool, verbose: bool = False) -> str:
    text = plan.format_plan(verbose=verbose)
    if not color:
        return text
    replacements = {
        "BUILD": COLORS["artifact"],
        "ACTION": COLORS["action"],
        "SERVICE": COLORS["service"],
        "CHECK": COLORS["check"],
    }
    lines = []
    for line in text.splitlines():
        for label, ansi in replacements.items():
            if line.startswith(label):
                line = paint(label, ansi + BOLD, True) + line[len(label) :]
                break
        lines.append(line)
    return "\n".join(lines)


def make_run_reporter(progress: str, *, color: bool):
    if progress == "tty" or (progress == "auto" and sys.stdout.isatty()):
        return InteractiveRunReporter(sys.stdout, color=color)
    return PlainRunReporter(sys.stdout, color=color)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    color = should_color(args.color)

    try:
        if args.command == "list":
            config = ConfigResolver().resolve()
            planner = Planner(config)
            print(format_goal_list(planner.list_goals(include_internal=args.internal), color=color))
            return 0

        config = ConfigResolver().resolve(profile=args.profile, set_values=args.set_values)
        plan = Planner(config).plan(args.goal)

        if args.command == "plan":
            print(format_plan(plan, color=color, verbose=args.verbose))
            return 0

        if args.command == "explain":
            if color:
                rendered = plan.format_explain(config, verbose=args.verbose)
                lines = []
                for line in rendered.splitlines():
                    if line in ("Artifact identities:", "Configuration provenance:"):
                        lines.append(paint(line, COLORS["heading"], True))
                    else:
                        lines.append(line)
                print("\n".join(lines))
            else:
                print(plan.format_explain(config, verbose=args.verbose))
            return 0

        if args.command == "run":
            reporter = make_run_reporter(args.progress, color=color)
            summary = Executor(config).run_plan(plan, reporter=reporter)
            return summary.returncode

        parser.error(f"Unknown command: {args.command}")
        return 2

    except (ConfigError, PlanError, ExecuteError) as exc:
        print(f"gpgpu: error: {exc}", file=sys.stderr)
        return 2
