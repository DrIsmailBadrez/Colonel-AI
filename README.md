# Colonel AI -- Battlefield Operations Center

A real-time tactical battlefield simulation with an AI voice commander. Soldiers on the field call in via WebRTC to receive situational awareness, request medics, report contacts, and get tactical guidance -- all powered by NVIDIA's Nemotron LLM with live battlefield state grounding.

```
     ADVERSARY SAFE ZONE (top-right)
     +---------+
     | ENEMY-1 |  <-- adversaries advance toward friendly HQ
     | ENEMY-2 |
     +---------+
                  \
                   \  <-- combat range: 2 cells
                    \
        [SOLDIER-1] <--> engagement
        [COMMANDER-1]
        [MEDCAR-1] <-- auto-seeks wounded

     +---------+
     | SAFE    |  <-- wounded retreat here, passive healing
     | ZONE    |
     +---------+
     FRIENDLY SAFE ZONE (bottom-left)
```

---

## What It Does

**Two systems working together:**

1. **Battlefield Simulation** -- A 20x20 grid where friendly and adversary units move, fight, heal, and die in real time. Friendly units have autonomous AI that makes tactical decisions, but the player can take manual control of any unit at any time.

2. **Voice AI Commander** -- Soldiers on the field call the Colonel via WebRTC. The Colonel sees the full battlefield, answers questions ("where's the nearest threat?"), dispatches reinforcements ("send me a medic"), processes reports ("contact at grid 15, 8"), and gives terse tactical guidance -- all in one sentence or less.

---

## Quick Start

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager

### 1. Environment Setup

```bash
cp .env.example .env
# Edit .env with your API keys (see Environment Variables below)
```

### 2. Start the Simulation Server

```bash
cd simulation
uv run uvicorn simulation.app:app --host 0.0.0.0 --port 8000 --reload
```

### 3. Start the Voice Bot

```bash
cd server
uv run bot.py
```

### 4. Open the UI

```
http://localhost:8000
```

---

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `STATE_SERVER_URL` | `http://localhost:8000` | Simulation server URL |
| `NVIDIA_ASR_URL` | -- | NVIDIA Parakeet WebSocket endpoint |
| `NEMOTRON_LLM_URL` | -- | Nemotron API endpoint (OpenAI-compatible `/v1`) |
| `NEMOTRON_LLM_MODEL` | `nvidia/nemotron-3-super` | LLM model name |
| `NEMOTRON_LLM_API_KEY` | `EMPTY` | LLM API key |
| `NEMOTRON_ENABLE_THINKING` | `false` | Extended reasoning mode |
| `GRADIUM_API_KEY` | -- | Gradium TTS API key |
| `GRADIUM_VOICE_ID` | `_6Aslh2DxfmnRLmP` | TTS voice selection |
| `TWILIO_ACCOUNT_SID` | -- | Optional: Twilio telephony |
| `TWILIO_AUTH_TOKEN` | -- | Optional: Twilio auth |
| `ENV` | `local` | `local` or cloud deployment |

---

## Simulation Mechanics

### Grid and Units

The battlefield is a **20x20 grid**. Each unit occupies one cell. No two units can share a cell.

**Factions:**
- **Friendly** (blue) -- player's team, autonomous AI with manual override
- **Adversary** (red) -- enemy forces, advance toward friendly HQ

**Roles:**

| Role | Shape | Combat | Special Behavior |
|------|-------|--------|-----------------|
| `soldier` | Circle | 3 dmg/tick | Engages if not outnumbered |
| `tank` | Square | 8 dmg/tick | Always pushes toward nearest enemy |
| `commander` | Circle | 3 dmg/tick | Stays near centroid of friendly forces |
| `scout` | Circle | -- | Advances but holds at distance 3 from enemies |
| `medical_car` | Square | -- | Auto-seeks any friendly under 100% HP, heals to full |
| `doctor` | Circle | -- | Same as medical_car |
| `car` | Square | -- | Holds position |

**Unit States:**
- `active` -- operational, full AI behavior
- `wounded` -- health below 50%, auto-retreats to safe zone (unless player-controlled)
- `destroyed` -- health reached 0, removed from simulation
- `unknown` -- unverified contact

### Combat

- **Range:** Chebyshev distance of 2 cells (includes diagonals)
- **Damage per tick:** Soldiers/commanders deal 3 HP, tanks deal 8 HP
- **Stacking:** Multiple attackers stack damage -- surrounded units die fast
- **Orientation:** Attackers turn to face their nearest target during combat (the white heading line points at the enemy)

