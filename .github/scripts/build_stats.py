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
MONO = "'JetBrains Mono','Cascadia Code',Consolas,Menlo,monospace"
REDUCED = "@media (prefers-reduced-motion: reduce){*{animation:none!important}}"

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

    def __call__(self, value, x, y, size, color, delay, anchor="start", weight=700):
        text = f"{value:,}"
        dw, cw, lh = size * 0.6, size * 0.32, size * 1.25
        width = sum(cw if ch == "," else dw for ch in text)
        x = x - width / 2 if anchor == "middle" else x - width if anchor == "end" else x
        out = []
        for k, ch in enumerate(text):
            if ch == ",":
                out.append(f'<text x="{x:.1f}" y="{y}" fill="{color}" font-size="{size}" font-weight="{weight}">,</text>')
                x += cw
                continue
            self.n += 1
            i, target = self.n, 10 + int(ch)
            self.css.append(f"@keyframes o{i}{{to{{transform:translateY(-{target * lh:.1f}px)}}}}"
                            f".o{i}{{animation:o{i} 1.6s cubic-bezier(.2,.8,.2,1) {delay + k * 0.08:.2f}s both}}")
            stack = "".join(f'<text x="{x:.1f}" y="{y + j * lh:.1f}">{j % 10}</text>' for j in range(20))
            out.append(f'<clipPath id="c{i}"><rect x="{x - 1:.1f}" y="{y - size:.1f}" width="{dw + 2:.1f}" height="{lh:.1f}"/></clipPath>'
                       f'<g clip-path="url(#c{i})"><g class="o{i}" fill="{color}" font-size="{size}" font-weight="{weight}">{stack}</g></g>')
            x += dw
        return "".join(out)


ACCENT = "#58a6ff"
ACCENT2 = "#a371f7"
LINE = "#21262d"
DIM = "#6e7681"
PAD = 24


def frame(W, H, title, meta):
    """Shared console frame: one hairline panel with a title strip."""
    return (f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="6" fill="{BG}" stroke="{BORDER}"/>'
            f'<text x="{PAD}" y="25" class="cap"><tspan fill="{ACCENT}">●</tspan>  {esc(title)}</text>'
            f'<text x="{W - PAD}" y="25" class="cap" text-anchor="end">{esc(meta)}</text>'
            f'<line x1="0" x2="{W}" y1="40.5" y2="40.5" stroke="{LINE}"/>')


