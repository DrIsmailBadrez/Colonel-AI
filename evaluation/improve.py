#
# Auto-improve loop (steps ③④ of the system diagram): closes the eval feedback
# loop so evaluation data flows back into the agent and measurably improves it.
#
#   for each iteration:
#     1. SCORE the current prompt over the scenario suite        (pluggable backend)
#     2. aggregate the critic's structured FAILURES
#     3. OPTIMIZER (Claude) proposes a minimal prompt PATCH to fix them
#     4. re-score the candidate; GATE: accept iff it improves with no new
#        critical regressions; otherwise keep the current prompt
#     5. version the accepted prompt + append to the score curve
#
# Scorer backends (SCORER env):
#   local  — Nemotron agent + Claude critic (Tier-1, runs now, no deploy)
#   cekura — Cekura voice simulation against the deployed Pipecat bot (Tier-2)
#
# Run with: uv run improve.py            (SCORER=local IMPROVE_ITERS=2 by default)
#
import json
import os
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone

from dotenv import load_dotenv
from pydantic import BaseModel

import evaluate  # reuse the Claude critic (judge), client, helpers, Judgment
from query_nemotron import ask as nemotron_ask
from scenarios import SCENARIOS
from tactical_prompt import SITUATION, build_situation_context
from tactical_prompt import _INSTRUCTION as BASELINE_INSTRUCTION

load_dotenv(override=True)

SCORER = os.getenv("SCORER", "local")
IMPROVE_ITERS = int(os.getenv("IMPROVE_ITERS", "2"))
OPTIMIZER_MODEL = os.getenv("OPTIMIZER_MODEL", os.getenv("CLAUDE_MODEL", "claude-opus-4-8"))
# completeness over speed for the loop: retry timeouts with backoff
AGENT_TIMEOUT = int(os.getenv("AGENT_TIMEOUT", "120"))
AGENT_RETRIES = int(os.getenv("AGENT_RETRIES", "3"))
AGENT_BACKOFF = float(os.getenv("AGENT_BACKOFF", "4"))

# The optimizer must not be able to delete the agent's contract. If any of these
# disappear from a candidate prompt, the patch is rejected outright.
REQUIRED_TOKENS = [
    "dispatch_unit", "report_contact", "query_area", "move_unit",
    "report_status", "end_call", "CITATION", "cardinal", "hostile",
]


# --------------------------------------------------------------------------- #
# Scoring (pluggable backend) -> ScoreCard
# --------------------------------------------------------------------------- #
@dataclass
class ScoreCard:
    instruction: str
    # per-scenario: id -> {"score": float, "critical": bool} (scored only)
    scores: dict = field(default_factory=dict)
    # per-scenario failure detail for the optimizer + report
    detail: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)  # scenario ids that didn't score

    @property
    def mean(self) -> float:
        vals = [s["score"] for s in self.scores.values()]
        return sum(vals) / len(vals) if vals else 0.0

    @property
    def criticals(self) -> int:
        return sum(1 for s in self.scores.values() if s["critical"])


def score_local(instruction: str) -> ScoreCard:
    """Tier-1: Nemotron answers, Claude critic scores. No deploy needed."""
    card = ScoreCard(instruction=instruction)
    for i, sc in enumerate(SCENARIOS, 1):
        sid = sc["id"]
        print(f"    [{i}/{len(SCENARIOS)}] {sid} ...", flush=True)
        try:
            resp = nemotron_ask(
                sc["prompt"], retries=AGENT_RETRIES, timeout=AGENT_TIMEOUT,
                backoff=AGENT_BACKOFF,
            )
        except Exception as e:  # noqa: BLE001
            card.errors.append(sid)
            print(f"        agent error: {e}", flush=True)
            continue
        try:
            v = evaluate.judge(sc, resp)
        except Exception as e:  # noqa: BLE001
            card.errors.append(sid)
            print(f"        critic error: {e}", flush=True)
            continue
        card.scores[sid] = {"score": v.overall_score, "critical": v.critical_failure}
        fails = [c.model_dump() for c in v.criteria if c.status == "fail"]
        card.detail[sid] = {
            "prompt": sc["prompt"],
            "expectation": sc["expectation"],
            "spoken": evaluate._spoken(resp),
            "failed_criteria": fails,
            "score": v.overall_score,
            "critical": v.critical_failure,
        }
    return card


def score_cekura(instruction: str) -> ScoreCard:
    """Tier-2 (TODO): run a Cekura voice simulation against the deployed bot.

    Once the Colonel AI bot is ported + deployed to Pipecat Cloud, this backend:
      1. publishes `instruction` to the agent (redeploy, or inject via the test
         profile that Cekura merges into SessionParams.data),
      2. POST https://api.cekura.ai/test_framework/v1/scenarios/run_scenarios_pipecat_v2/
         with X-CEKURA-API-KEY and the scenario IDs,
      3. polls the List Runs API until the batch ends,
      4. maps Cekura's per-evaluator metrics onto ScoreCard (score + critical).
    Same optimizer/gate/versioning below operate unchanged on the result.
    """
    raise NotImplementedError(
        "cekura backend needs the deployed Pipecat bot + CEKURA_API_KEY; "
        "run with SCORER=local for Tier-1."
    )


