"""Render the static profile cards (whoami, focus, stack) in the same console frame as the stats cards.

    python .github/scripts/build_cards.py [out_dir]

Brand icons live next to this script in icons/<name>.svg (256x256 viewBox, skill-icons style).
"""
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from build_stats import ACCENT, ACCENT2, DIM, FG, LINE, MONO, MUTED, PAD, PANEL, REDUCED, esc, frame  # noqa: E402

ICONS = HERE / "icons"
W = 840
LOGIN = "KATAKORN"
GREEN, YELLOW, RED = "#3fb950", "#d29922", "#f85149"

BASE_CSS = (f"text{{font-family:{MONO};font-variant-numeric:tabular-nums;fill:{FG}}}\n"
            f".cap{{font-size:10.5px;letter-spacing:.08em;fill:{DIM}}}\n"
            f".sub{{font-size:11px;fill:{DIM}}}")


def svg(H, css, body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">\n'
            f'<style>\n{BASE_CSS}\n{css}\n{REDUCED}\n</style>\n{"".join(body)}\n</svg>\n')


# ------------------------------------------------------------------ whoami
KW, IDENT, KEY, STR, PUNCT, CMT, GUTTER = "#ff7b72", "#d2a8ff", "#79c0ff", "#a5d6ff", FG, MUTED, "#484f58"


def field(key, *value):
    return [(KEY, f"    {key:<9}"), (PUNCT, " = ")] + list(value) + [(PUNCT, ",")]


def strs(*items):
    out = [(PUNCT, "{ ")]
    for i, it in enumerate(items):
        if i:
            out.append((PUNCT, ", "))
        out.append((STR, f'"{it}"'))
    return out + [(PUNCT, " }")]


CODE = [
    [(CMT, "---@class Developer")],
    [(KW, "local "), (IDENT, "Katakorn"), (PUNCT, " = {")],
    field("role", (STR, '"FiveM / Lua / Full Stack Developer"')),
    field("framework", *strs("ESX", "ox_lib", "oxmysql")),
    field("stack", *strs("Lua", "JavaScript", "TypeScript", "Svelte", "MySQL", "Node.js")),
    field("focus", *strs("FiveM", "Backend", "NUI", "Database", "Optimization")),
    field("motto", (STR, '"Clean code. High performance. Secure systems."')),
    [(PUNCT, "}")],
    [],
    [(KW, "return "), (IDENT, "Katakorn")],
]


def whoami_svg():
    """Typewriter listing of whoami.lua: each line is revealed by an animated clip, then the loop wipes."""
    CX, LH, Y0, CH = 66, 24, 68, 8.6           # code x, line height, first baseline, px per char
    H = Y0 + (len(CODE) - 1) * LH + 28
    DUR, clock = 14.0, 0.6
    defs, body = [], [frame(W, H, f"{LOGIN} / WHOAMI", "~/katakorn/whoami.lua · lua 5.4")]
    body.append(f'<line x1="52.5" x2="52.5" y1="41" y2="{H - 1}" stroke="{LINE}"/>')
    for i, toks in enumerate(CODE):
        y = Y0 + i * LH
        n = sum(len(s) for _, s in toks)
        w = 30 + CH * n
        a = clock
        clock += max(n * 0.018, 0.1)
        b = clock
        clock += 0.1
        defs.append(f'<clipPath id="l{i}"><rect x="{CX}" y="{y - 18}" height="{LH}" width="0">'
                    f'<animate attributeName="width" values="0;0;{w:.0f};{w:.0f};0" '
                    f'keyTimes="0;{a / DUR:.4f};{b / DUR:.4f};0.94;1" dur="{DUR}s" repeatCount="indefinite"/></rect></clipPath>')
        body.append(f'<text x="42" y="{y}" class="ln" text-anchor="end">{i + 1}</text>')
        spans = "".join(f'<tspan fill="{c}">{esc(s)}</tspan>' for c, s in toks)
        body.append(f'<text x="{CX}" y="{y}" class="code" clip-path="url(#l{i})" xml:space="preserve">{spans}</text>')
    n = sum(len(s) for _, s in CODE[-1])
    body.append(f'<rect class="cur" x="{CX + CH * n + 2:.0f}" y="{Y0 + (len(CODE) - 1) * LH - 14}" '
                f'width="8" height="18" fill="{ACCENT}"/>')
    css = (f".code{{font-size:14px}}\n.ln{{font-size:11px;fill:{GUTTER}}}\n"
           ".cur{animation:blink 1s steps(1) infinite}\n@keyframes blink{50%{opacity:0}}")
    return svg(H, css, [f"<defs>{''.join(defs)}</defs>"] + body)