### Health and Healing

Every unit has 100 HP. Three sources of healing:

| Source | Rate | Range | Condition |
|--------|------|-------|-----------|
| Medic (medical_car/doctor) | 15 HP/tick | Adjacent (1 cell) | Heals any friendly under 100% HP |
| Friendly safe zone | 10 HP/tick | Inside zone | Passive, automatic |
| Adversary safe zone | 10 HP/tick | Inside zone | For adversary units only |

- **Wounded** at < 50 HP, back to **active** at >= 50 HP
- **Destroyed** at 0 HP -- permanent, no revival
- Medics heal to 100%, not just to active status -- they stay with a patient until fully healed, then seek the next one
- Medics prioritize their own survival: if wounded, they retreat to the safe zone before healing others

### Safe Zones

Two faction-exclusive zones where units heal passively and enemies cannot enter:

| Zone | Center | Radius | Grid Area |
|------|--------|--------|-----------|
| Friendly | (2, 17) | 2 cells | Bottom-left corner |
| Adversary | (17, 2) | 2 cells | Top-right corner |

- Friendly units **cannot** enter the adversary safe zone
- Adversary units **cannot** enter the friendly safe zone
- Movement into an enemy safe zone is silently blocked

### Autonomous AI

All friendly units act autonomously by default. Each role has distinct behavior:

**Soldiers** -- Check local force balance within 4 cells. If friendlies >= enemies, advance toward nearest enemy (up to 6 cells detection range). If outnumbered, hold position.

**Tanks** -- Aggressive. Always advance toward the nearest enemy regardless of numbers.

**Commanders** -- Calculate the centroid of all friendly combat units. If more than 2 cells away from the group center, reposition. Provides cohesion.

**Scouts** -- Move toward enemies but stop at distance 3 (stay outside combat range 2). Recon without engaging.

**Medics** -- Seek the nearest friendly with health < 100. Move toward them, heal on adjacency. If wounded, retreat to safe zone first (survival priority).

**Adversary AI** -- All enemy units advance toward friendly HQ at (3, 10). 80% optimal pathing, 20% random perturbation for unpredictability.

### Manual Control

Click a friendly unit, then click **Take Control** to pause its AI. While controlled:

- The unit stops all autonomous movement
- NSEW movement buttons appear in the panel
- Wounded units stay where you put them (no forced retreat)
- Dispatch still works (set destinations for other units)

Click **Release to AI** to resume autonomous behavior.

A yellow **CTRL** badge appears above controlled units on the canvas.

### Dispatch and Escort

Dispatch sends a friendly unit to a grid cell. Click **Set Destination**, then click the target cell.

**Escort Mode:** If a dispatched unit arrives near a player-controlled unit, it enters escort mode -- it follows the controlled unit in real time, staying adjacent and performing its role (medics heal, soldiers fight alongside). Escort ends when the dispatch is cancelled.

### Simulation Tick Structure

Every 1 second, the engine runs these phases under a single async lock:

```
Phase 1: Movement
  |-- Player-controlled units: skip (manual only)
  |-- Wounded retreat: fall back to safe zone
  |-- Adversary AI: advance toward HQ
  |-- Dispatched units: pathfind to destination (+ escort follow)
  |-- Medical AI: seek nearest hurt friendly
  |-- Friendly combat AI: role-based engagement

Phase 2: Combat damage
  |-- All combat units damage enemies in range, orient toward target

Phase 3: Medic healing
  |-- Adjacent medics heal friendly units (15 HP/tick)

Phase 4: Safe zone passive healing
  |-- Units inside own safe zone heal (10 HP/tick)

Broadcast: push snapshot to all WebSocket subscribers
```

---

## Voice AI System

### How a Call Works

1. Player clicks a friendly unit, clicks **Call as [Callsign]**
2. Browser negotiates WebRTC audio with the Pipecat bot (port 7860)
3. Soldier speaks -- audio streams to NVIDIA Parakeet STT
4. Transcribed text goes to Nemotron LLM with full battlefield context
5. LLM responds (and optionally calls tools like `dispatch_unit`)
6. Response streams through Gradium TTS back to the browser
7. Transcript is logged and displayed in the UI

### Speech Pipeline

```
Browser Mic --> WebRTC --> Parakeet STT --> User Aggregator (VAD)
  --> Nemotron LLM (+ tool calls) --> Gradium TTS --> WebRTC --> Browser Speaker
```

