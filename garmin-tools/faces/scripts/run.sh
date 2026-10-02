#!/bin/bash
source "$(dirname "$0")/env.sh"
open -a "$CIQ_SDK/bin/ConnectIQ.app"
# The native simulator stores its virtual watch filesystem here on macOS.
SIM_APPS="${TMPDIR:-/tmp/}/com.garmin.connectiq/GARMIN/APPS"
mkdir -p "$SIM_APPS"
cp build/HealthLabTime.prg "$SIM_APPS/14F33C6F21834451A866E6F7DB67A980.PRG"
exec /usr/bin/expect scripts/run.exp "$CIQ_SDK/bin/shell"
