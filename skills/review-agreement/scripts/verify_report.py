#!/usr/bin/env python3
"""Deterministic verifier for review-agreement reports.

The model writes report.json; this script decides whether it may be shown.
It fails (exit 1) when the report:
  - cites a statute, section or case that is not in the playbook index;
  - cites a repealed law (e.g. IPC) for a document dated after the repeal;
  - quotes text that is not actually in the clause it points to;
  - uses a rule that does not exist or does not apply to the document type;
  - changes a rule's severity, or computes the overall verdict wrongly;
  - fails to escalate when a fired rule requires escalation;
  - drops a pre-scan candidate without either reporting or dismissing it;
  - ignores injection flags (overall cannot be GREEN if any were found);
  - has no disclaimer.

With --render it also writes the human-readable Markdown report.

Usage:
  python3 verify_report.py report.json --prescan prescan.json [--render report.md]
"""
import argparse
import json
import sys
from pathlib import Path

import yaml

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # Windows consoles default to cp1252
    except (AttributeError, ValueError):
        pass


HERE = Path(__file__).resolve().parent
PLAYBOOK = HERE.parent / "playbook"
RANK = {"GREEN": 0, "YELLOW": 1, "RED": 2}
DISCLAIMER_MIN = "not legal advice"


def load_playbook():
    statutes = yaml.safe_load((PLAYBOOK / "statutes.yaml").read_text(encoding="utf-8"))
    cases = yaml.safe_load((PLAYBOOK / "cases.yaml").read_text(encoding="utf-8"))["cases"]
    rules = {}
    for f in sorted((PLAYBOOK / "rules").glob("*.yaml")):
        for r in yaml.safe_load(f.read_text(encoding="utf-8"))["rules"]:
            rules[r["id"]] = r
    return statutes, cases, rules


def norm(s):
    return " ".join((s or "").lower().split())


def check_citation(c, statutes, cases, exec_date, errors, unverified, where):
    if "case" in c:
        case = cases.get(c["case"])
        if not case:
            errors.append(f"{where}: case '{c['case']}' is not in cases.yaml")
        elif not case.get("verified"):
            unverified.add(f"{case['name']} ({case['citation']})")
        return
    sid, sec = c.get("statute"), str(c.get("section", ""))
    st = statutes["statutes"].get(sid)
    if not st:
        errors.append(f"{where}: statute '{sid}' is not in statutes.yaml")
        return
    if sec not in st.get("sections", {}):
        errors.append(f"{where}: section '{sec}' of {st['title']} is not in the index")
        return
    if st.get("status") == "repealed":
        rep = st.get("repealed_on")
        if exec_date is None or exec_date >= rep:
            new = st.get("section_map", {}).get(sec)
            hint = f" Use {statutes['statutes'][st['replaced_by']]['title']} s.{new}." if new else ""
            errors.append(f"{where}: cites repealed {st['title']} s.{sec} for a document dated "
                          f"{exec_date or 'unknown'} (repealed {rep}).{hint}")
    if not st["sections"][sec].get("text_checked"):
        unverified.add(f"{st['title']} s.{sec}")


