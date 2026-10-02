# Garmin workouts

Personal Garmin Connect tooling for a Forerunner 970, built with
[python-garminconnect](https://github.com/cyberjunky/python-garminconnect).
Supports account login, device/workout inspection, exercise search, and generation
and synchronization of six strength class rotations to Garmin Connect and a watch.

## Setup

Requires [uv](https://docs.astral.sh/uv/) and Python 3.13. From this directory:

```sh
uv sync --locked
uv run garmin-tools --help
```

## Login

```sh
uv run garmin-tools auth login
```

Login reuses a saved session when available. Otherwise, enter your email,
password, and MFA code when prompted. Password and MFA input are hidden.
Login can take several minutes while the library tries its authentication methods.

Session tokens are saved locally; passwords are not stored. On macOS, the token
file is `~/Library/Application Support/garmin-workouts/session/garmin_tokens.json`.
Keep this file private and out of Git.

The login flow follows the library's
[upstream example](https://github.com/cyberjunky/python-garminconnect/blob/master/example.py).
No separate example script is required.

## List devices

```sh
uv run garmin-tools devices list
```

Prints registered devices and their capabilities as JSON, using the saved session.
Run `auth login` again if the session expires. This reads your Garmin Connect
account; it does not pair directly with the watch or change account data.

## Exercises and workouts

```sh
uv run garmin-tools exercises search "romanian deadlift"
uv run garmin-tools workouts list
uv run garmin-tools workouts show WORKOUT_ID
```

Exercise search uses the installed Garmin client's bundled catalog and works
offline. Workout listing and inspection use your saved session. Listing returns
one page; use `--start 100 --limit 100` for the next page.

## Create the strength test

```sh
uv run garmin-tools workouts preview
uv run garmin-tools workouts create-test --dry-run
uv run garmin-tools workouts create-test --apply
```

The test is named `TEST - Berlin Strength - RDL 3x8`: three sets of eight Romanian
Deadlift reps, each followed by 30 seconds of rest, including the final set.
Use `--rest-seconds 45` on preview or creation to change the rest duration.

`preview` prints JSON offline. `create-test` defaults to a dry run, checking your
account and printing the proposed payload. Only `--apply` creates a workout.
An existing workout with the same name prevents creation; it is not compared or
updated. The command does not send the workout to a device. Avoid simultaneous
creation commands, as the name check and upload are separate requests.

Garmin Connect accepts this test's structure. Auto Set behavior and step
advancement still require testing on the watch.

## Generate class workouts

Edit [config/berlin-strength.toml](config/berlin-strength.toml), then run:

```sh
uv run garmin-tools workouts generate
uv run garmin-tools workouts generate --start 3
uv run garmin-tools workouts generate --format json
```

The default output summarizes all six rotations, named `Lifted 1`
through `Lifted 6`. The number is the starting station. `--start` selects one
rotation; `--format json` prints an array
of Garmin payloads. Use `--config PATH` for another definition. Generation is
offline and does not upload or modify workouts.

Station names stay fixed: Deadlift, Arms, Lunge, Machine Pull, Leg Press, Chest
Press. Optional `exercise` fields use exact names from `exercises search`.
Arms and Machine Pull are initially unmapped, producing description-only work
steps rather than assuming a particular exercise. The summary flags these.

The shared defaults are 3 sets of 8 reps, 30-second rests after every set, and
15-second transitions between stations. Station entries can override `sets`,
`reps`, and `work_mode`. Each station is a repeat group containing an exercise
and rest. The final set's rest is followed by the transition, giving 45 seconds
between stations by default. Optional `before`/`after` blocks contain warmup, break, core,
stretching, and breathing; set `enabled = false` to omit a block.

For open-ended rests or blocks, set `mode = "lap"` and remove `seconds`.
For manually advanced work sets, set `work_mode = "lap"`; the rep goal then
appears in the description instead of controlling the step's end condition.
These options do not configure or guarantee Auto Set behavior.

Blocks can specify an exercise `category` and `weight = "body"` (zero external
load). Warmup uses `category = "WARM_UP"`, with no specific exercise subtype,
and retains its six-minute timer. Core uses `category = "CORE"` with bodyweight
and a two-minute timer. Their display in future watch recordings still
needs verification.

For timed work sets, set a station's `work_mode = "time"` and `work_seconds = 30`.
Leg Press currently uses this mode: three rounds of 30 seconds work and 30 seconds
rest. The 8-rep goal stays in the description. Other stations retain rep targets.

## Upload and send to your watch

```sh
uv run garmin-tools workouts sync --dry-run
uv run garmin-tools workouts sync --apply
uv run garmin-tools devices list
uv run garmin-tools workouts sync --apply --device DEVICE_ID
```

Sync defaults to a dry run. With `--apply`, it creates missing workouts, updates
changed workouts with the same name while preserving their IDs, and leaves
matching workouts unchanged. Duplicate names stop the sync. Use `--start 3` to
select one rotation or `--config PATH` for another definition. Avoid running
multiple sync commands simultaneously.

`--device` queues all selected workouts for that device after verifying their
saved steps, including unchanged workouts. Sync Garmin Connect with your watch
to download them; a successful queue request does not confirm delivery.

The default six rotations have been uploaded and their saved steps verified in
Garmin Connect. Timed Leg Press advancement still needs watch testing. Auto Set
on rep-based sets is inconclusive: the initial class test used the lap button,
possibly before automatic detection had time to trigger.

## Lifted dashboard

```sh
uv run garmin-tools lifted login
uv run garmin-tools lifted logs --date 2026-10-02
uv run garmin-tools lifted logs --output .local/exercise_logs.json
uv run garmin-tools lifted logs --source .local/exercise_logs.json --date 2026-10-02
```

Login uses Lifted's Firebase email/password flow. Email is visible; password input
is hidden and never stored. Refreshable tokens are stored separately from Garmin,
on macOS at `~/Library/Application Support/garmin-workouts/lifted/session.json`.
Google-only sign-in, MFA, or CAPTCHA may require a browser; this CLI currently
supports email/password only.

Log commands are read-only. The summary omits Lifted's prescribed reps; Garmin's
recorded reps must be preserved when reconciling activities. Exported raw JSON
retains the original response. Weights are shown as Lifted records them; dumbbell
weights need exercise-specific interpretation before importing into Garmin.

## Update recorded activities from Lifted

```sh
uv run garmin-tools lifted sync
uv run garmin-tools lifted sync --days 7 --apply
```

The default is a read-only preview for the last seven calendar days. Use
`--date YYYY-MM-DD` for one day. Both Garmin and Lifted sessions must be logged in.
The command matches `Lifted 1`–`Lifted 6` strength activities to a single attended
class on the same Berlin date, within 45 minutes of the activity start. It updates
exercise names and total weights for the 18 lifting sets, preserving watch reps,
timings, and all other entries, including warmup/core/cooldown edits. Re-running
skips activities whose sets already match.

Exercise mappings live in [config/lifted-exercises.toml](config/lifted-exercises.toml).
Each entry specifies an exact Lifted name, station, Garmin catalog name, and
weight multiplier. Barbell and machine loads are unchanged; paired dumbbells
are doubled, with the single-dumbbell triceps extension exception. Add a reviewed
mapping when a new exercise appears; use `--mappings PATH` for another file.

The supported recorded layout is six stations of three exercise/rest pairs,
with warmup and the standard after blocks. Ambiguous matches, missing weights,
unknown exercises, and changed layouts stop the preview before any activity is
written. The mapping uses recorded step references and the rotation number,
not the current workout template.

Before each write, the command saves the complete original exercise-set payload,
proposed payload, matched Lifted class, activity listing, and change list. Backups
default to `~/Library/Application Support/garmin-workouts/activity-backups` on
macOS; override with `--backups PATH`. Files are private to your user. It checks
for intervening edits and verifies Garmin's saved response. A network or readback
failure stops the run; earlier verified activities may already have been updated.
Avoid simultaneous sync/edit commands.

To undo one update, use the backup directory printed by the command:

```sh
uv run garmin-tools lifted restore BACKUP_DIRECTORY
uv run garmin-tools lifted restore BACKUP_DIRECTORY --apply
```

Restore previews by default and refuses to overwrite newer edits. Backups cover
the exercise sets being edited; the original FIT recording is not modified.
Legacy downloads and investigation scripts in `.local` are not required by these
commands and can be retained as historical backups.

## Development

```sh
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

Tests use mocked Garmin responses and require no account credentials.
