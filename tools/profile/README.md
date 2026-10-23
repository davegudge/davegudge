# Public profile data and rendering

Run `python3 tools/profile/refresh.py --render-only` to regenerate desktop and
mobile SVGs from the committed snapshots. Run
`python3 -m unittest discover -s tools/profile -p 'test_*.py'` for feed and
rendering checks.

The public workflow runs every 30 minutes and can also be dispatched manually.
It uses a standard GitHub-hosted runner, reads SMON and ADS-B aggregates plus GitHub and GitLab activity,
validates exact schemas and observation times, and commits changed snapshots
and images. A failed source leaves the previous verified snapshot in place, with
a stale label once it ages beyond two hours.

| Setting | Value |
| --- | --- |
| `SMON_PROFILE_STATS_URL` repository variable | `https://smon.gudge.uk/api/profile_stats` |
| `ADSB_PROFILE_STATS_URL` repository variable | `https://smon.gudge.uk/api/profile_adsb` |
| `SMON_PROFILE_STATS_TOKEN` repository secret | Read-only token for both profile endpoints |

The ADS-B receiver sends a separate authenticated aggregate to SMON every
minute. A mode-600 state file on the receiver holds salted hashes of aircraft
identifiers for the rolling 30-minute count. Neither those hashes nor aircraft
locations are sent to SMON or committed here. After a restart or a polling gap
longer than five minutes, the receiver sends the earlier one-minute schema
until it has collected a complete window. The 30-minute count is distinct
aircraft heard with at least two messages during that window. The other cards
show the 60-second sample, including the position subset, and receiver radio
messages over the preceding 15 minutes. These are saved receiver observations,
not live values when a visitor opens GitHub or totals from FlightAware,
Flightradar24, or ADS-B Exchange. Links to those feeder statistics pages follow
the aviation card.

SMON's cumulative successful-deployment figure combines a fixed verified
historical aggregate of 6,963 with the current instance's cumulative total
from feed schema v2. Current health, projects, deployments in the past 30 days,
and monitoring checks are separate current-instance metrics. The rendering
code falls back to a `6,963+` lower bound if only schema v1 is available.

The original `github-history.json`, `github-preview.json` and
`github-languages.json` files remain dated archives. New activity is collected
separately and combined only in memory when rendering. The language strip stays
dated 6 October 2026; its percentages count repositories by primary language,
not code bytes. Losing access must not silently reduce these historical figures.

The renderer is original code; design credits are in the profile README.
Promote approved files from the private design checkout as a clean public commit.
Never merge its Git history or publish private repository names or daily records.
Review both desktop and mobile layouts, links, alt text, animations and source
aggregates before pushing. Credentials and source identity settings belong in
Actions settings or ignored local configuration, never committed files.

## Current GitHub and GitLab activity

Current activity refreshes every 30 minutes in both repositories, including the
open month. The profile has one Git Signal section and one contribution history,
with a compact observation-time footer and stale or pending-source states.
Completed months are
archived separately inside each source's snapshot; the current month is never
added to its own archive until it has closed and been collected one final time.
API failures preserve the previous aggregate and fail the refresh. Incomplete
pagination or partial project failures never publish partial totals.

Dave requested these continuous current-month updates on 23 October 2026. Raw
daily arrays, commit records, repository names, identities and credentials stay
out of committed files, but the public history of changing monthly totals can
reveal activity between refreshes. Monthly publication is not required.

### GitLab

`data/gitlab-history.json` schema v2 has separate `monthly` and `current_month`
fields. The collector counts exact selected author emails on the configured
integration branch, deduplicating SHAs across projects within each month. Merge
commits are included in the total; there is no separate merge-commit tile. Dates use `committed_date` in the
configured time zone, not the date a commit first reached that branch.

The initial period starts on 12 October 2026 in Europe/London. Current-month
commits are requested up to the actual observation time; completed months use
exclusive end boundaries. Completed months remain fixed after final collection,
so later access changes cannot reduce archived totals. Late merges of commits
with older committed dates do not rewrite already-finalized months. Corrections
require review. Schema v1 archives migrate without losing previously published
months. A changed historical start date or time zone requires review.

Configure these settings independently in preview and public repositories:

| Kind | Name | Purpose |
| --- | --- | --- |
| Secret | `GITLAB_PROFILE_TOKEN` | Personal access token with `read_api` only |
| Variable | `GITLAB_PROFILE_URL` | HTTPS instance origin, without `/api/v4` |
| Optional variable | `GITLAB_PROFILE_USERNAME` | Assert the expected authenticated username |
| Optional variable | `GITLAB_PROFILE_AUTHOR_EMAILS` | Comma-separated exact author emails; defaults to the authenticated account's primary email |
| Optional variable | `GITLAB_PROFILE_PROJECT_IDS` | JSON array of project IDs; defaults to readable membership projects with the selected branch |
| Optional variable | `GITLAB_PROFILE_BRANCH` | Integration branch; defaults to `develop` |
| Optional variable | `GITLAB_PROFILE_START_DATE` | ISO start date; defaults to `2026-10-12` |
| Optional variable | `GITLAB_PROFILE_TIMEZONE` | IANA time zone; defaults to `Europe/London` |

