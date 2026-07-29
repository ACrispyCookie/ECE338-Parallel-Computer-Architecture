#!/usr/bin/env bash
# Repository command router for ECE338 GPGPU.
#
# This script is intentionally thin: it documents topics/operations and dispatches
# to the domain-owned script/Makefile/Tcl command. Operation-specific flags are
# forwarded unchanged; domain scripts decide whether no args mean help, a menu, or
# a default operation.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_PATH="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"

usage() {
    cat <<'EOF'
ECE338 GPGPU command router

Usage:
  ./run.sh TOPIC OPERATION [operation args...]
  ./run.sh TOPIC                 Show operations for a topic
  ./run.sh                       Show this API overview

Topics:
  test      Verification operations
  build     Build/generation operations
  run       Program, FPGA, and demo execution operations
  clean     Generated-artifact cleanup operations

Examples:
  ./run.sh test rtl
  ./run.sh test rtl-standard --tb e2e
  ./run.sh test rtl-standard --tb smx --range 14
  ./run.sh test rtl-random --iters 100
  ./run.sh test fpga --port /dev/ttyUSB1 --baud 115200

  ./run.sh build programs PROG=nbody
  ./run.sh build hw
  ./run.sh build hw-project
  ./run.sh build hw-bitstream --jobs 8

  ./run.sh run programs -p nbody riscv --no-x86 --no-visualize
  ./run.sh run fpga -p nbody --port /dev/ttyUSB1 --kernel-calls 1000
  ./run.sh run demo --program nbody-3d --fake --steps 4 --no-browser

  ./run.sh clean all
  ./run.sh clean hardware

Notes:
  The root router does not parse operation-specific flags. Everything after
  TOPIC OPERATION is forwarded to the selected operation.

  If an operation is called with no operation args, the target script decides
  what that means. For example, a domain script may open its own menu.

Naming:
  Use "hw" for hardware build operations and "fpga" for board-backed run/test
  operations. This keeps Vivado/RTL generation distinct from board execution.
EOF
}

topic_help() {
    case "${1:-}" in
        test)
            cat <<'EOF'
Topic: test

Usage:
  ./run.sh test OPERATION [operation args...]

Operations:
  rtl             Forward directly to the RTL test runner
                  -> tests/hardware/rtl/run.sh [args...]
  rtl-standard    Run standard RTL simulation tests
                  -> tests/hardware/rtl/run.sh --standard [args...]
  rtl-random      Run RTL standard tests plus random/fuzzer tests
                  -> tests/hardware/rtl/run.sh --rand [args...]
  rtl-gen         Generate RTL test memories only
                  -> tests/hardware/rtl/run.sh --gen-only [args...]
  fpga            Run board-backed FPGA/UART tests
                  -> tests/hardware/rtl/run.sh --host [args...]

Examples:
  ./run.sh test rtl
  ./run.sh test rtl --help
  ./run.sh test rtl-standard --tb e2e
  ./run.sh test rtl-standard --tb smx --range 14
  ./run.sh test rtl-random --iters 500
  ./run.sh test fpga --port /dev/ttyUSB1 --baud 115200
EOF
            ;;
        build)
            cat <<'EOF'
Topic: build

Usage:
  ./run.sh build OPERATION [operation args...]

Operations:
  programs      Build programs through software/programs/Makefile
                -> make -C software/programs [args...]
  hw            Open/delegate to the hardware runner
                -> hardware/run.sh [args...]
  hw-project    Regenerate the Vivado project/block design only
                -> hardware/run.sh --project [args...]
  hw-bitstream  Regenerate project, then synth/impl/bitstream/XSA
                -> hardware/run.sh --bitstream [args...]

Examples:
  ./run.sh build programs PROG=nbody
  ./run.sh build hw
  ./run.sh build hw --help
  ./run.sh build hw-project
  ./run.sh build hw-bitstream --jobs 8
  ./run.sh build hw-bitstream --skip-project --jobs 8

Vivado operations require Vivado in PATH first, for example:
  source /home/njason/Xilinx/2025.2/Vivado/settings64.sh
EOF
            ;;
        run)
            cat <<'EOF'
Topic: run

Usage:
  ./run.sh run OPERATION [operation args...]

Operations:
  programs       Program build/run wrapper
                 -> software/programs/run.sh [args...]
  fpga           Generic FPGA/UART program runner
                 -> python3 software/programs/fpga_run.py [args...]
  demo           Browser demo launcher
                 -> demo/run.sh [args...]

