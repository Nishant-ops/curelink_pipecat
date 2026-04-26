import re
import random
import logging
from enum import Enum, auto
from typing import Callable, List, Optional

from pipecat.frames.frames import (
    Frame,
    TextFrame,
    TranscriptionFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    StartFrame,
    EndFrame,
)
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection

from .frames import GameStartFrame, GameStateFrame

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
        self._total_rounds = total_rounds
        self._on_state_update = on_state_update
        self._on_turn_complete = on_turn_complete

        self._phase = GamePhase.IDLE
        self._current_word: Optional[str] = None
        self._score = 0
        self._round = 0
        self._interrupted = False

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

        if isinstance(frame, TranscriptionFrame):
            return

        if isinstance(frame, TextFrame):
            if self._phase == GamePhase.WAITING:
                if self._interrupted:
                    self._interrupted = False
                    await self._announce_current_word(
                        prefix="Sorry, I was interrupted. Let me repeat. "
                    )
                else:
                    await self._evaluate(frame.text)
            return

        if isinstance(frame, GameStateFrame):
            if self._on_state_update:
                self._on_state_update(frame.to_dict())
            await self.push_frame(frame, direction)
            return

        await self.push_frame(frame, direction)

    async def _begin_game(self):
        self._current_word = random.choice(self._word_list)
        self._round = 1
        self._score = 0
        self._phase = GamePhase.ANNOUNCING
        await self._push_state("")
        intro = (
            f"Welcome to Spell Bee! I will say a word and you spell it out loud, "
            f"one letter at a time. We will play {self._total_rounds} rounds. "
            f"Round 1. Your word is: {self._current_word}. "
            f"Please spell: {self._current_word}."
        )
        await self._say(intro)

    async def _announce_current_word(self, prefix: str = ""):
        self._phase = GamePhase.ANNOUNCING
        text = (
            f"{prefix}"
            f"Round {self._round}. Your word is: {self._current_word}. "
            f"Please spell: {self._current_word}."
        )
        await self._say(text)

    async def _evaluate(self, raw_input: str):
        self._phase = GamePhase.EVALUATING
        user_spelling = self._normalize(raw_input)
        expected = self._current_word.upper()
        correct = user_spelling == expected

        if correct:
            self._score += 1
            result_speech = "Correct! Well done."
            result_key = "correct"
        else:
            spelled_out = ", ".join(list(expected))
            result_speech = f"Not quite. The correct spelling is: {spelled_out}."
            result_key = "incorrect"

        logger.info(
            "SpellBee round %d: expected=%s got=%s correct=%s",
            self._round, expected, user_spelling, correct,
        )

        await self._push_state(result_key)

        if self._on_turn_complete:
            self._on_turn_complete()

        if self._round >= self._total_rounds:
            await self._end_game(result_speech)
        else:
            self._round += 1
            self._current_word = random.choice(self._word_list)
            self._phase = GamePhase.ANNOUNCING
            next_text = (
                f"{result_speech} "
                f"Round {self._round}. Your next word is: {self._current_word}. "
                f"Please spell: {self._current_word}."
            )
            await self._say(next_text)

    async def _end_game(self, last_result_speech: str):
        self._phase = GamePhase.FINISHED
        pct = self._score / self._total_rounds
        if pct == 1.0:
            grade = "Perfect score! Outstanding!"
        elif pct >= 0.7:
            grade = "Great job!"
        elif pct >= 0.5:
            grade = "Good effort!"
        else:
            grade = "Better luck next time!"
        ending = (
            f"{last_result_speech} "
            f"Game over! You scored {self._score} out of {self._total_rounds}. "
            f"{grade}"
        )
        await self._push_state("", game_over=True)
        await self._say(ending)

    async def _say(self, text: str):
        await self.push_frame(TextFrame(text=text), FrameDirection.DOWNSTREAM)

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
            r'\b(CAPITAL|LOWER|LETTER|DASH|HYPHEN|DOT|PERIOD|COMMA|SPACE|AND|THE)\b',
            ' ',
            text,
        )
        return ''.join(re.findall(r'[A-Z]', text))
