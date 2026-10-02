# Forerunner 970 Custom Watch Face

Project brief / handoff for a new Codex instance

Goal: build a custom Garmin Connect IQ watch face for a Forerunner 970
using Zed as the editor, the Garmin command-line toolchain for
build/run/deploy, and Codex as the primary coding assistant.

# 1. Project goals

-   Create a native Connect IQ watch-face app targeted first at the
    Garmin Forerunner 970.

-   Use Zed + terminal/CLI rather than depending on VS Code.

-   Make the developer loop simple: edit -\> build -\> run in simulator
    -\> iterate.

-   Keep Garmin-specific compiler/simulator commands behind Makefile
    targets or small scripts.

-   Support sideloading to the physical watch without requiring
    publication to the Connect IQ Store.

-   Design intentionally for the 970's round 454 x 454 AMOLED display
    and its low-power / always-on behavior.

-   Start minimal, then add useful health/training/status data once the
    basic face is stable.

# 2. Known target and constraints

# 3. Recommended repository shape

forerunner-970-face/ ├── manifest.xml ├── monkey.jungle ├── source/ │
├── App.mc │ └── WatchFace.mc ├── resources/ │ ├── layouts/ │ ├── fonts/
│ ├── images/ │ └── strings/ ├── scripts/ ├── Makefile ├── README.md └──
.gitignore

# 4. Desired developer experience

Codex should prefer reproducible CLI commands over IDE-specific actions.
The exact Garmin commands should be discovered from the
installed/current SDK rather than assumed.

make build \# compile for Forerunner 970 make run \# build and
launch/run in Garmin simulator make clean \# remove generated output
make device \# produce/sideload a build suitable for the physical watch,
if practical

If Make is awkward for a particular SDK operation, use scripts under
scripts/ but retain the same small, obvious command surface. Do not
require VS Code merely to build or run the project.

# 5. First milestone: prove the toolchain

1.  Install/configure the current Garmin Connect IQ SDK and the
    Forerunner 970 device support on macOS.

2.  Confirm the compiler and simulator can be invoked without VS Code.

3.  Create the smallest valid watch-face project.

4.  Render the current local time centered on the screen.

5.  Launch it in the Forerunner 970 simulator.

6.  Document the exact setup and commands in README.md.

7.  Only after this works, begin UI/data-field design.

# 6. Watch-face architecture

Keep the first implementation deliberately small. A watch face is an
event-driven Connect IQ app whose view draws into Garmin's graphics
context. Separate data gathering/formatting from drawing once the face
grows beyond the initial prototype.

Likely responsibilities:

-   App.mc: application entry point / lifecycle.

-   WatchFace.mc: watch-face view, lifecycle callbacks, drawing,
    awake/sleep behavior.

-   Data/model helper(s), later: gather and normalize metrics used by
    the UI.

-   Resources: strings, fonts, bitmaps/icons, and layouts where useful.

# 7. AMOLED / always-on requirements

-   Treat awake and low-power/always-on states as distinct design modes.

-   Keep the always-on face sparse and avoid illuminating unnecessary
    pixels.

-   Avoid unnecessary redraws and high-frequency work.

-   Verify Garmin's current Connect IQ rules for AMOLED burn-in
    mitigation, partial updates, and per-second updates before
    implementing them.

-   Optimize for battery life rather than assuming desktop-style
    rendering is cheap.

# 8. Initial UI direction

The final information hierarchy is intentionally undecided. Start with
time only. Potential later fields include current heart rate, date,
battery, steps, Body Battery, recovery/training information, weather,
and sunset. Do not add everything merely because it is available.

             14:37

        HR 72     BB 64

        8,421     73%

          sunset 19:24

# 9. Important implementation questions for Codex to resolve

-   What is the current recommended direct/CLI installation path for the
    Connect IQ SDK on macOS?

-   What are the exact current compiler and simulator commands and
    environment variables?

-   What product/device identifier should be used for the Forerunner 970
    in manifest/build configuration?

