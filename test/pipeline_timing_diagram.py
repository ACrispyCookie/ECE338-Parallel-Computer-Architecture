#!/usr/bin/env python3
"""Serve an interactive pipeline timing diagram from generated RTL traces."""

from __future__ import annotations

import argparse
import csv
import json
import re
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
DEFAULT_TESTS_DIR = HERE / "tests"
DEFAULT_HTML = HERE / "pipeline_timing_diagram.html"
TEST_DIR_RE = re.compile(r"test([0-9]+)$")
STAGES = ("if", "id", "ex", "mem", "wb")
BUBBLE_VALUES = {"", "x", "xxxxxxxx", "ffffffff"}


def discover_tests(tests_dir: Path) -> list[dict[str, object]]:
    """Return numerically sorted test cases that have source and a generated trace."""
    discovered: list[dict[str, object]] = []
    if not tests_dir.is_dir():
        return discovered
    for case in tests_dir.iterdir():
        match = TEST_DIR_RE.fullmatch(case.name)
        if not match or not case.is_dir():
            continue
        if not (case / "program.asm").is_file() or not (case / "trace.csv").is_file():
            continue
        number = int(match.group(1))
        discovered.append({"id": number, "name": f"Test {number}"})
    return sorted(discovered, key=lambda item: int(item["id"]))


def parse_program(path: Path) -> list[dict[str, str]]:
    instructions: list[dict[str, str]] = []
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", "//", ".")) or line.endswith(":"):
            continue
        pc = f"{len(instructions) * 4:08x}"
        instructions.append({"pc": pc, "instruction": line})
    return instructions


def normalize_pc(value: str) -> str | None:
    pc = value.strip().lower()
    if pc in BUBBLE_VALUES:
        return None
    if pc.startswith("0x"):
        pc = pc[2:]
    try:
        return f"{int(pc, 16):08x}"
    except ValueError:
        return None


def build_timing_rows(
    program: list[dict[str, str]], cycles: list[dict[str, object]]
) -> list[dict[str, object]]:
    """Arrange stage occupancy as instruction rows and cycle columns."""
    rows: list[dict[str, object]] = [
        {"pc": item["pc"], "instruction": item["instruction"], "cells": {}}
        for item in program
    ]
    row_by_pc = {str(row["pc"]): row for row in rows}
    for cycle in cycles:
        cycle_number = int(cycle["cycle"])
        for stage in STAGES:
            value = cycle.get(stage)
            if not isinstance(value, dict):
                continue
            row = row_by_pc.get(str(value.get("pc")))
            if row is None:
                continue
            cells = row["cells"]
            assert isinstance(cells, dict)
            cells.setdefault(cycle_number, []).append(stage.upper())
    return rows


def load_test(tests_dir: Path, test_number: int) -> dict[str, object]:
    case = tests_dir / f"test{test_number}"
    program_path = case / "program.asm"
    trace_path = case / "trace.csv"
    if not program_path.is_file() or not trace_path.is_file():
        raise FileNotFoundError(f"test {test_number} does not have both program.asm and trace.csv")

    program = parse_program(program_path)
    instruction_by_pc = {item["pc"]: item["instruction"] for item in program}
    cycles: list[dict[str, object]] = []
    with trace_path.open(newline="") as trace_file:
        for line_number, row in enumerate(csv.reader(trace_file), start=1):
            if not row or all(not value.strip() for value in row):
                continue
            if len(row) != 6:
                raise ValueError(f"{trace_path}:{line_number}: expected 6 columns, got {len(row)}")
            try:
                cycle_number = int(row[0].strip())
            except ValueError as error:
                raise ValueError(f"{trace_path}:{line_number}: invalid cycle {row[0]!r}") from error

            cycle: dict[str, object] = {"cycle": cycle_number}
            trace_index = len(cycles)
            for stage_index, (stage, raw_pc) in enumerate(zip(STAGES, row[1:])):
                # The RTL resets every stage PC register to INITIAL_PC. During
                # startup those deeper-stage zeros are empty pipeline slots,
                # not additional instances of the first instruction.
                pc = None if trace_index < stage_index else normalize_pc(raw_pc)
                cycle[stage] = None if pc is None else {
                    "pc": pc,
                    "instruction": instruction_by_pc.get(pc, f"unknown instruction @ 0x{pc}"),
                }
            cycles.append(cycle)

    return {
        "test": test_number,
        "program": program,
        "cycles": cycles,
        "timing": build_timing_rows(program, cycles),
    }


class PipelineTimingDiagramHTTPServer(ThreadingHTTPServer):
    def __init__(self, address, handler, *, tests_dir: Path, html_path: Path, selected_test: int | None):
        super().__init__(address, handler)
        self.tests_dir = tests_dir
        self.html_path = html_path
        self.selected_test = selected_test


class PipelineTimingDiagramHandler(BaseHTTPRequestHandler):
    server: PipelineTimingDiagramHTTPServer

    def log_message(self, format: str, *args: object) -> None:
        print(f"[pipeline-timing] {self.address_string()} - {format % args}")

    def send_bytes(self, body: bytes, content_type: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_bytes(json.dumps(payload).encode(), "application/json; charset=utf-8", status)

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        path = urlparse(self.path).path
        if path in {"/", "/pipeline_timing_diagram.html"}:
            self.send_bytes(self.server.html_path.read_bytes(), "text/html; charset=utf-8")
            return
        if path == "/api/tests":
            self.send_json({
                "tests": discover_tests(self.server.tests_dir),
                "selected": self.server.selected_test,
            })
            return
        match = re.fullmatch(r"/api/tests/([0-9]+)", path)
        if match:
            try:
                self.send_json(load_test(self.server.tests_dir, int(match.group(1))))
            except FileNotFoundError as error:
                self.send_json({"error": str(error)}, HTTPStatus.NOT_FOUND)
            except ValueError as error:
                self.send_json({"error": str(error)}, HTTPStatus.UNPROCESSABLE_ENTITY)
            return
        self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Open the GPGPU pipeline timing diagram.")
    parser.add_argument("--test", type=int, help="test to select initially")
    parser.add_argument("--host", default="127.0.0.1", help="server bind address")
    parser.add_argument("--port", type=int, default=8000, help="server port; use 0 for any free port")
    parser.add_argument("--tests-dir", type=Path, default=DEFAULT_TESTS_DIR)
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser automatically")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    server = PipelineTimingDiagramHTTPServer(
        (args.host, args.port),
        PipelineTimingDiagramHandler,
        tests_dir=args.tests_dir.resolve(),
        html_path=DEFAULT_HTML,
        selected_test=args.test,
    )
    port = server.server_address[1]
    browser_host = "127.0.0.1" if args.host in {"0.0.0.0", "::"} else args.host
    query = f"?test={args.test}" if args.test is not None else ""
    url = f"http://{browser_host}:{port}/{query}"
    print(f"Pipeline timing diagram: {url}", flush=True)
    print("Press Ctrl+C to stop.", flush=True)
    if not args.no_browser:
        threading.Timer(0.2, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping pipeline timing diagram.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
