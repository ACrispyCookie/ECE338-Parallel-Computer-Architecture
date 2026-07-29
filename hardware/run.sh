#!/usr/bin/env bash
# Main hardware/Vivado topic script.
#
# No args opens an interactive menu. Flags run noninteractively so the root
# router and Makefile can call specific operations repeatably.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_PATH="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
CONFIG_PATH="$REPO_PATH/config/gpgpu.json"
BUILD_PATH="$REPO_PATH/build"
HARDWARE_PATH="$REPO_PATH/hardware"
RTL_PATH="$HARDWARE_PATH/rtl"
VIVADO_PATH="$HARDWARE_PATH/vivado"
VIVADO_BUILD_PATH="$BUILD_PATH/hardware/vivado"
REPORTS_PATH="$BUILD_PATH/hardware/reports"
HW_EXPORT_PATH="$BUILD_PATH/hardware/hw"
BITSTREAM_PATH="$BUILD_PATH/hardware/bitstream"

PROJECT_TCL="$VIVADO_PATH/create_project.tcl"
BUILD_TCL="$VIVADO_PATH/build.tcl"
REPORTS_TCL="$VIVADO_PATH/reports.tcl"

MODE=""
JOBS="32"
SKIP_PROJECT=0

usage() {
    cat <<EOF
Hardware/Vivado runner

Usage:
  $0                         Open interactive hardware menu
  $0 --help                  Show this help
  $0 --project               Regenerate Vivado project/block design only
  $0 --bitstream             Regenerate project, then synth/impl/bitstream/XSA
  $0 --reports               Regenerate reports from an implemented project
  $0 --clean                 Remove generated Vivado/hardware artifacts

Options:
  --jobs N                   Vivado synth/impl job count for --bitstream (default: $JOBS)
  --skip-project             For --bitstream, reuse existing Vivado project instead of regenerating it

Paths:
  REPO_PATH          $REPO_PATH
  CONFIG_PATH        $CONFIG_PATH
  HARDWARE_PATH      $HARDWARE_PATH
  RTL_PATH           $RTL_PATH
  VIVADO_PATH        $VIVADO_PATH
  VIVADO_BUILD_PATH  $VIVADO_BUILD_PATH
  REPORTS_PATH       $REPORTS_PATH
  HW_EXPORT_PATH     $HW_EXPORT_PATH

Examples:
  $0 --project
  $0 --bitstream --jobs 8
  $0 --bitstream --skip-project --jobs 8
  $0 --reports
  $0 --clean
EOF
}

require_vivado() {
    if ! command -v vivado >/dev/null 2>&1; then
        echo "[ERROR] vivado not found in PATH." >&2
        echo "Source Vivado first, for example:" >&2
        echo "  source /home/njason/Xilinx/2025.2/Vivado/settings64.sh" >&2
        exit 1
    fi
}

clean_hardware() {
    rm -rf "$VIVADO_BUILD_PATH" "$REPORTS_PATH" "$HW_EXPORT_PATH" "$BITSTREAM_PATH"
    rm -rf "$REPO_PATH/.Xil"
    rm -f "$REPO_PATH"/*.jou "$REPO_PATH"/*.log "$REPO_PATH"/*.str "$REPO_PATH"/*.wdb "$REPO_PATH"/*.vcd
    echo "[OK] Cleaned Vivado/hardware generated artifacts."
}

run_project() {
    require_vivado
    rm -rf "$VIVADO_BUILD_PATH"
    mkdir -p "$VIVADO_BUILD_PATH" "$REPORTS_PATH" "$HW_EXPORT_PATH"
    vivado -mode batch -source "$PROJECT_TCL"
    echo "[OK] Vivado project regenerated."
}

run_bitstream() {
    require_vivado
    if [[ "$SKIP_PROJECT" -eq 0 ]]; then
        run_project
    fi
    mkdir -p "$REPORTS_PATH" "$HW_EXPORT_PATH" "$BITSTREAM_PATH"
    vivado -mode batch -source "$BUILD_TCL" -tclargs -jobs "$JOBS"
    echo "[OK] Vivado bitstream/build flow complete."
    echo "Reports: $REPORTS_PATH"
    echo "XSA:     $HW_EXPORT_PATH/gpgpu_system.xsa"
}

run_reports() {
    require_vivado
    mkdir -p "$REPORTS_PATH"
    vivado -mode batch -source "$REPORTS_TCL"
    echo "[OK] Vivado reports regenerated."
}

interactive_menu() {
    while true; do
        cat <<EOF

Hardware/Vivado Menu
====================
1) Regenerate Vivado project/block design
2) Build bitstream/XSA (regenerates project first)
3) Build bitstream/XSA from existing project
4) Regenerate reports from implemented project
5) Clean hardware/Vivado generated artifacts
h) Help
0) Exit
EOF
        read -rp "Select: " choice
        case "$choice" in
            1) exec "$0" --project ;;
            2)
                read -rp "Vivado jobs [$JOBS]: " jobs
                jobs="${jobs:-$JOBS}"
                exec "$0" --bitstream --jobs "$jobs"
                ;;
            3)
                read -rp "Vivado jobs [$JOBS]: " jobs
                jobs="${jobs:-$JOBS}"
                exec "$0" --bitstream --skip-project --jobs "$jobs"
                ;;
            4) exec "$0" --reports ;;
            5) exec "$0" --clean ;;
            h|H) usage ;;
            0|q|Q) exit 0 ;;
            *) echo "Invalid selection: $choice" ;;
        esac
    done
}

if [[ $# -eq 0 ]]; then
    interactive_menu
fi

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help|help)
            usage
            exit 0
            ;;
        --project)
            MODE="project"
            shift
            ;;
        --bitstream)
            MODE="bitstream"
            shift
            ;;
        --reports)
            MODE="reports"
            shift
            ;;
        --clean)
            MODE="clean"
            shift
            ;;
        --jobs)
            if [[ $# -lt 2 ]]; then
                echo "[ERROR] Missing value for --jobs" >&2
                exit 1
            fi
            JOBS="$2"
            shift 2
            ;;
        --skip-project)
            SKIP_PROJECT=1
            shift
            ;;
        *)
            echo "[ERROR] Unknown argument: $1" >&2
            usage >&2
            exit 1
            ;;
    esac
done

case "$MODE" in
    project) run_project ;;
    bitstream) run_bitstream ;;
    reports) run_reports ;;
    clean) clean_hardware ;;
    "")
        echo "[ERROR] No operation selected." >&2
        usage >&2
        exit 1
        ;;
    *)
        echo "[ERROR] Internal error: unknown mode $MODE" >&2
        exit 1
        ;;
esac
