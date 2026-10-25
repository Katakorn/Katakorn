"""Fetch GitHub stats (private included when the token allows) and render animated SVG cards.

Env:
  GH_TOKEN       token used for the GraphQL API (a PAT with `repo` + `read:user` sees private data)
  GH_USER        login to fall back to when the token cannot query `viewer`
  OUT_DIR        output directory (default: assets)
  EXCLUDE_LANGS  comma separated languages to hide from the language card
"""
import datetime as dt
import html
import json
import os
import pathlib
import urllib.request

API = "https://api.github.com/graphql"

BG = "#0d1117"
PANEL = "#161b22"
BORDER = "#30363d"
FG = "#e6edf3"
MUTED = "#8b949e"
SANS = "'Segoe UI',Ubuntu,'Helvetica Neue',Arial,sans-serif"
REDUCED = "@media (prefers-reduced-motion: reduce){*{animation:none!important}}"

_S = 'fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"'
ICONS = {
    "activity": f'<path {_S} d="M3 12h4l3 8l4-16l3 8h4"/>',
    "commit": f'<path {_S} d="M9 12a3 3 0 1 0 6 0a3 3 0 1 0-6 0m3-9v6m0 6v6"/>',
    "pr": f'<g {_S}><path d="M4 18a2 2 0 1 0 4 0a2 2 0 1 0-4 0M4 6a2 2 0 1 0 4 0a2 2 0 1 0-4 0m12 12a2 2 0 1 0 4 0a2 2 0 1 0-4 0M6 8v8"/><path d="M11 6h5a2 2 0 0 1 2 2v8"/><path d="m14 9l-3-3l3-3"/></g>',
    "issue": f'<g {_S}><path d="M11 12a1 1 0 1 0 2 0a1 1 0 1 0-2 0"/><path d="M3 12a9 9 0 1 0 18 0a9 9 0 1 0-18 0"/></g>',
    "review": f'<g {_S}><path d="M10 12a2 2 0 1 0 4 0a2 2 0 0 0-4 0"/><path d="M11.102 17.957Q6.297 17.495 3 12q3.6-6 9-6t9 6a20 20 0 0 1-.663 1.032M15 19l2 2l4-4"/></g>',
    "repo": f'<g {_S}><path d="M19 4v16H7a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z"/><path d="M19 16H7a2 2 0 0 0-2 2M9 8h6"/></g>',
    "star": f'<path {_S} d="m12 17.75l-6.172 3.245l1.179-6.873l-5-4.867l6.9-1l3.086-6.253l3.086 6.253l6.9 1l-5 4.867l1.179 6.873z"/>',
    "users": f'<path {_S} d="M5 7a4 4 0 1 0 8 0a4 4 0 1 0-8 0M3 21v-2a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v2m1-17.87a4 4 0 0 1 0 7.75M21 21v-2a4 4 0 0 0-3-3.85"/>',
    "flame": f'<path {_S} d="M12 10.941c2.333-3.308.167-7.823-1-8.941c0 3.395-2.235 5.299-3.667 6.706C5.903 10.114 5 12 5 14.294C5 17.998 8.134 21 12 21s7-3.002 7-6.706c0-1.712-1.232-4.403-2.333-5.588c-2.084 3.353-3.257 3.353-4.667 2.235"/>',
    "trophy": f'<path {_S} d="M8 21h8m-4-4v4M7 4h10m0 0v8a5 5 0 0 1-10 0V4M3 9a2 2 0 1 0 4 0a2 2 0 1 0-4 0m14 0a2 2 0 1 0 4 0a2 2 0 1 0-4 0"/>',
    "calendar": f'<g {_S}><path d="M4 7a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2zm12-4v4M8 3v4m-4 4h16"/><path d="M8 15h2v2H8z"/></g>',
    "code": f'<path {_S} d="m7 8l-4 4l4 4m10-8l4 4l-4 4M14 4l-4 16"/>',
}