The URL, author identities and project selection stay in Actions settings, not
committed configuration. The PAT is passed in an environment variable and an
HTTPS request header. Redirects are rejected. API responses, repository details,
SHAs, messages and raw daily records are never logged or saved. Rotate the
secret in both repositories before it expires.

For local testing, use a mode-600 ignored configuration with the keys `base_url`,
`token`, `username`, `author_emails`, `start_date`, `timezone`, and `branch`:

```sh
python3 tools/profile/refresh.py --gitlab-config .local/profile/gitlab.json
```

Never put a token in `.gitignore`; it only excludes `/.local/profile/`.
`--render-only` makes no network requests. Missing configuration preserves the
previous aggregate; incomplete configuration fails rather than publishing zero.

### Recent GitHub activity

`data/github-recent.json` stores a separate API-visible period from 7 October
2026 UTC. The historical calendar was captured on 6 October without a precise
cutoff time, so the following UTC day avoids overlapping it. This new period is
added to the saved monthly totals only in the rendered view. It is not a
reconstruction of lost private activity. The original `github-history.json`, `github-preview.json`, and
`github-languages.json` remain unchanged, with dated labels.

The GraphQL query requests only contribution-calendar totals, visible commit
and pull-request counts, and shared restricted-contribution totals for each
month. This monthly query never requests daily calendars, repository lists, names or emails. The separate rolling collector described below reads daily activity transiently.
GitHub contributions include more activity types than GitLab commits. Their
combined total is an activity count, not a count of unique changes or distinct
commits across both services. The rolling contribution tile uses the same GitHub-contributions-plus-GitLab-commits definition as the chart.
The first recent GitHub month starts on 7 October, not
on the first of that month. GraphQL's inclusive end bounds are adjusted to keep
adjacent completed months disjoint.

Actions supplies `GITHUB_ACTIVITY_TOKEN` from its automatic `github.token` and
`GITHUB_PROFILE_LOGIN` from the repository owner. These counts reflect what the
workflow can see; its token cannot access all the owner's private repositories.
An optional repository secret `GITHUB_PROFILE_TOKEN` overrides that token for
profile queries. Use a personal token with `read:user` when shared private
profile counts are needed, and review scope changes before comparing totals.
Keep the GitLab PAT separate. Current private counts depend on GitHub's profile
settings and remaining access; the historical archive protects the older data.

The workflow also runs when collector/rendering code changes on `main`.
Refreshes are serialized, and snapshot-only commits do not start another run.
Before publication, test failures, unchanged input, month rollover, time zones,
multiple projects, archive preservation and both rendered layouts.

## Unified Git Signal and contribution chart

Git Signal shows contributions, authored pull requests/merge requests opened,
and authored pull requests/merge requests merged over the last 30 UTC calendar
days (today plus the preceding 29 days, up to the observation time), and the
combined contribution streak. GitLab merge commits are included once in commit
activity and have no separate tile. Contributions retain the chart's definition:
GitHub profile contributions plus authored GitLab commits reachable from the
configured integration branch. Merge-request counts are separate; they are not
added again to this contribution total. GitLab activity starts at the configured
employment date. Only readable membership projects with that branch are included.

`data/git-signal.json` contains only these rolling totals, window start,
observation time and streak. The collector reads GitHub calendar days and GitLab
commit timestamps in memory, never saving daily records, commit identities,
project names or request details. It deduplicates GitLab commit SHAs across
projects. GitHub and GitLab PR/MR totals count authored requests by creation time
or actual merge time respectively: a request opened before the window can be
merged inside it. GitLab uses the compatible `updated_after` filter followed by
an exact `merged_at` check, not creation date for merged requests.

The streak is consecutive active UTC calendar days across either source,
including weekends. It ends today if active, otherwise yesterday. Activity from
both services on one day advances it once. Up to 365 days are checked; a streak
reaching the lookback boundary displays `+` rather than claiming an exact length.
Private PR metadata depends on the token's repository access; anonymous shared
private contribution counts do not reveal PR state. The existing optional
`GITHUB_PROFILE_TOKEN` can provide broader access than Actions' automatic token.
A missing or failed source preserves the previous rolling aggregate with its
original observation time; it never publishes a partial combined total as zero.
The primary-language strip keeps its historical date in the heading.

`merge_activity_history` creates a fresh in-memory copy of the historical GitHub
monthly aggregate. It adds each finalized and current recent GitHub month once,
then each finalized and current GitLab commit month once. Historical months
before the new periods remain unchanged. GitHub's recent start must follow the
historical capture date. The current record must not overlap a finalized month.
The original three GitHub snapshot files remain byte-identical across refreshes.

The combined monthly history feeds the chart cells, year and decade
totals, total contributions and record highlights. New years and decades extend
the existing chart. GitHub uses UTC month buckets and GitLab uses its configured
time zone; these source-defined monthly aggregates are retained when combined.
No raw daily records are saved. This is activity across services, not a claim
of cross-service commit deduplication.

The visible footers show only `AS OF ...` (or a stale/pending state). Use the
older source observation for a conservative combined freshness label; a failed
or missing source must never make unknown current activity look like zero.
Detailed metric scope is in this document and the image alt text, not repeated
as paragraphs below the cards. There are no standalone GitHub or GitLab panels.
The older standalone generated SVGs are retired from the profile.
