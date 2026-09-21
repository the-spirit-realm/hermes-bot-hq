# Archive GitHub traffic (maintainers)

GitHub Insights and the [traffic REST APIs](https://docs.github.com/en/rest/metrics/traffic) only keep **14 days** of views/clones. The **Archive GitHub traffic** workflow snapshots those APIs daily onto an orphan `traffic` branch so history can grow past that window.

This is not plugin telemetry. Nothing in `desktop/`, `dashboard/`, or `skills/` phones home. Users who clone the default branch never get these files.

## One-time setup

1. Create a **fine-grained PAT** for `the-spirit-realm/hermes-bot-hq` with:
   - **Administration: Read** (required to read traffic)
   - **Contents: Read** (API access)
2. Add it as a repository secret named **`TRAFFIC_TOKEN`**.
3. Merge the workflow to the **default branch** (schedules do not run from feature branches).
4. Run **Actions → Archive GitHub traffic → Run workflow** once to seed the last 14 days and create `traffic`.

Pushing the `traffic` branch uses `GITHUB_TOKEN` (`contents: write`). The PAT is only for reading `/traffic/*`.

If `TRAFFIC_TOKEN` is missing, the job **skips successfully** so scheduled runs do not fail red.

## Schedule

- Cron: `17 3 * * *` (**03:17 UTC**, once per day)
- Also: manual `workflow_dispatch`

GitHub may delay scheduled jobs by several minutes.

## What gets written on `traffic`

- `views.json` / `clones.json` — UTC date keys, `{ "count", "uniques" }`. Each run **upserts** GitHub’s overlapping 14-day window (overwrites those dates; older keys stay).
- `README.md` — large unique-cloners total (sum of daily uniques) at the top; sources in fine print at the bottom.
- `snapshots/YYYY-MM-DD-referrers.json` and `...-paths.json` — that day’s top-10 snapshot (do not sum across days).

Inspect with GitHub’s branch dropdown or:

```bash
git fetch origin traffic
git log origin/traffic
```

History starts on the first successful run. Gaps longer than 14 days cannot be backfilled.
