"""Keyboard layout, common words, and n-gram data."""

# QWERTY rows used for adjacency lookup.
QWERTY_ROWS = (
    "`1234567890-=",
    "qwertyuiop[]\\",
    "asdfghjkl;'",
    "zxcvbnm,./",
)

# Left-hand <-> right-hand mirror approximation (wrong-hand typos).
_MIRROR_BASE = {
    "q": "p", "w": "o", "e": "i", "r": "u", "t": "y",
    "a": ";", "s": "l", "d": "k", "f": "j", "g": "h",
    "z": "/", "x": ".", "c": ",", "v": "m", "b": "n",
}
MIRROR_KEYS = {**_MIRROR_BASE, **{v: k for k, v in _MIRROR_BASE.items()}}

# Common English 3/4-grams mapped to a speed multiplier (<1.0 = faster).
# These runs get burst-typed inside a chunk.
COMMON_NGRAMS = {
    "the": 0.55, "ing": 0.55, "tion": 0.58, "and": 0.58, "ent": 0.62,
    "ion": 0.60, "tio": 0.60, "for": 0.62, "ate": 0.64, "ous": 0.63,
    "all": 0.62, "her": 0.62, "ter": 0.62, "hat": 0.63, "tha": 0.60,
    "ere": 0.62, "his": 0.62, "con": 0.63, "res": 0.64, "ver": 0.63,
    "est": 0.62, "ith": 0.62, "not": 0.63, "ome": 0.64, "out": 0.63,
    "you": 0.60, "are": 0.60, "was": 0.62, "ment": 0.60, "ight": 0.60,
    "ould": 0.58, "ever": 0.62,
}

COMMON_WORDS = frozenset({
    "the", "be", "to", "of", "and", "a", "in", "that", "have", "i",
    "it", "for", "not", "on", "with", "he", "as", "you", "do", "at",
    "this", "but", "his", "by", "from", "they", "we", "say", "her", "she",
    "or", "an", "will", "my", "one", "all", "would", "there", "their", "what",
    "so", "up", "if", "about", "who", "get", "which", "go", "me", "when",
    "can", "could", "should", "just", "like", "been", "had", "than", "its",
    "also", "into", "only", "other", "new", "some", "time", "very",
    "your", "how", "each", "make", "way", "our", "after", "then", "them",
    "these", "two", "may", "did", "more", "any", "over", "such", "know",
    "most", "well", "back", "much", "before", "right", "too", "does", "good",
    "want", "give", "day", "think", "because", "people", "still", "here",
    "even", "own", "take", "come", "made", "find", "long", "first",
    "now", "look", "down", "use", "many", "see", "work", "need",
    "is", "was", "were", "has", "been", "are", "am", "being",
})

CONJUNCTIONS = frozenset({
    "but", "however", "because", "although", "though", "since", "while",
    "yet", "therefore", "moreover", "furthermore", "nevertheless", "whereas",
})


def get_adjacent_key(char: str) -> str:
    """Return a key adjacent to `char` on QWERTY, preserving case."""
    lower = char.lower()
    for row_idx, row in enumerate(QWERTY_ROWS):
        if lower not in row:
            continue
        idx = row.index(lower)
        candidates = []
        if idx > 0:
            candidates.append(row[idx - 1])
        if idx < len(row) - 1:
            candidates.append(row[idx + 1])
        if row_idx > 0:
            upper = QWERTY_ROWS[row_idx - 1]
            candidates.append(upper[min(idx, len(upper) - 1)])
        if row_idx < len(QWERTY_ROWS) - 1:
            lower_row = QWERTY_ROWS[row_idx + 1]
            candidates.append(lower_row[min(idx, len(lower_row) - 1)])
        if candidates:
            import random
            pick = random.choice(candidates)
            return pick.upper() if char.isupper() else pick
    return char


def is_word_boundary(text: str, pos: int) -> bool:
    if pos == 0 or pos >= len(text):
        return False
    return text[pos].isalnum() and not text[pos - 1].isalnum()


def word_at_position(text: str, pos: int) -> str:
    start = pos
    while start > 0 and text[start - 1].isalnum():
        start -= 1
    end = pos
    while end < len(text) and text[end].isalnum():
        end += 1
    return text[start:end].lower()


def current_ngram_multiplier(text: str, pos: int) -> float:
    """If the position falls inside a common 3/4-gram, return its speed factor."""
    lower = text.lower()
    for length in (4, 3):
        for offset in range(length):
            start = pos - offset
            if start < 0 or start + length > len(text):
                continue
            ngram = lower[start:start + length]
            if ngram in COMMON_NGRAMS:
                return COMMON_NGRAMS[ngram]
    return 1.0
