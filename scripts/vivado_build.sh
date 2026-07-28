#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if ! command -v vivado >/dev/null 2>&1; then
    echo "[ERROR] vivado not found in PATH."
    echo "Source Vivado first, for example:"
    echo "  source /tools/Xilinx/Vivado/2026.1/settings64.sh"
    exit 1
fi

# Deterministic rebuild: never reuse old generated project/runs/reports.
rm -rf build/vivado build/vivado_reports build/hw

vivado -mode batch -source vivado/create_project.tcl
vivado -mode batch -source vivado/build.tcl

echo "[SUCCESS] Vivado project regenerated and implemented."
echo "Reports: build/vivado_reports/"
echo "XSA:     build/hw/gpgpu_system.xsa"
