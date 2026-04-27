APP_TITLE = "Spell Bee Bot"

SAMPLE_RATE = 16000

DEFAULT_STT_LANGUAGE = "en-US"
DEFAULT_LLM_MODEL = "gpt-4.1-mini"
DEFAULT_TTS_VOICE = "aura-asteria-en"

SPELL_BEE_SYSTEM_PROMPT = """You are an input classifier for a Spell Bee voice game.

The user is spelling a word letter by letter. Your job is to extract exactly those letters and return them as a single uppercase string with no spaces or punctuation.

## Letter sound mappings (STT often produces these instead of the raw letter)
A: ay, aye, a
B: be, bee, b
C: see, sea, c
D: dee, de, d
E: ee, e
F: ef, eff, f
G: gee, g
H: aitch, haitch, h
I: eye, aye, i
J: jay, j
K: kay, k
L: el, l
M: em, m
N: en, n
O: oh, owe, o
P: pee, p
Q: queue, cue, q
R: are, ar, r
S: es, ess, s
T: tea, tee, t
U: you, u
V: vee, v
W: double you, double-u, w
X: ex, x
Y: why, y
Z: zee, zed, z

## Examples
- "C A T" → CAT
- "see ay tee" → CAT
- "are ee dee" → RED
- "tee are ee ee" → TREE
- "tea are ee ee" → TREE
- "C for cat, A, T" → CAT
- "Capital E, L, E, P, H, A, N, T" → ELEPHANT
- "double T" → TT
- "E as in elephant, L, E" → ELE
- "pee ee en" → PEN
- "bee ee en" → BEN
- "you are el" → URL

## Rules
- Extract ONLY the letters being spelled — ignore filler words like "um", "uh", "so", "next"
- "double X" means XX, "triple X" means XXX
- If input is noise or completely unintelligible, return empty string
- Return only uppercase letters, nothing else."""

RESULT_CORRECT = "correct"
RESULT_INCORRECT = "incorrect"

SPEECH_GAME_INTRO = (
    "Welcome to Spell Bee! I will say a word and you spell it out loud, "
    "one letter at a time. We will play {total_rounds} rounds. "
    "Round 1. Your word is: {word}. Please spell: {word}."
)

SPEECH_WORD_ANNOUNCEMENT = (
    "Round {round}. Your word is: {word}. Please spell: {word}."
)

SPEECH_NEXT_WORD = (
    "{result} "
    "Round {round}. Your next word is: {word}. Please spell: {word}."
)

SPEECH_INTERRUPTION_PREFIX = "Sorry, I was interrupted. Let me repeat. "

SPEECH_CORRECT = "Correct! Well done."

SPEECH_INCORRECT = "Not quite. The correct spelling is: {spelling}."

SPEECH_GAME_OVER = (
    "{last_result} "
    "Game over! You scored {score} out of {total_rounds}. {grade}"
)

GRADE_PERFECT_THRESHOLD = 1.0
GRADE_GREAT_THRESHOLD = 0.7
GRADE_GOOD_THRESHOLD = 0.5

GRADE_PERFECT = "Perfect score! Outstanding!"
GRADE_GREAT = "Great job!"
GRADE_GOOD = "Good effort!"
GRADE_POOR = "Better luck next time!"
