import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from spell_bee_bot import run_spell_bee_bot
from constants import APP_TITLE

load_dotenv()
logger = logging.getLogger(__name__)

_REQUIRED_ENV_VARS = ["OPENAI_API_KEY", "DEEPGRAM_API_KEY"]
for _var in _REQUIRED_ENV_VARS:
    if not os.getenv(_var):
        raise RuntimeError(f"Missing required environment variable: {_var}")

_game_state: dict = {
    "score": 0,
    "round": 0,
    "total_rounds": 5,
    "current_word": "",
    "last_result": "",
    "game_over": False,
    "session_active": False,
}

app = FastAPI(title=APP_TITLE)


@app.get("/health")
async def health():
    return JSONResponse({"status": "ok"})


@app.get("/game-state")
async def game_state():
    return JSONResponse(_game_state)


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket, total_rounds: int = 5):
    await websocket.accept()

    _game_state.update({
        "score": 0,
        "round": 0,
        "total_rounds": total_rounds,
        "current_word": "",
        "last_result": "",
        "game_over": False,
        "session_active": True,
    })

    def _update(state: dict):
        _game_state.update(state)

    try:
        await run_spell_bee_bot(
            websocket=websocket,
            on_state_update=_update,
            total_rounds=total_rounds,
        )
    except WebSocketDisconnect:
        pass
    finally:
        _game_state["session_active"] = False