Examples:
  ./run.sh run programs
  ./run.sh run programs -p nbody riscv --no-x86 --no-visualize
  ./run.sh run fpga -p nbody --port /dev/ttyUSB1 --kernel-calls 1000
  ./run.sh run demo --program nbody-3d --fake --steps 4 --no-browser
EOF
            ;;
        clean)
            cat <<'EOF'
Topic: clean

Usage:
  ./run.sh clean OPERATION [operation args...]

Operations:
  all       Clean all generated artifacts through root Makefile
            -> make clean [args...]
  software  Clean software/program generated artifacts
            -> make -C software/programs clean [args...]
  hardware  Clean hardware/Vivado generated artifacts
            -> hardware/run.sh --clean [args...]
  tests     Clean RTL test generated artifacts
            -> make -C tests/hardware/rtl clean [args...]
  demo      Clean demo generated artifacts
            -> conservative demo-local generated file cleanup

Examples:
  ./run.sh clean all
  ./run.sh clean software
  ./run.sh clean hardware
  ./run.sh clean tests
  ./run.sh clean demo
EOF
            ;;
        *)
            echo "Unknown topic: ${1:-}" >&2
            echo "" >&2
            usage >&2
            return 1
            ;;
    esac
}

clean_demo() {
    # Keep this intentionally conservative. Demo sources/assets stay untouched;
    # only common generated media/data/cache artifacts are removed.
    find "$REPO_PATH/demo" -type d -name __pycache__ -prune -exec rm -rf {} +
    find "$REPO_PATH/demo" -type f \( \
        -name '*.csv' -o \
        -name '*.log' -o \
        -name '*.mp4' -o \
        -name '*.gif' -o \
        -name '*.png' -o \
        -name '*.svg' -o \
        -name '*.pgm' \
    \) -delete
}

if [[ $# -eq 0 ]]; then
    usage
    exit 0
fi

case "${1:-}" in
    -h|--help|help)
        usage
        exit 0
        ;;
esac

TOPIC="$1"
shift

if [[ $# -eq 0 ]]; then
    topic_help "$TOPIC"
    exit $?
fi

case "${1:-}" in
    -h|--help|help)
        topic_help "$TOPIC"
        exit $?
        ;;
esac

OP="$1"
shift

case "$TOPIC:$OP" in
    test:rtl)
        exec "$REPO_PATH/tests/hardware/rtl/run.sh" "$@"
        ;;
    test:rtl-standard|test:standard)
        exec "$REPO_PATH/tests/hardware/rtl/run.sh" --standard "$@"
        ;;
    test:rtl-random|test:random)
        exec "$REPO_PATH/tests/hardware/rtl/run.sh" --rand "$@"
        ;;
    test:rtl-gen|test:gen)
        exec "$REPO_PATH/tests/hardware/rtl/run.sh" --gen-only "$@"
        ;;
    test:fpga|test:zedboard|test:board)
        exec "$REPO_PATH/tests/hardware/rtl/run.sh" --host "$@"
        ;;

    build:programs|build:program)
        exec make -C "$REPO_PATH/software/programs" "$@"
        ;;
    build:hw)
        exec "$REPO_PATH/hardware/run.sh" "$@"
        ;;
    build:hw-project|build:project)
        exec "$REPO_PATH/hardware/run.sh" --project "$@"
        ;;
    build:hw-bitstream|build:bitstream)
        exec "$REPO_PATH/hardware/run.sh" --bitstream "$@"
        ;;

    run:programs|run:program)
        exec "$REPO_PATH/software/programs/run.sh" "$@"
        ;;
    run:fpga|run:zedboard|run:board)
        exec python3 "$REPO_PATH/software/programs/fpga_run.py" "$@"
        ;;
    run:demo)
        exec "$REPO_PATH/demo/run.sh" "$@"
        ;;

    clean:all)
        exec make -C "$REPO_PATH" clean "$@"
        ;;
    clean:software|clean:programs|clean:program)
        exec make -C "$REPO_PATH/software/programs" clean "$@"
        ;;
    clean:hardware|clean:hw|clean:vivado)
        exec "$REPO_PATH/hardware/run.sh" --clean "$@"
        ;;
    clean:tests|clean:test)
        exec make -C "$REPO_PATH/tests/hardware/rtl" clean "$@"
        ;;
    clean:demo)
        clean_demo "$@"
        ;;

    *)
        echo "Unknown operation: $TOPIC $OP" >&2
        echo "" >&2
        topic_help "$TOPIC" >&2 || usage >&2
        exit 1
        ;;
esac
