import logging
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()
logger = logging.getLogger(__name__)

_game_state: dict = {
    "score": 0,
    "round": 0,
    "total_rounds": 10,
    "current_word": "",
    "last_result": "",
    "game_over": False,
    "session_active": False,
}


def _update_game_state(state: dict):
    _game_state.update(state)


app = FastAPI(title="Spell Bee Bot")


@app.on_event("startup")
async def _prewarm_models():
    try:
        from bot import _get_smart_turn, _get_vad
        import asyncio
        await asyncio.to_thread(_get_vad)
        await asyncio.to_thread(_get_smart_turn)
        logger.info("Prewarmed VAD + smart-turn models")
    except Exception:
        logger.exception("Model prewarm failed; will lazy-load on first /ws")


@app.get("/game-state")
async def game_state():
    return JSONResponse(_game_state)


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket, total_rounds: int = 10):
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

    from bot import run_bot
    try:
        await run_bot(
            websocket=websocket,
            on_state_update=_update_game_state,
            total_rounds=total_rounds,
        )
    except WebSocketDisconnect:
        pass
    finally:
        _game_state["session_active"] = False


DIST = Path(__file__).parent / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/")
    async def index():
        return FileResponse(DIST / "index.html")
