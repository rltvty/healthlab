#!/bin/bash
source "$(dirname "$0")/env.sh"
mkdir -p .local build
if [[ ! -f .local/developer-key-pkcs8.der ]]; then
    (umask 077; openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:4096 |
        openssl pkcs8 -topk8 -inform PEM -outform DER -out .local/developer-key-pkcs8.der -nocrypt)
fi
podman run --rm --network=none \
    -v "$CIQ_SDK:/sdk-source:ro" \
    -v "$CIQ_HOME/Devices:/devices-source:ro" \
    -v "$CIQ_HOME/Fonts:/fonts-source:ro" \
    -v "$FACE_ROOT:/work:rw" -w /work \
    "$JAVA_IMAGE" sh -eu -c '
        cp -R /sdk-source /tmp/sdk
        mkdir -p /root/.Garmin/ConnectIQ
        cp -R /devices-source /root/.Garmin/ConnectIQ/Devices
        cp -R /fonts-source /root/.Garmin/ConnectIQ/Fonts
        exec java -Djava.awt.headless=true -jar /tmp/sdk/bin/monkeybrains.jar "$@"
    ' build \
    -f monkey.jungle -d fr970 -o build/HealthLabTime.prg \
    -y .local/developer-key-pkcs8.der -w -l 3 "$@"
