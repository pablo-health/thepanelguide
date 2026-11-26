#!/usr/bin/env python3
"""Build aetna-rates/index.html from the aggregates in data/aetna-2026-11/.

    python3 tools/build_aetna_rates.py

The page is static: charts are plain HTML and CSS, so nothing loads but the
page itself and the site's Cloudflare Web Analytics beacon (no cookies).
The JSON files are aggregates only (medians and ranges). The build refuses
to show any row resting on fewer than 11 practices.
"""

from __future__ import annotations

import json
import math
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "aetna-2026-11"
OUT = ROOT / "aetna-rates" / "index.html"

MIN_PRACTICES = 11
OFFER = "https://pablo.health/independence?src=panelguide-rates"
OFFER_END = "https://pablo.health/independence?src=panelguide-rates-end"
ASK = "mailto:rates@pablo.health?subject=Rates%20request"

CODES = ["90837", "90834", "90832", "90791", "90847"]
CODE_LABEL = {
    "90837": "90837 · 60 min",
    "90834": "90834 · 45 min",
    "90832": "90832 · 30 min",
    "90791": "90791 · intake",
    "90847": "90847 · family",
}
LICENSES = [
    "LCSW",
    "LPC",
    "LMFT",
    "Social worker (other)",
    "Addiction counselor",
    "Psych NP/CNS",
    "Psychologist",
    "Psychiatrist",
]
RUNG_OF = {
    "LCSW": "masters",
    "LPC": "masters",
    "LMFT": "masters",
    "Social worker (other)": "masters",
    "Addiction counselor": "masters",
    "Psych NP/CNS": "np",
    "Psychologist": "doctoral",
    "Psychiatrist": "doctoral",
}
LIC_LABEL = {
    "LPC": "LPC / LMHC",
    "master's": "Master's level (all)",
    "nurse practitioner": "Nurse practitioner (all)",
    "doctoral": "Doctoral (all)",
}
STATE = {"GA": "Georgia", "FL": "Florida"}
SET_LABEL = {"lower": "Lower set", "upper": "Upper set", "one": "One set"}


def load(name: str) -> list[dict]:
    rows = json.loads((DATA / f"{name}.json").read_text())["rows"]
    return rows


def keep(rows: list[dict]) -> list[dict]:
    """Drop any row resting on fewer than MIN_PRACTICES practices."""
    return [r for r in rows if r.get("practices") is None or r["practices"] >= MIN_PRACTICES]


def money(v: float | None) -> str:
    if v is None:
        return "—"
    s = f"${v:,.2f}"
    return s[:-3] if s.endswith(".00") else s


def pct(v: float | None) -> str:
    return "—" if v is None else f"{math.floor(v + 0.5)}%"  # half up, as people round


def lic(label: str) -> str:
    return LIC_LABEL.get(label, label)


def e(s: object) -> str:
    return escape(str(s))


SOURCE_FILES = [
    ("Aetna's public rate files page (no login)",
     "https://health1.aetna.com/app/public/#/one/insurerCode=AETNACVS_I&brandCode=ALICSI/machine-readable-transparency-in-coverage"),
    ('The exact file: Aetna Life Insurance Company in-network rates "pl-sk", Nov 5, 2026 '
     "(1.6 GB compressed, about 22 GB unpacked; JSON)",
     "https://mrf.healthsparq.com/aetnacvs-egress.nophi.kyruushsq.com/prd/mrf/AETNACVS_I/ALICSI/2026-11-05/"
     "inNetworkRates/2026-11-05_pl-sk-tr25_Aetna-Life-Insurance-Company.json.gz"),
    ("Aetna's index of all its files",
     "https://mrf.healthsparq.com/aetnacvs-egress.nophi.kyruushsq.com/prd/mrf/AETNACVS_I/ALICSI/latest_metadata.json"),
    ("The federal NPI registry download, for state and license (November 2026 file)",
     "https://download.cms.gov/nppes/NPI_Files.html"),
    ("The federal file format", "https://github.com/CMSgov/price-transparency-guide"),
]


def files_list() -> str:
    """The method card's source links, then this site's own aggregate JSON."""
    def link(label: str, href: str) -> str:
        return f'<a href="{e(href)}" target="_blank" rel="noopener">{e(label)}</a>'
    items = [f"          <li>{link(label, href)}</li>" for label, href in SOURCE_FILES]
    ours = ", ".join(link(f.name, f"../data/aetna-2026-11/{f.name}") for f in sorted(DATA.glob("*.json")))
    items.append(f"          <li>Our numbers behind this page: {ours}</li>")
    return "\n".join(items)


rates = keep(load("rates"))
standard = keep(load("standard"))
coverage = keep(load("coverage"))
ladder = {r["key"]: r for r in load("ladder")}
cohorts_all = load("cohorts")
cohorts = keep(cohorts_all)
platforms = load("platforms")

FL = ladder["FL|90837"]
assert ladder["GA|90837"]["masters"] == FL["masters"], "GA and FL standard sets differ; copy says they match"


def row(rows: list[dict], key: str) -> dict:
    return next(r for r in rows if r["key"] == key)


# ---------------------------------------------------------------- charts


def domain(lo: float, hi: float, step: int = 10) -> tuple[float, float]:
    return (math.floor((lo - 5) / step) * step, math.ceil((hi + 5) / step) * step)


