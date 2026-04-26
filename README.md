# Spell Bee Voice Bot

A real-time voice-based spelling game built with [Pipecat](https://github.com/pipecat-ai/pipecat). The bot speaks a word, the user spells it out loud letter by letter, and the bot evaluates the answer.

## How it works

The pipeline runs entirely over a WebSocket connection using the Pipecat framework:

```
Browser mic → STT (Deepgram) → LLM normalizer (OpenAI) → Game logic → TTS (Deepgram) → Browser speaker
```

- **STT** transcribes the user's spoken letters into text
- **LLM** normalizes the transcription into a clean letter sequence (e.g. "see ay tee" → "CAT")
- **SpellBeeGameProcessor** is a custom Pipecat frame processor that manages game state, evaluates spelling, and handles barge-in
- **TTS** speaks the result and the next word back to the user

Turn detection uses Silero VAD combined with a local smart-turn model (LocalSmartTurnAnalyzerV3) to decide when the user has finished speaking.

Barge-in is handled by tracking game phase. If the user speaks while the bot is still announcing a word, the system sets an interrupted flag and re-announces the word instead of evaluating the input.

## Requirements

- Python 3.11+
- Node.js 18+
- Docker + Docker Compose
- [Deepgram](https://deepgram.com) API key (STT + TTS)
- [OpenAI](https://platform.openai.com) API key (or Groq/Gemini compatible endpoint)

## Setup

### 1. Clone and configure

```bash
git clone <repo-url>
cd curelink_pipcat
cp .env.example .env
```

Edit `.env`:

```
DEEPGRAM_API_KEY=your_deepgram_key
OPENAI_API_KEY=your_openai_key
OPENAI_MODEL=gpt-4.1-mini        # optional, defaults to gpt-4.1-mini
DEEPGRAM_VOICE=aura-asteria-en   # optional
```

### 2. Build the frontend

```bash
cd frontend
npm install
npm run build
cd ..
```

### 3. Run with Docker

```bash
docker compose up --build
```

Open [http://localhost:8000](http://localhost:8000) in your browser.

### Running without Docker

```bash
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 8000
```

## Project structure

```
├── server.py                  # FastAPI server — WebSocket endpoint + game state API
├── bot.py                     # Pipecat pipeline definition
├── word_list.py               # Hardcoded word list (easy / medium / hard)
├── processors/
│   ├── frames.py              # Custom Pipecat frames (GameStartFrame, GameStateFrame)
│   └── spell_bee.py           # Core game logic frame processor
├── frontend/
│   └── src/App.jsx            # React UI — connects via @pipecat-ai/websocket-transport
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## Game flow

1. Browser connects to `/ws` via WebSocket
2. `GameStartFrame` is queued into the pipeline — bot announces the first word
3. User spells the word out loud, one letter at a time
4. After the user stops speaking (VAD + smart-turn), the LLM normalizes the input
5. `SpellBeeGameProcessor` compares against the expected word and announces correct/incorrect
6. Game continues for the configured number of rounds (5, 10, 15, or 20)

## Frontend

The UI polls `/game-state` every 700ms to display live score, current word, and last result. Audio is streamed bidirectionally over the same WebSocket connection using Pipecat's protobuf frame serialization.
