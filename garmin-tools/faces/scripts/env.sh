#!/bin/bash
# Sourced by the project commands; no global Java or shell configuration needed.
set -euo pipefail
FACE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CIQ_HOME="${CIQ_HOME:-$HOME/Library/Application Support/Garmin/ConnectIQ}"
if [[ -z "${CIQ_SDK:-}" ]]; then
    CIQ_SDK="$(cat "$CIQ_HOME/current-sdk.cfg")"
fi
[[ -f "$CIQ_SDK/bin/monkeybrains.jar" ]] || { echo "Connect IQ SDK not found: $CIQ_SDK" >&2; exit 1; }
JAVA_IMAGE="${JAVA_IMAGE:-docker.io/library/eclipse-temurin@sha256:32764b27154c93fec8cdfcb1656b630d64bc22329b38a3c02c07c3f706dc893c}"
cd "$FACE_ROOT"
