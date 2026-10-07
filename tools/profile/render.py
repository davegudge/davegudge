#!/usr/bin/env python3
"""Render the local GitHub profile preview from an explicit data snapshot."""

from __future__ import annotations

import argparse
import json
import math
import textwrap
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "assets" / "profile"
DATA = ROOT / "tools" / "profile" / "data" / "github-preview.json"
SMON_DATA = ROOT / "tools" / "profile" / "data" / "smon-latest.json"
ADSB_DATA = ROOT / "tools" / "profile" / "data" / "adsb-latest.json"
HISTORY_DATA = ROOT / "tools" / "profile" / "data" / "github-history.json"
LANGUAGES_DATA = ROOT / "tools" / "profile" / "data" / "github-languages.json"
INK = "#edf8ff"
MUTED = "#a3b5c8"
CYAN = "#58e8ff"
PINK = "#ff69d9"
VIOLET = "#b58cff"
LIME = "#c1f75a"
ORANGE = "#ffae58"
BASE = "#080c19"
PANEL = "#111b2c"
ACCENTS = (CYAN, VIOLET, LIME, PINK, ORANGE)


def t(x: float, y: float, value: str, size: int = 18, color: str = INK,
      weight: int = 400, anchor: str = "start", extra: str = "") -> str:
    return (f'<text x="{x:.1f}" y="{y:.1f}" fill="{color}" font-size="{size}" '
            f'font-weight="{weight}" text-anchor="{anchor}" {extra}>{escape(str(value))}</text>')


def box(x: float, y: float, w: float, h: float, fill: str = PANEL,
        stroke: str = "#254255", radius: int = 10, extra: str = "") -> str:
    return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
            f'rx="{radius}" fill="{fill}" stroke="{stroke}" {extra}/>')


def line(x1: float, y1: float, x2: float, y2: float, color: str = "#284555",
         width: float = 1, extra: str = "") -> str:
    return (f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{color}" stroke-width="{width}" {extra}/>')


def svg(w: int, h: int, title: str, body: str, *, top=False, bottom=False,
        left=True, right=True) -> str:
    rail = ""
    if left:
        rail += line(2, 0, 2, h, CYAN, 2)
    if right:
        rail += line(w - 2, 0, w - 2, h, CYAN, 2)
    if top:
        rail += line(2, 2, w - 2, 2, CYAN, 2)
    if bottom:
        rail += line(2, h - 2, w - 2, h - 2, CYAN, 2)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{escape(title, quote=True)}">
<title>{escape(title)}</title>
<style>
text {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }}
.blink {{ animation: blink 1.4s steps(1,end) infinite; }}
.sweep {{ transform-origin: 50% 50%; animation: sweep 9s linear infinite; }}
.plane {{ animation: fly 18s linear infinite; }}
.ambient {{ animation: ambient 5s ease-in-out infinite; }}
.metric-edge {{ animation: metric-edge 5s ease-in-out infinite; }}
.arrow-drift {{ animation: arrow-drift 3.5s ease-in-out infinite; }}
.month-focus {{ animation: month-focus 3s ease-in-out infinite; }}
@keyframes blink {{ 50% {{ opacity: .2 }} }}
@keyframes sweep {{ to {{ transform: rotate(360deg) }} }}
@keyframes fly {{ from {{ transform: translateX(-100px) }} to {{ transform: translateX({w + 100}px) }} }}
@keyframes ambient {{ 50% {{ opacity: .35; }} }}
@keyframes metric-edge {{ 0%,100% {{ stroke-opacity: .35; }} 50% {{ stroke-opacity: 1; }} }}
@keyframes arrow-drift {{ 0%,35%,65%,100% {{ transform: translateX(0); }} 50% {{ transform: translateX(7px); }} }}
@keyframes month-focus {{ 50% {{ stroke-opacity: .25; }} }}
@media (prefers-reduced-motion: reduce) {{ .blink,.sweep,.plane,.ambient,.metric-edge,.arrow-drift,.month-focus {{ animation: none; }} }}
</style>
<rect width="100%" height="100%" fill="{BASE}"/>
{rail}{body}
</svg>'''


def save(name: str, content: str, mobile: bool) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    suffix = "-mobile" if mobile else ""
    (OUT / f"{name}{suffix}.svg").write_text(content, encoding="utf-8")


def heading(w: int, label: str, index: str, mobile: bool) -> str:
    size = 13 if mobile else 16
    color = (CYAN, VIOLET, LIME, ORANGE, PINK, CYAN)[int(index) - 1]
    return (t(24, 37, f"{index} // {label}", size, color, 700) +
            line(24, 53, w - 24, 53, color, 1, 'opacity=".52"'))


def render_header(mobile: bool) -> None:
    w, h = (420, 286) if mobile else (1000, 340)
    body = '''<style>