def verify(report, prescan):
    statutes, cases, rules = load_playbook()
    errors, warnings, unverified = [], [], set()

    for key in ("document", "overall", "escalate", "findings", "dismissed_candidates", "checked_ok", "disclaimer"):
        if key not in report:
            errors.append(f"missing top-level field '{key}'")
    if errors:
        return errors, warnings, unverified

    doc_types = prescan["doc_types"]
    exec_date = report["document"].get("execution_date") or prescan.get("execution_date_guess")
    clauses = {c["id"]: c["text"] for c in prescan["clauses"]}

    if not prescan.get("supported"):
        if report["findings"]:
            errors.append("document type unsupported, but the report contains findings")
        if report["overall"] != "UNSUPPORTED":
            errors.append("document type unsupported: overall must be 'UNSUPPORTED'")
        return errors, warnings, unverified

    if report["overall"] not in RANK:
        errors.append(f"overall must be GREEN, YELLOW or RED, got {report['overall']!r}")

    worst, must_escalate, reported = "GREEN", False, set()
    for i, f in enumerate(report["findings"]):
        where = f"finding #{i + 1} ({f.get('rule_id')})"
        rule = rules.get(f.get("rule_id"))
        if not rule:
            errors.append(f"{where}: unknown rule_id")
            continue
        if "any" not in rule["applies_to"] and not set(rule["applies_to"]) & set(doc_types):
            errors.append(f"{where}: rule does not apply to doc types {doc_types}")
        if f.get("severity") != rule["severity"]:
            errors.append(f"{where}: severity {f.get('severity')} differs from playbook {rule['severity']}")
        ref = f.get("clause_ref")
        if rule["type"] == "missing":
            if ref:
                warnings.append(f"{where}: 'missing' finding should have clause_ref null")
        elif rule["type"] == "judgement" and ref is None:
            pass  # whole-document assessment (e.g. stamp duty) — no single clause
        else:
            if ref not in clauses:
                errors.append(f"{where}: clause_ref {ref!r} does not exist")
            elif not f.get("quote") or norm(f["quote"]) not in norm(clauses[ref]):
                errors.append(f"{where}: quote is not found verbatim in {ref}")
        cits = f.get("citations", [])
        if rule["basis"] != "best_practice" and not cits:
            errors.append(f"{where}: statutory/case-law finding with no citation")
        for c in cits:
            check_citation(c, statutes, cases, exec_date, errors, unverified, where)
            if c not in rule["citations"]:
                warnings.append(f"{where}: citation {c} is outside the rule's own citation list")
        worst = max(worst, rule["severity"], key=RANK.get)
        must_escalate |= bool(rule["escalate"])
        reported.add((rule["id"], ref))

    dismissed = {(d.get("rule_id"), d.get("clause_ref")) for d in report["dismissed_candidates"]}
    for d in report["dismissed_candidates"]:
        if not d.get("reason"):
            errors.append(f"dismissed candidate {d.get('rule_id')}/{d.get('clause_ref')} has no reason")
    ok_rules = {c.get("rule_id") for c in report["checked_ok"]}
    rule_ids_reported = {r for r, _ in reported}
    for cand in prescan["candidates"]:
        rid = cand["rule_id"]
        if cand["kind"] == "flag":
            for cid in cand["clauses"]:
                if (rid, cid) not in reported and (rid, cid) not in dismissed:
                    errors.append(f"candidate {rid} in {cid} was neither reported nor dismissed")
        elif cand["kind"] == "missing":
            if rid not in rule_ids_reported and (rid, None) not in dismissed:
                errors.append(f"missing-element candidate {rid} was neither reported nor dismissed")
        else:
            if rid not in rule_ids_reported and rid not in ok_rules:
                errors.append(f"judgement rule {rid} was not assessed (add a finding or a checked_ok entry)")

    if prescan["injection_flags"]:
        if not report.get("injection_flags"):
            errors.append("pre-scan found injection content but the report does not show it")
        worst = max(worst, "YELLOW", key=RANK.get)
        must_escalate = True

    if report["overall"] in RANK and report["overall"] != worst:
        errors.append(f"overall is {report['overall']} but findings/flags require {worst}")
    if must_escalate and not report["escalate"]:
        errors.append("a fired rule or injection flag requires escalation to an advocate, but escalate is false")
    if DISCLAIMER_MIN not in norm(report["disclaimer"]):
        errors.append("disclaimer must state that the report is not legal advice")
    return errors, warnings, unverified


