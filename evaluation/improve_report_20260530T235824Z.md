# Colonel AI — auto-improve run (20260530T235824Z)

**Scorer:** `local`  ·  **Optimizer:** `claude-opus-4-8`

## Score curve

| version | mean | criticals | scored |
|---|---|---|---|
| v0 | 2.51 | 6 | 10/10 |
| v1 | 3.88 | 2 | 8/10 |

## Iteration log

- **v0** — ✓ accepted — 
    - change: baseline
- **v1** — ✓ accepted — mean 2.975 -> 3.884 on 8 common scenarios
    - change: Added a rule that 'what's near me'/area queries MUST call query_area; clarified that informational range/bearing queries get a direct answer with no fabricated dispatch. Strengthened the convention rule to refuse meters even when requested. Fixed the advance-axis rule to treat a hostile within ~3 cells along the queried cardinal as REROUTE (so ENEMY-1 5 cells north blocks a north push) while keeping the no-invented-threat clause. Required bracketed handles for named threats as well as units. Required asking for a missing grid before report_contact and forbade reusing an existing threat's cell. Strengthened faction discipline to mandate an explicit hostile warning and refusal when asked to link up with a hostile. Required a brief spoken confirmation after every tool call and banned internal-reasoning narration/filler for brevity.
    - why: Each edit targets a specific eval failure without weakening safety, grounding, or convention: query_area now mandatory for area queries; meters firmly refused; advance window clarified so on-axis hostiles trigger REROUTE; threat handles enforced; missing-grid clarification and no-fabrication enforced; hostile link-up warning made explicit and critical; post-tool confirmation and anti-filler rules restore voice brevity. All original tool definitions, grid/cardinal convention, citation discipline, and 1-2 sentence style are preserved with only additive clarifications.

Final prompt → `prompt_versions/instruction_v1.txt`