.header-node { animation: header-twinkle 7s ease-in-out infinite; }
@keyframes header-twinkle {
  0%,72%,100% { opacity: .16; }
  79% { opacity: .56; }
  87% { opacity: .23; }
}
@media (prefers-reduced-motion: reduce) { .header-node { animation: none; } }
</style>'''
    # An abstract topology across the header, with no axes or implied measurements.
    traces = (
        (((24, 98), (78, 72), (132, 119), (185, 80), (239, 115), (293, 70), (347, 117), (401, 82)),
         ((23, 255), (76, 221), (130, 261), (183, 216), (237, 258), (291, 224), (346, 263), (402, 228)))
        if mobile else
        (((28, 107), (95, 138), (165, 89), (235, 126), (305, 78), (375, 117),
          (445, 83), (515, 127), (572, 165), (641, 186), (695, 135), (760, 150),
          (819, 111), (895, 129), (951, 86)),
         ((26, 285), (98, 245), (171, 283), (244, 235), (317, 274), (390, 226),
          (463, 263), (532, 277), (596, 240), (653, 261), (711, 212), (771, 235),
          (831, 177), (909, 197), (967, 144)))
    )
    for trace_index, trace in enumerate(traces):
        for (x1, y1), (x2, y2) in zip(trace, trace[1:]):
            body += line(x1, y1, x2, y2, MUTED, 1.5, 'opacity=".11"')
        for point_index, (x, y) in enumerate(trace):
            delay = (point_index * 1.7 + trace_index * 2.3) % 7
            body += (f'<circle cx="{x}" cy="{y}" r="3" fill="{MUTED}" opacity=".16" '
                     f'class="header-node" style="animation-delay:-{delay:.1f}s"/>')
    for point_index in (2, 5):
        (x1, y1), (x2, y2) = traces[0][point_index], traces[1][point_index]
        body += line(x1, y1, x2, y2, MUTED, 1, 'opacity=".06"')
    body += box(17, 17, w - 34, 29, "#15243b", CYAN, 4)
    body += t(30, 37, "◉  DAVE.GUDGE  /  PROFILE.CONSOLE", 11 if mobile else 13, CYAN, 700)
    body += t(w - 30, 37, "● PUBLIC PROFILE", 10 if mobile else 12, LIME, 700, "end")
    body += t(29, 84 if mobile else 102, "$", 15 if mobile else 18, LIME, 700)
    body += t(51, 84 if mobile else 102, "./dave --about", 14 if mobile else 17, MUTED, 700)
    body += box(174 if mobile else 207, 70 if mobile else 86,
                8 if mobile else 10, 16 if mobile else 19, LIME, "none", 0,
                'class="blink"')
    body += t(29, 150 if mobile else 207, "DAVE", 56 if mobile else 98, INK, 800)
    body += t(32, 203 if mobile else 292, "GUDGE", 56 if mobile else 98, PINK, 800,
              extra='class="ambient"')
    body += t(29, 203 if mobile else 292, "GUDGE", 56 if mobile else 98, CYAN, 800)
    if mobile:
        body += t(29, 244, "RAILS · HOTWIRE NATIVE", 13, MUTED, 700)
        body += t(29, 265, "INFRASTRUCTURE · AVIATION", 13, MUTED, 700)
    else:
        body += t(616, 163, "RUBY ON RAILS", 18, ORANGE, 700)
        body += t(616, 196, "HOTWIRE NATIVE", 18, PINK)
        body += t(616, 229, "INFRASTRUCTURE", 18, VIOLET)
        body += t(616, 262, "AVIATION", 18, LIME)
    save("header", svg(w, h, "Dave Gudge — Rails, infrastructure and aviation", body, top=True), mobile)


def render_stats(user: dict, mobile: bool, fetched_at: str | None = None,
                 history: dict | None = None, languages: dict | None = None) -> None:
    w, h = ((420, 552) if mobile else (1000, 390)) if languages else \
           ((420, 357) if mobile else (1000, 246))
    calendar = user["contributionsCollection"]["contributionCalendar"]
    values = [(f'{calendar["totalContributions"]:,}', "CONTRIBUTIONS / 12 MO"),
              (f'{user["pullRequests"]["totalCount"]:,}', "PULL REQUESTS"),
              (f'{user["mergedPullRequests"]["totalCount"]:,}', "MERGED PRS"),
              (f'{history["current_streak_days"]}d' if history else
               str(user["repositories"]["totalCount"]),
               f'STREAK · {datetime.fromisoformat(history["observed_at"]).strftime("%d %b").upper()}'
               if history else "PUBLIC REPOSITORIES")]
    body = heading(w, "GITHUB SIGNAL", "01", mobile)
    for i, (value, label) in enumerate(values):
        cols = 2 if mobile else 4
        col, row = i % cols, i // cols
        cell_w = (w - 48 - (cols - 1) * 12) / cols
        x = 24 + col * (cell_w + 12)
        y = 72 + row * (100 if mobile else 0)
        color = ACCENTS[i]
        body += box(x, y, cell_w, 88, PANEL, color,
                    extra=f'class="metric-edge" style="animation-delay:-{i * 3}s"')
        body += t(x + 15, y + 45, value, 29 if mobile else 35, color, 800)
        body += t(x + 15, y + 72, label, 10 if mobile else 12, MUTED, 700)
    if languages:
        language_counts = languages["languages"]
        total = languages["counted_repositories"]
        if languages["schema_version"] != 1 or total != sum(language_counts.values()) or total <= 0:
            raise ValueError("invalid GitHub language snapshot")
        colors = (ORANGE, CYAN, LIME, PINK, VIOLET, "#7db6ff", "#8b9bb1")
        language_items = sorted(language_counts.items(), key=lambda item: (-item[1], item[0]))
        section_y = 300 if mobile else 206
        body += line(24, section_y - 20, w - 24, section_y - 20)
        body += t(24, section_y, "TOP LANGUAGES", 13 if mobile else 16, CYAN, 700)
        scope = f'{total} OWN REPOS · PRIVATE + PUBLIC · NO FORKS'
        body += t(24 if mobile else w - 24, section_y + (19 if mobile else 0), scope,
                  9 if mobile else 11, MUTED, 700, "start" if mobile else "end")
        bar_y = 331 if mobile else 222
        bar_left, bar_width = 24, w - 48
        cursor = bar_left
        for index, (name, count) in enumerate(language_items):
            color = colors[index % len(colors)]
            segment_width = bar_width * count / total
            body += box(cursor, bar_y, segment_width, 18 if mobile else 20, color, "none", 0)
            cursor += segment_width
            col_count = 2 if mobile else 4
            col, row = index % col_count, index // col_count
            x = 24 + col * (192 if mobile else 238)
            y = (372 if mobile else 270) + row * (25 if mobile else 28)
            body += box(x, y - 10, 9, 9, color, "none", 1)
            body += t(x + 16, y, f'{name} {100 * count / total:.1f}%',
                      10 if mobile else 12, INK, 700)
    foot_y = (493 if mobile else 342) if languages else (300 if mobile else 193)
    body += line(24, foot_y - 19, w - 24, foot_y - 19)
    account_label = "GITHUB ACTIVITY"
    if history:
        account_label = f'LONGEST STREAK {history["longest_streak_days"]}D'
        if not mobile:
            account_label += f' · {user["repositories"]["totalCount"]} PUBLIC REPOS'
    body += t(24, foot_y, account_label, 10 if mobile else 13, ORANGE, 700)
    snapshot_date = (datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
                     .strftime("%d %b %Y")) if fetched_at else "05 Oct 2026"
    body += t(24, foot_y + 21,
              f"Snapshot: {snapshot_date} · private activity included" if history else
              f"Snapshot: {snapshot_date} · private activity may be included",
              9 if mobile else 12, MUTED)
    if mobile and history:
        body += t(24, foot_y + 42, f'{user["repositories"]["totalCount"]} PUBLIC REPOS',
                  9, MUTED, 700)
    save("stats", svg(w, h, "GitHub activity snapshot", body), mobile)


def render_history(history: dict, mobile: bool) -> None:
    w, h = (420, 916) if mobile else (1000, 916)
    months: dict[str, int] = history["monthly"]
    years = list(range(history["first_year"], history["last_year"] + 1))
    if history["schema_version"] != 1 or len(months) < 12 or any(
            not isinstance(value, int) or value < 0 for value in months.values()):
        raise ValueError("invalid GitHub history snapshot")
    annual = {year: sum(months.get(f"{year}-{month:02d}", 0)
                        for month in range(1, 13)) for year in years}
    if sum(annual.values()) != history["total_contributions"]:
        raise ValueError("GitHub history totals do not match")
    current_year = history["last_year"]
    top_month, top_month_count = max(months.items(), key=lambda item: item[1])
    top_year, _ = max(annual.items(), key=lambda item: item[1])
    body = ('''<style>
