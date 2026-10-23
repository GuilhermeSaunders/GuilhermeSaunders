"""Generate the profile cards for the last 12 months:
    assets/contributions.svg   contribution heatmap with a wave animation
    assets/activity.svg        activity overview (commits, pull requests, issues, code review)

Usage (PowerShell):
    $env:GITHUB_TOKEN = gh auth token
    python scripts/generate_heatmap.py              # theme from HEATMAP_THEME, default "light-green"
    python scripts/generate_heatmap.py --preview    # every theme into preview/ (git-ignored)

Needs only the standard library. The token is read from GITHUB_TOKEN and never written anywhere.
"""

import base64
import hashlib
import json
import os
import re
import sys
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

LOGIN = os.environ.get("GITHUB_USER", "GuilhermeSaunders")
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "contributions.svg"
OUT_ACTIVITY = ROOT / "assets" / "activity.svg"
README = ROOT / "README.md"
PREVIEW = ROOT / "preview"

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      totalPullRequestReviewContributions
      totalRepositoriesWithContributedCommits
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
    "light-green": {  # GitHub's classic contribution colours
        "rest": ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"],
        "peak": ["#9be9a8", "#40c463", "#30a14e", "#216e39", "#0f4d24"],
        "accent": "#1a7f37",
        "border": "#1f2328",
        "bg": "#ffffff",
        "text": "#57606a",
        "glow": False,
        "frame": "#1f2328",
        "cell_stroke": "rgba(31,35,40,0.10)",
    },
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
WAVE_SECONDS = 8
WAVE_STEP = 0.09  # delay between neighbouring columns


def fetch_collection(token):
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
    return payload["data"]["user"]["contributionsCollection"]


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


