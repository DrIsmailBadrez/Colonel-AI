#
# Ad-hoc Nemotron LLM eval: send a list of prompts to the live endpoint and
# dump the verbatim responses to a parseable .txt file.
#
# Output format (one record per prompt, blank-line separated, stable delimiters):
#
#   ===PROMPT===
#   <the prompt text>
#   ===RESPONSE===
#   <model reply, possibly multi-line>
#   ===END===
#
# Run with: uv run query_nemotron.py
#
import json
import os
import urllib.request
from datetime import datetime, timezone

from dotenv import load_dotenv

from tactical_prompt import build_messages

load_dotenv(override=True)

BASE_URL = os.environ["NEMOTRON_LLM_URL"].rstrip("/")
MODEL = os.getenv("NEMOTRON_LLM_MODEL", "nvidia/nemotron-3-super")
ENABLE_THINKING = os.getenv("NEMOTRON_ENABLE_THINKING", "false").lower() == "true"

# --- Performance / sampling knobs (tunable via env) -------------------------
# The dominant latency lever is NEMOTRON_ENABLE_THINKING: with thinking OFF the
# model skips the long <think> trace and answers in ~1-3s (~90-100 tok/s) vs
# >120s with it ON. The five-line output is ~80-130 tokens, so a small
# MAX_TOKENS caps the worst case; low TEMPERATURE keeps tactical answers
# deterministic. The endpoint is a vLLM fleet behind an ALB, so cold-node
# routing still causes occasional timeouts — handled by retries below.
MAX_TOKENS = int(os.getenv("NEMOTRON_MAX_TOKENS", "256"))
TEMPERATURE = float(os.getenv("NEMOTRON_TEMPERATURE", "0.2"))
TOP_P = float(os.getenv("NEMOTRON_TOP_P", "0.9"))

OUT_PATH = os.getenv(
    "OUT_PATH",
    f"tactical_results_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.txt",
)

PROMPTS = [
    "Where's the nearest friendly medic?",
    "What's on the other side of this ridge?",
    "Am I clear to advance north?",
]


def ask(prompt: str, retries: int = 3, timeout: int = 120) -> str:
    body = {
        "model": MODEL,
        "messages": build_messages(prompt),
        "max_tokens": MAX_TOKENS,
        "temperature": TEMPERATURE,
        "top_p": TOP_P,
        # Stop once the record's terminal field is done so we don't pay for
        # trailing tokens after the parseable block.
        "stop": ["===END===", "\n\n\n"],
        "chat_template_kwargs": {"enable_thinking": ENABLE_THINKING},
    }
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(
                f"{BASE_URL}/chat/completions",
                data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"]
        except Exception as e:  # noqa: BLE001
            last_err = e
            print(f"    attempt {attempt}/{retries} failed: {e}", flush=True)
    raise last_err


def main() -> None:
    records = []
    for i, prompt in enumerate(PROMPTS, 1):
        print(f"[{i}/{len(PROMPTS)}] {prompt!r} ...", flush=True)
        try:
            answer = ask(prompt)
        except Exception as e:  # noqa: BLE001
            answer = f"<ERROR: {e}>"
        records.append(f"===PROMPT===\n{prompt}\n===RESPONSE===\n{answer}\n===END===")

    # Append each run (don't overwrite) so progress is tracked across runs.
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    header = (
        f"\n##### RUN {stamp} | model={MODEL} | thinking={ENABLE_THINKING} | "
        f"max_tokens={MAX_TOKENS} | temp={TEMPERATURE} | top_p={TOP_P} #####\n\n"
    )
    with open(OUT_PATH, "a") as f:
        f.write(header + "\n\n".join(records) + "\n")
    print(f"\nAppended {len(records)} responses to {os.path.abspath(OUT_PATH)}")


if __name__ == "__main__":
    main()
