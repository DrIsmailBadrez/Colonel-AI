# llm-prompting

Tactical situational-awareness prompt tests for an NVIDIA Nemotron LLM endpoint.

The system builds a structured **SITUATION** bundle, applies a rules-first
scaffold, and enforces a strict parseable output format (Answer / Recommendation
/ Referenced / Caveats / Confidence) with citation discipline.

## Files

| File | Purpose |
| --- | --- |
| `tactical_prompt.py` | Builds the chat messages (`build_messages(prompt)`): system scaffold + SITUATION bundle. Pure, no network. |
| `query_nemotron.py` | Sends a list of prompts to the live endpoint and appends verbatim responses to a results file. |
| `parse_results.py` | Parses a results file and reports the five structured fields plus inferred **gaps** (what the model says is missing from the bundle). |
| `tactical_results.sample.txt` | Example output, so you can try `parse_results.py` without hitting the endpoint. |
| `.env.example` | Template for the required environment variables. |

## Setup

Requires Python >= 3.11 and [`uv`](https://docs.astral.sh/uv/).

```bash
cp .env.example .env      # then fill in NEMOTRON_LLM_URL
uv sync                   # installs python-dotenv
```

## Run the prompt test

```bash
uv run query_nemotron.py
```

Edit the `PROMPTS` list in `query_nemotron.py` to change the test prompts.
Results are **appended** (one run per `##### RUN ... #####` header) so progress is
tracked across runs. Output path defaults to a timestamped file, or set `OUT_PATH`.

## Analyze the results

```bash
uv run parse_results.py <results-file>     # default: tactical_results.txt

# Try it against the bundled sample:
uv run parse_results.py tactical_results.sample.txt
```

This prints each prompt's structured fields and flags gaps — prompts the model
answered with `Recommendation=UNKNOWN`, `Referenced=none`, or caveats that signal
missing data — i.e. what to add to the SITUATION bundle next.
