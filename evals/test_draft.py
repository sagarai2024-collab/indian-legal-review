#!/usr/bin/env python3
"""Deterministic tests for the draft-agreement skill (runs in CI).

1. Both example term sheets build, meet the full protection floor, and produce
   a .docx with no hidden or injected text.
2. Removing a protection without an acknowledged override stops the build.
3. The same removal with an acknowledged override builds and is reported.
4. Each built draft is recognised by the review skill's pre-scan as the right
   document type, and contains the key author protections.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # Windows consoles default to cp1252
    except (AttributeError, ValueError):
        pass


ROOT = Path(__file__).resolve().parent.parent
DRAFT = ROOT / "skills" / "draft-agreement"
BUILD = DRAFT / "scripts" / "build_agreement.py"
PRESCAN = ROOT / "skills" / "review-agreement" / "scripts" / "prescan.py"
MUST_CONTAIN = {
    "publishing": ["Copyright in the Work remains with the Author", "film, television, web-series and OTT rights",
                   "No set-off", "Audit", "revert to the Author automatically"],
    "film_life_rights": ["Copyright in the Book remains with the Author", "No rights before payment",
                         "sole discretion", "Nothing in this Agreement assigns or waives that right",
                         "Box-office success bonuses", "Director's Undertaking", "sequels, prequels, remakes"],
}
EXPECTED_TYPE = {"publishing": "publishing", "film_life_rights": "life_rights"}
fails = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    for t in ("publishing", "film_life_rights"):
        out = tmp / t
        r = subprocess.run([sys.executable, str(BUILD), str(DRAFT / "termsheets" / f"{t}.example.yaml"), "--out-dir", str(out)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        check(r.returncode == 0, f"{t}: example builds ({r.stdout.strip() or r.stderr.strip()})")
        check((out / "agreement.docx").exists() and (out / "notes.md").exists(), f"{t}: docx and notes written")
        md = (out / "agreement.md").read_text(encoding="utf-8")
        for phrase in MUST_CONTAIN[t]:
            check(phrase in md, f"{t}: draft contains '{phrase}'")
        check("❌" not in (out / "notes.md").read_text(encoding="utf-8"), f"{t}: full floor met")
        scan = tmp / f"{t}.scan.json"
        subprocess.run([sys.executable, str(PRESCAN), str(out / "agreement.md"), "--out", str(scan)], check=True, capture_output=True)
        p = json.loads(scan.read_text(encoding="utf-8"))
        check(EXPECTED_TYPE[t] in p["doc_types"], f"{t}: review pre-scan recognises type ({p['doc_types']})")
        check(not p["injection_flags"], f"{t}: no hidden or injected text")

    ts = yaml.safe_load((DRAFT / "termsheets" / "film_life_rights.example.yaml").read_text(encoding="utf-8"))
    ts["approvals"]["sole_discretion_items"] = ts["approvals"]["sole_discretion_items"][:2]
    ts["money"]["statutory_royalty_acknowledged"] = False
    bad = tmp / "bad.yaml"
    bad.write_text(yaml.safe_dump(ts, sort_keys=False), encoding="utf-8")
    r = subprocess.run([sys.executable, str(BUILD), str(bad), "--out-dir", str(tmp / "bad")], capture_output=True, text=True, encoding="utf-8", errors="replace")
    check(r.returncode == 2 and "statutory_royalty_acknowledged" in r.stdout, "floor breach without override stops the build")

    ts["floor_overrides"] = [
        {"item": "sole_discretion_approvals_complete", "reason": "test", "acknowledged_by_author": True},
        {"item": "statutory_royalty_acknowledged", "reason": "test", "acknowledged_by_author": False},
    ]
    bad.write_text(yaml.safe_dump(ts, sort_keys=False), encoding="utf-8")
    r = subprocess.run([sys.executable, str(BUILD), str(bad), "--out-dir", str(tmp / "bad")], capture_output=True, text=True, encoding="utf-8", errors="replace")
    check(r.returncode == 2, "override without author acknowledgement is rejected")

    ts["floor_overrides"][1]["acknowledged_by_author"] = True
    bad.write_text(yaml.safe_dump(ts, sort_keys=False), encoding="utf-8")
    r = subprocess.run([sys.executable, str(BUILD), str(bad), "--out-dir", str(tmp / "ok")], capture_output=True, text=True, encoding="utf-8", errors="replace")
    notes = (tmp / "ok" / "notes.md").read_text(encoding="utf-8") if (tmp / "ok" / "notes.md").exists() else ""
    check(r.returncode == 0 and notes.count("OVERRIDDEN") == 2, "acknowledged overrides build and are shown in notes")

print(f"\n{'ALL PASSED' if not fails else f'{len(fails)} FAILED'}")
sys.exit(1 if fails else 0)