# ------------------------------------------------------------------ fetching
def gql(token, query, variables=None):
    req = urllib.request.Request(
        API, data=json.dumps({"query": query, "variables": variables or {}}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        body = json.load(r)
    if body.get("errors"):
        raise RuntimeError(body["errors"])
    return body["data"]


USER_FIELDS = """
  login name createdAt
  followers { totalCount }
  repositories(ownerAffiliations: OWNER) { totalCount }
"""

YEAR_Q = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions totalIssueContributions totalPullRequestContributions
      totalPullRequestReviewContributions restrictedContributionsCount
      contributionCalendar { totalContributions weeks { contributionDays { date contributionCount } } }
    }
  }
}"""

REPO_Q = """
query($login: String!, $after: String) {
  user(login: $login) {
    repositories(first: 100, after: $after, ownerAffiliations: [OWNER, COLLABORATOR, ORGANIZATION_MEMBER], isFork: false) {
      pageInfo { hasNextPage endCursor }
      nodes {
        owner { login } stargazerCount
        languages(first: 20, orderBy: {field: SIZE, direction: DESC}) { edges { size node { name color } } }
      }
    }
  }
}"""


def fetch(token, fallback_login):
    try:
        user = gql(token, f"{{ viewer {{ {USER_FIELDS} }} }}")["viewer"]
    except Exception:
        user = gql(token, f'query($l:String!){{ user(login:$l) {{ {USER_FIELDS} }} }}', {"l": fallback_login})["user"]
    login = user["login"]

    now = dt.datetime.now(dt.timezone.utc)
    start = dt.datetime.fromisoformat(user["createdAt"].replace("Z", "+00:00"))
    totals = dict(commits=0, issues=0, prs=0, reviews=0, contributions=0)
    days = {}
    cursor = start
    while cursor < now:
        end = min(cursor + dt.timedelta(days=365), now)
        cc = gql(token, YEAR_Q, {"login": login, "from": cursor.isoformat(), "to": end.isoformat()})
        cc = cc["user"]["contributionsCollection"]
        totals["commits"] += cc["totalCommitContributions"] + cc["restrictedContributionsCount"]
        totals["issues"] += cc["totalIssueContributions"]
        totals["prs"] += cc["totalPullRequestContributions"]
        totals["reviews"] += cc["totalPullRequestReviewContributions"]
        totals["contributions"] += cc["contributionCalendar"]["totalContributions"]
        for w in cc["contributionCalendar"]["weeks"]:
            for d in w["contributionDays"]:
                days[d["date"]] = d["contributionCount"]
        cursor = end

    langs, stars, after = {}, 0, None
    while True:
        page = gql(token, REPO_Q, {"login": login, "after": after})["user"]["repositories"]
        for repo in page["nodes"]:
            if repo["owner"]["login"] == login:
                stars += repo["stargazerCount"]
            for e in repo["languages"]["edges"]:
                n = e["node"]["name"]
                langs.setdefault(n, {"size": 0, "color": readable(e["node"]["color"] or MUTED)})["size"] += e["size"]
        if not page["pageInfo"]["hasNextPage"]:
            break
        after = page["pageInfo"]["endCursor"]

    return {
        "name": user["name"] or login, "login": login,
        "followers": user["followers"]["totalCount"], "repos": user["repositories"]["totalCount"],
        "stars": stars, **totals, "days": days, "langs": langs, "since": start.date().isoformat(),
    }


def streaks(days):
    dates = sorted(days)
    if not dates:
        return {"current": 0, "cur_range": None, "longest": 0, "long_range": None, "active": 0, "best": (None, 0)}
    longest, long_range, run, run_start = 0, None, 0, None
    for d in dates:
        if days[d] > 0:
            run_start = d if run == 0 else run_start
            run += 1
            if run > longest:
                longest, long_range = run, (run_start, d)
        else:
            run = 0
    # current streak: today may still be empty, so start from yesterday in that case
    i = len(dates) - 1
    if days[dates[i]] == 0:
        i -= 1
    current, cur_end = 0, dates[i] if i >= 0 else None
    while i >= 0 and days[dates[i]] > 0:
        current += 1
        i -= 1
    cur_range = (dates[i + 1], cur_end) if current else None
    best = max(days.items(), key=lambda kv: kv[1])
    return {"current": current, "cur_range": cur_range, "longest": longest, "long_range": long_range,
            "active": sum(1 for v in days.values() if v > 0), "best": best}


# ----------------------------------------------------------------- rendering
def readable(color):
    """Lift very dark language colors (e.g. Lua navy) so they show on the dark card."""
    h = color.lstrip("#")
    if len(h) != 6:
        return color
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    if 0.2126 * r + 0.7152 * g + 0.0722 * b >= 70:
        return color
    r, g, b = (int(c + (255 - c) * 0.45) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


def esc(s):
    return html.escape(str(s), quote=False)


def icon(name, x, y, color, size=20, cls=""):
    c = f' class="{cls}"' if cls else ""
    return (f'<g transform="translate({x},{y})"><g{c} style="color:{color}">'
            f'<svg width="{size}" height="{size}" viewBox="0 0 24 24">{ICONS[name]}</svg></g></g>')


def fmt_date(iso):
    d = dt.date.fromisoformat(iso)
    return f"{d.strftime('%b')} {d.day}, {d.year}"


def fmt_range(r):
    if not r:
        return "—"
    a, b = dt.date.fromisoformat(r[0]), dt.date.fromisoformat(r[1])
    fa = f"{a.strftime('%b')} {a.day}"
    return f"{fa} – {b.strftime('%b')} {b.day}" if a != b else fa


class Odo:
    """Rolling digit counter: every digit spins down to its value."""

    def __init__(self):
        self.n = 0
        self.css = []

    def __call__(self, value, cx, y, size, color, delay):
        text = f"{value:,}"
        dw, cw, lh = size * 0.6, size * 0.32, size * 1.25
        width = sum(cw if ch == "," else dw for ch in text)
        x = cx - width / 2
        out = []
        for k, ch in enumerate(text):
            if ch == ",":
                out.append(f'<text x="{x:.1f}" y="{y}" fill="{color}" font-size="{size}" font-weight="700">,</text>')
                x += cw
                continue
            self.n += 1
            i, target = self.n, 10 + int(ch)
            self.css.append(f"@keyframes o{i}{{to{{transform:translateY(-{target * lh:.1f}px)}}}}"
                            f".o{i}{{animation:o{i} 1.6s cubic-bezier(.2,.8,.2,1) {delay + k * 0.08:.2f}s both}}")
            stack = "".join(f'<text x="{x:.1f}" y="{y + j * lh:.1f}">{j % 10}</text>' for j in range(20))
            out.append(f'<clipPath id="c{i}"><rect x="{x - 1:.1f}" y="{y - size:.1f}" width="{dw + 2:.1f}" height="{lh:.1f}"/></clipPath>'
                       f'<g clip-path="url(#c{i})"><g class="o{i}" fill="{color}" font-size="{size}" font-weight="700">{stack}</g></g>')
            x += dw
        return "".join(out)


def stats_svg(s, st):
    W = 840
    odo = Odo()
    tiles = [
        ("activity", "#58a6ff", "Contributions", s["contributions"]),
        ("commit", "#a371f7", "Commits", s["commits"]),
        ("pr", "#3fb950", "Pull Requests", s["prs"]),
        ("issue", "#d29922", "Issues", s["issues"]),
        ("review", "#39c5cf", "Code Reviews", s["reviews"]),
        ("repo", "#f778ba", "Repositories", s["repos"]),
        ("star", "#e3b341", "Stars Earned", s["stars"]),
        ("users", "#f85149", "Followers", s["followers"]),
    ]
    TW, TH, GAP = (W - 3 * 16) / 4, 92, 16
    out = []
    for i, (ic, color, label, val) in enumerate(tiles):
        r, c = divmod(i, 4)
        x, y = c * (TW + GAP), 2 + r * (TH + GAP)
        d = 0.1 + i * 0.08
        out.append(
            f'<g transform="translate({x:.1f},{y})"><g class="tile" style="animation-delay:{d:.2f}s">'
            f'<rect x="1" y="1" width="{TW - 2:.1f}" height="{TH - 2}" rx="12" fill="{PANEL}" stroke="{BORDER}"/>'
            f'<rect x="1" y="1" width="4" height="{TH - 2}" rx="2" fill="{color}"/>'
            f'{icon(ic, 18, 16, color, 18)}'
            f'<text x="44" y="30" class="lbl">{esc(label)}</text>'
            f'{odo(val, TW / 2, 72, 28, FG, d + 0.2)}'
            f'</g></g>')

    y0 = 2 + 2 * (TH + GAP)
    SH = 150
    cw = (W - 2 * 16) / 3
    ring_r, circ = 44, 2 * 3.14159 * 44
    ring_css = ""
    pct = min(1.0, st["current"] / max(1, st["longest"]))
    cols = [
        ("trophy", "#e3b341", "Longest Streak", st["longest"], fmt_range(st["long_range"])),
        (None, "#a371f7", "Current Streak", st["current"], fmt_range(st["cur_range"])),
        ("calendar", "#3fb950", "Active Days", st["active"],
         f"best day: {st['best'][1]} on {fmt_range((st['best'][0], st['best'][0]))}" if st["best"][0] else "—"),
    ]
    for i, (ic, color, label, val, sub) in enumerate(cols):
        x = i * (cw + 16)
        d = 0.8 + i * 0.12
        body = [f'<rect x="1" y="1" width="{cw - 2:.1f}" height="{SH - 2}" rx="12" fill="{PANEL}" stroke="{BORDER}"/>']
        if ic is None:
            cx, cy = cw / 2, 62
            body.append(f'<circle cx="{cx:.1f}" cy="{cy}" r="{ring_r}" fill="none" stroke="{BORDER}" stroke-width="6"/>')
            body.append(f'<circle class="ring" cx="{cx:.1f}" cy="{cy}" r="{ring_r}" fill="none" stroke="url(#ringg)" '
                        f'stroke-width="6" stroke-linecap="round" transform="rotate(-90 {cx:.1f} {cy})" '
                        f'stroke-dasharray="{circ:.1f}"/>')
            ring_css = (f".ring{{stroke-dashoffset:{circ:.1f};animation:ring 1.8s cubic-bezier(.2,.8,.2,1) 1.1s forwards}}"
                        f"@keyframes ring{{to{{stroke-dashoffset:{circ * (1 - max(pct, .04)):.1f}}}}}")
            body.append(icon("flame", cx - 11, 6, "#f78166", 22, "flame"))
            body.append(odo(val, cx, cy + 11, 30, FG, d + 0.2))
            body.append(f'<text x="{cx:.1f}" y="128" class="lbl" text-anchor="middle" fill="{color}">{label}</text>')
            body.append(f'<text x="{cx:.1f}" y="144" class="sub" text-anchor="middle">{esc(sub)}</text>')
        else:
            body.append(icon(ic, cw / 2 - 12, 22, color, 24))
            body.append(odo(val, cw / 2, 90, 34, FG, d + 0.2))
            body.append(f'<text x="{cw / 2:.1f}" y="118" class="lbl" text-anchor="middle">{label}</text>')
            body.append(f'<text x="{cw / 2:.1f}" y="138" class="sub" text-anchor="middle">{esc(sub)}</text>')
        out.append(f'<g transform="translate({x:.1f},{y0})"><g class="tile" style="animation-delay:{d:.2f}s">'
                   f'{"".join(body)}</g></g>')

    H = y0 + SH + 22
    out.append(f'<text x="{W / 2}" y="{H - 4}" class="sub" text-anchor="middle">'
               f'since {fmt_date(s["since"])} · public + private · updated {dt.date.today().isoformat()}</text>')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<style>
text{{font-family:{SANS};font-variant-numeric:tabular-nums}}
.lbl{{font-size:13px;font-weight:600;fill:{MUTED}}}
.sub{{font-size:11.5px;fill:#6e7681}}
.tile{{opacity:0;animation:in .6s cubic-bezier(.2,.8,.2,1) both}}
@keyframes in{{from{{opacity:0;transform:translateY(14px)}}to{{opacity:1;transform:none}}}}
{ring_css}
.flame{{transform-box:fill-box;transform-origin:50% 100%;animation:flk 1.4s ease-in-out infinite}}
@keyframes flk{{0%,100%{{transform:scale(1)}}50%{{transform:scale(1.12,1.2)}}}}
{"".join(odo.css)}
{REDUCED}
</style>
<defs><linearGradient id="ringg" x1="0" x2="1"><stop offset="0" stop-color="#1f6feb"/><stop offset="1" stop-color="#a371f7"/></linearGradient></defs>
{"".join(out)}
</svg>
'''


def langs_svg(s, exclude):
    langs = {k: v for k, v in s["langs"].items() if k.lower() not in exclude}
    total = sum(v["size"] for v in langs.values()) or 1
    top = sorted(langs.items(), key=lambda kv: -kv[1]["size"])[:10]
    W = 840
    rows = (len(top) + 1) // 2
    H = 92 + rows * 34 + 10
    out = [f'<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="12" fill="{PANEL}" stroke="{BORDER}"/>',
           icon("code", 22, 20, "#58a6ff", 20),
           f'<text x="52" y="36" class="h">Most Used Languages</text>',
           f'<text x="{W - 22}" y="36" class="sub" text-anchor="end">{len(langs)} languages · public + private repos</text>']
    bx, bw, by = 22, W - 44, 56
    segs, x = [], bx
    for name, v in top:
        w = bw * v["size"] / total
        segs.append(f'<rect x="{x:.2f}" y="{by}" width="{max(w, 0.5):.2f}" height="12" fill="{v["color"]}"/>')
        x += w
    out.append(f'<clipPath id="barclip"><rect x="{bx}" y="{by}" width="0" height="12" rx="6">'
               f'<animate attributeName="width" from="0" to="{bw}" dur="1.4s" begin="0.2s" fill="freeze" '
               f'calcMode="spline" keySplines=".2 .8 .2 1" keyTimes="0;1"/></rect></clipPath>'
               f'<rect x="{bx}" y="{by}" width="{bw}" height="12" rx="6" fill="{BORDER}"/>'
               f'<g clip-path="url(#barclip)">{"".join(segs)}</g>')
    colw = (W - 44 - 40) / 2
    for i, (name, v) in enumerate(top):
        r, c = i % rows, i // rows
        x, y = 22 + c * (colw + 40), 100 + r * 34
        p = 100 * v["size"] / total
        mw = (colw - 180) * v["size"] / top[0][1]["size"]
        d = 0.5 + i * 0.07
        out.append(
            f'<g transform="translate({x:.1f},{y})"><g class="row" style="animation-delay:{d:.2f}s">'
            f'<circle cx="6" cy="0" r="6" fill="{v["color"]}"/>'
            f'<text x="20" y="5" class="n">{esc(name)}</text>'
            f'<rect x="130" y="-4" width="{colw - 180:.1f}" height="8" rx="4" fill="{BORDER}"/>'
            f'<rect class="mini" x="130" y="-4" width="{max(mw, 4):.1f}" height="8" rx="4" fill="{v["color"]}" style="animation-delay:{d + 0.2:.2f}s"/>'
            f'<text x="{colw:.1f}" y="5" class="p" text-anchor="end">{p:.1f}%</text>'
            f'</g></g>')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<style>
text{{font-family:{SANS};font-variant-numeric:tabular-nums}}
.h{{font-size:16px;font-weight:600;fill:{FG}}}
.sub{{font-size:11.5px;fill:#6e7681}}
.n{{font-size:13.5px;font-weight:600;fill:{FG}}}
.p{{font-size:13px;fill:{MUTED}}}
.row{{opacity:0;animation:in .5s ease-out both}}
@keyframes in{{from{{opacity:0;transform:translateX(-12px)}}to{{opacity:1;transform:none}}}}
.mini{{transform-box:fill-box;transform-origin:left center;animation:grow 1.1s cubic-bezier(.2,.8,.2,1) both}}
@keyframes grow{{from{{transform:scaleX(0)}}to{{transform:scaleX(1)}}}}
{REDUCED}
</style>
{"".join(out)}
</svg>
'''


def main():
    token = os.environ["GH_TOKEN"]
    out = pathlib.Path(os.environ.get("OUT_DIR", "assets"))
    out.mkdir(parents=True, exist_ok=True)
    exclude = {x.strip().lower() for x in os.environ.get("EXCLUDE_LANGS", "").split(",") if x.strip()}
    s = fetch(token, os.environ.get("GH_USER", ""))
    st = streaks(s["days"])
    (out / "stats.svg").write_text(stats_svg(s, st), encoding="utf-8")
    (out / "languages.svg").write_text(langs_svg(s, exclude), encoding="utf-8")
    print(f"{s['login']}: {s['contributions']} contributions, {s['commits']} commits, "
          f"{len(s['langs'])} languages, streak {st['current']}/{st['longest']}")


if __name__ == "__main__":
    main()