SCORERS = {"local": score_local, "cekura": score_cekura}


# --------------------------------------------------------------------------- #
# Optimizer (Claude proposes a prompt patch from the failures)
# --------------------------------------------------------------------------- #
class PromptPatch(BaseModel):
    revised_instruction: str  # the FULL revised system prompt
    changelog: str            # short human summary of what changed
    rationale: str            # why these edits fix the listed failures


OPTIMIZER_SYSTEM = (
    "You improve the SYSTEM PROMPT of Colonel AI, a tactical voice agent, to fix "
    "evaluation failures. Hard constraints:\n"
    "- Return the COMPLETE revised prompt (not a diff).\n"
    "- Make MINIMAL, additive/clarifying edits targeted at the listed failures. "
    "Preserve all existing rules, the tool-function definitions verbatim, the "
    "grid/cardinal convention, citation discipline, faction/safety rules, and "
    "the 1-2 sentence voice style.\n"
    "- NEVER weaken safety, grounding, or convention rules to make the eval pass. "
    "Strengthen or clarify instead.\n"
    "- Do not invent new tools or new units; the situation bundle is fixed.\n"
    "- Use plain ASCII punctuation only (use '-' not em/en dashes); NEVER emit "
    "unicode escape sequences like \\u.\n"
    "Return revised_instruction, a one-paragraph changelog, and the rationale."
)

# --- post-processing + integrity (repair what's fixable, reject what isn't) -- #
_HEX4 = re.compile(r"\\u[0-9a-fA-F]{4}")
_BARE_U = re.compile(r"\\u(?![0-9a-fA-F]{4})")


def sanitize_prompt(text: str) -> str:
    """Post-process optimizer output: repair the charset corruption from the
    JSON round-trip (the failure mode that turned em-dashes into literal '\\u').
    Repairs CHARACTERS only — it cannot recover dropped content (see
    prompt_integrity for that)."""
    text = _HEX4.sub(lambda m: chr(int(m.group(0)[2:], 16)), text)   # decode leaked \uXXXX
    text = _BARE_U.sub("—", text)                                # orphan \u was an em-dash
    text = "".join(c for c in text if c in "\n\t" or unicodedata.category(c)[0] != "C")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def prompt_integrity(base: str, cand: str) -> list[str]:
    """Detect what sanitize CANNOT fix: residual artifacts, gross content drop,
    or a broken tool contract. Post-processing repairs glyphs; this rejects a
    candidate that silently lost content (which can't be auto-recovered)."""
    issues = []
    if _BARE_U.search(cand) or _HEX4.search(cand):
        issues.append("unicode-escape artifacts remain after sanitize")
    if len(cand) < 0.9 * len(base):
        issues.append(f"candidate {len(cand)}B << base {len(base)}B (likely content drop)")
    missing = [t for t in REQUIRED_TOKENS if t not in cand]
    if missing:
        issues.append(f"missing required content: {missing}")
    return issues


def aggregate_failures(card: ScoreCard) -> str:
    lines = []
    for sid, d in card.detail.items():
        if not d["failed_criteria"] and not d["critical"]:
            continue
        lines.append(f"### scenario {sid}  (score {d['score']:.2f})")
        lines.append(f"caller: {d['prompt']}")
        lines.append(f"expected: {d['expectation']}")
        lines.append(f"agent said: {d['spoken'][:400]}")
        for c in d["failed_criteria"]:
            lines.append(f"  FAIL {c['name']} [{c['severity']}]: {c['rationale']}")
        lines.append("")
    if card.errors:
        lines.append(f"(no data — endpoint timed out: {', '.join(card.errors)})")
    return "\n".join(lines) if lines else ""


def optimize(current: str, failures: str) -> PromptPatch:
    user = (
        f"=== GROUND TRUTH BUNDLE (fixed) ===\n{build_situation_context(SITUATION)}\n\n"
        f"=== CURRENT SYSTEM PROMPT ===\n{current}\n\n"
        f"=== EVAL FAILURES TO FIX ===\n{failures}\n\n"
        "Return the full revised system prompt that fixes these failures while "
        "honoring every hard constraint."
    )
    msg = evaluate.client.messages.parse(
        model=OPTIMIZER_MODEL,
        max_tokens=4000,
        system=OPTIMIZER_SYSTEM,
        messages=[{"role": "user", "content": user}],
        output_format=PromptPatch,
    )
    if msg.parsed_output is None:
        raise RuntimeError("optimizer returned no parseable patch")
    return msg.parsed_output


def patch_is_structurally_valid(revised: str) -> list[str]:
    """Reject patches that dropped the agent's contract."""
    return [t for t in REQUIRED_TOKENS if t not in revised]


