#!/usr/bin/env python3
"""Build an author-favourable agreement from a term sheet.

  python3 build_agreement.py termsheet.yaml --out-dir ./drafts/<name>

Writes:
  agreement.md     the draft (Markdown)
  agreement.docx   the same draft as a Word file, marked DRAFT on every page
  notes.md         blanks still to be agreed, protection-floor status, and a
                   before-you-sign checklist

Guardrails (deterministic, cannot be skipped by the model):
  * Protection floor: the build FAILS if the term sheet removes an author
    protection, unless floor_overrides lists that item with a reason and
    acknowledged_by_author: true. Overrides are printed in notes.md.
  * Typos in the template or term sheet fail loudly (unknown keys).
  * Missing values never get invented: they print as "__________" and are
    listed in notes.md.
  * The finished draft is pre-scanned by the review skill's prescan.py to
    confirm it contains no hidden or injected text.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # Windows consoles default to cp1252
    except (AttributeError, ValueError):
        pass


HERE = Path(__file__).resolve().parent
TEMPLATES = HERE.parent / "templates"
PRESCAN = HERE.parent.parent / "review-agreement" / "scripts" / "prescan.py"
BLANK = "__________"

REQUIRED_SOLE_DISCRETION = [
    "new fictional or composite characters",
    "invented events or scenes not in the Book",
    "exaggeration or dramatisation that changes the meaning of real events",
    "any change to how real, identifiable people are shown",
    "any depiction of children",
]


class TermSheet:
    def __init__(self, data):
        self.data = data
        self.blanks = []

    def get(self, path):
        cur = self.data
        for part in path.split("."):
            if not isinstance(cur, dict) or part not in cur:
                raise KeyError(f"term sheet has no field '{path}'")
            cur = cur[part]
        return cur

    def v(self, path):
        val = self.get(path)
        if val is None or val == "":
            self.blanks.append(path)
            return BLANK
        if isinstance(val, float) and val.is_integer():
            val = int(val)
        return val

    def blank_if_none(self, val):
        if val is None:
            self.blanks.append("money.box_office_bonuses[].bonus")
            return BLANK
        return val


# ------------------------------------------------------------------ floor
def floor_checks(ts):
    t = ts["type"]
    checks = []

    def add(item, ok, why):
        checks.append({"item": item, "ok": bool(ok), "why": why})

    if t == "publishing":
        add("statements_not_annual", ts["statements"] in ("half_yearly", "quarterly"),
            "royalty statements at least half-yearly")
        add("approval_window_reasonable", (ts["approvals"]["approval_days"] or 0) >= 5,
            "author gets at least 5 working days to approve")
        add("no_next_work_lock", ts["next_work_option"] in ("none", "first_look_30_days"),
            "no option/first refusal/matching right over future books")
        add("sublicence_share_majority", (ts["money"]["sublicence_author_share_percent"] or 0) >= 50,
            "author gets the majority of any sub-licence income")
        add("royalty_slabs_present", bool(ts["money"]["print_royalty_slabs"]),
            "print royalty rates are stated")
        add("film_rights_not_granted", not set(ts["grant"]["formats"]) & {"film", "tv", "adaptation", "ott"},
            "film/TV/adaptation rights stay with the author")
        add("publisher_pays_legal_vetting", ts["legal_vetting_by_publisher"],
            "publisher pays for defamation/privacy legal reading of life writing")
    elif t == "film_life_rights":
        items = [i.strip().lower() for i in ts["approvals"]["sole_discretion_items"] or []]
        add("sole_discretion_approvals_complete", all(r.lower() in items for r in REQUIRED_SOLE_DISCRETION),
            "author approval in her sole discretion for fictional characters, invented or exaggerated events, real people and children")
        add("statutory_royalty_acknowledged", ts["money"]["statutory_royalty_acknowledged"] is True,
            "Copyright Act s.18/s.19(9) royalty share is acknowledged, not waived")
        add("success_participation", bool(ts["money"]["box_office_bonuses"]) or ts["money"]["non_theatrical_gross_percent"],
            "author shares in the Picture's success (bonuses and/or % of receipts)")
        add("production_window_set", ts["licence"]["start_photography_within_months"] and ts["licence"]["release_within_months"],
            "rights revert if the film is not made in time")
        add("exploitation_limited", ts["licence"]["exploitation_years_after_release"] is not None,
            "producer's right to exploit the completed Picture is time-limited")
        add("payment_before_rights", (ts["money"]["fee_on_signing_percent"] or 0) > 0,
            "part of the fee is paid on signing; rights vest only on full payment")
        add("promotion_is_paid", "appearance_fee_per_day" in ts["appearance"] and ts["appearance"]["promo_days_included"],
            "promotion days are capped and paid")
        add("children_protected", ts["children_or_minors_depicted"] is not False,
            "children's identities are protected unless the author confirms none are depicted")
    else:
        sys.exit(f"Unknown type '{t}'. Use publishing or film_life_rights.")
    return checks


def apply_overrides(checks, overrides):
    by_item = {o.get("item"): o for o in overrides or []}
    failed = []
    for c in checks:
        if c["ok"]:
            continue
        o = by_item.get(c["item"])
        if o and o.get("reason") and o.get("acknowledged_by_author") is True:
            c["overridden"] = o["reason"]
        else:
            failed.append(c)
    return failed


# ------------------------------------------------------------------ docx
def to_docx(md_text, path, title):
    import docx
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt

    d = docx.Document()
    style = d.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)
    for section in d.sections:
        hp = section.header.paragraphs[0]
        hp.text = f"DRAFT FOR DISCUSSION — {title} — subject to review by a practising advocate"
        hp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        fp = section.footer.paragraphs[0]
        fp.text = "Initials:  Author ________    Counterparty ________"
        fp.alignment = WD_ALIGN_PARAGRAPH.CENTER

    def add_runs(par, text):
        for i, chunk in enumerate(re.split(r"\*\*", text)):
            if chunk:
                par.add_run(chunk).bold = (i % 2 == 1)

    for block in re.split(r"\n\s*\n", md_text.strip()):
        lines = [l for l in block.splitlines() if l.strip()]
        if not lines:
            continue
        for line in lines:
            if line.startswith("# "):
                h = d.add_heading(line[2:].strip(), level=0)
                h.alignment = WD_ALIGN_PARAGRAPH.CENTER
            elif line.startswith("## "):
                d.add_heading(line[3:].strip(), level=1)
            elif line.startswith("- "):
                add_runs(d.add_paragraph(style="List Bullet"), line[2:].strip())
            else:
                p = d.add_paragraph()
                add_runs(p, line.strip())
                p.paragraph_format.space_after = Pt(6)
    d.save(str(path))


# ------------------------------------------------------------------ notes
CHECKLIST = [
    "Verify the other party's registration (CIN/LLPIN), registered office and directors/partners on the MCA portal.",
    "Get a copy of the board or partners' resolution authorising the person who signs.",
    "Register copyright in the manuscript (Copyright Act s.45) before sharing it, and share drafts only under a written NDA.",
    "Fill every blank and initial every page. Never sign a document with blank spaces or missing pages.",
    "Never sign with a date other than the actual date of signing.",
    "Pay or confirm stamp duty under the stamp law of the State where it is signed.",
    "All money must be paid to your own bank account. Do not let an agent or third party receive it.",
    "Check that nothing in this agreement conflicts with any earlier agreement you have signed (publisher, producer, agent). Ask your advocate to read the earlier agreements together with this one.",
    "Have a practising advocate review the final draft before signing.",
]


def write_notes(path, ts_obj, ts, checks, prescan_result):
    L = [f"# Notes for the {ts['type'].replace('_', ' ')} draft", "",
         "This draft is a starting point for negotiation, written from the author's side. "
         "It is not legal advice. A practising advocate must review it before it is signed.", ""]
    blanks = sorted(set(ts_obj.blanks))
    L += ["## Still to be agreed or filled in", ""]
    L += [f"- `{b}`" for b in blanks] or ["- nothing"]
    L += ["", "## Author-protection floor", ""]
    for c in checks:
        status = "✅" if c["ok"] else (f"⚠️ OVERRIDDEN ({c['overridden']}) —" if "overridden" in c else "❌")
        L.append(f"- {status} {c['why']}")
    L += ["", "## Document safety check", "",
          f"- Hidden or injected text found in the draft: {'none' if not prescan_result else prescan_result}", "",
          "## Before you sign", ""]
    L += [f"- [ ] {c}" for c in CHECKLIST]
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("termsheet")
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args()

    ts = yaml.safe_load(Path(a.termsheet).read_text(encoding="utf-8"))
    checks = floor_checks(ts)
    failed = apply_overrides(checks, ts.get("floor_overrides"))
    if failed:
        print("BUILD STOPPED - the term sheet removes author protections:")
        for c in failed:
            print(f"  x {c['item']}: {c['why']}")
        print("Restore them, or add each to floor_overrides with a reason and acknowledged_by_author: true.")
        sys.exit(2)

    ts_obj = TermSheet(ts)
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), undefined=StrictUndefined,
                      trim_blocks=True, lstrip_blocks=True, keep_trailing_newline=True)
    ctx = {"v": ts_obj.v, "opt": ts_obj.get, "blank_if_none": ts_obj.blank_if_none}
    if ts["type"] == "publishing":
        names = {"print_paperback": "paperback", "print_hardcover": "hardcover", "ebook": "e-book", "audiobook": "audiobook"}
        ctx["formats_text"] = ", ".join(names.get(f, f) for f in ts["grant"]["formats"])
        ctx["languages_text"] = ", ".join(ts["grant"]["languages"])
    md = env.get_template(f"{ts['type']}.md.j2").render(**ctx)
    md = re.sub(r"\n{3,}", "\n\n", md)

    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "agreement.md").write_text(md, encoding="utf-8")
    title = "Author–Publisher Licence Agreement" if ts["type"] == "publishing" else "Literary and Life-Story Rights Licence"
    to_docx(md, out / "agreement.docx", title)

    scan_out = out / ".prescan.json"
    subprocess.run([sys.executable, str(PRESCAN), str(out / "agreement.md"), "--out", str(scan_out)],
                   check=True, capture_output=True)
    flags = json.loads(scan_out.read_text(encoding="utf-8"))["injection_flags"]
    scan_out.unlink()
    write_notes(out / "notes.md", ts_obj, ts, checks, flags)

    print(f"built {out/'agreement.docx'} and notes.md - {len(set(ts_obj.blanks))} blank field(s) to agree; "
          f"floor: {sum(c['ok'] for c in checks)}/{len(checks)} met"
          + (f"; {len(checks) - sum(c['ok'] for c in checks)} overridden" if any(not c['ok'] for c in checks) else ""))
    if flags:
        print("WARNING: the draft contains text flagged as hidden or injected - check notes.md")
        sys.exit(3)


if __name__ == "__main__":
    main()
