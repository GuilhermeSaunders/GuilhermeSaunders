"""Generate assets/contributions.svg: a neon contribution heatmap with a wave animation.

Usage (PowerShell):
    $env:GITHUB_TOKEN = gh auth token
    python scripts/generate_heatmap.py

Needs only the standard library. The token is read from GITHUB_TOKEN and never written anywhere.
"""

import json
import os
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

LOGIN = os.environ.get("GITHUB_USER", "GuilhermeSaunders")
OUT = Path(__file__).resolve().parent.parent / "assets" / "contributions.svg"

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date weekday contributionCount contributionLevel } }
      }
    }
  }
}
"""

# Resting colour and wave-peak colour for each GitHub contribution level.
LEVELS = {
    "NONE": ("#161b22", "#1f9a3a"),
    "FIRST_QUARTILE": ("#0f5a24", "#39ff14"),
    "SECOND_QUARTILE": ("#17a83a", "#6dff4f"),
    "THIRD_QUARTILE": ("#2bd94f", "#a6ff8f"),
    "FOURTH_QUARTILE": ("#39ff14", "#d4ffc9"),
}

CELL, GAP = 12, 3
PITCH = CELL + GAP
LEFT, TOP, RIGHT = 40, 70, 24
WAVE_SECONDS = 4.5
WAVE_STEP = 0.045  # delay between neighbouring columns


def fetch_calendar(token):
    body = json.dumps({"query": QUERY, "variables": {"login": LOGIN}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        payload = json.load(resp)
    if "errors" in payload:
        raise SystemExit(f"GraphQL error: {payload['errors']}")
    return payload["data"]["user"]["contributionsCollection"]["contributionCalendar"]


def month_labels(weeks):
    labels, last_month, last_col = [], None, -10
    for col, week in enumerate(weeks):
        month = date.fromisoformat(week["contributionDays"][0]["date"]).month
        if month != last_month:
            if col - last_col >= 3:
                labels.append((col, date(2000, month, 1).strftime("%b")))
                last_col = col
            last_month = month
    return labels


def build_svg(calendar):
    weeks = calendar["weeks"]
    total = calendar["totalContributions"]
    width = LEFT + len(weeks) * PITCH - GAP + RIGHT
    grid_bottom = TOP + 7 * PITCH - GAP
    height = grid_bottom + 46
    font = "ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"

    level_keys = list(LEVELS)
    css = [
        f"text{{font-family:{font};fill:#8b949e;font-size:11px}}",
        ".title{fill:#39ff14;font-size:14px;font-weight:700}",
        f".d{{animation:{WAVE_SECONDS}s ease-in-out infinite both;"
        "transform-box:fill-box;transform-origin:center}",
    ]
    for i, key in enumerate(level_keys):
        rest, peak = LEVELS[key]
        css.append(f".l{i}{{fill:{rest};animation-name:w{i}}}")
        css.append(
            f"@keyframes w{i}{{0%,16%,100%{{fill:{rest};transform:scale(1)}}"
            f"7%{{fill:{peak};transform:scale(1.22)}}}}"
        )
    for col in range(len(weeks)):
        css.append(f".c{col}{{animation-delay:{col * WAVE_STEP:.3f}s}}")
    css.append("@media (prefers-reduced-motion:reduce){.d{animation:none}}")

    cells = []
    for col, week in enumerate(weeks):
        x = LEFT + col * PITCH
        for day in week["contributionDays"]:
            y = TOP + day["weekday"] * PITCH
            lvl = level_keys.index(day["contributionLevel"])
            cells.append(f'<rect class="d l{lvl} c{col}" x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2"/>')

    months = "".join(
        f'<text x="{LEFT + col * PITCH}" y="{TOP - 8}">{name}</text>' for col, name in month_labels(weeks)
    )
    weekdays = "".join(
        f'<text x="{LEFT - 8}" y="{TOP + row * PITCH + CELL - 2}" text-anchor="end">{name}</text>'
        for row, name in ((1, "Mon"), (3, "Wed"), (5, "Fri"))
    )

    legend_x = width - RIGHT - 5 * PITCH + GAP - 36  # leave room for "More"
    legend_y = grid_bottom + 20
    legend = "".join(
        f'<rect x="{legend_x + i * PITCH}" y="{legend_y}" width="{CELL}" height="{CELL}" rx="2" fill="{LEVELS[k][0]}"/>'
        for i, k in enumerate(level_keys)
    )
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{total} GitHub contributions in the last year">
<style>{''.join(css)}</style>
<defs><filter id="glow" x="-5%" y="-20%" width="110%" height="140%"><feGaussianBlur stdDeviation="2.2" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>
<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="10" fill="#0d1117" stroke="#1f3d2a"/>
<text class="title" x="{LEFT}" y="32">$ git log --since="1 year ago"</text>
<text x="{width - RIGHT}" y="32" text-anchor="end"><tspan fill="#39ff14" font-weight="700">{total}</tspan> contributions in the last year</text>
{months}{weekdays}
<g filter="url(#glow)">{''.join(cells)}</g>
<text x="{LEFT}" y="{legend_y + 10}">updated {updated}</text>
<text x="{legend_x - 8}" y="{legend_y + 10}" text-anchor="end">Less</text>{legend}<text x="{legend_x + 5 * PITCH + 3}" y="{legend_y + 10}">More</text>
</svg>
"""


def main():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("Set GITHUB_TOKEN first (locally: $env:GITHUB_TOKEN = gh auth token)")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build_svg(fetch_calendar(token)), encoding="utf-8")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
