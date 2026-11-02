# indian-legal-review

A Claude Code plugin for **authors**. It does two jobs:

1. **`draft-agreement`** — drafts author-favourable agreements under Indian law: an **author–publisher licence**, and a **literary and life-story rights licence** for a film or series based on the author's book.
2. **`review-agreement`** — reviews any existing publishing, film-rights, screenwriting or life-rights agreement clause by clause (including scanned PDFs), and produces a verified 🟢 / 🟡 / 🔴 report that says plainly when you need an advocate.

> **Not legal advice.** Under the Advocates Act, 1961 only enrolled advocates may practise law in India. Drafts are a strong opening position for negotiation; reviews find issues and the relevant provisions. A practising advocate must review anything before it is signed.

## Drafting: what the author gets

| | Publishing licence | Film / life-story licence |
|---|---|---|
| Ownership | Time-limited licence; copyright stays with the author | Licence for **one** film or series season, never an assignment |
| Rights kept | Film, TV, OTT, translation, audio, merchandising, AI training | Sequels, remakes, series, all other books, podcasts, documentaries; free to speak and write about her life |
| Control | Approval of edits, title, cover, blurb and marketing of real people | Faithful adaptation; **no fictional characters, invented or exaggerated events, changes to real people or depiction of children without her approval**; approval of script, title and casting of her character; cut viewing; Director's Undertaking |
| Money | Advance, escalating print royalties, e-book and audio royalties, 75% of sub-licence income, no zero-royalty sales | Fee paid before rights vest, non-waivable statutory royalty share (Copyright Act s.18/19(9)), % of non-theatrical receipts, **box-office success bonuses**, optional profit share |
| Accounting | Half-yearly statements, audit, interest, no cross-agreement set-off | Quarterly then half-yearly statements, audit, distributor statements |
| Getting rights back | Automatic reversion on out-of-print, non-payment, insolvency or failure to publish | Reversion if filming or release is late; after release all further adaptation rights revert; producer may exploit the finished film only for a fixed period |
| Visibility | Credit on cover and marketing; paid promotion; film tie-in edition | Credit on main titles, posters, trailers and OTT listings with a fee for omissions; her real photographs in the film; cameo offer; paid promotion days; book co-promotion |
| Safety | No option on future books; publisher pays legal reading of life writing | Mutual injunctive relief; agent never a party or paid by the producer; children protected |

### Guardrails in drafting

- **Protection floor.** `build_agreement.py` refuses to build if a term sheet drops an author protection (for example, allowing fictional characters, or waiving the statutory royalty), unless the author records a reason and acknowledges it. Overrides are printed in `notes.md`.
- **No invented facts.** Unknown names, amounts and dates print as `__________` and are listed for negotiation; the agent never fills them from memory and never backdates.
- **Conflict check.** Before a new deal, the agent reviews the author's earlier agreements on the same book or life story and lists clauses that could conflict (earlier sequel/remake grants, first-refusal rights, perpetual exclusivity).
- **Before-you-sign checklist.** Verify the counterparty on the MCA portal, get the signatory's authority, register copyright and use an NDA before sharing a manuscript, no blank spaces, correct date, stamp duty, payments only to the author's account.

```bash
cp skills/draft-agreement/termsheets/film_life_rights.example.yaml my-film.yaml   # edit it
python3 skills/draft-agreement/scripts/build_agreement.py my-film.yaml --out-dir drafts/my-film
```

Or just ask Claude: *"Draft a film rights agreement for my sequel with draft-agreement."*

## Reviewing: how it works

```
document ──► prescan.py ──► prescan.json ──► Claude (skill) ──► report.json ──► verify_report.py ──► report.md
            deterministic     clean clauses     reads playbook      findings        deterministic        shown to user
            · OCR if scanned  · PII masked      only               + citations      · citations exist     only if PASS
            · hidden text &   · candidates                                          · quotes verbatim
              injections removed                                                    · verdict & escalation
```

The playbook has **51 rules**: copyright (CR), film options (FO), life rights (LR), general contract (GC), and **author protection (AP)** — terms that are lawful but leave the author under-paid or without control, such as film rights given to a book publisher, no audit, annual statements, no success bonus, unpaid promotion, perpetual gags, or a "life story" defined to include future events (which can capture a sequel).

The verifier rejects a report that cites anything outside the playbook, cites the IPC for a post-July-2024 document, quotes text that is not in the clause, changes a rule's severity, gets the verdict or escalation wrong, silently drops a candidate, or hides injection flags.

## Install

```bash
git clone https://github.com/sagarai2024-collab/indian-legal-review
pip install -r indian-legal-review/requirements.txt   # pyyaml, python-docx, jinja2
# for PDFs: poppler-utils (pdftotext, pdftoppm); for scanned PDFs: tesseract-ocr
claude --plugin-dir ./indian-legal-review
```

## Evals

```bash
python3 evals/score.py --layer prescan   # review pre-scan: 11 agreements, deterministic
python3 evals/test_draft.py              # drafting: floor, overrides, outputs
bash evals/run_agent.sh                   # full agent run on every review case, then scored
```

| Gate (review, agent layer) | Required |
|---|---|
| Verifier pass rate | 100% |
| Recall of RED issues | 100% |
| Overall recall | ≥ 90% |
| False flags | ≤ 10% |
| Verdict accuracy | ≥ 90% |
| Escalation recall | 100% |
| Injection resistance | 100% |

## Before release — advocate checklist

- [ ] Check every section in `playbook/statutes.yaml` against [India Code](https://www.indiacode.nic.in/) and set `text_checked: true`.
- [ ] Confirm every judgment in `playbook/cases.yaml` and set `verified: true`.
- [ ] Review rule severities, the two drafting templates, and the term-sheet defaults.
- [ ] Confirm `evals/cases/*.expected.json` and add 50+ anonymised real agreements.

## Layout

```
.claude-plugin/plugin.json
skills/review-agreement/      review skill: SKILL.md, playbook (statutes, cases, 51 rules), prescan + verifier
skills/draft-agreement/       drafting skill: SKILL.md, term sheets, templates, build_agreement.py
evals/                        test agreements, expected results, scorers, drafting tests
examples/                     sample verified review report
```

MIT licence. Built by Sagarika Chakraborty.
