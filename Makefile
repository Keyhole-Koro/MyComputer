PYTHON ?= python3
QA_DIR := qa

.PHONY: help run system build system-build kernel kernel-build emulator qa test qa-no-build \
	qa-compiler qa-assembler qa-linker qa-heap qa-serial-rx qa-scheduler \
	mlc-test as-test linker-test serial-rx-test profile clean-qa

help:
	@printf '%s\n' \
		'Targets:' \
		'  make run              Build and run the full system' \
		'  make build            Build system images without running the emulator' \
		'  make kernel           Build and run the kernel ROM path' \
		'  make qa               Run all QA suites' \
		'  make qa-compiler      Run compiler QA suite' \
		'  make qa-assembler     Run assembler QA suite' \
		'  make qa-linker        Run linker QA suite' \
		'  make qa-heap          Run kernel heap QA suite' \
		'  make qa-serial-rx     Run serial RX QA suite' \
		'  make qa-scheduler     Run scheduler QA suite' \
		'  make profile ARGS="profile.json --map image.mbin.map"' \
		'' \
		'Pass script options with ARGS="...".'

run system:
	$(PYTHON) $(QA_DIR)/run_system.py $(ARGS)

build system-build:
	$(PYTHON) $(QA_DIR)/run_system.py --no-run $(ARGS)

kernel:
	$(PYTHON) $(QA_DIR)/run_kernel.py $(ARGS)

kernel-build:
	$(PYTHON) $(QA_DIR)/run_kernel.py --no-run $(ARGS)

emulator:
	$(MAKE) -C runtime/MyEmulator

qa test:
	$(PYTHON) $(QA_DIR)/test-all.py $(ARGS)

qa-no-build:
	$(PYTHON) $(QA_DIR)/test-all.py --no-build $(ARGS)

qa-compiler:
	$(PYTHON) $(QA_DIR)/test-all.py compiler $(ARGS)

qa-assembler:
	$(PYTHON) $(QA_DIR)/test-all.py assembler $(ARGS)

qa-linker:
	$(PYTHON) $(QA_DIR)/test-all.py linker $(ARGS)

qa-heap:
	$(PYTHON) $(QA_DIR)/test-all.py heap $(ARGS)

qa-serial-rx:
	$(PYTHON) $(QA_DIR)/test-all.py serial-rx $(ARGS)

qa-scheduler:
	$(PYTHON) $(QA_DIR)/test-all.py scheduler $(ARGS)

mlc-test:
	$(PYTHON) $(QA_DIR)/mlc-test.py $(ARGS)

as-test:
	$(PYTHON) $(QA_DIR)/as-test.py $(ARGS)

linker-test:
	$(PYTHON) $(QA_DIR)/linker-test.py $(ARGS)

serial-rx-test:
	$(PYTHON) $(QA_DIR)/serial-rx-test.py $(ARGS)

profile:
	$(PYTHON) $(QA_DIR)/profile_report.py $(ARGS)

clean-qa:
	rm -rf $(QA_DIR)/outputs
