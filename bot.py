import logging
import os

from dotenv import load_dotenv
from fastapi import WebSocket

from pipecat.audio.turn.smart_turn.base_smart_turn import SmartTurnParams
from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.serializers.protobuf import ProtobufFrameSerializer
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.deepgram.tts import DeepgramTTSService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams, FastAPIWebsocketTransport
from pipecat.turns.user_stop import TurnAnalyzerUserTurnStopStrategy
from pipecat.turns.user_turn_strategies import UserTurnStrategies

from processors.frames import GameStartFrame
from processors.spell_bee import SpellBeeGameProcessor
from word_list import WORDS

load_dotenv()
logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000

SYSTEM_PROMPT = """You are a spelling input normalizer for a Spell Bee game.
The user will say letters one at a time to spell a word.
Extract only the letters they spelled and return them as a single uppercase string with no spaces or punctuation.

Examples:
- "C A T" → "CAT"
- "see ay tee" → "CAT"
- "C for cat, A, T" → "CAT"
- "Capital E, L, E, P, H, A, N, T" → "ELEPHANT"
- "double T" → "TT"
- "E as in elephant, L, E" → "ELE"

Return only the uppercase letters, nothing else."""

_VAD_SINGLETON: SileroVADAnalyzer | None = None
_SMART_TURN_SINGLETON: LocalSmartTurnAnalyzerV3 | None = None


def _get_vad() -> SileroVADAnalyzer:
    global _VAD_SINGLETON
    if _VAD_SINGLETON is None:
        _VAD_SINGLETON = SileroVADAnalyzer(
            sample_rate=SAMPLE_RATE,
            params=VADParams(
                confidence=0.7,
                start_secs=0.1,
                stop_secs=0.8,
                min_volume=0.6,
            ),
        )
    return _VAD_SINGLETON


def _get_smart_turn() -> LocalSmartTurnAnalyzerV3:
    global _SMART_TURN_SINGLETON
    if _SMART_TURN_SINGLETON is None:
        _SMART_TURN_SINGLETON = LocalSmartTurnAnalyzerV3(
            params=SmartTurnParams(stop_secs=2.5),
        )
    return _SMART_TURN_SINGLETON


async def run_bot(
    websocket: WebSocket,
    on_state_update,
    total_rounds: int = 10,
):
    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            serializer=ProtobufFrameSerializer(),
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_in_sample_rate=SAMPLE_RATE,
            audio_out_sample_rate=SAMPLE_RATE,
        ),
    )

    stt = DeepgramSTTService(
        api_key=os.environ["DEEPGRAM_API_KEY"],
        language="en-US",
    )

    vad = _get_vad()
    smart_turn = _get_smart_turn()

    context = LLMContext(messages=[{"role": "system", "content": SYSTEM_PROMPT}])

    user_aggregator, _ = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=vad,
            user_turn_strategies=UserTurnStrategies(
                stop=[TurnAnalyzerUserTurnStopStrategy(turn_analyzer=smart_turn)]
            ),
        ),
    )

    llm = OpenAILLMService(
        api_key=os.environ["OPENAI_API_KEY"],
        model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
    )

    tts = DeepgramTTSService(
        api_key=os.environ["DEEPGRAM_API_KEY"],
        voice=os.getenv("DEEPGRAM_VOICE", "aura-asteria-en"),
        sample_rate=SAMPLE_RATE,
    )

    def _reset_context():
        context.set_messages([{"role": "system", "content": SYSTEM_PROMPT}])

    spell_bee = SpellBeeGameProcessor(
        word_list=WORDS,
        total_rounds=total_rounds,
        on_state_update=on_state_update,
        on_turn_complete=_reset_context,
    )

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            user_aggregator,
            llm,
            spell_bee,
            tts,
            transport.output(),
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(allow_interruptions=True),
    )

    @transport.event_handler("on_client_connected")
    async def on_connected(transport, client):
        logger.info("Client connected — starting game")
        await task.queue_frames([GameStartFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_disconnected(transport, client):
        logger.info("Client disconnected — cancelling pipeline")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=False)
    await runner.run(task)
