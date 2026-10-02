# Oura → Garmin sleep experiment

## Goal

Import Oura sleep into Garmin Connect so it can contribute to Garmin's health and
recovery statistics. A separate dashboard or custom report is not the goal.

The user generally wears Oura nearly 24/7, but does not wear the Forerunner 970
overnight. For the initial experiment, wear both for one night and sync both the
following morning. Proposed recording night: October 2–3, 2026, Europe/Berlin;
confirm the actual dates before collecting data.

## Evidence and limits

- Garmin documents exporting daily wellness FIT files and importing wellness
  files during account migration. The watch that recorded them must be active on
  the destination account. This makes file-based ingestion worth investigating;
  it does not establish support for synthetic Oura-derived files.
  [Export instructions](https://support.garmin.com/en-US/?faq=W1TvTPW8JZ6LfJSfK512Q8)
  · [Migration instructions](https://support.garmin.com/en-PH/?faq=mZi3iyunkt3VSzheytHbz7)
- Garmin's official Health API provides access to Garmin-collected data, rather
  than documenting arbitrary third-party sleep uploads.
  [Health API](https://developer.garmin.com/gc-developer-program/health-api/)
- Manual sleep entry supplies duration, without generating sleep data or a Sleep
  Score. Automating that alone would not meet the goal.
  [Sleep tracking](https://support.garmin.com/en-IE/?faq=mBRMf4ks7XAQ03qtsbI8J6&productID=698519&tab=topics&textPage=1&topicTag=region_sleeptracking)
- Health Connect and Apple Health cannot bridge the gap: Garmin exports to them
  but does not read their data. Health Sync lists Garmin as a source, not a
  destination.
  [Health Connect](https://support.garmin.com/lv-LV/?faq=JToBEy0jfe6pIygark2Ui5)
  · [Apple Health](https://support.garmin.com/en-HK/?faq=lK5FPB9iPF5PXFkIpFlFPA)
  · [Health Sync](https://healthsync.app/about/)
- Oura supports API access using OAuth2, and exports sleep through Health Connect.
  Verify the API's actual fields and sampling intervals; availability in Health
  Connect does not establish identical detail in the API.
  [Oura authentication](https://cloud.ouraring.com/docs/authentication)
  · [Oura Health Connect integration](https://support.ouraring.com/hc/en-us/articles/10786105824531-Health-Connect-by-Android-Integration)
- Garmin's official Python FIT SDK supports decoding and encoding. Its encoder
  ignores unknown fields, so a decode/re-encode cycle must not be assumed to
  preserve proprietary wellness data.
  [Python FIT SDK](https://github.com/garmin/fit-python-sdk)

The suggested `/upload-service/upload/wellness` endpoint is an unverified lead
from the discussion. Verify its behavior before relying on it; start with the
documented manual import route.

## Experiment sequence

1. **Record a reference night.** Wear the 970 and Oura simultaneously. Sync both
   in the morning and confirm Garmin produced sleep data. Record the timezone,
   actual dates, and any manual sleep edits.
2. **Preserve source data.** Export Garmin wellness files for both calendar dates
   spanning the night through Connect's Account Information page. Preserve the
   original archives and FIT files. Also save the Garmin sleep API response and
   available Sleep Score, HRV Status, Body Battery, and Training Readiness data.
   These form a baseline, not proof of which data came from the FIT files.
3. **Inspect the FIT files.** Validate integrity and inventory message types,
   timestamps, device metadata, and unknown fields. Compare decoded contents with
   the sleep API response. Determine whether stages and scores are present,
   derived elsewhere, or missing. Do not assume one file contains the whole night.
4. **Retrieve the matching Oura night.** Use OAuth with private token storage.
   Inspect sleep boundaries, stages, HR, HRV, and respiration where available.
   Compare units, definitions, timezones, and sampling intervals. Do not treat
   aggregate HRV or respiration values as raw time series, or substitute Oura's
   score for Garmin's score.
5. **Build a minimal candidate offline.** Only after identifying the required
   messages, encode the supported Oura-derived values and decode the result to
   verify it. Inventory fields lost during encoding. Keep synthetic output
   separate from original recordings and document its provenance.
6. **Test ingestion deliberately.** Preserve before-state data and establish how
   duplicates, overlaps, and deletion/restoration behave before choosing a test
   date. Avoid overwriting the reference night. Upload the candidate manually
   first, then inspect both Connect and API results. A backup alone does not
   guarantee wellness data can be restored.
7. **Evaluate downstream effects.** Separately establish whether stages display,
   a Garmin Sleep Score exists, and recovery metrics change after sync. Existing
   watch-recorded sleep on the reference night could confound this test. A
   successful upload or a changed score alone is insufficient evidence that the
   imported data drove the calculation.

## Questions to resolve

- Which sleep-related FIT messages does the 970 actually export? Are essential
  fields private or undocumented?
- Does Connect import sleep stages, recompute sleep metrics, or only retain
  monitoring data? Are some metrics computed on the watch?
- What device association and file metadata does ingestion require?
- How are duplicate files and overlapping sleep records handled?
- Can an experimental import be removed without damaging unrelated wellness data?
- What Oura detail is available through the API, and is it sufficient?
- Does imported sleep affect Sleep Score, Body Battery, HRV Status, or Training
  Readiness? Evaluate each independently, including any history requirements.

Possible outcomes range from rejection or partial import, through stages visible
without recovery effects, to usable input for Garmin's derived metrics. None has
been demonstrated yet.

## Implementation direction

Keep this experiment under `garmin-tools/sleep`, separate from workout tooling.
Use Python with uv and evaluate `garmin-fit-sdk`; no TypeScript migration is
needed. Start with a read-only FIT inspection tool. Add conversion and upload
only as the evidence supports them.

Store personal exports, decoded files, API snapshots, and synthetic candidates
under the ignored `.local/` directory. Keep credentials and OAuth tokens out of
tracked files. No sleep tooling or uploads have been implemented as part of
these notes.
