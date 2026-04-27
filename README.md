# Spell Bee Voice Bot

A real-time voice-based spelling game built with [Pipecat](https://github.com/pipecat-ai/pipecat). The bot speaks a word, the user spells it out loud letter by letter, and the bot evaluates the answer.

---

## Approach

The core idea is to use an LLM not for conversation but as a normalizer — a pure input classifier that converts messy STT output ("see ay tee", "tee-ar-ee-ee") into a clean letter sequence ("CAT", "TREE"). This sidesteps the fundamental problem that STT models are not designed to recognize isolated letters reliably.

The pipeline runs over a WebSocket connection:

```
Browser mic → STT (Deepgram Nova-3) → LLM normalizer (OpenAI) → Game processor → TTS (Deepgram) → Browser speaker
```

- **STT** transcribes spoken letters with keyterm boosting for phonetic letter sounds
- **LLM** maps phonetic sounds and homophones to their corresponding letters
- **SpellBeeGameProcessor** is a custom Pipecat `FrameProcessor` that owns all game state, evaluates spelling, and handles barge-in
- **TTS** speaks the result and next word back to the user

Turn detection uses Silero VAD with a `SpeechTimeoutUserTurnStopStrategy` (1.5s silence threshold). This is intentional — semantic turn detection fires too early when the user is spelling individual letters like "I".

Barge-in is handled through game phase tracking. If the user speaks while the bot is announcing a word (`GamePhase.ANNOUNCING`), the processor sets an interrupted flag and re-announces the word instead of evaluating the partial input.

---

## Assumptions

- **Single concurrent session.** The server runs one game at a time. The global `_game_state` dict is intentional — this follows Pipecat's 1-bot-1-process model, which in production means each session gets its own container.
- **English only.** STT language is fixed to `en-US`. The keyterm list and LLM prompt are English-specific.
- **Fixed 10-word list.** Words are hardcoded and played in order. This is an assignment constraint, not a production assumption.
- **Browser with microphone access.** The frontend requires a browser that supports `getUserMedia`.
- **LLM as normalizer, not judge.** The LLM only extracts letters — it does not evaluate correctness. Correctness is a string comparison in `SpellBeeGameProcessor._evaluate`.

---

## Tradeoffs

**Polling vs WebSocket for game state**
The frontend polls `/game-state` every 5 seconds instead of receiving state updates over the audio WebSocket. This keeps the concerns separate (audio transport vs UI state) at the cost of up to 5s lag in the scoreboard. A proper solution would push state over a secondary WebSocket or Server-Sent Events.

**LLM normalizer latency**
Using an LLM to normalize every spelling attempt adds ~300–700ms of latency per turn. The alternative — pure regex/phoneme mapping — would be faster but much harder to maintain across all the edge cases (NATO alphabet, "C for cat", "double T", etc.). The LLM approach is more robust and easier to extend.

**Per-session VAD vs singleton**
Each session creates its own `SileroVADAnalyzer` instance (~1.26s init time). The singleton pattern (one shared instance) would be faster but is not safe for concurrent sessions since VAD state is mutated on every audio frame. Per-session is correct; the cold start cost is addressed by `compileall` in the Dockerfile.

**Global game state**
`_game_state` is a module-level dict. For a single-session server this is fine. For multi-session, each connection would need its own state object keyed by session ID. The current design makes the single-session constraint explicit rather than hiding it behind premature abstractions.

---

## What I would improve given more time

**1. True multi-session support**
Follow Pipecat's production model: an orchestrator that spawns one worker process per session, each with its own state and pipeline. The current single-process design would break under concurrent users.

**2. STT accuracy**
Single-letter recognition is the hardest part of this problem. I'd experiment with a custom Deepgram model fine-tuned on spelling audio, or explore running a secondary phoneme-level classifier before the LLM to reduce hallucination on ambiguous input.

**3. Word list from a database**
Replace the hardcoded list with a difficulty-tiered word bank stored in a database, with per-user progress tracking.

**4. Streaming LLM response**
Currently `stream=False` on the OpenAI call. Streaming would reduce perceived latency — the game processor could act on the first token instead of waiting for the full response.

**5. Proper state push**
Replace polling with Server-Sent Events or a dedicated state WebSocket so the UI reflects results immediately instead of up to 5s later.

**6. Observability**
Add structured logging with session IDs, per-turn latency breakdown (VAD → STT → LLM → TTS), and a metrics endpoint for monitoring in production.

**7. Intent classification**
The LLM currently assumes every user utterance is a spelling attempt. A production voice UX needs the LLM to classify intent first — spell, repeat, skip, restart, define, help, or noise — and route accordingly. Today, if the user says "wait, can you repeat that?", the system extracts garbled letters and marks them wrong. With an intent layer, "repeat" triggers a re-announcement, "skip" advances to the next word, and only explicit spelling attempts go through evaluation. This is the architecture every real voice product uses; it was out of scope for the assignment.



---

## Requirements

- Python 3.11+
- Node.js 18+
- Docker + Docker Compose
- [Deepgram](https://deepgram.com) API key (STT + TTS)
- [OpenAI](https://platform.openai.com) API key

---

## Setup

```bash
cp .env.example .env
# fill in OPENAI_API_KEY and DEEPGRAM_API_KEY
```

```bash
cd frontend && npm install && npm run build && cd ..
docker compose up --build
```

Open [http://localhost:8000](http://localhost:8000).

---

## Project structure

```
├── server.py                  # FastAPI server — WebSocket endpoint, game state API, health check
├── spell_bee_bot.py           # Pipecat pipeline definition (transport, STT, LLM, TTS, VAD)
├── spell_bee_words.py         # Hardcoded 10-word list played in order
├── constants.py               # Config values and LLM system prompt
├── processors/
│   ├── game_frames.py         # Custom Pipecat frames (GameStartFrame, GameStateFrame)
│   └── spell_bee.py           # Game logic — state machine, evaluation, barge-in handling
├── frontend/
│   └── src/
│       ├── App.jsx            # React UI — audio via @pipecat-ai/websocket-transport
│       └── constants.js       # Frontend config (poll interval, paths)
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```
