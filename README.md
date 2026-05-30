# Colonel AI

**Real-time AI-powered battlefield command and control.**

Colonel AI is an autonomous tactical intelligence system that gives every soldier on the battlefield a direct voice line to an AI commander with full situational awareness. Operators speak naturally -- "I'm taking fire from the east, send backup" -- and the system processes speech in real time, reasons over live battlefield state, and executes tactical decisions (dispatching units, repositioning assets, coordinating medical evacuation) in under 2 seconds end-to-end.

Built for contested environments where seconds matter and radio operators are overwhelmed.

---

## The Problem

Modern battlefield communications are a bottleneck. A wounded soldier calling for a medic has to reach a human radio operator, who relays to a human commander, who makes a decision, who relays back down the chain. That loop takes minutes. In those minutes, soldiers die.

Meanwhile, no single human can maintain real-time awareness of every unit's position, health, heading, and threat proximity across an entire operational area. Commanders make decisions on stale information. Units get dispatched to the wrong location. Medics arrive too late.

## The Solution

Colonel AI collapses the entire command chain into a single voice call. Every soldier gets:

- **An AI commander who sees everything** -- every friendly position, every threat contact, every unit's health status, updated every second
- **Natural voice interaction** -- no radio protocols, no codes, just speak
- **Instant action** -- say "send me a medic" and the nearest medical unit is dispatched to your GPS coordinates within the same breath
- **Autonomous unit coordination** -- units that aren't under direct human control make intelligent tactical decisions on their own: engaging threats, maintaining formation, retreating when wounded, seeking medical aid

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

## API Surface

### Command & Control API

| Method | Endpoint | Function |
|--------|----------|----------|
| GET | `/api/state` | Full battlefield state snapshot |
| POST | `/api/move` | Reposition a unit |
| POST | `/api/dispatch` | Route a unit to coordinates or another unit |
| POST | `/api/control` | Transfer unit to human control |
| POST | `/api/release` | Return unit to autonomous AI |
| POST | `/api/report` | Register a new threat contact |
| POST | `/api/status` | Update unit operational status |
| POST | `/api/query` | Area scan for nearby units |
| WS | `/ws` | Real-time state stream (full snapshot on every mutation) |

### Voice Agent API

| Method | Endpoint | Function |
|--------|----------|----------|
| POST | `/start` | Initiate secure voice session |
| POST | `/sessions/{id}/api/offer` | WebRTC signaling (SDP exchange) |
| PATCH | `/api/offer` | ICE candidate negotiation |

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
