# Garmin watch faces

A minimal local-time watch face for the Forerunner 970, with a Zed/terminal
workflow. The compiler runs in Podman; Garmin's simulator runs natively on macOS.
No Java installation on macOS, Homebrew, or VS Code is required.

The face displays hours and minutes using the watch's 12/24-hour setting.
Ambient mode is blank until an AMOLED-safe always-on design is implemented.
Metric UTC time and additional fields are planned in [task.md](task.md).

## Setup

1. Install Podman and start its VM with `podman machine start`.
2. Install Garmin's [SDK Manager](https://developer.garmin.com/connect-iq/sdk/)
   directly from its macOS disk image. Download an SDK and **Forerunner 970**
   device support, and select the active SDK.
3. Ensure Make, Bash, OpenSSL, and macOS `/usr/bin/expect` are available.

Tested with Connect IQ SDK **9.2.0**, device target `fr970`, and an ARM64 Eclipse
Temurin Java 17 container. The image is pinned by digest in `scripts/env.sh`;
Podman downloads it on first build if needed.

SDK discovery reads
`~/Library/Application Support/Garmin/ConnectIQ/current-sdk.cfg`.
Set `CIQ_HOME` or `CIQ_SDK` to override the data directory or SDK path.
`JAVA_IMAGE` overrides the pinned image for deliberate runtime updates.
No shell profile changes are needed.

## Build and run

From this directory:

```sh
make build     # compile with strict type checking in Podman
make run       # build and launch in the native Mac simulator
make device    # build and print physical-watch installation instructions
make clean     # remove generated build files
```

The first build creates a private signing key at `.local/developer-key-pkcs8.der`.
Keep it to sign future updates with the same identity. Keys and build outputs are
ignored by Git.

Build containers are removed after use, and compiler execution has networking
disabled. SDK, device, and font directories are mounted read-only and copied
inside the disposable container because Garmin generates files beside them.
The project is mounted writable for build output. The Java image stays cached in
Podman; it installs no macOS runtime or updater.

`make run` uses Garmin's native `shell` helper and macOS Expect instead of the
Java-based `monkeydo`. It copies the program into the simulator's temporary
`com.garmin.connectiq/GARMIN/APPS` directory and checks for an `appStarted`
acknowledgement. Initial launch and repeated build/run have been verified with
SDK 9.2.0. This relies on simulator details that may change in future SDKs;
visually check the display when changing the face.

If the helper cannot connect after restarting the simulator, quit the simulator,
wait briefly, and retry. Its local transport normally listens on port 1234.

## Physical watch

Connect the watch by USB and use an MTP client such as OpenMTP to copy
`build/HealthLabTime.prg` into the watch's `GARMIN/APPS` directory. Disconnect
cleanly and select **HealthLab Time** in the watch-face picker. Store publication
is not required. Physical-watch deployment has not been tested here;
`make device` does not copy anything automatically.

## Cleanup

`make clean` removes build output. To remove Java, use `podman image rm` with the
image reference from `scripts/env.sh`; there is no host Java uninstaller.
Only delete `.local/` if you no longer need its signing keys. Garmin's SDK Manager
and downloaded SDK/device files are separate from the container.

## References

- [Connect IQ command-line setup](https://developer.garmin.com/connect-iq/reference-guides/monkey-c-command-line-setup/)
- [Monkey C](https://developer.garmin.com/connect-iq/monkey-c/)
- [Supported devices and display specifications](https://developer.garmin.com/connect-iq/compatible-devices/)
- [Garmin simulator shell example](https://forums.garmin.com/developer/connect-iq/f/discussion/4979/connect-iq-2-3-beta---blue-arrow-on-startup/36120)
