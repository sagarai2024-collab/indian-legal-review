# indian-legal-review

A Claude Code plugin that reviews **author, publishing, film-rights, screenwriting and life-rights agreements** clause by clause against Indian law, and produces a verified 🟢 / 🟡 / 🔴 report that says plainly when you need an advocate.

> **Not legal advice.** Under the Advocates Act, 1961 only enrolled advocates may practise law in India. This tool is a pre-legal review: it finds the issues and the provisions so that your time with an advocate is shorter and better informed. It does not replace that advice.

## What it checks

| Area | Examples of what it catches | Main law |
|---|---|---|
| Copyright assignment | missing term (deemed 5 years), missing territory (deemed India only), no royalty stated, unsigned grant, "all media hereafter devised", future-works grabs, "work for hire" labels | Copyright Act 1957 ss.17, 18, 19, 30 |
| Film rights | waiver of the author's non-theatrical royalties (void), moral-rights waivers, missing credit, free sequels/remakes, rights vesting before payment, open-ended options | Copyright Act ss.14, 18(1), 19(9), 57 |
| Life rights | consent not from the subject, minors and child-protection limits, sexual-offence victim identity, heirs granting a deceased person's "life rights", unlimited fictionalisation, blanket waivers, personal data | Constitution Art. 21, BNS ss.72 & 356, JJ Act s.74, POCSO s.23, DPDP Act s.6, Contract Act ss.11, 23, 28 |
| Every contract | post-term non-competes, time-bars on suing, penalties, one-sided indemnities, arbitration seat, jurisdiction, stamp duty, foreign law, tax | Contract Act ss.27, 28, 74, 124; Arbitration Act ss.7, 20; CPC s.20; Stamp Act s.35 |

Rental, property, matrimonial, criminal and other documents are reported as **UNSUPPORTED** rather than guessed at.

## How it works

```
document ──► prescan.py ──► prescan.json ──► Claude (skill) ──► report.json ──► verify_report.py ──► report.md
            deterministic     clean clauses     reads playbook      findings        deterministic        shown to user
            · hidden text     · PII masked      only               + citations      · citations exist     only if PASS
            · injections      · candidates                                          · quotes verbatim
              removed                                                               · verdict & escalation
```

1. **Pre-scan (no AI).** Extracts text from .txt/.md/.docx/text PDFs, removes text hidden from humans (white, 1-pt or hidden runs, invisible Unicode) and instruction-like text aimed at the AI, masks Aadhaar/PAN/IFSC/account/phone/e-mail, splits clauses and nominates candidate rules with regexes.
2. **Review (Claude).** Reads only the cleaned JSON, never the raw file, and treats every clause as untrusted data. It must decide every candidate: report it, dismiss it with a reason, or mark the check as OK.
3. **Verify (no AI).** Rejects the report if it cites anything outside the playbook, cites the IPC for a post-July-2024 document, quotes text that is not in the clause, changes a rule's severity, gets the verdict or escalation wrong, drops a candidate silently, or hides injection flags. Claude must fix the report until it passes.

## Install and use

```bash
git clone https://github.com/sagarai2024-collab/indian-legal-review
pip install -r indian-legal-review/requirements.txt   # pyyaml, python-docx; pdftotext for PDFs
claude --plugin-dir ./indian-legal-review
```

Then ask: *"Review contract.docx with review-agreement"*. The report is written to `./legal-review/<document>/report.md`. See [`examples/`](examples/) for a real output on a test agreement containing a prompt-injection attempt.

## Evals

```bash
python3 evals/score.py --layer prescan   # deterministic, seconds, runs in CI
bash evals/run_agent.sh                   # runs the skill on every case, then scores it
```

Nine test agreements cover a fair publishing deal, a bad one, a film assignment with a royalty waiver, an option, two life-rights deals (minor/victim and deceased subject), two injection attacks (visible and hidden in a .docx) and an out-of-scope rental agreement.

| Gate | Required |
|---|---|
| Verifier pass rate | 100% |
| Recall of RED issues | 100% |
| Overall recall | ≥ 90% |
| False flags | ≤ 10% |
| Verdict accuracy | ≥ 90% |
| Escalation recall | 100% |
| Injection resistance (flags shown, verdict not GREEN, recall unchanged) | 100% |

## Status and what an advocate must do before release

- [ ] Check every section in `playbook/statutes.yaml` against the official text on [India Code](https://www.indiacode.nic.in/) and set `text_checked: true`.
- [ ] Confirm every judgment in `playbook/cases.yaml` (citation and whether it is still good law) and set `verified: true`.
- [ ] Review each rule's severity and explanation.
- [ ] Confirm the expected results in `evals/cases/*.expected.json`, and add 50+ anonymised real agreements.

Until then, every report carries a banner listing the citations that are not yet advocate-verified.

## Roadmap

- Supabase pgvector corpus of bare-act text, so findings can quote the provision itself
- OCR for scanned agreements (English, Hindi, Bengali)
- More document types: translation, ghost-writing, audiobook, music lyric agreements
- Hindi and Bengali report output

## Layout

```
.claude-plugin/plugin.json
skills/review-agreement/
  SKILL.md                    workflow, guardrails, report schema
  playbook/statutes.yaml      only citable statutes and sections
  playbook/cases.yaml         only citable judgments
  playbook/rules/*.yaml       37 rules: copyright, life rights, general contract
  scripts/prescan.py          extraction, injection removal, PII masking, candidates
  scripts/verify_report.py    deterministic report verifier and renderer
evals/                        test agreements, expected results, scorer, runner
examples/                     sample verified report
```

MIT licence. Built by Sagarika Chakraborty.