def weekly(days, weeks=52):
    if not days:
        return [0] * weeks, []
    last = dt.date.fromisoformat(max(days))
    start = last - dt.timedelta(days=weeks * 7 - 1)
    sums, labels = [0] * weeks, []
    for iso, n in days.items():
        d = dt.date.fromisoformat(iso)
        if d >= start:
            sums[(d - start).days // 7] += n
    for w in range(weeks):
        d0 = start + dt.timedelta(days=w * 7)
        if (d0 + dt.timedelta(days=6)).month != d0.month or w == 0:
            m = (d0 + dt.timedelta(days=6))
            labels.append((w, m.strftime("%b").upper()))
    return sums, labels


def stats_svg(s, st):
    W, H = 840, 400
    odo = Odo()
    out = [frame(W, H, f"{s['login'].upper()} / ACTIVITY",
                 f"since {fmt_date(s['since'])} · synced {dt.date.today().isoformat()}")]

    # hero: the one number that matters
    out.append(odo(s["contributions"], PAD - 2, 122, 64, FG, 0.2, weight=800))
    out.append(f'<text x="{PAD}" y="150" class="lbl">contributions</text>')
    out.append(f'<text x="{PAD}" y="170" class="sub">public + private, all time</text>')

    # weekly activity line, last 52 weeks
    sums, labels = weekly(s["days"])
    cx0, cx1, cy0, cy1 = 300, W - PAD, 78, 168
    top = max(max(sums), 1)
    step = (cx1 - cx0) / (len(sums) - 1)
    pts = [(cx0 + i * step, cy1 - (v / top) * (cy1 - cy0)) for i, v in enumerate(sums)]
    line = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"{line} L{cx1:.1f},{cy1} L{cx0:.1f},{cy1} Z"
    peak = max(range(len(sums)), key=lambda i: sums[i])
    px, py = pts[peak]
    out.append(f'<line x1="{cx0}" x2="{cx1}" y1="{cy1 + .5}" y2="{cy1 + .5}" stroke="{LINE}"/>')
    for w, lab in labels:
        x = cx0 + w * step
        out.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{cy1 + 1}" y2="{cy1 + 5}" stroke="{BORDER}"/>'
                   f'<text x="{x:.1f}" y="{cy1 + 18}" class="tick">{lab}</text>')
    out.append(f'<path class="area" d="{area}" fill="url(#ag)"/>')
    out.append(f'<path class="line" d="{line}" fill="none" stroke="{ACCENT}" stroke-width="1.75" '
               f'stroke-linejoin="round" pathLength="1"/>')
    lx = min(max(px, cx0 + 40), cx1 - 40)
    out.append(f'<g class="peak"><circle cx="{px:.1f}" cy="{py:.1f}" r="3.5" fill="{BG}" stroke="{ACCENT}" stroke-width="1.75"/>'
               f'<text x="{lx:.1f}" y="{py - 9:.1f}" class="tick" text-anchor="middle" style="fill:{FG}">peak {sums[peak]}/wk</text></g>')
    out.append(f'<text x="{cx0}" y="56" class="tick">WEEKLY · LAST 12 MONTHS</text>')

    # secondary metrics: one ruled row, no boxes
    y0 = 206
    out.append(f'<line x1="0" x2="{W}" y1="{y0 + .5}" y2="{y0 + .5}" stroke="{LINE}"/>')
    metrics = [("commits", s["commits"]), ("pull requests", s["prs"]), ("issues", s["issues"]),
               ("reviews", s["reviews"]), ("repositories", s["repos"]), ("stars", s["stars"]),
               ("followers", s["followers"])]
    cw = (W - 2 * PAD) / len(metrics)
    for i, (lab, val) in enumerate(metrics):
        x = PAD + i * cw
        if i:
            out.append(f'<line x1="{x - 12:.1f}" x2="{x - 12:.1f}" y1="{y0 + 18}" y2="{y0 + 70}" stroke="{LINE}"/>')
        dim = val == 0
        out.append(f'<g class="up" style="animation-delay:{0.5 + i * 0.06:.2f}s">'
                   f'<text x="{x:.1f}" y="{y0 + 44}" class="val"{" fill=%r" % DIM if dim else ""}>{val:,}</text>'
                   f'<text x="{x:.1f}" y="{y0 + 64}" class="cap">{lab.upper()}</text></g>')

    # streak: last 35 days as a strip, current run outlined
    y1 = y0 + 88
    out.append(f'<line x1="0" x2="{W}" y1="{y1 + .5}" y2="{y1 + .5}" stroke="{LINE}"/>')
    out.append(f'<text x="{PAD}" y="{y1 + 46}" class="big">{st["current"]}<tspan class="unit"> day streak</tspan></text>')
    out.append(f'<text x="{PAD}" y="{y1 + 68}" class="sub">current · {esc(fmt_range(st["cur_range"]))}</text>')
    last = dt.date.fromisoformat(max(s["days"])) if s["days"] else dt.date.today()
    n, sq, gap = 28, 9, 3
    sx = 222
    cur = set()
    if st["cur_range"]:
        a, b = (dt.date.fromisoformat(v) for v in st["cur_range"])
        cur = {(a + dt.timedelta(days=k)).isoformat() for k in range((b - a).days + 1)}
    vals = [s["days"].get((last - dt.timedelta(days=n - 1 - k)).isoformat(), 0) for k in range(n)]
    vmax = max(max(vals), 1)
    for k, v in enumerate(vals):
        iso = (last - dt.timedelta(days=n - 1 - k)).isoformat()
        x = sx + k * (sq + gap)
        op = 0.12 if v == 0 else 0.35 + 0.65 * v / vmax
        col = ACCENT2 if iso in cur else ACCENT
        stroke = f' stroke="{ACCENT2}" stroke-width="1"' if iso in cur else ""
        out.append(f'<rect class="day" x="{x}" y="{y1 + 28}" width="{sq}" height="{sq}" rx="2" fill="{col if v else FG}" '
                   f'fill-opacity="{op:.2f}"{stroke} style="animation-delay:{0.9 + k * 0.025:.3f}s"/>')
    out.append(f'<text x="{sx}" y="{y1 + 62}" class="tick">LAST 4 WEEKS</text>')
    out.append(f'<text x="{sx + n * (sq + gap) - gap}" y="{y1 + 62}" class="tick" text-anchor="end">TODAY</text>')
    rx = W - PAD
    best = st["best"]
    rows = [("longest", f'{st["longest"]}d', fmt_range(st["long_range"])),
            ("active", f'{st["active"]}d', ""),
            ("best day", f'{best[1]}', fmt_range((best[0], best[0])) if best[0] else "")]
    for i, (k, v, extra) in enumerate(rows):
        y = y1 + 30 + i * 18
        out.append(f'<text x="{rx - 236}" y="{y}" class="cap">{k.upper()}</text>'
                   f'<text x="{rx}" y="{y}" class="kv" text-anchor="end">{esc(v)}'
                   f'{f"<tspan fill={chr(34)}{DIM}{chr(34)}>  {esc(extra)}</tspan>" if extra else ""}</text>')

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<style>
text{{font-family:{MONO};font-variant-numeric:tabular-nums;fill:{FG}}}
.cap{{font-size:10.5px;letter-spacing:.08em;fill:{DIM}}}
.tick{{font-size:10px;letter-spacing:.06em;fill:{DIM}}}
.lbl{{font-size:14px;fill:{FG}}}
.sub{{font-size:11.5px;fill:{DIM}}}
.val{{font-size:22px;font-weight:700}}
.big{{font-size:30px;font-weight:800}}
.unit{{font-size:13px;font-weight:400;fill:{MUTED}}}
.kv{{font-size:12.5px;font-weight:600}}
.line{{stroke-dasharray:1;stroke-dashoffset:1;animation:draw 2.2s cubic-bezier(.4,0,.2,1) .3s forwards}}
@keyframes draw{{to{{stroke-dashoffset:0}}}}
.area,.peak{{opacity:0;animation:fade 1s ease-out 1.8s forwards}}
@keyframes fade{{to{{opacity:1}}}}
.up{{opacity:0;animation:up .6s cubic-bezier(.2,.8,.2,1) both}}
@keyframes up{{from{{opacity:0;transform:translateY(8px)}}to{{opacity:1;transform:none}}}}
.day{{opacity:0;animation:fade .3s ease-out both}}
{"".join(odo.css)}
{REDUCED}
</style>
<defs><linearGradient id="ag" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{ACCENT}" stop-opacity=".22"/><stop offset="1" stop-color="{ACCENT}" stop-opacity="0"/></linearGradient></defs>
{"".join(out)}
</svg>
'''


def langs_svg(s, exclude):
    langs = {k: v for k, v in s["langs"].items() if k.lower() not in exclude}
    total = sum(v["size"] for v in langs.values()) or 1
    ranked = sorted(langs.items(), key=lambda kv: -kv[1]["size"])
    top, rest = ranked[:6], ranked[6:]
    rows = [(n, v["size"], v["color"]) for n, v in top]
    if rest:
        rows.append((f"+{len(rest)} other", sum(v["size"] for _, v in rest), DIM))

    W, RH, Y0 = 840, 30, 76
    H = Y0 + len(rows) * RH + 40
    out = [frame(W, H, "RESMON / LANGUAGES", f"{len(langs)} languages · share of code bytes")]
    TX, TN, TW, TG = 300, 40, 8, 2.5
    out.append(f'<text x="{PAD}" y="62" class="cap">RESOURCE</text>'
               f'<text x="250" y="62" class="cap" text-anchor="end">SHARE</text>'
               f'<text x="{TX}" y="62" class="cap">USAGE</text>'
               f'<text x="{W - PAD}" y="62" class="cap" text-anchor="end">KB</text>')
    for r, (name, size, color) in enumerate(rows):
        y = Y0 + r * RH
        p = 100 * size / total
        lit = max(1, round(p / 100 * TN)) if size else 0
        lead = r == 0
        if r % 2 == 0:
            out.append(f'<rect x="1" y="{y}" width="{W - 2}" height="{RH}" fill="{PANEL}" fill-opacity=".55"/>')
        cy = y + RH / 2
        out.append(f'<g class="up" style="animation-delay:{0.15 + r * 0.07:.2f}s">'
                   f'<rect x="{PAD}" y="{cy - 4}" width="8" height="8" rx="1.5" fill="{color}"/>'
                   f'<text x="{PAD + 18}" y="{cy + 4.5}" class="{"name lead" if lead else "name"}">{esc(name.lower())}</text>'
                   f'<text x="250" y="{cy + 4.5}" class="pct" text-anchor="end">{p:.1f}%</text>'
                   f'<text x="{W - PAD}" y="{cy + 4.5}" class="kb" text-anchor="end">{size / 1024:,.0f}</text></g>')
        for t in range(TN):
            x = TX + t * (TW + TG)
            on = t < lit
            fill = (ACCENT if not lead else FG) if on else LINE
            cls = ' class="tk"' if on else ""
            style = f' style="animation-delay:{0.4 + r * 0.07 + t * 0.018:.3f}s"' if on else ""
            out.append(f'<rect{cls} x="{x:.1f}" y="{cy - 6}" width="{TW}" height="12" rx="1" fill="{fill}"{style}/>')
    out.append(f'<text x="{PAD}" y="{H - 14}" class="sub">non-fork repos I own or contribute to · public + private</text>')

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<style>
text{{font-family:{MONO};font-variant-numeric:tabular-nums;fill:{FG}}}
.cap{{font-size:10.5px;letter-spacing:.08em;fill:{DIM}}}
.sub{{font-size:11px;fill:{DIM}}}
.name{{font-size:13px}}
.lead{{font-weight:700}}
.pct{{font-size:13px;font-weight:600}}
.kb{{font-size:12px;fill:{DIM}}}
.up{{opacity:0;animation:up .5s cubic-bezier(.2,.8,.2,1) both}}
@keyframes up{{from{{opacity:0;transform:translateX(-8px)}}to{{opacity:1;transform:none}}}}
.tk{{opacity:0;animation:on .25s ease-out both}}
@keyframes on{{from{{opacity:0}}to{{opacity:1}}}}
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
