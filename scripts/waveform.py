#!/usr/bin/env python3
"""Render the 'year of building' waveform from the real GitHub contribution calendar.

Standard library only, so it runs on a stock GitHub Actions runner.
Type comes from scripts/glyphs.json (Inter outlines, pre-generated), so no fonts are needed.

  python3 scripts/waveform.py --login aderemi-onalaja --out assets          # fetch via GITHUB_TOKEN
  python3 scripts/waveform.py --calendar data.json --out assets             # offline
  python3 scripts/waveform.py --check assets                                # validate SVGs only

Safety: refuses to overwrite when the new total drops below half the previous one,
which would point to a token that can't see the shared private counts.
"""
import argparse, datetime, json, os, sys, urllib.request
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
GLYPHS = json.load(open(os.path.join(HERE, "glyphs.json")))
W, H, MID, AMP = 880, 214, 112, 58
PAL = {
    "light": dict(ink="#141414", ink2="#59636e", ink3="#818b98", line="#d1d9e0", acc="#3a5bd9"),
    "dark":  dict(ink="#f0f6fc", ink2="#9198a1", ink3="#656c76", line="#3d444d", acc="#8aa4ff"),
}
QUERY = """query($login:String!){user(login:$login){contributionsCollection{contributionCalendar{
  totalContributions weeks{contributionDays{date contributionCount}}}}}}"""


def fetch(login):
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("GITHUB_TOKEN is not set")
    req = urllib.request.Request("https://api.github.com/graphql",
                                 data=json.dumps({"query": QUERY, "variables": {"login": login}}).encode(),
                                 headers={"Authorization": f"bearer {token}", "User-Agent": "profile-waveform"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    if "errors" in data:
        sys.exit(f"GraphQL error: {data['errors']}")
    return data["data"]["user"]["contributionsCollection"]["contributionCalendar"]


def text(s, x, y, size, fill, style="r", anchor="start"):
    """Lay out text from the glyph cache (advance widths, no kerning: fine at label sizes)."""
    g = GLYPHS[style]; scale = size / GLYPHS["upm"]
    width = sum(g.get(c, g[" "])["a"] for c in s) * scale
    if anchor == "end": x -= width
    out, cx = [], x
    for c in s:
        gl = g.get(c, g[" "])
        if gl["d"]:
            out.append(f'<use href="#{style}{ord(c)}" fill="{fill}" transform="translate({cx:.1f} {y:.1f}) scale({scale:.4f})"/>')
        cx += gl["a"] * scale
    return "".join(out), {f"{style}{ord(c)}" for c in s if g.get(c, g[" "])["d"]}


def render(cal, mode):
    p = PAL[mode]
    days = [d for w in cal["weeks"] for d in w["contributionDays"]][-365:]
    total = sum(d["contributionCount"] for d in days)
    active = sum(1 for d in days if d["contributionCount"])
    first, last = days[0]["date"], days[-1]["date"]
    used, parts = set(), []

    def t(*a, **k):
        s, u = text(*a, **k); used.update(u); parts.append(s)

    t("A year of building", 0, 20, 20, p["ink"], style="m")
    t(f"{total:,} contributions · {active} active days", W, 20, 16, p["ink2"], anchor="end")

    n = len(days); bw = W / n; peak = max(d["contributionCount"] for d in days) ** 0.5 or 1
    bars = []
    for k, d in enumerate(days):
        v = d["contributionCount"]; x = k * bw; w = max(bw - 0.6, 0.6)
        if v:
            h = max(2, AMP * v ** 0.5 / peak)
            bars.append(f"M{x:.1f} {MID-h:.1f}h{w:.1f}v{2*h:.1f}h-{w:.1f}z")
    parts.append(f'<rect x="0" y="{MID-0.5}" width="{W}" height="1" fill="{p["line"]}"/>')
    parts.append(f'<path fill="{p["ink"]}" d="{"".join(bars)}"/>')

    ticks = []
    for k, d in enumerate(days):
        if d["date"].endswith("-01"):
            x = k * bw
            ticks.append(f"M{x:.1f} 180h1v6h-1z")
            label = datetime.date.fromisoformat(d["date"]).strftime("%b")
            t(label, x + 4, 204, 14, p["ink3"])
    parts.append(f'<path fill="{p["ink3"]}" d="{"".join(ticks)}"/>')
    parts.append(f'<rect class="scan" x="0" y="{MID-AMP-4}" width="1.5" height="{2*AMP+8}" fill="{p["acc"]}"/>')

    defs = "".join(f'<path id="{gid}" d="{GLYPHS[gid[0]][chr(int(gid[1:]))]["d"]}"/>' for gid in sorted(used))
    body = "".join(parts)
    style = ("<style>.scan{animation:s 14s linear infinite}"
             f"@keyframes s{{to{{transform:translateX({W-2}px)}}}}"
             "@media (prefers-reduced-motion:reduce){.scan{animation:none;opacity:0}}</style>")
    desc = (f"Daily GitHub contributions from {first} to {last}, drawn as a mirrored waveform: "
            f"{total} contributions across {active} active days. Taller bars mean more contributions that day.")
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" '
           f'aria-labelledby="t d"><title id="t">A year of building</title><desc id="d">{desc}</desc>'
           f'{style}<defs>{defs}</defs>{body}</svg>')
    return svg, total


def check(folder):
    ok = True
    for mode in ("light", "dark"):
        path = os.path.join(folder, f"waveform-{mode}.svg")
        try:
            root = ET.parse(path).getroot()
            assert root.find("{http://www.w3.org/2000/svg}title") is not None, "missing <title>"
            size = os.path.getsize(path)
            assert size < 60_000, f"too large ({size} bytes)"
            print(f"ok  {path}  {size:,} bytes")
        except Exception as e:  # noqa: BLE001
            ok = False; print(f"FAIL {path}: {e}")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--login"); ap.add_argument("--calendar"); ap.add_argument("--out", default="assets")
    ap.add_argument("--check")
    a = ap.parse_args()
    if a.check:
        sys.exit(0 if check(a.check) else 1)
    if a.calendar:
        raw = json.load(open(a.calendar))
        cal = raw.get("data", {}).get("user", {}).get("contributionsCollection", {}).get("contributionCalendar", raw)
    else:
        cal = fetch(a.login)
    os.makedirs(a.out, exist_ok=True)
    stamp = os.path.join(a.out, ".waveform-total")
    prev = int(open(stamp).read()) if os.path.exists(stamp) else 0
    rendered = {m: render(cal, m) for m in ("light", "dark")}
    total = rendered["light"][1]
    if prev and total < prev * 0.5:
        sys.exit(f"Refusing to overwrite: total fell from {prev} to {total}. Check the token can see shared private counts.")
    for m, (svg, _) in rendered.items():
        open(os.path.join(a.out, f"waveform-{m}.svg"), "w").write(svg)
    open(stamp, "w").write(str(total))
    print(f"waveform: {total} contributions")


if __name__ == "__main__":
    main()
