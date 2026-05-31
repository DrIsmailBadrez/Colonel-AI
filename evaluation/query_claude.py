#
# Ad-hoc Claude (Opus) eval: send the tactical prompts to the Anthropic API and
# dump the verbatim responses to the same parseable .txt format as
# query_nemotron.py, so the two models can be compared side by side.
#
# Output format (one record per prompt, blank-line separated, stable delimiters):
#
#   ===PROMPT===
#   <the prompt text>
#   ===RESPONSE===
#   <model reply, possibly multi-line>
#   ===END===
#
# Run with: uv run query_claude.py
#
import os
from datetime import datetime, timezone

import anthropic
from dotenv import load_dotenv

from tactical_prompt import build_messages

load_dotenv(override=True)

# anthropic.Anthropic() reads ANTHROPIC_API_KEY from the environment (loaded from
# .env above). The key is never hardcoded here — keep it in .env (gitignored).
MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-4-8")
ENABLE_THINKING = os.getenv("CLAUDE_ENABLE_THINKING", "false").lower() == "true"
MAX_TOKENS = int(os.getenv("CLAUDE_MAX_TOKENS", "2048"))
OUT_PATH = os.getenv(
    "OUT_PATH",
    f"tactical_results_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.txt",
)

PROMPTS = [
    "Colonel, this is Rifle-3, I'm hit — send me a medic.",
    "What friendly units are near my position?",
    "Am I clear to advance north?",
]

client = anthropic.Anthropic()


def _split_messages(prompt: str) -> tuple[list[dict], list[dict]]:
    """Adapt build_messages (OpenAI-style) to Anthropic's split system/messages.

    The Anthropic API takes the system prompt as a top-level ``system`` arg, not
    as ``role: "system"`` entries in ``messages``. We collect every system block
    into a list of text blocks and put a cache_control breakpoint on the last one
    so the (identical) scaffold + situation bundle is cached across prompts.
    """
    msgs = build_messages(prompt)
    system_blocks = [
        {"type": "text", "text": m["content"]} for m in msgs if m["role"] == "system"
    ]
    if system_blocks:
        system_blocks[-1]["cache_control"] = {"type": "ephemeral"}
    chat = [
        {"role": m["role"], "content": m["content"]} for m in msgs if m["role"] != "system"
    ]
    return system_blocks, chat


def ask(prompt: str) -> str:
    system_blocks, chat = _split_messages(prompt)
    kwargs: dict = {
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "system": system_blocks,
        "messages": chat,
    }
    if ENABLE_THINKING:
        # Adaptive thinking routes reasoning into separate thinking blocks. Opus
        # omits the thinking text by default, so opt into summarized display to
        # actually get the reasoning response back.
        kwargs["thinking"] = {"type": "adaptive", "display": "summarized"}

    # Stream + get_final_message: the SDK auto-retries 429/5xx and streaming
    # avoids HTTP timeouts on larger max_tokens.
    with client.messages.stream(**kwargs) as stream:
        final = stream.get_final_message()
    # Same convention as query_nemotron: fold the reasoning trace (here, Claude's
    # thinking blocks — the provider's reasoning channel) into a <think>...</think>
    # prefix ahead of the answer text.
    reasoning = "".join(b.thinking for b in final.content if b.type == "thinking").strip()
    answer = "".join(b.text for b in final.content if b.type == "text").strip()
    return f"<think>{reasoning}</think>\n{answer}" if reasoning else answer


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
