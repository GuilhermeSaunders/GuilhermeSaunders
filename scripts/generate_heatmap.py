"""Generate assets/contributions.svg: a contribution heatmap of the last 12 months with a wave animation.

Usage (PowerShell):
    $env:GITHUB_TOKEN = gh auth token
    python scripts/generate_heatmap.py              # theme from HEATMAP_THEME, default "light-blue"
    python scripts/generate_heatmap.py --preview    # every theme into preview/ (git-ignored)

Needs only the standard library. The token is read from GITHUB_TOKEN and never written anywhere.
"""

import base64
import json
import os
import sys
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

LOGIN = os.environ.get("GITHUB_USER", "GuilhermeSaunders")
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "contributions.svg"
PREVIEW = ROOT / "preview"

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

LEVEL_KEYS = ["NONE", "FIRST_QUARTILE", "SECOND_QUARTILE", "THIRD_QUARTILE", "FOURTH_QUARTILE"]

# Per theme: resting colour and wave-peak colour for each level, plus card colours.
# Optional keys: bg, text, glow, frame (inner border around the grid), cell_stroke (outline of each day).
THEMES = {
    "light-blue": {
        "rest": ["#ebedf0", "#b6d4fe", "#6ea8fe", "#2f7cf6", "#0b4fc4"],
        "peak": ["#9ec5fe", "#3b8cff", "#1a6cf0", "#0b55d0", "#05348a"],
        "accent": "#0969da",
        "border": "#54aeff",
        "bg": "#ffffff",
        "text": "#57606a",
        "glow": False,
        "frame": "#d0d7de",
        "cell_stroke": "rgba(31,35,40,0.10)",
    },
    "green": {
        "rest": ["#161b22", "#0f5a24", "#17a83a", "#2bd94f", "#39ff14"],
        "peak": ["#1f9a3a", "#39ff14", "#6dff4f", "#a6ff8f", "#d4ffc9"],
        "accent": "#39ff14",
        "border": "#1f3d2a",
    },
    "cyan": {
        "rest": ["#161b22", "#0b4f5c", "#0e8fa3", "#19c8e0", "#3ef2ff"],
        "peak": ["#1a7f8f", "#3ef2ff", "#6ff5ff", "#a8faff", "#dcfdff"],
        "accent": "#3ef2ff",
        "border": "#163a40",
    },
    "blue": {
        "rest": ["#161b22", "#0d3b75", "#1a63c4", "#3b8cff", "#79b8ff"],
        "peak": ["#2a5fa8", "#79b8ff", "#9cc9ff", "#c2ddff", "#e6f1ff"],
        "accent": "#58a6ff",
        "border": "#1b2f4d",
    },
    "purple": {
        "rest": ["#161b22", "#3b1f6b", "#6a35c2", "#9b5cff", "#c49bff"],
        "peak": ["#5b3a9a", "#c49bff", "#d3b3ff", "#e3ceff", "#f3e9ff"],
        "accent": "#b388ff",
        "border": "#2e2347",
    },
    "amber": {
        "rest": ["#161b22", "#5c3b06", "#a86a0a", "#f0a020", "#ffcc4d"],
        "peak": ["#8a5a10", "#ffcc4d", "#ffd970", "#ffe7a3", "#fff4d6"],
        "accent": "#ffb84d",
        "border": "#3d2e12",
    },
}
THEME_DEFAULTS = {"bg": "#0d1117", "text": "#8b949e", "glow": True, "frame": None, "cell_stroke": None}

CELL, GAP = 12, 3
PITCH = CELL + GAP
LEFT, TOP, RIGHT = 48, 78, 28
FRAME_PAD = 7  # space between the inner frame and the cells
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


