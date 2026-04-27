import logging
import os

from collections.abc import Callable

from dotenv import load_dotenv
from fastapi import WebSocket

from pipecat.audio.filters.rnnoise_filter import RNNoiseFilter
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
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)
from pipecat.turns.user_stop import SpeechTimeoutUserTurnStopStrategy
from pipecat.turns.user_turn_strategies import UserTurnStrategies

from constants import (
    DEFAULT_LLM_MODEL,
    DEFAULT_STT_LANGUAGE,
    DEFAULT_TTS_VOICE,
    SAMPLE_RATE,
    SPELL_BEE_SYSTEM_PROMPT,
)
from processors.game_frames import GameStartFrame
from processors.spell_bee import SpellBeeGameProcessor
from spell_bee_words import WORDS

load_dotenv()
logger = logging.getLogger(__name__)


async def run_spell_bee_bot(
    websocket: WebSocket,
    on_state_update: Callable[[dict], None],
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
            audio_in_filter=RNNoiseFilter(),
        ),
    )

    stt = DeepgramSTTService(
        api_key=os.environ["DEEPGRAM_API_KEY"],
        settings=DeepgramSTTService.Settings(
            model="nova-3-general",
            language=DEFAULT_STT_LANGUAGE,
            keyterm=[
                "ay", "bee", "see", "dee", "ee", "ef", "gee", "aitch",
                "eye", "jay", "kay", "el", "em", "en", "oh", "pee",
                "queue", "are", "ess", "tea", "tee", "you", "vee",
                "double-u", "ex", "why", "zee", "zed",
            ],
        ),
    )

    vad = SileroVADAnalyzer(
        sample_rate=SAMPLE_RATE,
        params=VADParams(
            confidence=0.7,
            start_secs=0.1,
            stop_secs=0.2,
            min_volume=0.6,
        ),
    )

    context = LLMContext(
        messages=[{"role": "system", "content": SPELL_BEE_SYSTEM_PROMPT}]
    )

    user_aggregator, _ = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=vad,
            user_turn_strategies=UserTurnStrategies(
                stop=[SpeechTimeoutUserTurnStopStrategy(user_speech_timeout=1.5)]
            ),
        ),
    )

    llm = OpenAILLMService(
        api_key=os.environ["OPENAI_API_KEY"],
        model=os.getenv("OPENAI_MODEL", DEFAULT_LLM_MODEL),
        stream=False,
    )

    tts = DeepgramTTSService(
        api_key=os.environ["DEEPGRAM_API_KEY"],
        voice=os.getenv("DEEPGRAM_VOICE", DEFAULT_TTS_VOICE),
        sample_rate=SAMPLE_RATE,
    )

    def _reset_context():
        context.set_messages([{"role": "system", "content": SPELL_BEE_SYSTEM_PROMPT}])

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
        await task.queue_frames([GameStartFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_disconnected(transport, client):
        await task.cancel()

    runner = PipelineRunner(handle_sigint=False)
    await runner.run(task)