# ------------------------------------------------------------------- focus
TABLER = {  # 24x24 stroke icons
    "gamepad": '<path d="M12 5h3.5a5 5 0 0 1 0 10H10l-4.015 4.227a2.3 2.3 0 0 1-3.923-2.035l1.634-8.173A5 5 0 0 1 8.6 5z"/>'
               '<path d="m14 15l4.07 4.284a2.3 2.3 0 0 0 3.925-2.023l-1.6-8.232M8 9v2m-1-1h2m5 0h2"/>',
    "layout": '<path d="M5 4h4a1 1 0 0 1 1 1v6a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1m0 12h4a1 1 0 0 1 1 1v2a1 1 0 0 1-1 '
              '1H5a1 1 0 0 1-1-1v-2a1 1 0 0 1 1-1m10-4h4a1 1 0 0 1 1 1v6a1 1 0 0 1-1 1h-4a1 1 0 0 1-1-1v-6a1 1 0 0 1 1-1m0-8h4a1 '
              '1 0 0 1 1 1v2a1 1 0 0 1-1 1h-4a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1"/>',
    "database": '<path d="M4 6a8 3 0 1 0 16 0A8 3 0 1 0 4 6"/><path d="M4 6v6a8 3 0 0 0 16 0V6"/><path d="M4 12v6a8 3 0 0 0 16 0v-6"/>',
    "bolt": '<path d="M13 3v7h6l-8 11v-7H5z"/>',
    "shield": '<path d="M12 3a12 12 0 0 0 8.5 3A12 12 0 0 1 12 21A12 12 0 0 1 3.5 6A12 12 0 0 0 12 3"/>'
              '<path d="M11 11a1 1 0 1 0 2 0a1 1 0 1 0-2 0m1 1v2.5"/>',
}

FOCUS = [  # icon, color, area, detail, tools
    ("gamepad", ACCENT, "fivem resources", "client / server / shared, modular lua architecture", "lua · esx · ox_lib"),
    ("layout", ACCENT2, "nui / ui", "in-game interfaces with svelte, html, css, js", "svelte · vite · ts"),
    ("database", GREEN, "database", "mysql schema design & efficient oxmysql queries", "mysql · oxmysql"),
    ("bolt", YELLOW, "optimization", "low resmon, lean threads, fast server ticks", "0.00ms target"),
    ("shield", RED, "security", "server-side validation & event protection", "server authority"),
]


def focus_svg():
    RH, Y0 = 36, 76
    H = Y0 + len(FOCUS) * RH + 40
    body = [frame(W, H, f"{LOGIN} / FOCUS", f"{len(FOCUS)} areas · what i build")]
    body.append(f'<text x="{PAD}" y="62" class="cap">AREA</text>'
                f'<text x="250" y="62" class="cap">DETAIL</text>'
                f'<text x="{W - PAD}" y="62" class="cap" text-anchor="end">TOOLS</text>')
    for r, (ic, color, name, detail, tools) in enumerate(FOCUS):
        y = Y0 + r * RH
        cy = y + RH / 2
        if r % 2 == 0:
            body.append(f'<rect x="1" y="{y}" width="{W - 2}" height="{RH}" fill="{PANEL}" fill-opacity=".55"/>')
        body.append(f'<g class="up" style="animation-delay:{0.15 + r * 0.08:.2f}s">'
                    f'<svg x="{PAD}" y="{cy - 8}" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="{color}" '
                    f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{TABLER[ic]}</svg>'
                    f'<text x="{PAD + 28}" y="{cy + 4.5}" class="name">{esc(name)}</text>'
                    f'<text x="250" y="{cy + 4.5}" class="det">{esc(detail)}</text>'
                    f'<text x="{W - PAD}" y="{cy + 4.5}" class="tag" text-anchor="end">{esc(tools)}</text></g>')
    body.append(f'<text x="{PAD}" y="{H - 14}" class="sub">most production projects are private</text>')
    css = (f".name{{font-size:13px;font-weight:600}}\n.det{{font-size:12px;fill:{MUTED}}}\n"
           f".tag{{font-size:11px;letter-spacing:.04em;fill:{DIM}}}\n"
           ".up{opacity:0;animation:up .5s cubic-bezier(.2,.8,.2,1) both}\n"
           "@keyframes up{from{opacity:0;transform:translateX(-8px)}to{opacity:1;transform:none}}")
    return svg(H, css, body)