.peak-cell { animation: peak-cell 5s ease-in-out infinite; }
@keyframes peak-cell { 0%,100% { stroke-opacity: .4; } 50% { stroke-opacity: 1; } }
@media (prefers-reduced-motion: reduce) { .peak-cell { animation: none; } }
</style>''' +
            heading(w, f'CONTRIBUTION ARCHIVE / {history["first_year"]}–{history["last_year"]}',
                    "02", mobile))
    body += t(24, 79, f'{history["total_contributions"]:,} CONTRIBUTIONS',
              15 if mobile else 19, ORANGE, 800)
    body += t(w - 24, 79, "MONTH BY MONTH" if mobile else "MONTH BY MONTH · LIME = TOP 3",
              10 if mobile else 13, MUTED, 700, "end")
    groups = [("2000s", [y for y in years if y < 2010]),
              ("2010s", [y for y in years if 2010 <= y < 2020]),
              ("2020s", [y for y in years if y >= 2020])]
    y = 107
    month_names = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN",
                   "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")
    left, step, cell_width = (58, 25, 22) if mobile else (105, 69, 62)
    row_step = 21 if mobile else 23
    peak_keys = set(sorted(months, key=lambda key: months[key], reverse=True)[:3])
    for group_index, (group_name, group_years) in enumerate(groups):
        if not group_years:
            continue
        color = (CYAN, VIOLET, PINK)[group_index]
        body += t(24, y, group_name, 13 if mobile else 16, color, 800)
        body += t(w - 24, y, f'{sum(annual[year] for year in group_years):,}',
                  11 if mobile else 14, color, 700, "end")
        body += line(24, y + 6, w - 24, y + 6, color, 1, 'opacity=".4"')
        for month_index, name in enumerate(month_names):
            body += t(left + month_index * step + cell_width / 2, y + 25, name,
                      7 if mobile else 11, MUTED, 700, "middle")
        top = y + 37
        for row, year in enumerate(group_years):
            cell_y = top + row * row_step
            body += t(24, cell_y + 14, str(year) + ("*" if year == history["last_year"] else ""),
                      10 if mobile else 13, INK, 700)
            for month in range(1, 13):
                key = f"{year}-{month:02d}"
                if key not in months:
                    continue
                count = months[key]
                fill = ("#182a3d" if count == 0 else "#367789" if count < 100 else
                        CYAN if count < 250 else VIOLET if count < 500 else PINK)
                x = left + (month - 1) * step
                body += box(x, cell_y, cell_width, 17 if mobile else 19, fill, "none", 2)
                if key == history["observed_at"][:7]:
                    body += box(x, cell_y, cell_width, 17 if mobile else 19,
                                "none", ORANGE, 2,
                                'class="month-focus" stroke-width="1.5"')
                if key in peak_keys:
                    body += box(x, cell_y, cell_width, 17 if mobile else 19,
                                "none", LIME, 2,
                                f'class="peak-cell" stroke-width="1.7" style="animation-delay:-{month % 3 * 1.4}s"')
                if not mobile and count:
                    body += t(x + cell_width / 2, cell_y + 14, str(count), 9,
                              BASE if count >= 100 else INK, 700, "middle")
            body += t(w - 24, cell_y + 14, f'{annual[year]:,}',
                      10 if mobile else 13, color, 700, "end")
        y = top + len(group_years) * row_step + (18 if mobile else 22)
    summary_y = y + (7 if mobile else 8)
    if mobile:
        body += box(24, summary_y, w - 48, 66, PANEL, ORANGE, 6,
                    'class="metric-edge"')
        body += t(38, summary_y + 35, f'{annual[current_year]:,}', 30, ORANGE, 800)
        body += t(w - 38, summary_y + 27, f'{current_year} SO FAR', 12, INK, 700, "end")
        body += t(w - 38, summary_y + 48,
                  f'THROUGH {datetime.fromisoformat(history["observed_at"]).strftime("%d %b").upper()}',
                  9, MUTED, 700, "end")
        lower_y = summary_y + 76
        for x, value, label, color in (
                (24, f'{top_month_count:,}',
                 f'TOP MONTH · {datetime.strptime(top_month, "%Y-%m").strftime("%b %Y").upper()}', PINK),
                (216, str(top_year),
                 'TOP YEAR · PARTIAL' if top_year == current_year else 'TOP YEAR', LIME)):
            body += box(x, lower_y, 180, 65, PANEL, color, 6)
            body += t(x + 12, lower_y + 30, value, 22, color, 800)
            body += t(x + 12, lower_y + 52, label, 9, MUTED, 700)
    else:
        card_width = (w - 72) / 3
        highlights = (
            (f'{annual[current_year]:,}', f'{current_year} SO FAR · THROUGH '
             f'{datetime.fromisoformat(history["observed_at"]).strftime("%d %b").upper()}', ORANGE),
            (f'{top_month_count:,}',
             f'TOP MONTH · {datetime.strptime(top_month, "%Y-%m").strftime("%b %Y").upper()}', PINK),
            (str(top_year),
             'TOP YEAR · STILL IN PROGRESS' if top_year == current_year else 'TOP YEAR', LIME),
        )
        for index, (value, label, color) in enumerate(highlights):
            x = 24 + index * (card_width + 12)
            body += box(x, summary_y, card_width, 90, PANEL, color, 6,
                        'class="metric-edge"' if index == 0 else "")
            body += t(x + 14, summary_y + 46, value, 34, color, 800)
            body += t(x + 14, summary_y + 73, label, 12, MUTED, 700)
    body += line(24, h - (44 if mobile else 35), w - 24, h - (44 if mobile else 35))
    body += t(24, h - (26 if mobile else 16),
              f'* {history["last_year"]} through {datetime.fromisoformat(history["observed_at"]).strftime("%d %b")}; private activity included',
              9 if mobile else 11, MUTED)
    if mobile:
        body += t(24, h - 11, "Cell = month · right = year · lime = top 3 months", 9, MUTED)
    save("contributions", svg(
        w, h,
        f'Monthly GitHub contributions from {history["first_year"]} to {history["last_year"]}, '
        'with current-year and record highlights', body), mobile)


def as_of(value: str) -> str:
    moment = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    return moment.strftime("%d %b %Y %H:%M UTC")


def snapshot_label(value: str, max_age: timedelta) -> str:
    moment = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    prefix = "STALE · LAST VERIFIED" if datetime.now(timezone.utc) - moment > max_age else "AS OF"
    return f"{prefix} {as_of(value)}"


def render_adsb(mobile: bool, data: dict | None = None) -> None:
    w, h = (420, 634) if mobile else (1000, 355)
    body = heading(w, "AVIATION / ADS-B", "04", mobile)
    body += t(24, 82, "AIRCRAFT RADIO, HEARD FROM HOME", 13 if mobile else 17, INK, 700)
    body += t(24, 105, "Local receiver counts · not tracking-site totals", 10 if mobile else 13, MUTED)
    cx, cy, r = (105, 198, 70) if mobile else (132, 208, 83)
    for radius in (.35, .68, 1):
        body += f'<circle cx="{cx}" cy="{cy}" r="{r*radius:.1f}" fill="none" stroke="{LIME}" opacity=".55"/>'
    body += line(cx-r, cy, cx+r, cy, LIME, 1, 'opacity=".45"') + line(cx, cy-r, cx, cy+r, LIME, 1, 'opacity=".45"')
    lead_x = cx + r * math.cos(math.radians(15))
    lead_y = cy - r * math.sin(math.radians(15))
    beam_edge = line(cx, cy, lead_x, lead_y, LIME, 2, 'opacity=".7"')
    body += (f'<g class="sweep" style="transform-box:view-box;transform-origin:{cx}px {cy}px">'
             f'<path d="M {cx} {cy} L {cx} {cy-r} A {r} {r} 0 0 1 '
             f'{lead_x:.1f} {lead_y:.1f} Z" fill="{LIME}" opacity=".28"/>'
             f'{beam_edge}'
             '</g>')
    body += f'<circle cx="{cx+r*.35:.1f}" cy="{cy-r*.18:.1f}" r="4" fill="{PINK}" class="blink"/>'
    if mobile:
        body += t(202, 164, "HOME RECEIVER", 13, LIME, 700)
        body += t(202, 188, "Picks up aircraft", 11, MUTED)
        body += t(202, 205, "radio broadcasts.", 11, MUTED)
        body += t(202, 238, "Shared with flight", 11, MUTED)
        body += t(202, 255, "tracking networks.", 11, MUTED)
    else:
        body += t(258, 131, "RECEIVER SNAPSHOT", 12, LIME, 700)
    if data:
        if data.get("schema_version") == 2:
            metrics = [
                (f'{data["aircraft_seen_last_30_minutes"]:,}', "AIRCRAFT / 30M", LIME,
                 "Distinct aircraft heard", "in the past 30 minutes."),
                (f'{data["aircraft_seen_last_60_seconds"]:,}', "AIRCRAFT / 60S", CYAN,
                 f'{data["aircraft_with_positions_last_60_seconds"]:,} with a position',
                 "in this one-minute sample."),
                (f'{data["messages_last_15_minutes"]:,}', "MESSAGES / 15M", PINK,
                 "Radio broadcasts received;", "not a count of flights."),
            ]
        else:
            metrics = [
                (f'{data["aircraft_seen_last_60_seconds"]:,}', "AIRCRAFT HEARD", LIME,
                 "Distinct aircraft heard", "in 60s before snapshot."),
                (f'{data["aircraft_with_positions_last_60_seconds"]:,}', "RECENT POSITION", CYAN,
                 "Of those, with a position", "in the same 60 seconds."),
                (f'{data["messages_last_15_minutes"]:,}', "RADIO MESSAGES", PINK,
                 "Broadcasts received in", "15 minutes; not flights."),
            ]
        for index, (value, label, color, detail_1, detail_2) in enumerate(metrics):
            if mobile:
                y = 288 + index * 96
                body += box(24, y, 372, 84, PANEL, color, 6)
                body += t(39, y + 49, value, 24 if index == 2 else 29, color, 800)
                body += t(190, y + 24, label, 12, INK, 700)
                body += t(190, y + 46, detail_1, 10, MUTED)
                body += t(190, y + 63, detail_2, 10, MUTED)
            else:
                x = 258 + index * 239
                body += box(x, 146, 221, 132, PANEL, color, 6)
                body += t(x + 15, 186, value, 27, color, 800)
                body += t(x + 15, 210, label, 12, INK, 700)
                body += t(x + 15, 240, detail_1, 11, MUTED)
                body += t(x + 15, 259, detail_2, 11, MUTED)
        body += t(24 if mobile else 258, 585 if mobile else 310,
                  "LOCAL RECEIVER · " + snapshot_label(data["observed_at"], timedelta(hours=2)),
                  9 if mobile else 11, MUTED)
    else:
        body += t(24 if mobile else 258, 332 if mobile else 185,
                  "Receiver snapshot being connected", 12 if mobile else 16, LIME)
    if mobile:
        body += t(24, 611, "FEEDER STATISTICS  ↓  LINKS BELOW", 10, ORANGE, 700)
    else:
        body += t(258, 334, "FEEDER STATISTICS  ↓  LINKS BELOW", 11, ORANGE, 700)
    title = "Home ADS-B receiver aggregate snapshot" if data else "Home ADS-B receiver telemetry preview; live source pending"
    save("adsb", svg(w, h, title, body), mobile)


def render_adsb_links(mobile: bool) -> None:
    links = (("FLIGHTAWARE", "FLIGHTAWARE", CYAN),
             ("FLIGHTRADAR24", "FR24", VIOLET),
             ("ADS-B EXCHANGE", "ADS-B EXCHANGE", PINK))
    w, h = (140, 50) if mobile else (333, 50)
    for index, (label, short_label, color) in enumerate(links, 1):
        body = box(6, 4, w - 12, h - 8, PANEL, color, 5)
        body += t(w / 2, 31, f'↗ {short_label if mobile else label}',
                  11 if mobile else 14, color, 700, "middle")
        save(f"adsb-link-{index}", svg(w, h, f'{label} feeder statistics', body,
                                      left=index == 1, right=index == 3), mobile)


ARCHIVED_SMON_DEPLOYMENTS = 6_963


def render_smon(mobile: bool, data: dict | None = None) -> None:
    w, h = (420, 418) if mobile else (1000, 316)
    body = heading(w, "SMON / OPERATIONS", "03", mobile)
    body += t(24, 83, "$ smon status", 16 if mobile else 20, ORANGE, 700)
    body += t(w - 24, 83, "IN PRODUCTION SINCE 2016", 10 if mobile else 13,
              LIME, 700, "end")
    metrics = [
        (f'{data["services_healthy"]}/{data["services_monitored"]}' if data else "—",
         "SERVICES HEALTHY", LIME),
        (str(data["active_projects"]) if data else "—", "ACTIVE PROJECTS", CYAN),
        (str(data["successful_deployments_last_30_days"]) if data else "—",
         "DEPLOYS / 30D", ORANGE),
        (f'{data["monitoring_checks_last_24_hours"]:,}' if data and
         "monitoring_checks_last_24_hours" in data else "—",
         "MONITORING CHECKS / 24H", VIOLET),
    ]
    for index, (value, label, color) in enumerate(metrics):
        if mobile:
            x, y, width = 24 + (index % 2) * 192, 102 + (index // 2) * 84, 180
            font_size = 27
        else:
            x, y, width = 24 + index * 241, 101, 229
            font_size = 33
        body += box(x, y, width, 72, PANEL, color, 6)
        body += t(x + 12, y + 37, value, font_size, color, 800)
        body += t(x + 12, y + 59, label, 9 if mobile else 11, MUTED, 700)
    current_total = data.get("successful_deployments_total") if data else None
    total_label = (f'{ARCHIVED_SMON_DEPLOYMENTS + current_total:,}' if current_total is not None
                   else f'{ARCHIVED_SMON_DEPLOYMENTS:,}+')
    caption = ("SUCCESSFUL DEPLOYMENTS · ALL INSTANCES" if current_total is not None
               else "VERIFIED DEPLOYMENTS · CURRENT TOTAL PENDING")
    banner_y = 285 if mobile else 192
    body += box(24, banner_y, w - 48, 86, PANEL, ORANGE, 6,
                'class="metric-edge"')
    body += t(40, banner_y + 49, total_label, 39 if mobile else 44, ORANGE, 800)
    body += t(40 if mobile else 440, banner_y + (70 if mobile else 48), caption,
              10 if mobile else 14, MUTED, 700)
    if data:
        body += t(24, 403 if mobile else 297,
                  f'CURRENT INSTANCE · {snapshot_label(data["generated_at"], timedelta(hours=2))}',
                  9 if mobile else 12, MUTED)
    save("smon", svg(w, h, "SMON operations and successful deployments since 2016", body), mobile)


PROJECTS = [
    ("SMON", "Infrastructure health, releases and deployment coordination.", "RAILS · HOTWIRE · POSTGRESQL"),
    ("LESSON LOOP", "Practice and learning platform for teachers and students.", "RAILS 8 · HOTWIRE · PWA"),
    ("GPS MAP", "Location-aware mapping for remote terrain and ski resorts.", "POSTGIS · LEAFLET · SWIFT"),
    ("HOLLY KATHLEEN", "Long-lived business workflow and operations platform.", "RAILS · POSTGRESQL · HOTWIRE"),
]


def render_project(i: int, mobile: bool) -> None:
    w, h = (420, 155) if mobile else (1000, 160)
    name, description, stack = PROJECTS[i]
    color = ACCENTS[i]
    body = box(10, 8, w - 20, h - 16, PANEL, color, 6)
    body += box(10, 8, 5, h - 16, color, color, 0)
    body += t(25, 37, f"0{i+1}  /  {name}", 17 if mobile else 22, color, 800)
    if mobile:
        for row, phrase in enumerate(textwrap.wrap(description, width=43)):
            body += t(25, 67 + row * 19, phrase, 11, INK)
        body += t(25, 126, stack, 10, ORANGE, 700)
    else:
        body += t(25, 82, description, 14, INK)
        body += t(25, 136, stack, 12, ORANGE, 700)
    body += t(w - 27, 37, "↗", 21, color, 700, "end",
              f'class="arrow-drift" style="animation-delay:-{(i + 1) * 1.5}s"')
    save(f"project-{i+1}", svg(w, h, f"{name}: {description}", body), mobile)


def render_projects(mobile: bool) -> None:
    w, h = (420, 70) if mobile else (1000, 78)
    save("projects", svg(w, h, "Selected projects", heading(w, "SELECTED SYSTEMS", "05", mobile)), mobile)
    for i in range(4):
        render_project(i, mobile)


def render_stack(mobile: bool) -> None:
    w, h = (420, 306) if mobile else (1000, 239)
    body = heading(w, "TOOLS I REACH FOR", "06", mobile)
    rows = [
        ("BUILD", ("Ruby", "Rails", "Hotwire", "Turbo", "Stimulus")),
        ("MOBILE", ("Hotwire Native", "Swift", "Kotlin")),
        ("SYSTEMS", ("PostgreSQL", "PostGIS", "Redis", "Linux")),
        ("SHIP", ("Docker", "Kamal", "GitHub Actions", "APIs")),
    ]
    for i, (label, values) in enumerate(rows):
        color = ACCENTS[i]
        if mobile:
            body += t(24, 82 + i * 53, label, 11, color, 700)
            x, top, font_size, padding, gap = 24, 91 + i * 53, 11, 8, 7
        else:
            body += t(24, 89 + i * 39, label, 13, color, 700)
            x, top, font_size, padding, gap = 180, 70 + i * 39, 13, 11, 9
        for value in values:
            width = round(len(value) * font_size * .62 + padding * 2)
            body += box(x, top, width, 27, BASE, color, 4)
            body += t(x + padding, top + 18, value, font_size, INK, 700)
            x += width + gap
    save("stack", svg(w, h, "Curated technology stack", body), mobile)


def render_footer(mobile: bool) -> None:
    w, h = (420, 118) if mobile else (1000, 122)
    body = line(24, 16, w - 24, 16)
    body += t(24, 55, "END OF TRANSMISSION // 73", 13 if mobile else 17, CYAN, 700)
    body += t(24, 84, "Console inspired by Giorgi Kobaidze.", 10 if mobile else 13, MUTED)
    save("footer", svg(w, h, "End of transmission; console design credit to Giorgi Kobaidze", body, bottom=True), mobile)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=DATA)
    parser.add_argument("--smon-data", type=Path, default=SMON_DATA)
    parser.add_argument("--adsb-data", type=Path, default=ADSB_DATA)
    parser.add_argument("--history-data", type=Path, default=HISTORY_DATA)
    parser.add_argument("--languages-data", type=Path, default=LANGUAGES_DATA)
    args = parser.parse_args()
    github_data = json.loads(args.data.read_text(encoding="utf-8"))
    user = github_data["data"]["user"]
    smon_data = json.loads(args.smon_data.read_text(encoding="utf-8")) if args.smon_data.is_file() else None
    adsb_data = json.loads(args.adsb_data.read_text(encoding="utf-8")) if args.adsb_data.is_file() else None
    history_data = json.loads(args.history_data.read_text(encoding="utf-8"))
    language_data = json.loads(args.languages_data.read_text(encoding="utf-8")) if args.languages_data.is_file() else None
    for mobile in (False, True):
        render_header(mobile)
        render_stats(user, mobile, github_data.get("fetched_at"), history_data, language_data)
        render_history(history_data, mobile)
        render_smon(mobile, smon_data)
        render_adsb(mobile, adsb_data)
        render_adsb_links(mobile)
        render_projects(mobile)
        render_stack(mobile)
        render_footer(mobile)


if __name__ == "__main__":
    main()