| Component | Technology | Role |
|-----------|-----------|------|
| Transport | SmallWebRTC / WebSocket | Bidirectional audio |
| STT | NVIDIA Parakeet | 16kHz PCM speech-to-text |
| VAD | Silero | Voice activity detection |
| LLM | NVIDIA Nemotron-3-Super | Tactical reasoning + tool calling |
| TTS | Gradium | Voice synthesis |
| Transcript | Custom Pipecat processor | Captures both sides of conversation |

### LLM Grounding

The Colonel's system prompt is rebuilt every second with live state:

- **Caller identity:** Which soldier is calling, their position, status, health
- **Friendly units:** Each unit with pre-computed grid offset from the caller (e.g., "Doc-1 @ (1,10): 2 cells west, status=active")
- **Threats:** Each adversary with distance and direction from the caller
- **Recent events:** Last battlefield events for situational awareness

The Colonel is instructed to:
- Respond in **one sentence maximum**
- Always cite unit handles (`[UNIT:SOLDIER-1]`, `[THREAT:ENEMY-2]`)
- Give **one actionable fact**, never list options
- Use tool calls for any action (dispatch, move, report)

### LLM Tool Functions

| Tool | What It Does |
|------|-------------|
| `report_contact` | Create a new adversary unit on the grid |
| `query_area` | Get all units within radius of a position |
| `move_unit` | Move a specific unit one cell in a direction |
| `dispatch_unit` | Send nearest unit of a role to a location or unit |
| `report_status` | Update a unit's status (wounded, destroyed, etc.) |
| `end_call` | Hang up the call |

---

## Web UI

### Canvas (Left)

- 20x20 grid with coordinate labels
- Units rendered as circles (infantry) or squares (vehicles)
- Blue = friendly, red = adversary, gray = destroyed
- Health bars above each unit (green > 50%, orange 25-50%, red < 25%)
- White heading line shows movement/attack direction
- Yellow selection ring on clicked unit
- Blue dashed line + diamond for dispatch paths
- Safe zones rendered as tinted regions with dashed borders
- **CTRL** badge on player-controlled units
- Green pulsing ring on unit during active voice call

### Panel (Right)

- **Unit Info:** ID, callsign, role, faction, status, health %, position, heading, control mode
- **Control Toggle:** Take Control / Release to AI
- **Movement:** NSEW buttons (only when controlled)
- **Dispatch:** Set Destination / Cancel Dispatch
- **Radio Call:** Call as [Callsign] / End Call
- **Live Transcript:** During active call
- **Call History:** Past transcripts for selected unit

### Event Log (Bottom)

Color-coded real-time log of all battlefield events:
- Red: contact reports
- Yellow: status changes (wounded, destroyed, healed)
- Gray: movement
- Purple: dispatch orders
- Blue: reports

---

## API Reference

### REST Endpoints (port 8000)

**State**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/state` | Full battlefield snapshot |
| GET | `/api/item/{id}` | Single unit details |
| POST | `/api/query` | Units within radius of a position |

**Commands**

| Method | Path | Body | Description |
|--------|------|------|-------------|
| POST | `/api/move` | `{id, direction}` | Move unit one cell (N/S/E/W) |
| POST | `/api/dispatch` | `{unit_id or role, target_x, target_y}` | Dispatch unit to location |
| POST | `/api/cancel_dispatch` | `{unit_id}` | Cancel dispatch order |
| POST | `/api/control` | `{unit_id}` | Take manual control |
| POST | `/api/release` | `{unit_id}` | Release to AI |
| POST | `/api/report` | `{grid_x, grid_y, description, role}` | Report enemy contact |
| POST | `/api/status` | `{id, status, detail}` | Update unit status |

**Transcripts**

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/transcript` | Add transcript entry |
| GET | `/api/transcript/{soldier_id}` | Get call history |

### WebSocket

| Path | Description |
|------|-------------|
| `/ws` | Full state broadcast on every mutation + 1-second heartbeat |

### Bot Endpoints (port 7860)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/start` | Initiate WebRTC session |
| POST | `/sessions/{id}/api/offer` | WebRTC SDP offer/answer exchange |
| PATCH | `/api/offer` | Send ICE candidates |

---

## Architecture

