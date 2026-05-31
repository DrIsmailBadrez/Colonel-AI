# Colonel AI

## 1. What is this?

**Real-time AI-powered battlefield command and control.**

Colonel AI is an autonomous tactical intelligence system -- the brain that sees, controls, and coordinates everything on the battlefield. Every soldier, every tank, every drone, every armored vehicle, every medical unit -- Colonel AI tracks them all in real time and makes command decisions across the entire force simultaneously.

Any operator on the battlefield gets a direct voice line to this brain. Speak naturally -- "I'm taking fire from the east, send backup" -- and the system processes speech in real time, reasons over the full operational picture, and executes: dispatching reinforcements, rerouting armor, scrambling drones, coordinating medical evacuation, repositioning scouts. Any asset on the battlefield can be dispatched through Colonel AI in under 2 seconds, end-to-end.

Built for contested environments where seconds matter and radio operators are overwhelmed.

---

---

## 2. Demo

[Demo video](https://www.loom.com/share/0ee88d3d01da4f8e912c4ae44751c5e0)

## 3. How we used Cekura, Nemotron models, and Pipecat

We used **Nemotron** (NVIDIA open-weights, served via a vLLM OpenAI-compatible endpoint) as the agent's reasoning LLM, and **Pipecat** for the end-to-end voice pipeline (STT -> Nemotron -> TTS). Nemotron was fast but under-followed instructions and gave terse, incomplete reasoning; Claude was accurate but over-reasoned and too slow for voice. So rather than swap models, we used **Claude as a critic to automatically improve Nemotron's system prompt** -- evaluation-driven, not vibes.

Goal of evaluation: turn "is the agent good?" into a measured, repeatable signal and feed it back into the agent. We defined **10 critical tactical scenarios** (CASEVAC dispatch, faction/safety, grounding, clear-to-advance...) each with ground truth, scored Nemotron with **Claude Opus as an LLM-judge critic** on a quantifiable rubric (correct tool call, grounding, safety, convention, brevity) with a **critical-failure gate**, then looped: failures -> Claude proposes a prompt patch -> re-score -> keep only if it measurably improves.

**Result: critical failures dropped from 6/10 to 2/10 in one measured round.**

## 4. What we built new during the hackathon

Built from scratch during the hackathon:

- **Voice agent on Pipecat** -- end-to-end STT -> Nemotron (vLLM) -> TTS for a tactical command-and-control assistant.
- **Real-time GUI** -- a live military map that visualizes the agent's tool calls (dispatch, contact reports, movement) as commands are issued.
- **Nemotron integration** -- a client that captures Nemotron's reasoning trace, with retry/backoff and prompt structuring to exploit vLLM prefix caching.
- **Auto-improvement loop** -- an automated eval harness (10-scenario suite, Claude-Opus critic, quantifiable rubric + critical-failure gate) that feeds failures back to Claude to rewrite Nemotron's prompt, with a regression gate so only measured gains are kept.

## 5. Feedback on the tools

**Nemotron (nvidia/nemotron-3-super, via the vLLM OpenAI-compatible endpoint)**

*Did well:* Fast and naturally terse -- a good fit for low-latency voice, often clean military-radio-style replies. When it followed the scaffold it reasoned correctly on tactical logic (e.g. "clear to advance north?" correctly returned REROUTE, named the hostile, and used our cells-plus-cardinal convention). The OpenAI-compatible vLLM surface made integration trivial.

*Could be better:*

- **Instruction-following** -- against a detailed system prompt it under-complied: skipping required tool calls, dropping citation handles, or not applying selection rules (e.g. nearest medic without checking `status==active`). Baseline 6/10 critical failures. Claude was accurate but over-reasoned and too slow for voice, so the sweet spot is Nemotron's speed with tighter steerability.
- **Reasoning depth was inconsistent** -- short/incomplete chains on multi-constraint prompts.
- **`reasoning_content` not surfaced** -- the hosted endpoint ran no reasoning parser, so with thinking enabled the chain-of-thought leaks into `content` rather than a separate field.
- **Hosted-endpoint reliability (NVIDIA/AWS infra, not the weights)** -- frequent timeouts (6/10 scenarios timed out even at 45-120s) throttled our eval loop.

**Cekura (building self-improvement loops)**

We built the loop primarily with our own local critic harness (Claude-Opus judge), using Cekura's workflow and Pipecat-integration model as the blueprint -- so this is design feedback plus loop-building lessons.

What would make closing the loop easier on Cekura:

- A first-class optimizer -> re-run -> gate primitive (or an API to update agent config + diff scores across runs). Cekura gives a great eval signal; the "feed failures back, accept only measured gains" controller is left to the builder.
- Machine-readable, per-criterion structured failures from the run API to drive an optimizer.
- First-class tool-call assertions --> agent tool calls fire server-side.
- A score-curve / cross-version regression view to directly serve the auto-improve theme.

Bugs / gotchas (transferable to anyone building loops):

- **LLM-judge score-scale drift** -- an unconstrained `overall_score` float drifted between runs (0-1 one run, ~0-5 the next) because JSON-schema structured outputs can't enforce numeric bounds; pin the scale in the prompt and clamp.
- **Prompt-optimizer corruption** -- regenerating the full prompt via structured output mangled unicode (em-dash to literal `\u`) and silently dropped a phrase; additive diffs + integrity checks are needed.
- **Self-eval reward-hacking risk** -- agent, critic, and optimizer in the same model family means a "win" can game the judge; a held-out set + regression gate are essential.

For more information about the evaluation pipeline, check our README [here](https://github.com/DrIsmailBadrez/Colonel-AI/blob/main/evaluation/EVAL.md)

## 6. [App Link](https://0cb0-2601-642-4c01-5ace-5886-eb43-606e-2da5.ngrok-free.app) 
## The Problem

Modern battlefield communications are a bottleneck. A wounded soldier calling for a medic has to reach a human radio operator, who relays to a human commander, who makes a decision, who relays back down the chain. That loop takes minutes. In those minutes, soldiers die.

But it's not just medics. A squad is pinned down and needs reinforcement. The squad leader radios in -- but the radio operator is handling three other calls. The request reaches a commander who's looking at a map that was updated six minutes ago. He sends backup -- to the wrong location. The squad gets flanked. Two soldiers are dead before anyone realizes the mistake.

A scout spots an enemy tank column moving through a valley. He reports it. The report sits in a queue behind a logistics request and a medevac call. By the time someone who can act on it finally sees it, the tanks have moved. The window to intercept them is gone.

A medic gets dispatched to a wounded soldier's last known position. But the squad moved 400 meters east under fire. The medic arrives at an empty field. The soldier bleeds out waiting for help that went to the wrong place.

And underneath all of it, there's a fundamental constraint: a human radio operator can only handle one call at a time. While they're coordinating a medevac, the squad calling for reinforcement is on hold. While they're relaying a fire mission, the scout report goes unheard. Every soldier is competing for the same single channel to the same overwhelmed human. Ten emergencies happening simultaneously, and one person picking which one to answer first.

Every one of these failures has the same root cause: information passes through a chain of overwhelmed humans, each one operating on data that's already stale by the time they see it. The right information exists somewhere in the system -- it just never reaches the right person fast enough to matter.

## The Solution

Colonel AI collapses the entire command chain into a single voice call. One AI brain replaces the radio operator, the battalion TOC, and the decision loop. And unlike a human operator who can only take one call at a time -- every soldier on the battlefield can call the brain simultaneously. Ten soldiers calling in ten emergencies at once, and every single one gets an immediate response with real-time information and real-time help. No queue. No hold. No one waiting while someone else's call gets handled first.

Every operator on the battlefield gets:

- **A commander who sees everything** -- every soldier, tank, drone, vehicle, and medic on the field, with real-time position, health, heading, and threat proximity, updated continuously
- **Total asset control** -- tanks, drones, armored vehicles, infantry squads, scout teams, medical units -- anything on the battlefield can be dispatched, repositioned, or redirected through a single voice command
- **Natural voice interaction** -- no radio protocols, no codes, just speak
- **Instant action** -- say "send me armor" and the nearest tank is rerouted to your position. Say "I need a medic" and the closest medical unit is dispatched to your GPS coordinates. Say "drone recon east" and a UAV is redirected. All within the same breath.
- **Autonomous unit coordination** -- because the AI sees every position, hears every call, and processes every threat in real time, every unit not under direct human control receives intelligent tactical decisions: tanks push aggressively toward threats, infantry engages when they have force advantage, scouts hold at recon distance, medics triage and heal, wounded units auto-evacuate to safety

---

## How It Works

### Voice Command Pipeline

A soldier initiates a call from the field. Audio flows through a low-latency pipeline:

```
Soldier's Voice
    |
    v
WebRTC Transport (peer-to-peer, encrypted)
    |
    v
NVIDIA Parakeet ASR (real-time speech-to-text, 16kHz streaming)
    |
    v
Silero VAD (voice activity detection -- knows when to listen vs. process)
    |
    v
NVIDIA Nemotron LLM (tactical reasoning + tool execution)
    |   \
    |    +---> Tool Calls: dispatch_unit, report_contact, move_unit, ...
    |    +---> Mutates live battlefield state via REST API
    |
    v
Gradium TTS (text-to-speech synthesis)
    |
    v
WebRTC Transport --> Soldier's Earpiece
```

**End-to-end latency: under 2 seconds from speech to action.**

The LLM's system prompt is rebuilt every second with a full spatial context dump: the caller's position, every friendly unit with pre-computed distance and cardinal direction from the caller, every known threat with range and bearing, and the last 50 battlefield events. The AI reasons over real positions, not approximations.

### Autonomous Battlefield Engine

Between voice commands, units operate autonomously. A real-time engine runs continuous tactical cycles:

```
+------ Tactical Cycle (1-second intervals) ------+
|                                                   |
|  1. Autonomous Movement                          |
|     - Infantry: engage if force advantage,       |
|       hold if outnumbered                        |
|     - Armor: aggressive push toward threats      |
|     - Scouts: advance to recon distance,         |
|       hold outside engagement range              |
|     - Commanders: maintain formation cohesion     |
|       (centroid tracking)                        |
|     - Medical: seek nearest casualty, heal to    |
|       100%, move to next                         |
|     - Wounded: auto-retreat to safe zone         |
|                                                   |
|  2. Combat Resolution                            |
|     - All combat units engage hostiles in range  |
|     - Damage stacking from multiple attackers    |
|     - Weapon orientation toward primary target   |
|                                                   |
|  3. Medical & Recovery                           |
|     - Field medics heal adjacent casualties      |
|     - Safe zone passive recovery                 |
|     - Triage: medics prioritize own survival,    |
|       then seek worst-off friendly               |
|                                                   |
|  4. State Broadcast                              |
|     - Full battlefield snapshot pushed to all     |
|       connected clients via WebSocket            |
+---------------------------------------------------+
```

### Human Override

Any unit can be pulled from autonomous control into direct human command at any time. One click: the AI stops, you drive. Release control and the unit seamlessly resumes autonomous operations. No mode switches, no reconfiguration.

Dispatched units that arrive near a human-controlled unit automatically enter **escort mode** -- they follow the operator, performing their role (medics heal, soldiers provide fire support) until dismissed.

---

## System Architecture

```
+-----------------------------------------------------------+
|              Operator Interface (Browser)                   |
|                                                             |
|  Tactical Display <-- WebSocket <-- C2 State Server        |
|  Unit Control                        (port 8000)           |
|                                                             |
|  Voice Input --> WebRTC --> AI Voice Agent (port 7860)     |
|  Voice Output <-- WebRTC <--                               |
+-------------------+-------------------+--------------------+
                    |                   |
     +--------------v--------+  +------v-----------------+
     |  C2 State Server      |  |   AI Voice Agent       |
     |  (FastAPI)             |  |   (Pipecat)            |
     |                       |  |                        |
     |  Battlefield State    |<-+  LLM Tool Execution:   |
     |  +-- unit registry    |  |  dispatch_unit()       |
     |  +-- event stream     |  |  report_contact()      |
     |  +-- comms transcripts|  |  move_unit()           |
     |                       |  |  report_status()       |
     |  Tactical Engine      |  |  query_area()          |
     |  +-- autonomous AI    |  |                        |
     |  +-- combat resolver  |  |  Voice Pipeline:       |
     |  +-- medical system   |  |  ASR -> LLM -> TTS     |
     |  +-- zone enforcement |  |                        |
     +-----------------------+  +------+-----------------+
                                       |
                    +------------------+------------------+
                    |                  |                  |
           +--------v------+ +--------v-----+ +---------v------+
           | NVIDIA Parakeet| |  Nemotron    | |  Gradium TTS   |
           | Speech-to-Text | |  LLM         | |  Text-to-Speech|
           | (streaming ASR)| |  (reasoning  | |  (voice synth) |
           |                | |   + tools)   | |                |
           +----------------+ +--------------+ +----------------+
```

---

## Tactical AI Behaviors

### Force-Level Decision Making

Every friendly unit runs a role-specific tactical algorithm each cycle:

| Role | Doctrine | Decision Logic |
|------|----------|---------------|
| **Infantry** | Engage with advantage | Scans 6-cell radius for threats. Counts friendly vs. hostile force ratio within 4 cells. Engages only when at numerical parity or advantage. Holds position when outnumbered. |
| **Armor** | Aggressive interdiction | Locks nearest hostile regardless of force balance. Continuously advances to engage. High damage output compensates for risk. |
| **Commander** | Formation cohesion | Computes centroid of all friendly combat units. Repositions if drift exceeds 2 cells. Keeps the force together. |
| **Scout** | Stand-off reconnaissance | Advances toward nearest threat but maintains 3-cell buffer (outside combat range). Provides early warning without engaging. |
| **Medical** | Triage and recover | Seeks nearest friendly with any HP deficit. Heals to 100% before moving to next casualty. If wounded, retreats to safe zone first -- survival over duty. |

### Wounded Auto-Evacuation

When a unit drops below 50% health, it automatically disengages and retreats toward its faction's safe zone. This behavior is overridden when a human operator takes direct control -- allowing deliberate risk-taking when tactically necessary.

### Safe Zone Enforcement

Each faction maintains a rear-area safe zone where units recover passively and enemy forces cannot penetrate. The boundary is enforced at the movement level -- hostile units are physically blocked from entering, creating defensible fallback positions.

---

## LLM Tactical Grounding

The AI commander doesn't hallucinate positions or guess at distances. Every second, the system prompt is rebuilt with:

```
SELF: You are speaking with Rifle-1 (SOLDIER-1) at grid (3,10), status=active, health=85%

FRIENDLY FORCES:
- [UNIT:COMMANDER-1] Eagle-6 @ (2,10): 1 cell west, status=active, health=100%
- [UNIT:MEDCAR-1] Doc-1 @ (1,10): 2 cells west, status=active, health=100%
- [UNIT:SOLDIER-2] Rifle-2 @ (5,8): 3 cells east-northeast, status=wounded, health=35%

THREATS:
- [THREAT:ENEMY-1] Contact-1 @ (8,7): 6 cells east-northeast, soldier, advancing west
- [THREAT:ENEMY-2] Contact-2 @ (12,12): 9 cells east-south, tank, advancing west

RECENT EVENTS:
- 14:32:07 Rifle-2 wounded (35% HP)
- 14:32:05 Contact-1 moved W to [8, 7]
```

When a soldier says "where's the nearest threat?", the AI answers with exact grid coordinates and distance. When they say "send a medic to Rifle-2", the AI dispatches the nearest medical unit to Rifle-2's actual position -- not an approximation.

### Voice-Executable Actions

| Command | What the AI Does |
|---------|-----------------|
| `report_contact` | Registers a new hostile on the battlefield at the reported grid position |
| `dispatch_unit` | Finds the nearest available unit of the requested role and routes it to the target |
| `move_unit` | Repositions a specific unit in a cardinal direction |
| `report_status` | Updates a unit's operational status (wounded, destroyed, active) |
| `query_area` | Returns all units within a specified radius of any grid position |
| `end_call` | Terminates the voice session |

Role aliasing handles natural language: "send me a medic" resolves to the nearest `medical_car` or `doctor`. "I need backup" dispatches the nearest `soldier`. "Send armor" finds the nearest `tank`.

---

## Operational Display

### Tactical Map

Real-time canvas rendering of the full battlespace:

- **Blue force tracking** -- all friendly units with role-specific icons, health bars, heading indicators
- **Red force tracking** -- all known hostile contacts with movement vectors
- **Engagement visualization** -- weapon orientation lines show who's firing at whom
- **Dispatch routing** -- dashed pathlines show unit movement orders
- **Safe zone overlays** -- faction-exclusive recovery areas highlighted
- **Casualty indicators** -- health bars color-shift from green to red as units take damage
- **Control state** -- CTRL badge on human-controlled units

### Command Panel

- Full unit telemetry: ID, callsign, role, faction, status, health, position, heading
- One-click control transfer (autonomous <-> manual)
- Cardinal movement controls for direct maneuvering
- Dispatch targeting with click-to-designate
- Live voice transcript during active calls
- Call history per unit

### Event Stream

Chronological feed of all battlefield events -- contact reports, status changes, dispatch orders, unit movements -- color-coded by type for rapid scanning.

---

## Deployment

### Local

```bash
cp .env.example .env    # configure API keys

# Terminal 1: C2 State Server
uv run uvicorn simulation.app:app --host 0.0.0.0 --port 8000

# Terminal 2: AI Voice Agent
cd server && uv run bot.py

# Access: http://localhost:8000
```

### Cloud (Pipecat Cloud)

```toml
# pcc-deploy.toml
agent_name = "colonel-ai"
agent_profile = "agent-1x"

[krisp_viva]
audio_filter = "tel"    # battlefield noise suppression

[scaling]
min_agents = 1          # auto-scales with demand
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| C2 State Server | Python, FastAPI, asyncio |
| Tactical Engine | Custom async tick-based resolution engine |
| Voice Agent Framework | Pipecat (WebRTC + pipeline orchestration) |
| Speech Recognition | NVIDIA Parakeet (streaming WebSocket ASR) |
| Tactical Reasoning | NVIDIA Nemotron-3-Super (LLM with tool calling) |
| Voice Synthesis | Gradium TTS |
| Transport | WebRTC (peer-to-peer, encrypted) |
| Noise Suppression | Silero VAD + Krisp Viva |
| Operational Display | HTML5 Canvas, WebSocket (real-time) |

---

## Environment Configuration

| Variable | Purpose |
|----------|---------|
| `STATE_SERVER_URL` | C2 state server endpoint |
| `NVIDIA_ASR_URL` | Parakeet speech recognition endpoint |
| `NEMOTRON_LLM_URL` | Nemotron reasoning engine endpoint |
| `NEMOTRON_LLM_MODEL` | Model identifier |
| `NEMOTRON_LLM_API_KEY` | API authentication |
| `NEMOTRON_ENABLE_THINKING` | Extended tactical reasoning mode |
| `GRADIUM_API_KEY` | Voice synthesis authentication |
| `GRADIUM_VOICE_ID` | Voice profile selection |
| `TWILIO_ACCOUNT_SID` | Optional: telephony gateway |
| `TWILIO_AUTH_TOKEN` | Optional: telephony auth |

---

## Project Structure

```
Colonel-AI/
+-- simulation/                # C2 State Server & Tactical Engine
|   +-- app.py                 # FastAPI server, REST + WebSocket C2 API
|   +-- state.py               # Battlefield state manager (async, lock-protected)
|   +-- engine.py              # Tactical engine: autonomous AI, combat, medical, zones
|   +-- models.py              # Unit and event data models
|   +-- seed.py                # Initial force deployment
|   +-- static/index.html      # Operational display (tactical map + command panel)
|
+-- server/                    # AI Voice Agent
|   +-- bot.py                 # Pipecat pipeline orchestration, WebRTC transport
|   +-- tools.py               # LLM-callable tactical functions
|   +-- prompts.py             # Spatial context builder + system instruction template
|   +-- nemotron_llm.py        # Nemotron LLM integration (streaming + metrics)
|   +-- nvidia_stt.py          # NVIDIA Parakeet ASR integration (WebSocket)
|   +-- transcript_logger.py   # Voice transcript capture and storage
|   +-- pyproject.toml         # Dependencies
|   +-- pcc-deploy.toml        # Cloud deployment configuration
```