-   What API level and permissions are appropriate for this target?

-   What data APIs are available to watch faces for each desired metric,
    and which require permissions?

-   Which values are live versus cached or periodically updated?

-   What are the current always-on AMOLED restrictions and best
    practices?

-   What is the cleanest current sideload workflow for testing on the
    physical Forerunner 970?

-   Can useful diagnostics/linting be exposed to Zed through CLI output
    or an available language server?

# 10. Guidance for the Codex instance

-   Inspect the local environment and repository before making
    assumptions.

-   Use current Garmin documentation as the authority for SDK/toolchain
    details that may have changed.

-   Prefer the CLI even if Garmin documentation demonstrates an
    equivalent VS Code action.

-   Do not introduce Node/Python tooling unless it provides a clear
    benefit; keep the project lightweight.

-   Do not add dependencies or abstractions prematurely.

-   Keep commits/changes small enough that simulator failures are easy
    to diagnose.

-   When a Garmin API or device capability is uncertain, verify it
    rather than inventing a plausible API.

-   Make README.md sufficient for a fresh Codex session or human
    developer to reproduce the environment.

-   Once the simulator loop works, ask the user what data and visual
    style they want before building a dense dashboard.

# 11. Definition of done for the bootstrap phase

☐ Repository builds from a terminal on the user's Mac.

☐ A Forerunner 970 simulator instance displays the custom watch face.

☐ The face displays the correct time.

☐ The workflow does not require opening VS Code.

☐ A one-command or near-one-command build/run loop exists.

☐ README documents prerequisites, SDK location/configuration, build,
run, and physical-device testing.

☐ The repository is ready for iterative visual design.

# 12. Suggested first prompt to Codex

Use this document as the project brief. Bootstrap the repository for a
Garmin Forerunner 970 Connect IQ watch face using Zed/CLI rather than VS
Code. First inspect the machine for an existing Connect IQ
SDK/toolchain. Verify current Garmin CLI conventions as needed. Create
the minimal project and Makefile/scripts necessary to build and run a
time-only face in the Forerunner 970 simulator. Keep the implementation
minimal and document every setup/build/run step in README.md. Do not
start adding health/training fields until the basic simulator loop
works.

Status: bootstrap brief; UI/data-field requirements intentionally remain
open.

# 13. Product concept: experimental time + information face

The face should not merely rearrange Garmin's stock fields. A central
goal is to experiment with alternative representations of time while
retaining useful conventional time and health/environment information as
configurable secondary data.

# 14. Metric UTC time system

Metric time is defined as the fraction of the current UTC day that has
elapsed. It is intentionally anchored to UTC, not local civil time, so
the value is identical worldwide and unaffected by travel or
daylight-saving changes.

-   Day fraction = seconds since 00:00 UTC / 86,400.

-   Canonical 4-digit display: 0000 through 9999, conceptually .0000
    through .9999.

-   One 4-digit day tick represents 8.64 seconds.

-   A 3-digit compact form may be useful for lower-information or
    low-power views; one tick is 86.4 seconds.

-   The intended use is often approximate/abstract time: knowing roughly
    where the global UTC day is without immediately reading ordinary
    local clock time.

Example:

.6832

# 15. Metric date / timestamp

Extend the same idea to the year. The year fraction is the fraction of
the current UTC year elapsed, using 365 or 366 days as appropriate. The
project notation can combine civil year, year fraction, and UTC-day
fraction.

-   Linear notation example: 2026.7283.6832

-   2026 = UTC civil year.

-   7283 = approximately .7283 through that UTC year.

-   6832 = approximately .6832 through the current UTC day.

-   At four digits, the year-fraction display changes roughly every
    52-53 minutes.

-   Year and day fractions should be calculated independently and have
    simple, explicit semantics.

A stacked representation may fit the round display better:

2026 7238 2934

The year should be optional. Proposed density modes: Full = year + year
fraction + day fraction; Normal = year fraction + day fraction; Minimal
= day fraction only. Views should consume a small MetricTime model that
exposes year, yearFraction, and dayFraction rather than duplicating
calculations.

