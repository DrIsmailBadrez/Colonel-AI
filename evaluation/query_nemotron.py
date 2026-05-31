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
import time
import urllib.request
from datetime import datetime, timezone

from dotenv import load_dotenv

from tactical_prompt import build_messages

load_dotenv(override=True)

BASE_URL = os.environ["NEMOTRON_LLM_URL"].rstrip("/")
MODEL = os.getenv("NEMOTRON_LLM_MODEL", "nvidia/nemotron-3-super")
ENABLE_THINKING = os.getenv("NEMOTRON_ENABLE_THINKING", "false").lower() == "true"
OUT_PATH = os.getenv(
    "OUT_PATH",
    f"tactical_results_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.txt",
)

PROMPTS = [
    "Colonel, this is Rifle-3, I'm hit — send me a medic.",
    "What friendly units are near my position?",
    "Am I clear to advance north?",
]


def ask(
    prompt: str,
    retries: int = 3,
    timeout: int = 240,
    instruction: str | None = None,
    backoff: float = 0.0,
) -> str:
    body = {
        "model": MODEL,
        "messages": build_messages(prompt, instruction=instruction),
        "max_tokens": 1500,
        "temperature": 0.7,
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
            msg = data["choices"][0]["message"]
            # Same reasoning convention as the pipecat server (server/nemotron_llm.py):
            # with thinking enabled, vLLM running a reasoning parser returns the
            # reasoning trace in a separate `reasoning_content` field; without a
            # parser it arrives inline in `content`. Capture either so the reasoning
            # response isn't lost — fold a separate trace back into <think>...</think>.
            reasoning = (msg.get("reasoning_content") or "").strip()
            content = (msg.get("content") or "").strip()
            return f"<think>{reasoning}</think>\n{content}" if reasoning else content
        except Exception as e:  # noqa: BLE001
            last_err = e
            print(f"    attempt {attempt}/{retries} failed: {e}", flush=True)
            if backoff and attempt < retries:
                time.sleep(backoff * attempt)  # linear backoff between retries
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
        f"\n##### RUN {stamp} | model={MODEL} | thinking={ENABLE_THINKING} #####\n\n"
    )
    with open(OUT_PATH, "a") as f:
        f.write(header + "\n\n".join(records) + "\n")
    print(f"\nAppended {len(records)} responses to {os.path.abspath(OUT_PATH)}")


if __name__ == "__main__":
    main()