def build_activity_svg(collection, theme):
    """Activity overview like GitHub's: a cross with one arm per contribution type, plus bars with the counts."""
    t = {**THEME_DEFAULTS, **THEMES[theme]}
    width, height = 868, 300
    font = "ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"
    stats = [  # (label, count, axis direction)
        ("Commits", collection["totalCommitContributions"], (-1, 0)),
        ("Pull requests", collection["totalPullRequestContributions"], (0, 1)),
        ("Issues", collection["totalIssueContributions"], (1, 0)),
        ("Code review", collection["totalPullRequestReviewContributions"], (0, -1)),
    ]
    total = sum(count for _, count, _ in stats) or 1
    cx, cy, r = 250, 166, 70

    axes, labels, dots, points = [], [], [], []
    for label, count, (dx, dy) in stats:
        pct = count / total
        axes.append(f'<line x1="{cx}" y1="{cy}" x2="{cx + dx * r}" y2="{cy + dy * r}"/>')
        px, py = cx + dx * r * pct, cy + dy * r * pct
        points.append(f"{px:.1f},{py:.1f}")
        if count:
            dots.append(f'<circle class="dot" cx="{px:.1f}" cy="{py:.1f}" r="4"/>')
        pct_text = f'<tspan class="pct">{pct:.0%}</tspan>' if count else ""
        if dx:  # left / right: percentage above the label
            x, anchor = cx + dx * (r + 14), "end" if dx < 0 else "start"
            labels.append(f'<text x="{x}" y="{cy - 4}" text-anchor="{anchor}">{pct_text}</text>')
            labels.append(f'<text x="{x}" y="{cy + 12 if count else cy + 4}" text-anchor="{anchor}">{label}</text>')
        elif dy < 0:  # top
            labels.append(f'<text x="{cx}" y="{cy - r - 26}" text-anchor="middle">{pct_text}</text>')
            labels.append(f'<text x="{cx}" y="{cy - r - 12}" text-anchor="middle">{label}</text>')
        else:  # bottom
            labels.append(f'<text x="{cx}" y="{cy + r + 20}" text-anchor="middle">{pct_text}</text>')
            labels.append(f'<text x="{cx}" y="{cy + r + 34}" text-anchor="middle">{label}</text>')

    bar_x, bar_w = 500, 320
    bars = []
    for i, (label, count, _) in enumerate(stats):
        y = 110 + i * 44
        fill = bar_w * count / total
        bars.append(
            f'<text x="{bar_x}" y="{y}">{label}</text>'
            f'<text x="{bar_x + bar_w}" y="{y}" text-anchor="end"><tspan class="pct">{count}</tspan></text>'
            f'<rect x="{bar_x}" y="{y + 8}" width="{bar_w}" height="8" rx="4" fill="{t["rest"][0]}"/>'
            + (f'<rect class="bar" x="{bar_x}" y="{y + 8}" width="{fill:.1f}" height="8" rx="4"/>' if count else "")
        )

    frame_stroke = t["frame"] or t["border"]
    css = (
        f"text{{font-family:{font};fill:{t['text']};font-size:12px}}"
        f".title{{fill:{t['accent']};font-size:14px;font-weight:700}}"
        f".pct{{fill:{t['accent']};font-weight:700}}"
        f".axes line{{stroke:{t['accent']};stroke-width:2;stroke-linecap:round}}"
        f".area{{fill:{t['rest'][2]};fill-opacity:.55;stroke:{t['accent']};stroke-width:2;stroke-linejoin:round;"
        f"transform-origin:{cx}px {cy}px;animation:grow 1.2s cubic-bezier(.2,.8,.2,1) both}}"
        f".dot{{fill:{t['bg']};stroke:{t['accent']};stroke-width:2;transform-box:fill-box;transform-origin:center;"
        "animation:pulse 2.4s ease-in-out 1.2s infinite}"
        f".bar{{fill:{t['accent']};transform-box:fill-box;transform-origin:left;animation:fill 1.2s cubic-bezier(.2,.8,.2,1) both}}"
        "@keyframes grow{from{transform:scale(0)}to{transform:scale(1)}}"
        "@keyframes fill{from{transform:scaleX(0)}to{transform:scaleX(1)}}"
        "@keyframes pulse{0%,100%{transform:scale(1)}50%{transform:scale(1.35)}}"
        "@media (prefers-reduced-motion:reduce){.area,.dot,.bar{animation:none}}"
    )
    repos = collection["totalRepositoriesWithContributedCommits"]

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Activity overview: {', '.join(f'{c} {l.lower()}' for l, c, _ in stats)}">
<style>{css}</style>
<rect x="1" y="1" width="{width - 2}" height="{height - 2}" rx="10" fill="{t['bg']}" stroke="{t['border']}" stroke-width="2"/>
<text class="title" x="41" y="34">$ git shortlog --summary --since="1 year ago"</text>
<text x="827" y="34" text-anchor="end"><tspan class="pct">{repos}</tspan> repositories contributed to</text>
<rect x="41" y="52" width="786" height="{height - 72}" rx="6" fill="none" stroke="{frame_stroke}"/>
<line x1="460" y1="70" x2="460" y2="{height - 38}" stroke="{frame_stroke}"/>
<g class="axes">{''.join(axes)}</g>
<polygon class="area" points="{' '.join(points)}"/>
{''.join(dots)}{''.join(labels)}{''.join(bars)}
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
    collection = fetch_collection(token)
    calendar = collection["contributionCalendar"]

    if "--preview" in sys.argv:
        write(PREVIEW / "index.html", preview_page(calendar))
        return

    theme = os.environ.get("HEATMAP_THEME", "light-green")
    write(OUT, build_svg(calendar, theme))
    write(OUT_ACTIVITY, build_activity_svg(collection, theme))
    version_image_links()


def version_image_links():
    """Point README at ?v=<content hash> so browsers never show a cached old card."""
    text = README.read_text(encoding="utf-8")
    for path in (OUT, OUT_ACTIVITY):
        version = hashlib.sha1(path.read_bytes()).hexdigest()[:8]
        pattern = re.compile(rf'assets/{re.escape(path.name)}(\?v=[0-9a-f]+)?"')
        text = pattern.sub(f'assets/{path.name}?v={version}"', text)
    write(README, text)


if __name__ == "__main__":
    main()