def render(report, prescan, unverified):
    statutes, cases, rules = load_playbook()
    icon = {"RED": "🔴 RED", "YELLOW": "🟡 YELLOW", "GREEN": "🟢 GREEN", "UNSUPPORTED": "⚪ UNSUPPORTED"}
    d = report["document"]
    L = [f"# Agreement review — {prescan['source_file']}", "",
         f"**Overall:** {icon.get(report['overall'], report['overall'])}  ",
         f"**Document type:** {', '.join(prescan['doc_types']) or 'unsupported'}  ",
         f"**Date of execution:** {d.get('execution_date') or 'not found'}  ",
         f"**State of execution:** {d.get('state_of_execution') or 'not stated — needed for stamp duty'}", ""]
    if report["escalate"]:
        L += ["> **Consult a practising advocate before signing.** Reasons: "
              + "; ".join(report.get("escalation_reasons") or ["see findings"]), ""]
    if report.get("injection_flags"):
        L += ["## ⚠️ Suspicious content in the document", "",
              "The document contains text aimed at manipulating an AI reviewer, or text hidden from a human reader. "
              "It was removed before review. Treat the document with caution.", ""]
        for fl in report["injection_flags"]:
            L.append(f"- {fl.get('kind')}: {fl.get('excerpt') or ''}")
        L.append("")
    if unverified:
        L += ["> **Citation status:** the following references have not yet been checked by an advocate "
              "against the official text: " + "; ".join(sorted(unverified)), ""]
    order = sorted(report["findings"], key=lambda f: -RANK[f["severity"]])
    if order:
        L += ["## Findings", ""]
    for n, f in enumerate(order, 1):
        r = rules[f["rule_id"]]
        cits = []
        for c in f.get("citations", []):
            if "case" in c:
                k = cases[c["case"]]
                cits.append(f"{k['name']}, {k['citation']}" + ("" if k.get("verified") else " (unverified)"))
            else:
                cits.append(f"{statutes['statutes'][c['statute']]['title']}, s.{c['section']}")
        L += [f"### {n}. {icon[f['severity']]} — {r['title']} ({f['rule_id']})",
              f"**Clause:** {f.get('clause_ref') or 'missing from the document'}"]
        if f.get("quote"):
            L.append(f"> {f['quote']}")
        L += ["", f["issue"], "", f"**Law:** {'; '.join(cits) or 'best practice (no statute)'}  ",
              f"**Suggested change:** {f['recommendation']}  ", f"**Confidence:** {f.get('confidence', 'n/a')}", ""]
    if report.get("checked_ok"):
        L += ["## Checked, no issue found", ""]
        L += [f"- {c['rule_id']} — {rules[c['rule_id']]['title']}: {c.get('note', '')}" for c in report["checked_ok"]]
        L.append("")
    if report.get("out_of_scope"):
        L += ["## Not covered by this review", ""] + [f"- {x}" for x in report["out_of_scope"]] + [""]
    L += ["---", f"*{report['disclaimer']}*"]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("report")
    ap.add_argument("--prescan", required=True)
    ap.add_argument("--render")
    ap.add_argument("--json", action="store_true", help="print the result as JSON")
    a = ap.parse_args()
    report = json.loads(Path(a.report).read_text(encoding="utf-8"))
    prescan = json.loads(Path(a.prescan).read_text(encoding="utf-8"))
    errors, warnings, unverified = verify(report, prescan)
    if a.json:
        print(json.dumps({"pass": not errors, "errors": errors, "warnings": warnings,
                          "unverified_citations": sorted(unverified)}, indent=2))
    else:
        for w in warnings:
            print("WARN ", w)
        for e in errors:
            print("FAIL ", e)
        print("PASS" if not errors else f"{len(errors)} error(s) - report must be corrected before it is shown")
    if not errors and a.render:
        Path(a.render).write_text(render(report, prescan, unverified), encoding="utf-8")
        if not a.json:
            print(f"rendered -> {a.render}")
    sys.exit(0 if not errors else 1)


if __name__ == "__main__":
    main()