# 16. Time as a configurable data source

Metric time should be first-class but not necessarily permanently
hard-coded as the main display. A primary/secondary time slot should be
able to choose among Metric UTC, local conventional time, and
potentially conventional UTC time. Metric time is useful for
approximate/global temporal context; local time remains available when
precise civil time is actually needed.

# 17. Data of interest

## System / status

-   Local time; conventional UTC time; date/day of week.

-   Battery level and charging state.

-   Phone/Bluetooth connection status.

-   Activity-tracking enabled state.

-   Alarm/system-status information where exposed.

## Heart / physiology

-   Current heart rate and resting heart rate.

-   Heart-rate history, preferably with a compact sparkline or
    circular/arc visualization.

-   Current stress.

-   Respiration rate.

-   Other activity-monitor information that is both available and
    meaningful.

## Daily activity

-   Vertical meters climbed.

-   Active minutes today and active minutes this week.

-   Move-bar status.

-   Potential progress rings around the display for daily/weekly goals.

## Weather

-   Current temperature and conditions.

-   High/low.

-   Forecast.

-   Precipitation information.

-   Wind.

-   Weather/observation location and freshness where available.

## Astronomy / location

-   Sunrise and sunset are high-priority.

-   Also investigate civil, nautical, and astronomical dawn/dusk.

-   Explore a 24-hour ring showing daylight/twilight periods and solar
    events.

-   Moon information/phases where practical.

-   Altitude/elevation and other useful location-derived information.

## Garmin-derived health/training

-   Body Battery.

-   Training Readiness.

-   Sleep Score and nap/sleep information.

-   HRV status.

-   Training Status.

-   Acute load.

-   VO2 max.

-   Race predictions.

-   Training Effect.

-   Recovery / recovery time.

# 18. Trustworthiness and missing data

The user may not wear the watch continuously. Therefore the face must
distinguish values that remain valid without continuous wear from
accumulated or physiological values that may be incomplete.

-   Never manufacture a fallback physiological/training value when
    Garmin reports unavailable/null.

-   Prefer blank, unavailable, or visually de-emphasized data over
    confidently displaying stale or incomplete information.

-   For weather, use observation/update freshness if available and
    consider visually indicating stale data.

-   For accumulated activity such as active minutes or vertical ascent,
    remember that values may undercount when the watch was not worn.

-   For Garmin-derived metrics such as Body Battery, sleep, HRV,
    Training Readiness, and recovery, display Garmin's supplied
    value/complication when available rather than attempting to recreate
    proprietary calculations.

# 19. Specialized visualizations

Do not reduce every data source to a label + number. The round AMOLED
display should be used as a visual instrument where that improves
glanceability.

-   Heart-rate history: tiny sparkline or arc/circular history plot.

-   Daylight/twilight ring: map dawn, sunrise, daylight, sunset, dusk
    and possibly twilight classes around a 24-hour ring.

-   Day progress: circumference showing progress through the UTC or
    local day.

-   Activity progress: ring mode for daily/weekly goals.

-   Weather: consider compact forecast or precipitation visualization
    rather than only text.

-   Outer ring should be treated as a configurable visualization surface
    rather than assigned permanently to one metric.

# 20. Complication-oriented architecture

Prefer a small set of visual slots/components with configurable data
sources. Some sources will be custom (MetricTime); others may be backed
by Garmin system complications or direct Connect IQ APIs.

            [ PRIMARY ]

      [ LEFT ]       [ RIGHT ]

          [ SECONDARY ]

        [ OUTER RING ]

-   Primary: metric timestamp, metric day fraction, local time, or
    conventional UTC time.

-   Secondary/side slots: HR, battery, weather, stress, Body Battery,
    recovery, active minutes, etc.

-   Outer ring: daylight/twilight, day progress, activity progress, HR
    history, or another specialized visualization.

-   Status layer: compact Bluetooth, charging, alarm, tracking/system
    indicators.

