import re
import logging
from enum import Enum, auto
from typing import Callable, List, Optional

from constants import (
    GRADE_GOOD,
    GRADE_GOOD_THRESHOLD,
    GRADE_GREAT,
    GRADE_GREAT_THRESHOLD,
    GRADE_PERFECT,
    GRADE_PERFECT_THRESHOLD,
    GRADE_POOR,
    RESULT_CORRECT,
    RESULT_INCORRECT,
    SPEECH_CORRECT,
    SPEECH_GAME_INTRO,
    SPEECH_GAME_OVER,
    SPEECH_INCORRECT,
    SPEECH_INTERRUPTION_PREFIX,
    SPEECH_NEXT_WORD,
    SPEECH_WORD_ANNOUNCEMENT,
)

from pipecat.frames.frames import (
    Frame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    TextFrame,
    TTSSpeakFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    StartFrame,
    EndFrame,
)
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection

from .game_frames import GameStartFrame, GameStateFrame

logger = logging.getLogger(__name__)


class GamePhase(Enum):
    IDLE = auto()
    ANNOUNCING = auto()
    WAITING = auto()
    EVALUATING = auto()
    FINISHED = auto()


class SpellBeeGameProcessor(FrameProcessor):
    def __init__(
        self,
        word_list: List[str],
        total_rounds: int = 10,
        on_state_update: Optional[Callable[[dict], None]] = None,
        on_turn_complete: Optional[Callable[[], None]] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._word_list = list(word_list)
        self._on_state_update = on_state_update
        self._on_turn_complete = on_turn_complete

        self._total_rounds = min(total_rounds, len(self._word_list))
        self._phase = GamePhase.IDLE
        self._current_word: Optional[str] = None
        self._word_index = 0
        self._score = 0
        self._round = 0
        self._interrupted = False
        self._is_collecting_llm = False
        self._llm_buffer = ""

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, GameStartFrame):
            await self._begin_game()
            return

        if isinstance(frame, UserStartedSpeakingFrame):
            if self._phase == GamePhase.ANNOUNCING:
                self._interrupted = True
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, BotStoppedSpeakingFrame):
            if self._phase == GamePhase.ANNOUNCING:
                self._phase = GamePhase.WAITING
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, LLMFullResponseStartFrame):
            if self._phase == GamePhase.WAITING:
                self._llm_buffer = ""
                self._is_collecting_llm = True
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, TextFrame):
            if self._is_collecting_llm:
                logger.info("TextFrame [collecting-llm] phase=%s text=%r", self._phase.name, frame.text)
                self._llm_buffer += frame.text
            else:
                logger.info("TextFrame [non-collecting] phase=%s text=%r", self._phase.name, frame.text)
                if self._phase == GamePhase.WAITING:
                    if self._interrupted:
                        self._interrupted = False
                        await self._announce_current_word(prefix=SPEECH_INTERRUPTION_PREFIX)
                    else:
                        await self._evaluate(frame.text)
            return

        if isinstance(frame, LLMFullResponseEndFrame):
            if self._is_collecting_llm:
                self._is_collecting_llm = False
                llm_output = self._llm_buffer.strip()
                logger.info("SpellBee LLM output: %r", llm_output)
                if self._phase == GamePhase.WAITING:
                    if self._interrupted:
                        self._interrupted = False
                        await self._announce_current_word(
                            prefix=SPEECH_INTERRUPTION_PREFIX
                        )
                    else:
                        await self._evaluate(llm_output)
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, GameStateFrame):
            if self._on_state_update:
                self._on_state_update(frame.to_dict())
            await self.push_frame(frame, direction)
            return

        await self.push_frame(frame, direction)

    async def _begin_game(self):
        self._word_index = 0
        self._current_word = self._word_list[self._word_index]
        self._round = 1
        self._score = 0
        self._phase = GamePhase.ANNOUNCING
        await self._push_state("")
        intro = SPEECH_GAME_INTRO.format(
            total_rounds=self._total_rounds,
            word=self._current_word,
        )
        await self._say(intro)

    async def _announce_current_word(self, prefix: str = ""):
        self._phase = GamePhase.ANNOUNCING
        announcement = SPEECH_WORD_ANNOUNCEMENT.format(
            round=self._round,
            word=self._current_word,
        )
        await self._say(f"{prefix}{announcement}")

    async def _evaluate(self, raw_input: str):
        self._phase = GamePhase.EVALUATING
        user_spelling = self._normalize(raw_input)
        expected = self._current_word.upper()
        correct = user_spelling == expected
        logger.info(
            "SpellBee evaluate: raw=%r normalized=%r expected=%r correct=%s",
            raw_input,
            user_spelling,
            expected,
            correct,
        )
        if correct:
            self._score += 1
            result_speech = SPEECH_CORRECT
            result_key = RESULT_CORRECT
        else:
            spelled_out = ", ".join(list(expected))
            result_speech = SPEECH_INCORRECT.format(spelling=spelled_out)
            result_key = RESULT_INCORRECT

        await self._push_state(result_key)

        if self._on_turn_complete:
            self._on_turn_complete()

        if self._round >= self._total_rounds:
            await self._end_game(result_speech)
        else:
            self._round += 1
            self._word_index += 1
            self._current_word = self._word_list[self._word_index]
            self._phase = GamePhase.ANNOUNCING
            next_text = SPEECH_NEXT_WORD.format(
                result=result_speech,
                round=self._round,
                word=self._current_word,
            )
            await self._say(next_text)

    async def _end_game(self, last_result_speech: str):
        self._phase = GamePhase.FINISHED
        pct = self._score / self._total_rounds
        if pct >= GRADE_PERFECT_THRESHOLD:
            grade = GRADE_PERFECT
        elif pct >= GRADE_GREAT_THRESHOLD:
            grade = GRADE_GREAT
        elif pct >= GRADE_GOOD_THRESHOLD:
            grade = GRADE_GOOD
        else:
            grade = GRADE_POOR
        ending = SPEECH_GAME_OVER.format(
            last_result=last_result_speech,
            score=self._score,
            total_rounds=self._total_rounds,
            grade=grade,
        )
        await self._push_state("", game_over=True)
        await self._say(ending)

    async def _say(self, text: str):
        await self.push_frame(
            TTSSpeakFrame(text=text, append_to_context=False), FrameDirection.DOWNSTREAM
        )

    async def _push_state(self, last_result: str, game_over: bool = False):
        frame = GameStateFrame(
            score=self._score,
            round=self._round,
            total_rounds=self._total_rounds,
            current_word=self._current_word or "",
            last_result=last_result,
            game_over=game_over,
        )
        if self._on_state_update:
            self._on_state_update(frame.to_dict())
        await self.push_frame(frame, FrameDirection.DOWNSTREAM)

    @staticmethod
    def _normalize(text: str) -> str:
        text = text.upper()
        text = re.sub(
            r"\b(CAPITAL|LOWER|LETTER|DASH|HYPHEN|DOT|PERIOD|COMMA|SPACE|AND|THE)\b",
            " ",
            text,
        )
        return "".join(re.findall(r"[A-Z]", text))
