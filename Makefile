.PHONY: help test test-rtl test-programs create-vivado build-vivado demo clean clean-vivado status

help:
	@echo "ECE338 GPGPU repository targets:"
	@echo "  make test           Run default verification gates"
	@echo "  make test-rtl       Run RTL simulation tests from the current test/ layout"
	@echo "  make test-programs  Build/check example programs with the installed RISC-V toolchain"
	@echo "  make create-vivado  Regenerate the Vivado project/block design only"
	@echo "  make build-vivado   Run the Vivado wrapper script"
	@echo "  make demo           Run a noninteractive demo smoke test"
	@echo "  make clean          Remove generated build artifacts"
	@echo "  make status         Show git status"

test: test-rtl test-programs

test-rtl:
	cd test && ./run_tests.sh

test-programs:
	$(MAKE) -C programs CROSS_PREFIX=riscv64-elf

create-vivado:
	vivado -mode batch -source vivado/create_project.tcl

build-vivado:
	./scripts/vivado_build.sh

demo:
	./demo/run.sh --program nbody-3d --fake --steps 4 --no-browser

clean:
	rm -rf build

clean-vivado:
	rm -rf build/vivado build/vivado_reports build/hw

status:
	git status --short --branch