# ------------------------------------------------------------------- stack
STACK = [  # group label, [(icon file, caption)]
    ("LANGUAGES", [("lua", "lua"), ("javascript", "javascript"), ("typescript", "typescript"),
                   ("svelte", "svelte"), ("html", "html"), ("css", "css")]),
    ("RUNTIME & DATA", [("nodejs", "node.js"), ("mysql", "mysql")]),
    ("TOOLING", [("vite", "vite"), ("git", "git"), ("github", "github"), ("vscode", "vs code")]),
]


def icon(name, x, y, size, k):
    """Inline icons/<name>.svg at (x, y); ids get a per-slot prefix so repeated defs never collide."""
    raw = (ICONS / f"{name}.svg").read_text(encoding="utf-8")
    inner = re.search(r"<svg[^>]*>(.*)</svg>", raw, re.S).group(1).strip()
    inner = re.sub(r'id="([^"]+)"', rf'id="i{k}_\1"', inner)
    inner = re.sub(r"url\(#([^)]+)\)", rf"url(#i{k}_\1)", inner)
    inner = re.sub(r'href="#([^"]+)"', rf'href="#i{k}_\1"', inner)
    return f'<svg x="{x:.1f}" y="{y}" width="{size}" height="{size}" viewBox="0 0 256 256" fill="none">{inner}</svg>'


def stack_svg():
    CW, GAP, SZ, IY, H = 64, 12, 36, 74, 170
    n = sum(len(items) for _, items in STACK)
    body = [frame(W, H, f"{LOGIN} / STACK", f"{n} tools · languages, runtime, tooling")]
    x, k = PAD, 0
    for g, (label, items) in enumerate(STACK):
        if g:
            x += GAP
            body.append(f'<line x1="{x - GAP / 2:.1f}" x2="{x - GAP / 2:.1f}" y1="52" y2="{IY + SZ + 24}" stroke="{LINE}"/>')
        body.append(f'<text x="{x}" y="62" class="cap">{esc(label)}</text>')
        for name, title in items:
            body.append(f'<g class="up" style="animation-delay:{0.15 + k * 0.05:.2f}s">'
                        f'{icon(name, x + (CW - SZ) / 2, IY, SZ, k)}'
                        f'<text x="{x + CW / 2:.1f}" y="{IY + SZ + 16}" class="nm" text-anchor="middle">{esc(title)}</text></g>')
            x += CW
            k += 1
    assert x == W - PAD, x
    body.append(f'<text x="{PAD}" y="{H - 14}" class="sub">day-to-day stack · fivem resources, nui &amp; tooling</text>')
    css = (f".nm{{font-size:9.5px;fill:{MUTED}}}\n"
           ".up{opacity:0;animation:up .5s cubic-bezier(.2,.8,.2,1) both}\n"
           "@keyframes up{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}")
    return svg(H, css, body)


def main():
    out = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent.parent / "assets"
    out.mkdir(parents=True, exist_ok=True)
    for name, render in (("whoami", whoami_svg), ("what-i-do", focus_svg), ("tech-stack", stack_svg)):
        (out / f"{name}.svg").write_text(render(), encoding="utf-8")
        print(f"wrote {out / name}.svg")


if __name__ == "__main__":
    main()