def ticks(d: tuple[float, float]) -> list[float]:
    span = d[1] - d[0]
    step = next(s for s in (10, 20, 25, 50, 100) if span / s <= 7)
    first = math.ceil(d[0] / step) * step
    return list(range(int(first), int(d[1]) + 1, step))


def x(v: float, d: tuple[float, float]) -> str:
    return f"{100 * (v - d[0]) / (d[1] - d[0]):.2f}%"


def axis(d: tuple[float, float], fmt=lambda t: f"${t}") -> str:
    marks = "".join(f'<span style="left:{x(t, d)}">{e(fmt(t))}</span>' for t in ticks(d))
    grid = "".join(f'<i style="left:{x(t, d)}"></i>' for t in ticks(d))
    return f'<div class="rrow axisrow"><div></div><div class="raxis">{marks}</div></div>', grid


def range_chart(label: str, groups: list[tuple[str, list[tuple[int, dict | None, str]], float | None]],
                d: tuple[float, float]) -> str:
    """groups: (group label, [(series index, row, tooltip title)], reference value)."""
    ax, grid = axis(d)
    out = [f'<div class="rchart" role="img" aria-label="{e(label)}">']
    for glabel, series, ref in groups:
        lines = []
        for si, r, title in series:
            if r is None:
                lines.append('<div class="rs"></div>')
                continue
            tip = (f"{title}: median {money(r['median'])}; middle half {money(r['p25'])} to {money(r['p75'])}; "
                   f"{r['practices']:,} practices")
            b_l, b_r = x(r["p25"], d), f"{max(0.6, 100 * (r['p75'] - r['p25']) / (d[1] - d[0])):.2f}%"
            lines.append(
                f'<div class="rs c{si}" title="{e(tip)}">'
                f'<i class="bx" style="left:{b_l};width:{b_r}"></i>'
                f'<i class="dt" style="left:{x(r["median"], d)}"></i></div>'
            )
        refl = f'<i class="ref" style="left:{x(ref, d)}"></i>' if ref is not None else ""
        out.append(f'<div class="rrow"><div class="rlab">{e(glabel)}</div>'
                   f'<div class="rtrack">{grid}{refl}{"".join(lines)}</div></div>')
    out.append(ax)
    out.append("</div>")
    return "\n".join(out)


def license_chart() -> str:
    rows = [r for r in rates if r["code"] == "90837" and r["practice"] == "solo" and r["license"] in LICENSES]
    refs = [FL[RUNG_OF[l]] for l in LICENSES]
    d = domain(min([r["p25"] for r in rows] + refs), max([r["p75"] for r in rows] + refs))
    groups = []
    for l in LICENSES:
        series = []
        for si, st in enumerate(["GA", "FL"]):
            r = next((q for q in rows if q["license"] == l and q["state"] == st), None)
            series.append((si, r, f"{STATE[st]}, {lic(l)}, solo, 90837"))
        if any(s[1] for s in series):
            groups.append((lic(l), series, FL[RUNG_OF[l]]))
    return range_chart("Solo practice 90837 rates by license, Georgia and Florida", groups, d)


def code_chart(st: str) -> str:
    allm = [r for r in rates if r["license"] == "master's"]
    refs = [ladder[f"{s}|{c}"]["masters"] for s in STATE for c in CODES]
    d = domain(min([r["p25"] for r in allm] + refs), max([r["p75"] for r in allm] + refs))
    groups = []
    for c in CODES:
        series = []
        for si, p in enumerate(["solo", "group"]):
            r = next((q for q in allm if q["state"] == st and q["code"] == c and q["practice"] == p), None)
            series.append((si, r, f"{STATE[st]}, {CODE_LABEL[c]}, master's level, {p}"))
        groups.append((CODE_LABEL[c], series, ladder[f"{st}|{c}"]["masters"]))
    return range_chart(f"{STATE[st]}: master's-level solo and group rate ranges for five therapy codes", groups, d)


def takeit_chart() -> str:
    out = ['<div class="stack" role="img" aria-label="How often Aetna pays solo practices exactly its standard 90837 rate, more, or less, by license level, Georgia and Florida">']
    for g in ["master's", "nurse practitioner", "doctoral"]:
        for st in ["GA", "FL"]:
            r = next((q for q in standard if q["license"] == g and q["state"] == st and q["code"] == "90837"), None)
            if r is None:
                continue
            on = 100 * r["on_standard"] / r["practices"]
            ab = 100 * r["above"] / r["practices"]
            be = 100 * r["below"] / r["practices"]
            tip = (f"{STATE[st]}, {lic(g)}, solo, 90837: standard rate {money(r['standard'])}; paid exactly it {r['on_standard']} "
                   f"({pct(r['pct_on'])}); paid more {r['above']} ({pct(r['pct_above'])}); paid less {r['below']}; "
                   f"{r['practices']:,} solo practices")
            segs = ""
            for val, cls in ((on, "on"), (ab, "ab"), (be, "be")):
                if val > 0:
                    txt = pct(val) if val >= 9 else ""
                    segs += f'<i class="{cls}" style="width:{val:.2f}%">{txt}</i>'
            out.append(f'<div class="srow" title="{e(tip)}"><div class="rlab">{e(lic(g).replace(" (all)", ""))} · {st}'
                       f'<small>{r["practices"]:,} practices</small></div><div class="sbar">{segs}</div></div>')
    out.append("</div>")
    return "\n".join(out)


