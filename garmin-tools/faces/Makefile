.PHONY: build run clean device
build:
	bash scripts/build.sh

run: build
	bash scripts/run.sh

device: build
	@echo "Copy build/HealthLabTime.prg to GARMIN/APPS on the watch using an MTP client."

clean:
	rm -rf build
