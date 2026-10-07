# Agent guidance

This is Dave Gudge's public GitHub profile. `README.md`, `assets/profile/`, and
all commits on `main` are public. Read `tools/profile/README.md` before editing
profile images or data feeds.

- Keep credentials, database dumps, deployment records, aircraft identifiers
  and locations, private repository names, and daily private contribution
  records out of committed files. Publish reviewed aggregates only. Dave
  approved the ADS-B Exchange feeder statistics link in `README.md`; its URL
  contains the feeder short ID. Keep that exception limited to the link.
- The GitHub contribution and language figures are dated aggregates. Preserve
  their archive when access to private repositories changes. Do not replace
  them with a narrower snapshot or combine overlapping contribution periods.
- SMON's fixed historical deployment baseline and current-instance status
  have different scopes. Add current deployments to the baseline only when
  the verified feed supplies a cumulative total. Do not name the former
  employer in the profile.
- ADS-B aircraft counts describe the minute before the observation time,
  not the moment a visitor opens GitHub. The receiver pushes to SMON every
  five minutes; the public GitHub workflow samples the feed every 30 minutes.
  Show observation dates and stale states accurately.
- Regenerate desktop and mobile SVGs with
  `python3 tools/profile/refresh.py --render-only`. Run profile tests and
  inspect both layouts, links, animation, and alt text before publishing.
- Do not merge the private preview repository's Git history into this public
  repository. The initial redesign was published as a clean commit based on
  public `main` because older preview commits held daily contribution data.