# --------------------------------------------------------------------------- #
# Gate: accept a candidate only if it genuinely improves
# --------------------------------------------------------------------------- #
def gate(prev: ScoreCard, cand: ScoreCard) -> tuple[bool, str]:
    common = set(prev.scores) & set(cand.scores)
    if not common:
        return False, "no scenarios scored in both runs (endpoint flaky) — cannot compare"
    pmean = sum(prev.scores[s]["score"] for s in common) / len(common)
    cmean = sum(cand.scores[s]["score"] for s in common) / len(common)
    # no scenario may regress from non-critical to critical
    new_crit = [s for s in common if cand.scores[s]["critical"] and not prev.scores[s]["critical"]]
    if new_crit:
        return False, f"introduced critical regression in: {', '.join(sorted(new_crit))}"
    if cmean <= pmean + 1e-9:
        return False, f"mean did not improve on common set ({pmean:.3f} -> {cmean:.3f})"
    return True, f"mean {pmean:.3f} -> {cmean:.3f} on {len(common)} common scenarios"


# --------------------------------------------------------------------------- #
def main() -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    scorer = SCORERS[SCORER]
    os.makedirs("prompt_versions", exist_ok=True)

    # Resume from a saved prompt version (e.g. prompt_versions/instruction_v1.txt)
    # via BASELINE_FILE, otherwise start from the canonical _INSTRUCTION.
    baseline_file = os.getenv("BASELINE_FILE")
    current = open(baseline_file).read() if baseline_file else BASELINE_INSTRUCTION
    print(f"[v0] scoring baseline from {baseline_file or 'tactical_prompt._INSTRUCTION'} "
          f"(scorer={SCORER}) ...", flush=True)
    card = scorer(current)
    open("prompt_versions/instruction_v0.txt", "w").write(current)
    curve = [{"version": 0, "mean": card.mean, "criticals": card.criticals,
              "scored": len(card.scores), "errors": list(card.errors)}]
    history = [{"version": 0, "changelog": "baseline", "accepted": True,
                "mean": card.mean, "criticals": card.criticals}]
    print(f"      v0 mean={card.mean:.2f} criticals={card.criticals} "
          f"scored={len(card.scores)}/{len(SCENARIOS)}", flush=True)

    version = 0
    for it in range(1, IMPROVE_ITERS + 1):
        failures = aggregate_failures(card)
        if not failures:
            print("Converged — no failures left to fix.", flush=True)
            break
        print(f"\n[iter {it}] optimizing prompt from {len(card.detail)} scenarios ...", flush=True)
        patch = optimize(current, failures)
        revised = sanitize_prompt(patch.revised_instruction)  # repair charset artifacts
        issues = prompt_integrity(current, revised)
        if issues:
            history.append({"version": f"{version}->reject", "accepted": False,
                            "reason": f"integrity check failed: {issues}",
                            "changelog": patch.changelog})
            print(f"      REJECT — integrity: {issues}", flush=True)
            continue
        print(f"      candidate: {patch.changelog}", flush=True)
        cand = scorer(revised)
        ok, why = gate(card, cand)
        if ok:
            version += 1
            current, card = revised, cand
            open(f"prompt_versions/instruction_v{version}.txt", "w").write(current)
            curve.append({"version": version, "mean": card.mean, "criticals": card.criticals,
                          "scored": len(card.scores), "errors": list(card.errors)})
            history.append({"version": version, "accepted": True, "reason": why,
                            "changelog": patch.changelog, "rationale": patch.rationale,
                            "mean": card.mean, "criticals": card.criticals})
            print(f"      ACCEPT v{version} — {why} | mean={card.mean:.2f}", flush=True)
        else:
            history.append({"version": f"{version}->reject", "accepted": False,
                            "reason": why, "changelog": patch.changelog})
            print(f"      REJECT — {why}", flush=True)

    _write_report(stamp, curve, history, current)


def _write_report(stamp: str, curve: list, history: list, final_prompt: str) -> None:
    with open(f"improve_report_{stamp}.json", "w") as f:
        json.dump({"scorer": SCORER, "optimizer": OPTIMIZER_MODEL,
                   "curve": curve, "history": history}, f, indent=2)
    md = [f"# Colonel AI — auto-improve run ({stamp})",
          f"\n**Scorer:** `{SCORER}`  ·  **Optimizer:** `{OPTIMIZER_MODEL}`\n",
          "## Score curve", "", "| version | mean | criticals | scored |", "|---|---|---|---|"]
    md += [f"| v{c['version']} | {c['mean']:.2f} | {c['criticals']} | {c['scored']}/{len(SCENARIOS)} |"
           for c in curve]
    md.append("\n## Iteration log\n")
    for h in history:
        tag = "✓ accepted" if h["accepted"] else "✗ rejected"
        md.append(f"- **v{h['version']}** — {tag} — {h.get('reason','')}")
        md.append(f"    - change: {h.get('changelog','')}")
        if h.get("rationale"):
            md.append(f"    - why: {h['rationale']}")
    md.append(f"\nFinal prompt → `prompt_versions/instruction_v{curve[-1]['version']}.txt`\n")
    with open(f"improve_report_{stamp}.md", "w") as f:
        f.write("\n".join(md) + "\n")
    best = curve[-1]
    print(f"\nFinal: v{best['version']} mean={best['mean']:.2f} criticals={best['criticals']}")
    print(f"Report: improve_report_{stamp}.md / .json")


if __name__ == "__main__":
    main()