```
+-----------------------------------------------------------+
|                    Browser (Web UI)                         |
|                                                             |
|  Canvas <-- WebSocket (/ws) <-- State Server               |
|  Panel     real-time updates    (port 8000)                |
|  Controls                                                   |
|                                                             |
|  Microphone --> WebRTC --> Voice Bot (port 7860)           |
|  Speaker   <-- WebRTC <-- Voice Bot                        |
+-------------------+-------------------+--------------------+
                    |                   |
     +--------------v--------+  +------v-----------------+
     |  Simulation Server    |  |   Pipecat Voice Bot    |
     |  (FastAPI, :8000)     |  |   (:7860)              |
     |                       |  |                        |
     |  BattlefieldState     |<-+  Tool calls:           |
     |  +-- items (units)    |  |  POST /api/dispatch    |
     |  +-- events (log)     |  |  POST /api/report      |
     |  +-- transcripts      |  |  POST /api/move        |
     |                       |  |  POST /api/status      |
     |  Simulation Engine    |  |                        |
     |  +-- movement AI      |  |  Pipeline:             |
     |  +-- combat phase     |  |  STT -> LLM -> TTS     |
     |  +-- healing phase    |  |                        |
     |  +-- safe zone heal   |  |  State refresh: 1/s    |
     +-----------------------+  +------+-----------------+
                                       |
                    +------------------+------------------+
                    |                  |                  |
           +--------v------+ +--------v-----+ +---------v------+
           | NVIDIA Parakeet| |  Nemotron    | |  Gradium TTS   |
           | (STT)          | |  (LLM)       | |                |
           | WebSocket ASR  | |  HTTP /v1    | |  HTTPS API     |
           | 16kHz PCM      | |  streaming   | |  voice synth   |
           +----------------+ +--------------+ +----------------+
```

### File Structure

```
Colonel-AI/
+-- simulation/              # Battlefield simulation server
|   +-- app.py               # FastAPI server, REST + WebSocket endpoints
|   +-- state.py             # BattlefieldState: async state, locks, broadcast
|   +-- engine.py            # Tick loop: movement, combat, healing, AI
|   +-- models.py            # WarItem + Event dataclasses
|   +-- seed.py              # Initial unit placement
|   +-- static/
|       +-- index.html       # Full web UI (canvas, panels, WebRTC client)
|
+-- server/                  # Voice AI bot
|   +-- bot.py               # Pipecat pipeline, WebRTC transport, state refresh
|   +-- tools.py             # LLM tool functions (dispatch, report, move, etc.)
|   +-- prompts.py           # System prompt template + spatial context builder
|   +-- nemotron_llm.py      # Custom Nemotron LLM service (TTFB metrics)
|   +-- nvidia_stt.py        # NVIDIA Parakeet WebSocket STT service
|   +-- transcript_logger.py # Captures user + bot speech for transcript storage
|   +-- pyproject.toml       # Python dependencies
|   +-- pcc-deploy.toml      # Pipecat Cloud deployment config
|
+-- .env.example             # Environment variable template
+-- .gitignore
```

---

## Game Constants

### Combat

| Constant | Value |
|----------|-------|
| Soldier/Commander damage | 3 HP/tick |
| Tank damage | 8 HP/tick |
| Combat range | 2 cells (Chebyshev) |

### Healing

| Constant | Value |
|----------|-------|
| Medic healing | 15 HP/tick |
| Medic range | 1 cell (adjacent) |
| Safe zone healing | 10 HP/tick |

### AI Thresholds

| Constant | Value | Meaning |
|----------|-------|---------|
| `AI_ENGAGE_RANGE` | 6 | Soldiers detect enemies within this |
| `AI_LOCAL_RANGE` | 4 | Radius for counting force balance |
| `AI_SCOUT_KEEP` | 3 | Scouts hold at this distance |
| `AI_CMD_DRIFT` | 2 | Commanders reposition beyond this |

---

## Deployment

### Local

```bash
# Terminal 1
uv run uvicorn simulation.app:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2
cd server && uv run bot.py

# Browser
open http://localhost:8000
```

### Pipecat Cloud

The bot is deployable via Pipecat Cloud with the included `pcc-deploy.toml`:

```toml
agent_name = "colonel-ai"
agent_profile = "agent-1x"

[krisp_viva]
audio_filter = "tel"    # noise suppression for telephony

[scaling]
min_agents = 1
```

Cloud deployments automatically enable Krisp Viva audio filtering for cleaner speech input.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Simulation server | Python, FastAPI, asyncio, uvicorn |
| Voice bot framework | Pipecat |
| Speech-to-text | NVIDIA Parakeet |
| Language model | NVIDIA Nemotron-3-Super |
| Text-to-speech | Gradium |
| Voice transport | WebRTC (SmallWebRTC) |
| Frontend | HTML5 Canvas, vanilla JavaScript, WebSocket |
| Audio processing | Silero VAD, Krisp Viva (cloud) |