-   Ambient/always-on view: dramatically simplified while preserving the
    core identity of the face.

# 21. Touch / interaction

The Forerunner 970's watch-face-specific interaction and complication
configuration capabilities are interesting. Investigate them, but do not
assume generic foreground-app touch APIs apply to watch faces.

-   Where supported, tapping/selecting a displayed Garmin complication
    may open the corresponding Garmin glance/app.

-   Consider interaction for temporarily revealing local conventional
    time from a metric-time display.

-   Use Garmin's WatchFaceDelegate/complication model where appropriate.

-   Verify each desired deep-link/launch behavior against current
    Connect IQ documentation before implementing it.

# 22. Power-state design

Design awake and low-power/always-on states together. The richer face
can appear when the user raises their wrist; the ambient state should be
sparse, low-power, and AMOLED-friendly.

AWAKE AMBIENT

7238 293 2934 HR 72 BAT 73%

# 23. Research checklist before feature implementation

-   Inventory the complete complication catalog actually available to a
    Forerunner 970 watch face.

-   Confirm direct API vs complication availability for Body Battery,
    Training Readiness, Sleep Score, HRV status, Training Status, acute
    load, VO2 max, race predictions, Training Effect, and recovery.

-   Confirm HR-history sampling/history behavior and what is practical
    for a watch-face visualization.

-   Inventory astronomy/location APIs and determine whether
    civil/nautical/astronomical twilight should be calculated locally.

-   Confirm moon data availability; if absent, decide whether
    lightweight local astronomical calculation is appropriate.

-   Confirm altitude/elevation data availability and whether values are
    sufficiently fresh/useful on a watch face.

-   Confirm weather freshness metadata and update behavior.

-   Confirm which system/status indicators are exposed to third-party
    watch faces.

-   Confirm watch-face interaction/deep-link behavior for configurable
    complications.

-   Document all unsupported or unreliable desired fields rather than
    approximating them.

# 24. Updated bootstrap sequence

1.  Get Zed + Connect IQ CLI + Forerunner 970 simulator working.

2.  Implement a minimal local-time face to prove the toolchain.

3.  Implement MetricTime as a tested, UI-independent model: UTC year,
    year fraction, day fraction.

4.  Render the stacked metric timestamp and its Full/Normal/Minimal
    density variants.

5.  Add local conventional time as an alternate/secondary source.

6.  Prototype the configurable slot architecture.

7.  Prototype the solar/daylight outer ring.

8.  Add heart-rate/current-status data, then HR history.

9.  Add Garmin complication-backed health/training fields only after
    verifying availability.

10. Iterate on visual design and ambient mode after functionality is
    proven.

# 25. Updated suggested prompt to Codex

Use this document as the product and engineering brief. Bootstrap a
Garmin Forerunner 970 Connect IQ watch-face repository using Zed/CLI
rather than VS Code. First establish a reproducible terminal build and
simulator loop. Then implement a small, tested MetricTime model based
strictly on UTC: civil year, fraction through the UTC year, and fraction
through the UTC day. Support four-digit fractions and stacked
Full/Normal/Minimal views such as 2026 / 7238 / 2934. Keep local
conventional time available as a separate configurable source. Architect
the face around configurable visual slots and a configurable outer-ring
visualization, but do not implement the entire feature inventory at
once. Verify current Garmin APIs and Forerunner 970 complication support
before using any health/training/system field; represent unavailable or
stale data honestly. Document setup, verified capabilities, unsupported
items, and build/run commands in README.md.

### Table 1

| Item \| Current decision \|

| --- \| --- \|

| Device \| Garmin Forerunner 970 \|

| Display \| Round AMOLED, 454 x 454 \|

| Platform \| Garmin Connect IQ \|

| Language \| Monkey C \|

| Editor \| Zed \|

| Build/run \| Connect IQ SDK command-line tools \|

| Assistant \| Codex working directly in the repository \|

| Primary host \| macOS / Apple Silicon \|