def platforms_chart() -> str:
    rows = [r for r in platforms if r["masters"] is not None]
    solo = FL["masters"]
    vals = [r["masters"] for r in rows] + [solo]
    d = (math.floor((min(vals) - 10) / 10) * 10, math.ceil((max(vals) + 10) / 10) * 10)
    ax, grid = axis(d)
    out = ['<div class="rchart" role="img" aria-label="What Aetna pays each platform for a master\'s-level 90837 in Florida, against the solo standard rate">']
    names = list(dict.fromkeys(r["platform"] for r in rows))
    for n in names:
        rs = [r for r in rows if r["platform"] == n]
        tip = f"{n}, master's level, 90837: " + "; ".join(f"{SET_LABEL[r['set']]} {money(r['masters'])}" for r in rs) \
            + f"; solo standard {money(solo)}; {rs[0]['clinicians']:,} Florida clinicians"
        link = ""
        if len(rs) > 1:
            lo, hi = min(r["masters"] for r in rs), max(r["masters"] for r in rs)
            link = f'<i class="pl" style="left:{x(lo, d)};width:{100 * (hi - lo) / (d[1] - d[0]):.2f}%"></i>'
        dots = "".join(f'<i class="pd {"c1" if r["set"] == "upper" else "c0"}" style="left:{x(r["masters"], d)}"></i>' for r in rs)
        out.append(f'<div class="rrow" title="{e(tip)}"><div class="rlab">{e(n)}</div>'
                   f'<div class="rtrack">{grid}<i class="ref" style="left:{x(solo, d)}"></i>'
                   f'<div class="rs prow">{link}{dots}</div></div></div>')
    out.append(ax)
    out.append("</div>")
    return "\n".join(out)


def cohort_chart() -> tuple[str, list[str]]:
    order = sorted({(r["cohort_order"], r["cohort"]) for r in cohorts_all})
    dropped = sorted({r["cohort"] for r in cohorts_all if r["practices"] < MIN_PRACTICES and r["state"] == "GA"},
                     key=lambda c: next(o for o, n in order if n == c))
    out = ['<div class="cchart" role="img" aria-label="Share of master\'s-level solo practices Aetna pays more than its standard 90837 rate, by NPI year, Georgia and Florida">']
    for _, c in order:
        bars = ""
        for si, st in enumerate(["GA", "FL"]):
            r = next((q for q in cohorts if q["cohort"] == c and q["state"] == st and q["practice"] == "solo"), None)
            if r is None:
                bars += f'<div class="cb"><span class="na">{st}: too few practices to show</span></div>'
                continue
            tip = (f"{STATE[st]}, NPI {c}: {pct(r['pct_above'])} paid more than the standard rate; exactly it {r['on_standard']}, "
                   f"less {r['below_standard']}; median {money(r['median'])}; {r['practices']:,} master's-level solo practices")
            bars += (f'<div class="cb" title="{e(tip)}"><i class="c{si}" style="width:{r["pct_above"]:.1f}%"></i>'
                     f'<span>{st} {pct(r["pct_above"])} <small>({r["practices"]:,})</small></span></div>')
        out.append(f'<div class="crow"><div class="rlab">{e(c)}</div><div>{bars}</div></div>')
    out.append("</div>")
    return "\n".join(out), dropped


# ---------------------------------------------------------------- tables


def table(head: list[str], body: list[list[str]], left: int) -> str:
    th = "".join(f"<th>{e(h)}</th>" for h in head)
    trs = "".join("<tr>" + "".join(f"<td>{e(c)}</td>" for c in r) + "</tr>" for r in body)
    return f'<div class="tbl l{left}"><table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table></div>'


def takeit_table() -> str:
    order = ["master's", *LICENSES[:5], "nurse practitioner", "Psych NP/CNS", "doctoral", "Psychologist", "Psychiatrist"]
    rows = sorted((r for r in standard if r["code"] == "90837"),
                  key=lambda r: (0 if r["state"] == "GA" else 1, order.index(r["license"])))
    body = [[STATE[r["state"]], lic(r["license"]), money(r["standard"]), f"{r['practices']:,}", pct(r["pct_on"]),
             pct(r["pct_above"]), money(r["median_above"])] for r in rows]
    return table(["State", "License", "Standard rate", "Solo practices", "Paid exactly it", "Paid more",
                  "Median if paid more"], body, 2)


def platforms_table() -> str:
    body = [[r["platform"], SET_LABEL[r["set"]], f"{r['clinicians']:,}", money(r["masters"]), money(r["np"]),
             money(r["doctoral"])] for r in platforms]
    return table(["Platform", "Rate set", "FL clinicians", "Master's level", "Nurse practitioner", "Doctoral"], body, 2)


def full_table() -> str:
    rows = [r for r in rates if r["license"] in LICENSES]
    rows.sort(key=lambda r: (0 if r["state"] == "GA" else 1, LICENSES.index(r["license"]), CODES.index(r["code"]),
                             0 if r["practice"] == "solo" else 1))
    body = [[STATE[r["state"]], lic(r["license"]), CODE_LABEL[r["code"]], r["practice"], f"{r['practices']:,}",
             money(r["p10"]), money(r["p25"]), money(r["median"]), money(r["p75"]), money(r["p90"])] for r in rows]
    return table(["State", "License", "Code", "Practice", "Practices", "Low end (10%)", "Middle half from", "Median",
                  "Middle half to", "High end (90%)"], body, 4)


