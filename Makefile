.PHONY: help test test-rtl test-programs create-vivado build-vivado demo clean clean-vivado status

help:
	@echo "ECE338 GPGPU repository targets:"
	@echo "  make test           Run default verification gates"
	@echo "  make test-rtl       Run RTL simulation tests"
	@echo "  make test-programs  Build/check example programs with the installed RISC-V toolchain"
	@echo "  make create-vivado  Regenerate the Vivado project/block design only"
	@echo "  make build-vivado   Run the Vivado wrapper script"
	@echo "  make demo           Run a noninteractive demo smoke test"
	@echo "  make clean          Remove generated build artifacts"
	@echo "  make status         Show git status"

test: test-rtl test-programs

test-rtl:
	./tests/hardware/rtl/run.sh

test-programs:
	$(MAKE) -C software/programs

create-vivado:
	./hardware/vivado/run.sh --project

build-vivado:
	./hardware/vivado/run.sh --bitstream

demo:
	./demo/run.sh --program nbody-3d --fake --steps 4 --no-browser

clean:
	rm -rf build .Xil
	rm -f *.jou *.log *.str *.wdb *.vcd
	$(MAKE) -C tests/hardware/rtl clean
	find software/programs -mindepth 2 -maxdepth 2 \( -name "*.elf" -o -name "*.map" -o -name "*_dump_real.asm" -o -name "*_instructions.mem" -o -name "*_x86" \) -delete

clean-vivado:
	./hardware/vivado/run.sh --clean

status:
	git status --short --branch