def build_svg(calendar, theme):
    t = {**THEME_DEFAULTS, **THEMES[theme]}
    weeks = calendar["weeks"]
    total = calendar["totalContributions"]
    grid_right = LEFT + len(weeks) * PITCH - GAP
    grid_bottom = TOP + 7 * PITCH - GAP
    width = grid_right + RIGHT
    height = grid_bottom + 56
    font = "ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"

    css = [
        f"text{{font-family:{font};fill:{t['text']};font-size:11px}}",
        f".title{{fill:{t['accent']};font-size:14px;font-weight:700}}",
        f".d{{animation:{WAVE_SECONDS}s ease-in-out infinite both;"
        "transform-box:fill-box;transform-origin:center}",
    ]
    if t["cell_stroke"]:
        css.append(f".d,.k{{stroke:{t['cell_stroke']};stroke-width:1}}")
    for i, (rest, peak) in enumerate(zip(t["rest"], t["peak"])):
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
            lvl = LEVEL_KEYS.index(day["contributionLevel"])
            cells.append(f'<rect class="d l{lvl} c{col}" x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2"/>')

    months = "".join(
        f'<text x="{LEFT + col * PITCH}" y="{TOP - FRAME_PAD - 6}">{name}</text>' for col, name in month_labels(weeks)
    )
    weekdays = "".join(
        f'<text x="{LEFT - FRAME_PAD - 6}" y="{TOP + row * PITCH + CELL - 2}" text-anchor="end">{name}</text>'
        for row, name in ((1, "Mon"), (3, "Wed"), (5, "Fri"))
    )

    frame = ""
    if t["frame"]:
        frame = (
            f'<rect x="{LEFT - FRAME_PAD}" y="{TOP - FRAME_PAD}" width="{grid_right - LEFT + 2 * FRAME_PAD}" '
            f'height="{grid_bottom - TOP + 2 * FRAME_PAD}" rx="6" fill="none" stroke="{t["frame"]}"/>'
        )

    legend_x = grid_right - 5 * PITCH + GAP - 36  # leave room for "More"
    legend_y = grid_bottom + FRAME_PAD + 16
    legend = "".join(
        f'<rect class="k" x="{legend_x + i * PITCH}" y="{legend_y}" width="{CELL}" height="{CELL}" rx="2" fill="{rest}"/>'
        for i, rest in enumerate(t["rest"])
    )
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    glow = ' filter="url(#glow)"' if t["glow"] else ""

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{total} GitHub contributions in the last year">
<style>{''.join(css)}</style>
<defs><filter id="glow" x="-5%" y="-20%" width="110%" height="140%"><feGaussianBlur stdDeviation="2.2" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>
<rect x="1" y="1" width="{width - 2}" height="{height - 2}" rx="10" fill="{t['bg']}" stroke="{t['border']}" stroke-width="2"/>
<text class="title" x="{LEFT - FRAME_PAD}" y="34">$ git log --since="1 year ago"</text>
<text x="{grid_right + FRAME_PAD}" y="34" text-anchor="end"><tspan fill="{t['accent']}" font-weight="700">{total}</tspan> contributions in the last year</text>
{months}{weekdays}{frame}
<g{glow}>{''.join(cells)}</g>
<text x="{LEFT - FRAME_PAD}" y="{legend_y + 10}">updated {updated}</text>
<text x="{legend_x - 8}" y="{legend_y + 10}" text-anchor="end">Less</text>{legend}<text x="{legend_x + 5 * PITCH + 3}" y="{legend_y + 10}">More</text>
</svg>
"""


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    print(f"Wrote {path.relative_to(ROOT)}")


def preview_page(calendar):
    """One self-contained page with every theme, for picking a colour."""
    sections = []
    for i, theme in enumerate(THEMES, 1):
        svg = base64.b64encode(build_svg(calendar, theme).encode()).decode()
        sections.append(
            f'<section><h2>{i} · {theme}</h2><img src="data:image/svg+xml;base64,{svg}" alt="{theme}"></section>'
        )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Heatmap themes</title><style>'
        "body{margin:0;padding:24px;background:#0d1117;font:14px ui-monospace,Consolas,monospace}"
        "section{max-width:900px;margin:0 auto 28px}h2{font-size:15px;margin:0 0 8px;color:#8b949e}"
        "img{width:100%;display:block}</style></head><body>" + "".join(sections) + "</body></html>\n"
    )


def main():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("Set GITHUB_TOKEN first (locally: $env:GITHUB_TOKEN = gh auth token)")
    calendar = fetch_calendar(token)

    if "--preview" in sys.argv:
        write(PREVIEW / "index.html", preview_page(calendar))
        return

    write(OUT, build_svg(calendar, os.environ.get("HEATMAP_THEME", "light-blue")))


if __name__ == "__main__":
    main()
