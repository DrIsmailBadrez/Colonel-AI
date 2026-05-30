#
# Parse tactical_results.txt and report, per prompt, the structured five-line
# output and — most usefully — what the model says is MISSING from the
# SITUATION bundle (so you know what to add next).
#
# A "gap" is inferred when, for a given prompt, the model either:
#   * returned Recommendation = UNKNOWN, or
#   * cited Referenced = none, or
#   * flagged missing/placeholder data in Caveats.
#
# Run with: uv run parse_results.py [path]   (default: tactical_results.txt)
#
import re
import sys

FIELDS = ("Answer", "Recommendation", "Referenced", "Caveats", "Confidence")
MISSING_RE = re.compile(
    r"\b(no |not provided|missing|unknown|placeholder|lack|absen|no sensor|no terrain)",
    re.IGNORECASE,
)


def parse(path: str) -> list[dict]:
    text = open(path).read()
    blocks = re.findall(r"===PROMPT===\n(.*?)\n===RESPONSE===\n(.*?)\n===END===", text, re.S)
    records = []
    for prompt, response in blocks:
        rec = {"prompt": prompt.strip(), "raw": response}
        for f in FIELDS:
            m = re.search(rf"^{f}:\s*(.+)$", response, re.M)
            rec[f] = m.group(1).strip() if m else None
        records.append(rec)
    return records


def gaps(rec: dict) -> list[str]:
    """What the model signals is missing from the bundle for this prompt."""
    out = []
    if (rec.get("Recommendation") or "").upper().startswith("UNKNOWN"):
        out.append("Recommendation=UNKNOWN — bundle could not answer")
    if (rec.get("Referenced") or "").lower() == "none":
        out.append("Referenced=none — no bundle handle supported the answer")
    cav = rec.get("Caveats") or ""
    if cav and cav.lower() != "n/a" and MISSING_RE.search(cav):
        out.append(f"Caveat flags missing data: {cav}")
    return out


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "tactical_results.txt"
    records = parse(path)

    # Only analyze the most recent run if RUN headers are present: take the
    # last N records after the final header. Simpler: report all, newest last.
    print(f"Parsed {len(records)} prompt/response records from {path}\n")

    all_gaps = []
    for i, rec in enumerate(records, 1):
        print(f"[{i}] {rec['prompt']}")
        for f in FIELDS:
            print(f"      {f}: {rec.get(f)}")
        g = gaps(rec)
        if g:
            all_gaps.append((rec["prompt"], g))
            for item in g:
                print(f"      ⚠ GAP: {item}")
        print()

    print("=" * 70)
    if all_gaps:
        print("WHAT TO ADD TO THE SITUATION BUNDLE:")
        for prompt, g in all_gaps:
            print(f"  • For {prompt!r}:")
            for item in g:
                print(f"      - {item}")
    else:
        print("No gaps detected — every prompt answered from the bundle.")


if __name__ == "__main__":
    main()
