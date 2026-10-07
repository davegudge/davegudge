# Public profile data and rendering

Run `python3 tools/profile/refresh.py --render-only` to regenerate desktop and
mobile SVGs from the committed snapshots. Run
`python3 -m unittest discover -s tools/profile -p 'test_*.py'` for feed and
rendering checks.

The public workflow runs every 30 minutes and can also be dispatched manually.
It uses a standard GitHub-hosted runner, reads only aggregate data from SMON,
validates exact schemas and observation times, and commits changed snapshots
and images. A failed feed leaves the previous verified snapshot in place, with
a stale label once it ages beyond two hours.

| Setting | Value |
| --- | --- |
| `SMON_PROFILE_STATS_URL` repository variable | `https://smon.gudge.uk/api/profile_stats` |
| `ADSB_PROFILE_STATS_URL` repository variable | `https://smon.gudge.uk/api/profile_adsb` |
| `SMON_PROFILE_STATS_TOKEN` repository secret | Read-only token for both profile endpoints |

The ADS-B receiver sends a separate authenticated aggregate to SMON every five
minutes. The displayed aircraft and position figures describe the 60 seconds
before the shown observation time; messages cover the receiver's preceding 15
minutes. They are not live values when a visitor opens GitHub and are not
FlightAware, Flightradar24, or ADS-B Exchange totals. The public profile links
to those services' feeder statistics pages. No aircraft identifiers or
locations are stored in the profile snapshots.

SMON's cumulative successful-deployment figure combines a fixed verified
historical aggregate of 6,963 with the current instance's cumulative total
from feed schema v2. Current health, projects, deployments in the past 30 days,
and monitoring checks are separate current-instance metrics. The rendering
code falls back to a `6,963+` lower bound if only schema v1 is available.

GitHub activity is deliberately archived: `github-preview.json` holds a dated
12-month total and pull-request aggregates; `github-history.json` holds monthly
contribution counts from 2007 through 6 October 2026; and
`github-languages.json` holds primary-language counts across owned public and
private non-fork repositories. The snapshots contain no private repository
names or daily private contribution records. The workflow never refreshes
these GitHub figures automatically, so losing access to a private repository
cannot silently lower the historical totals. Add later activity only as a
reviewed, non-overlapping period.

The renderer is original code. The console design credits Giorgi Kobaidze and
jdx in the profile README.
