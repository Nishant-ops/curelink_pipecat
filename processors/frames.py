from dataclasses import dataclass
from typing import Literal
from pipecat.frames.frames import DataFrame, ControlFrame


@dataclass
class GameStartFrame(ControlFrame):
    pass


@dataclass
class GameStateFrame(DataFrame):
    score: int = 0
    round: int = 0
    total_rounds: int = 10
    current_word: str = ""
    last_result: Literal["correct", "incorrect", ""] = ""
    game_over: bool = False

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "round": self.round,
            "total_rounds": self.total_rounds,
            "current_word": self.current_word,
            "last_result": self.last_result,
            "game_over": self.game_over,
        }