# ---------------------------------------------------------------- page

fl_m = row(standard, "FL|master's|90837")
ga_m = row(standard, "GA|master's|90837")
none_below = all(r["below"] == 0 for r in standard)
cov_fl = row(coverage, "FL|solo|90837")["pct_mapped"]
cov_ga = row(coverage, "GA|solo|90837")["pct_mapped"]
hw_lo = row(platforms, "Headway|lower")["masters"]
hw_up = row(platforms, "Headway|upper")["masters"]
fl_solo = row(rates, "FL|solo|master's|90837")
cohort_html, cohort_dropped = cohort_chart()

TITLE = "What Aetna pays therapists, by license and billing code"
DESC = ("Aetna's published in-network rates for therapy codes in Georgia and Florida: the rate for each license, "
        "how often Aetna pays solo practices exactly its standard rate, and what it pays the platforms.")

page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(TITLE)} · The Panel Guide</title>
<link rel="canonical" href="https://thepanelguide.org/aetna-rates/">
<meta name="description" content="{e(DESC)}">
<meta property="og:type" content="article">
<meta property="og:url" content="https://thepanelguide.org/aetna-rates/">
<meta property="og:site_name" content="The Panel Guide">
<meta property="og:title" content="{e(TITLE)}">
<meta property="og:description" content="{e(DESC)}">
<meta property="og:image" content="https://thepanelguide.org/aetna-rates/hachi-grilled.jpg">
<meta name="twitter:card" content="summary_large_image">
<!-- Generated by tools/build_aetna_rates.py from data/aetna-2026-11/. Edit those, not this file. -->
<style>
  :root{{
    --paper:#f5efe3; --paper-2:#ece4d3; --ink:#1f2a24; --ink-2:#4a5650;
    --green:#2f5d48; --green-soft:#dfe8df; --rust:#a4532c; --rule:#d6cbb5; --amber:#c98b2b;
    --serif: "Iowan Old Style","Palatino Linotype",Palatino,"Book Antiqua",Georgia,serif;
    --sans: -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
    --c0:var(--green); --c1:var(--rust);
  }}
  html,body{{background:var(--paper);margin:0}}
  .site{{background:var(--paper);color:var(--ink);font-family:var(--serif);line-height:1.55;font-size:17px}}
  .wrap{{max-width:820px;margin:0 auto;padding:0 28px}}
  header.top{{border-bottom:1px solid var(--rule)}}
  header.top .wrap{{display:flex;justify-content:space-between;align-items:center;padding-top:16px;padding-bottom:14px;flex-wrap:wrap;gap:8px}}
  .mark{{font-weight:700;letter-spacing:.01em;font-size:18px;color:inherit;text-decoration:none}}
  .mark span{{color:var(--rust)}}
  nav a{{font:14px var(--sans);color:var(--ink-2);text-decoration:none;margin-left:16px}}
  nav a:hover{{color:var(--green)}}
  .hero{{padding:48px 0 32px}}
  .dateline{{font:600 13px var(--sans);letter-spacing:.06em;color:var(--rust);margin:0 0 12px}}
  .kicker{{font:600 12px var(--sans);letter-spacing:.14em;text-transform:uppercase;color:var(--rust)}}
  h1{{font-size:44px;line-height:1.08;margin:12px 0 10px;font-weight:600;letter-spacing:-.01em}}
  .byline{{font:14px/1.5 var(--sans);color:var(--ink-2);margin:0 0 18px}}
  .byline a{{color:inherit}}
  .lede{{font-size:21px;line-height:1.4;margin:0 0 16px;max-width:34em}}
  .facts{{font:14.5px/1.5 var(--sans);color:var(--ink-2);margin:0;padding:0;list-style:none}}
  .facts li{{padding-left:16px;position:relative;margin:2px 0}}
  .facts li:before{{content:"";position:absolute;left:2px;top:.6em;width:6px;height:6px;border-radius:50%;background:var(--green)}}
  section{{padding:40px 0;border-top:1px solid var(--rule)}}
  h2{{font-size:28px;line-height:1.15;margin:4px 0 14px;font-weight:600}}
  h3{{font:600 15px var(--sans);margin:18px 0 8px;letter-spacing:.02em}}
  p{{margin:0 0 14px;max-width:40em}}
  .sub{{font:14px/1.5 var(--sans);color:var(--ink-2)}}
  .ask{{background:var(--green-soft);border-left:3px solid var(--green);border-radius:0 10px 10px 0;padding:16px 20px;margin:26px 0 0;font:16px/1.5 var(--sans)}}
  .ask b{{font:600 19px var(--serif);display:block;margin-bottom:4px}}
  .ask a{{color:var(--green);font-weight:600}}
  .callout{{background:var(--paper-2);border-radius:12px;padding:22px 24px 8px}}
  .callout h2{{font-size:24px;margin-top:0}}
  ol.steps{{padding:0;margin:8px 0 14px;list-style:none;font:15.5px/1.5 var(--sans);counter-reset:s}}
  ol.steps li{{counter-increment:s;padding:7px 0 7px 40px;position:relative}}
  ol.steps li:before{{content:counter(s);position:absolute;left:0;top:6px;width:26px;height:26px;border-radius:50%;
    background:var(--ink);color:var(--paper);font:600 13px/26px var(--sans);text-align:center}}
  .ladder{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:8px 0 16px}}
  .ladder div{{background:var(--paper-2);border-radius:10px;padding:14px 16px;font:14px/1.4 var(--sans);color:var(--ink-2)}}
  .ladder b{{display:block;font:600 34px/1.1 var(--serif);color:var(--ink);margin:4px 0}}
  .card{{background:#fbf8f1;border:1px solid var(--rule);border-radius:12px;padding:16px 18px 10px;margin:10px 0 14px}}
  .legend{{display:flex;flex-wrap:wrap;gap:6px 16px;font:13px var(--sans);color:var(--ink-2);margin:4px 0 8px}}
  .legend i{{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px;vertical-align:-1px}}
  .legend .k0{{background:var(--c0)}} .legend .k1{{background:var(--c1)}}
  .legend .kon{{background:var(--green);border-radius:2px}} .legend .kab{{background:var(--amber);border-radius:2px}} .legend .kbe{{background:var(--ink-2);border-radius:2px}}
  .legend .kr{{width:16px;height:0;border-top:2px dashed var(--ink);border-radius:0;vertical-align:3px}}
  .legend .kb{{width:22px;height:8px;border-radius:4px;background:var(--ink-2);opacity:.35}}
  /* range charts */
  .rchart{{font:13px var(--sans)}}
  .rrow{{display:grid;grid-template-columns:10.5em 1fr;gap:10px;align-items:center;padding:5px 0}}
  .rlab{{color:var(--ink);line-height:1.25}}
  .rlab small{{display:block;color:var(--ink-2);font-size:11.5px}}
  .rtrack{{position:relative;padding:3px 0}}
  .rtrack > i{{position:absolute;top:0;bottom:0;width:0;border-left:1px solid #e6dcc8}}
  .rtrack > i.ref{{border-left:2px dashed var(--ink);z-index:1}}
  .rs{{position:relative;height:18px}}
  .rs i{{position:absolute;top:50%}}
  .rs .bx{{height:10px;margin-top:-5px;border-radius:5px;background:var(--c);opacity:.35}}
  .rs .dt{{width:12px;height:12px;margin:-6px 0 0 -6px;border-radius:50%;background:var(--c);border:2px solid #fbf8f1;box-sizing:border-box;z-index:2}}
  .rs.c0{{--c:var(--c0)}} .rs.c1{{--c:var(--c1)}}
  .prow{{height:22px}}
  .prow .pl{{height:2px;margin-top:-1px;background:var(--ink-2);opacity:.45}}
  .prow .pd{{width:14px;height:14px;margin:-7px 0 0 -7px;border-radius:50%;border:2px solid #fbf8f1;box-sizing:border-box;z-index:2}}
  .prow .pd.c0{{background:var(--c0)}} .prow .pd.c1{{background:var(--c1)}}
  .axisrow{{padding-top:0}}
  .raxis{{position:relative;height:18px;border-top:1px solid var(--ink-2);color:var(--ink-2);font-size:12px}}
  .raxis span{{position:absolute;top:3px;transform:translateX(-50%)}}
  /* stacked bars */
  .stack{{font:13px var(--sans)}}
  .srow{{display:grid;grid-template-columns:10.5em 1fr;gap:10px;align-items:center;padding:5px 0}}
  .sbar{{display:flex;height:22px;border-radius:4px;overflow:hidden;background:#e6dcc8}}
  .sbar i{{display:block;height:100%;color:#fff;font:600 12px/22px var(--sans);font-style:normal;text-align:center;overflow:hidden;white-space:nowrap}}
  .sbar .on{{background:var(--green)}} .sbar .ab{{background:var(--amber);color:var(--ink)}} .sbar .be{{background:var(--ink-2)}}
  /* cohort bars */
  .cchart{{font:13px var(--sans)}}
  .crow{{display:grid;grid-template-columns:6em 1fr;gap:10px;align-items:center;padding:6px 0;border-bottom:1px dashed var(--rule)}}
  .cb{{position:relative;height:20px;margin:3px 0;background:#ece4d3;border-radius:3px}}
  .cb i{{position:absolute;left:0;top:0;bottom:0;border-radius:3px}}
  .cb i.c0{{background:var(--c0)}} .cb i.c1{{background:var(--c1)}}
  .cb span{{position:absolute;left:8px;top:0;line-height:20px;color:#fff;font-weight:600;text-shadow:0 0 2px rgba(0,0,0,.35)}}
  .cb span small{{font-weight:400}}
  .cb span.na{{color:var(--ink-2);font-weight:400;text-shadow:none}}
  /* tables */
  .tbl{{overflow-x:auto;margin:8px 0 6px;-webkit-overflow-scrolling:touch}}
  table{{border-collapse:collapse;font:13.5px/1.35 var(--sans);font-variant-numeric:tabular-nums;width:100%;min-width:560px}}
  th{{text-align:right;font:600 11.5px var(--sans);letter-spacing:.05em;text-transform:uppercase;color:var(--ink-2);border-bottom:2px solid var(--ink);padding:7px 8px 5px}}
  td{{text-align:right;border-bottom:1px solid var(--rule);padding:6px 8px;white-space:nowrap}}
  .l2 th:nth-child(-n+2),.l2 td:nth-child(-n+2),.l4 th:nth-child(-n+4),.l4 td:nth-child(-n+4){{text-align:left}}
  .tall{{max-height:520px;overflow:auto;border-bottom:1px solid var(--rule)}}
  .tall thead th{{position:sticky;top:0;background:var(--paper)}}
  /* story */
  figure{{margin:18px 0 0}}
  figure img{{width:100%;height:auto;border-radius:10px;border:1px solid var(--rule);display:block}}
  figcaption{{font:14px/1.5 var(--sans);color:var(--ink-2);margin-top:8px}}
  figure.top{{margin:0 0 18px}}
  details.method{{font:14.5px/1.55 var(--sans);color:var(--ink-2);background:#fbf8f1;border:1px solid var(--rule);border-radius:12px;padding:14px 18px;margin:0 0 22px}}
  details.method summary{{cursor:pointer;font:600 18px var(--serif);color:var(--ink)}}
  details.method h3{{color:var(--ink);margin-top:20px}}
  details.method p{{max-width:none}}
  details.method p:first-of-type{{margin-top:12px}}
  details.method ul{{padding-left:1.2em;display:grid;gap:8px;margin:12px 0 4px}}
  .closing{{font:15px/1.55 var(--sans);color:var(--ink-2)}}
  .closing a{{color:var(--green)}}
  footer{{background:var(--ink);color:#cfc7b6;font:13.5px/1.55 var(--sans);padding:28px 0 32px;margin-top:20px}}
  footer a{{color:#f2c9a8}}
  footer .wrap{{display:grid;gap:10px}}
  @media (max-width:640px){{
    .site{{font-size:16px}}
    .wrap{{padding:0 18px}}
    h1{{font-size:32px}}
    .lede{{font-size:19px}}
    nav a{{margin-left:12px}}
    .ladder{{grid-template-columns:1fr}}
    .ladder b{{font-size:28px}}
    .card{{padding:12px 12px 8px}}
    .rrow,.srow{{grid-template-columns:1fr;gap:2px}}
    .axisrow > div:first-child{{display:none}}
    .crow{{grid-template-columns:4.6em 1fr}}
  }}
</style>
</head>
<body>
<div class="site">

  <header class="top"><div class="wrap">
    <a class="mark" href="/">The Panel Guide<span>.</span></a>
    <nav><a href="/">The guide</a><a href="{e(OFFER)}">Pablo</a></nav>
  </div></header>

  <div class="wrap">
    <div class="hero">
      <h1>{e(TITLE)}</h1>
      <p class="dateline">Georgia and Florida · Aetna's published rate file, Nov 5, 2026</p>
      <p class="byline">By Kurt Niemi, who builds <a href="{e(OFFER)}">Pablo</a>. Hachi, an AI assistant, ran the numbers; Kurt questioned each step until they made sense.</p>
      <figure class="top">
        <img src="hachi-grilled.jpg" width="1200" height="800" alt="Illustration: a small shiba plushie, Hachi, sits at a table in an interrogation room while a man points at spreadsheets of insurance rates. Caption: Kurt grilled his AI assistant, until the numbers made sense.">
        <figcaption>Hachi is the AI assistant that ran the numbers. It took a few rounds.</figcaption>
      </figure>
      <details class="method" id="method">
        <summary>How we figured this out, and the full method</summary>
        <p>Aetna publishes every rate it has agreed to in a huge public file. The first look made no sense: almost every practice had three different rates listed for the same session code, and the file gave no hint which one applied. An easy explanation was "plan tiers" or "office versus telehealth", and we nearly stopped there.</p>
        <p>Kurt Niemi, who builds Pablo, kept pushing. Office versus non-office only gives two rates, not three, and the file showed the three prices were identical in every other way. So we looked at the numbers themselves. In every practice and every code, the three rates sat at exactly 75%, 85% and 100% of each other, to the cent.</p>
        <p>That split is familiar: Medicare pays clinical social workers, marriage and family therapists and counselors 75% of the physician rate, and nurse practitioners 85%. Then we found contracts in the same Aetna file that do put the license code next to the rate (AJ/HO for social workers and master's-level clinicians, TD for nurse level, AF/AH for physicians and psychologists). Those labelled rates sit at the same 75%, 85% and 100%. Aetna's own provider newsletter calls 85% its "standard policy" for nurse practitioners, and an independent analysis of Aetna's data describes the same ladder.</p>
        <p>So the three rates are a license ladder: master's level at 75% of the top rate, nurse practitioners at 85%, doctoral at 100%. Every practice's contract lists all three, and the one you are paid depends on your license. Once we read it that way, the numbers lined up, and they are what this page shows.</p>
        <h3>The full method, and what it can't tell you</h3>
        <ul>
          <li>Source: Aetna Life Insurance Company's in-network rate file "pl-sk" (2026-11-05), used by 457 employer plans and covering Open Access Managed Choice and Choice POS II. Other Aetna files were not checked yet.</li>
          <li>State and license come from the federal NPI registry (November 2026): practice-location state and primary taxonomy. Florida LMHCs are counted with LPCs.</li>
          <li>The license rates: most practices list three rates per code at 75%, 85% and 100% of the top one, without saying which is which. A few contracts in the same file label their rates with Aetna's license modifiers (AJ/HO master's level, TD nurse, AF/AH physician or psychologist), and those sit at exactly the same 75/85/100. Each clinician here gets the rate for their own license. Outside support: Aetna's own March 2022 provider update calls 85% of the physician rate its "standard policy for mid-level practitioners" (nurse practitioners, physician assistants, nurse midwives, clinical nurse specialists), and Serif Health's September 2026 analysis of Aetna's data describes the same "standard rate ladder": nurse practitioners at 85% and master's level at 75% of the PhD rate. No public Aetna document found states the 75% for master's level in its own words.</li>
          <li>Florida solo practices whose rates follow the 75/85/100 pattern: {pct(cov_fl)}; Georgia: {pct(cov_ga)}. The rest (mostly older round-dollar schedules in Georgia) don't say which rate is which license and are left out.</li>
          <li>Standard rate: the state's most common rate for that license and code. "Exactly the standard rate" means paid that rate, to the cent.</li>
          <li>Low end (10%) and high end (90%), in the full table: one practice in ten is paid less than the low end, and one in ten is paid more than the high end.</li>
          <li>A few contracts (about 1%) also split each rate into office and non-office (facility, telehealth) prices. Only office or all-places prices are used here.</li>
          <li>Solo means a tax ID with exactly one clinician anywhere in the file. Everything else is a group. Platforms: the rates are what Aetna pays the platform's tax ID (Florida, 90837, read with the same 75/85/100 pattern). What a platform passes on to its clinicians is not in the file.</li>
          <li>Rates under $20 were dropped as placeholders. Some listed contracts are dormant: a clinician can be in the file and rarely bill Aetna.</li>
          <li>Medians and ranges only. No individual clinician's rate is shown, and no row rests on fewer than 11 practices.</li>
        </ul>
        <h3>The files we used</h3>
        <ul class="files">
{files_list()}
        </ul>
        <p>Aetna publishes new files every month, so this link may stop working once the file is replaced.</p>
      </details>
      <p class="lede">Aetna pays by license. For a 60-minute session (90837) its standard rate is <b>{money(FL["masters"])}</b> for master's-level clinicians, <b>{money(FL["np"])}</b> for nurse practitioners and <b>{money(FL["doctoral"])}</b> for psychologists and psychiatrists.</p>
      <p class="sub">Negotiated rates Aetna lists, not what anyone collected.</p>
      <div class="ask"><b>Want this for your state, your license or another insurer?</b>Email <a href="{ASK}">rates@pablo.health</a> and we'll run it.</div>
    </div>

    <section id="start-here" class="callout">
      <h2>Start here: what does Aetna pay someone like you?</h2>
      <ol class="steps">
        <li><b>Find your license</b> in <a href="#by-license">What each license is paid</a> (LCSW, LPC / LMHC, LMFT, nurse practitioner, psychologist, psychiatrist).</li>
        <li><b>Look at the dashed line first.</b> That is Aetna's standard rate for your license: what a practice on the standard contract is paid, and what a new contract usually starts at.</li>
        <li><b>Then look at the dot and the bar.</b> The dot is the median. The median is the rate in the middle when practices are lined up from lowest to highest. Many practices are paid exactly the same rate, so the median is often the standard rate itself. The bar shows where most practices are paid: in Florida, for 90837, most master's-level solo practices (the middle half) are paid between {money(fl_solo["p25"])} and {money(fl_solo["p75"])}. If the bar reaches well past the dashed line, many practices like yours are paid more than the standard rate.</li>
        <li><b>Check <a href="#standard-rate">How often Aetna pays exactly its standard rate</a></b> for how many solo practices Aetna pays exactly that, and what it pays the rest.</li>
        <li><b>Use <a href="#table">the big table</a></b> at the bottom for other codes (45-minute sessions, intakes, family sessions).</li>
      </ol>
      <p class="sub">These are rates Aetna has agreed to and published, by law, for its main national network. They can't tell you what your own contract says. If yours is below the standard rate for your license, that is worth a question to Aetna's provider line.</p>
    </section>

    <section id="ladder">
      <h2>One contract, three rates: which one is yours</h2>
      <p>Aetna lists three rates for each practice and pays the one that matches your license: master's level (LCSW, LPC / LMHC, LMFT), nurse practitioner, or doctoral (psychologist, psychiatrist). Georgia and Florida share the same standard rates.</p>
      <div class="ladder">
        <div>Master's level<b>{money(FL["masters"])}</b>LCSW, LPC / LMHC, LMFT</div>
        <div>Nurse practitioner<b>{money(FL["np"])}</b>Psychiatric NP</div>
        <div>Doctoral<b>{money(FL["doctoral"])}</b>Psychologist, psychiatrist</div>
      </div>
      <p class="sub">The standard rates for 90837, the ones the most Florida practices are on. How we worked out which rate goes with which license is in <a href="#method">How we figured this out</a>.</p>
    </section>

    <section id="standard-rate">
      <h2>How often Aetna pays solo practices exactly its standard rate</h2>
      <p>In Florida, Aetna pays {pct(fl_m["pct_on"])} of master's-level solo practices exactly its standard rate for 90837. The rest are paid more, nearly all on one other rate (median {money(fl_m["median_above"])}).{" None is paid less." if none_below else ""} In Georgia, Aetna pays {pct(ga_m["pct_on"])} of them exactly the standard rate, and the rest more (median {money(ga_m["median_above"])}).</p>
      <div class="card">
        <div class="legend"><span><i class="kon"></i>Exactly the standard rate</span><span><i class="kab"></i>Paid more</span>{"" if none_below else '<span><i class="kbe"></i>Paid less</span>'}</div>
        {takeit_chart()}
      </div>
      {takeit_table()}
    </section>

    <section id="by-license">
      <h2>What each license is paid: solo practices, 90837</h2>
      <p>Each clinician is counted at their practice's rate for their own license. Dashed line: the standard rate for that license.</p>
      <div class="card">
        <div class="legend"><span><i class="k0"></i>Georgia</span><span><i class="k1"></i>Florida</span><span><i class="kb"></i>Middle half</span><span><i class="kr"></i>Standard rate</span></div>
        {license_chart()}
      </div>
      <p class="sub">The dot is the median; the bar is the middle half. License groups with fewer than 11 solo practices are left out (Georgia has few nurse practitioners and psychiatrists in solo practice). Exact numbers are in <a href="#table">the table</a>.</p>
    </section>

    <section id="platforms">
      <h2>What Aetna pays your platform for your license: Florida, 90837</h2>
      <p>Headway, Alma, Rula and similar platforms hold Aetna contracts for all their clinicians, and the file lists what Aetna pays the platform for each session. You already know what your platform pays you for an Aetna 60-minute session, so you can put the two side by side. For a master's-level clinician, Aetna pays Headway {money(hw_lo)} or {money(hw_up)}, against {money(FL["masters"])} on a solo practice's standard contract.</p>
      <div class="card">
        <div class="legend"><span><i class="k0"></i>Lower set, or the only one</span><span><i class="k1"></i>Upper set</span><span><i class="kr"></i>Solo standard rate</span></div>
        {platforms_chart()}
      </div>
      {platforms_table()}
      <p class="sub">Headway contracts through nine tax IDs. All of them list the same rates: two sets of three, one per license, and the file doesn't say which set a given session is paid under.</p>
      <p class="sub">What Aetna pays the platform, not what the platform pays you: what a platform passes on to its clinicians is not in the file. Alma and Rula also list two rate sets for every clinician, again without saying which applies. Grow and Tava list one rate per license. Grow and Tava are matched by the name on their tax ID, so they are likely, not certain. Blank cells: the file has no clear rate for that license.</p>
    </section>

    <section id="by-code">
      <h2>Master's level, solo vs group, by billing code</h2>
      <p class="sub">The dot is the median; the bar is the middle half. Dashed line: the master's-level standard rate for that code.</p>
      <div class="card">
        <div class="legend"><span><i class="k0"></i>Solo practice</span><span><i class="k1"></i>Group practice</span><span><i class="kb"></i>Middle half</span><span><i class="kr"></i>Standard rate</span></div>
        <h3>Georgia</h3>
        {code_chart("GA")}
        <h3>Florida</h3>
        {code_chart("FL")}
      </div>
    </section>

    <section id="cohorts">
      <h2>Are new contracts lower? Master's-level solo practices paid more than the standard rate, by NPI year</h2>
      <p>Share of master's-level solo practices Aetna pays more than its standard rate for 90837, grouped by when the clinician's NPI was issued (a rough stand-in for when they started practicing). The number in brackets is how many practices each bar rests on.</p>
      <div class="card">
        <div class="legend"><span><i class="k0"></i>Georgia</span><span><i class="k1"></i>Florida</span></div>
        {cohort_html}
      </div>
      <p class="sub">Georgia has very few master's-level solo practices with NPIs from 2020 on ({", ".join(cohort_dropped)}: fewer than 11 each), so those years are left out rather than shown on a handful of practices.</p>
    </section>

    <section id="table">
      <h2>Every license and code, solo and group</h2>
      <p class="sub">Rows with fewer than 11 practices are left out. Scroll sideways on a phone.</p>
      <div class="tall">{full_table()}</div>
    </section>

    <section>
      <div class="ask" style="margin-top:0"><b>Want this for your state, your license or another insurer?</b>Email <a href="{ASK}">rates@pablo.health</a> and we'll run it.</div>
      <p class="closing" style="margin-top:22px"><a href="{e(OFFER_END)}">Pablo</a> is the practice software behind this research, built by Kurt for therapists. For the rest of going independent, read <a href="/">The Panel Guide</a>.</p>
    </section>
  </div>

  <footer><div class="wrap">
    <div><b style="color:#f5efe3">The Panel Guide</b> is a free guide from the team at <a href="{e(OFFER)}">Pablo</a>, who make practice software for therapists. Nothing here requires it. Spot something wrong? Tell us at <a href="mailto:guide@pablo.health">guide@pablo.health</a>.</div>
    <div>This is general information, not legal, tax or billing advice. Rates differ by plan, contract and state. Confirm with the payer.</div>
    <div>No cookies. We count anonymous page views with Cloudflare Web Analytics to see whether this is useful.</div>
  </div></footer>
</div>
<script defer src='https://static.cloudflareinsights.com/beacon.min.js' data-cf-beacon='{{"token": "ecca0ba5a41048279c408a19dabdd888"}}'></script>
</body>
</html>
"""

OUT.write_text(page)
print(f"wrote {OUT.relative_to(ROOT)} ({len(page):,} bytes)")
