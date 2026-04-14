"""
Daonna MCP Server — Full PC Control Layer
Gives Claude complete, safe control over keyboard, mouse, and screen.
Claude can see the screen via screenshots, move/click the mouse precisely,
type with human-like rhythm, and use keyboard shortcuts safely.

Safety: destructive key combos (ctrl+a, ctrl+z bulk, etc.) are blocked unless
force=True is passed explicitly.
"""

from mcp.server.fastmcp import FastMCP
import pyautogui
import random
import time
import threading
import math
import ctypes
import ctypes.wintypes
import io
import base64

pyautogui.FAILSAFE = False  # disable corner-of-screen abort so Claude has full control

mcp = FastMCP("daonna")

# ── Win32 helpers ─────────────────────────────────────────────────────────────
user32 = ctypes.windll.user32

def _enum_windows():
    results = []
    def _cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            buf = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, buf, 512)
            if buf.value:
                results.append((hwnd, buf.value))
        return True
    cb_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    user32.EnumWindows(cb_type(_cb), 0)
    return results

def _find_window(title_contains: str):
    needle = title_contains.lower()
    for hwnd, title in _enum_windows():
        if needle in title.lower():
            return hwnd, title
    return None, None

def _get_window_rect(hwnd):
    rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return rect.left, rect.top, rect.right, rect.bottom

def _focus_and_click_window(hwnd, x_pct=0.5, y_pct=0.45):
    """Bring window to foreground and click at (x_pct, y_pct) relative position."""
    SW_RESTORE = 9
    user32.ShowWindow(hwnd, SW_RESTORE)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.25)
    left, top, right, bottom = _get_window_rect(hwnd)
    cx = left + int((right - left) * x_pct)
    cy = top + int((bottom - top) * y_pct)
    pyautogui.click(cx, cy)
    time.sleep(0.2)

def _get_foreground_hwnd():
    return user32.GetForegroundWindow()

def _window_still_focused(hwnd):
    return user32.GetForegroundWindow() == hwnd

# ── Safety ────────────────────────────────────────────────────────────────────
# Key combos that could wipe/corrupt a document. Require force=True to use.
DANGEROUS_COMBOS = {
    "ctrl+a",           # select all — if followed by any key, deletes everything
    "ctrl+shift+k",     # delete line (Docs)
    "ctrl+backspace",   # delete word back
}

def _is_dangerous(keys: str) -> bool:
    return keys.lower().replace(" ", "") in DANGEROUS_COMBOS

# ── Shared typing state ───────────────────────────────────────────────────────
_typing_in_progress = False
_stop_flag = False
_last_error = ""
_chars_typed = 0
_total_chars = 0
_state_lock = threading.Lock()

# ── Typing engine constants ───────────────────────────────────────────────────
COMMON_NGRAMS = {
    "the": 0.65, "ing": 0.60, "tion": 0.62, "and": 0.65, "ent": 0.67,
    "ion": 0.63, "tio": 0.62, "for": 0.66, "ate": 0.68, "ous": 0.67,
    "all": 0.68, "her": 0.66, "ter": 0.65, "hat": 0.67, "tha": 0.64,
    "ere": 0.66, "his": 0.65, "con": 0.67, "res": 0.68, "ver": 0.67,
    "est": 0.66, "ith": 0.65, "not": 0.66, "ome": 0.68, "out": 0.67,
}

COMMON_WORDS = {
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
}

QWERTY_ROWS = [
    "`1234567890-=",
    "qwertyuiop[]\\",
    "asdfghjkl;'",
    "zxcvbnm,./"
]

MIRROR_KEYS = {
    'q': 'p', 'w': 'o', 'e': 'i', 'r': 'u', 't': 'y',
    'a': ';', 's': 'l', 'd': 'k', 'f': 'j', 'g': 'h',
    'z': '/', 'x': '.', 'c': ',', 'v': 'm', 'b': 'n',
}
MIRROR_KEYS.update({v: k for k, v in MIRROR_KEYS.items()})

CONJUNCTIONS = {
    "but", "however", "because", "although", "though", "since",
    "while", "yet", "therefore", "moreover", "furthermore", "nevertheless",
}

# ── Typing helpers ────────────────────────────────────────────────────────────

def get_adjacent_key(char):
    for row_idx, row in enumerate(QWERTY_ROWS):
        if char.lower() in row:
            char_idx = row.index(char.lower())
            adj = []
            if char_idx > 0: adj.append(row[char_idx - 1])
            if char_idx < len(row) - 1: adj.append(row[char_idx + 1])
            if row_idx > 0:
                upper = QWERTY_ROWS[row_idx - 1]
                adj.append(upper[min(char_idx, len(upper) - 1)])
            if row_idx < len(QWERTY_ROWS) - 1:
                lower = QWERTY_ROWS[row_idx + 1]
                adj.append(lower[min(char_idx, len(lower) - 1)])
            if adj:
                k = random.choice(adj)
                return k.upper() if char.isupper() else k
    return char

def human_delay(base, randomness):
    return max(0.01, min(random.lognormvariate(math.log(base), 0.3 * randomness), base * 6))

def fatigue_multiplier(i, total):
    if total == 0: return 1.0
    p = i / total
    if p < 0.05: return 1.3 - (p / 0.05) * 0.3
    elif p < 0.75: return 0.95
    else: return 1.0 + ((p - 0.75) / 0.25) * 0.15

def is_word_boundary(text, pos):
    return pos > 0 and text[pos].isalnum() and not text[pos - 1].isalnum()

def word_at_position(text, pos):
    s = pos
    while s > 0 and text[s - 1].isalnum(): s -= 1
    e = pos
    while e < len(text) and text[e].isalnum(): e += 1
    return text[s:e].lower()

def inter_word_pause(base, word, randomness):
    pause = random.lognormvariate(math.log(base * 2.5), 0.25 * randomness)
    if word in COMMON_WORDS: pause *= 0.7
    elif len(word) > 8: pause *= 1.2
    return max(0.01, min(pause, base * 10))

def ngram_multiplier(text, pos):
    t = text.lower()
    for length in (4, 3):
        for offset in range(length):
            s = pos - offset
            if s < 0 or s + length > len(text): continue
            if t[s:s + length] in COMMON_NGRAMS:
                return COMMON_NGRAMS[t[s:s + length]]
    return 1.0

def thinking_pause(text, pos, base, randomness):
    if pos < 2: return 0
    prev = text[max(0, pos - 2):pos]

    if len(prev) == 2 and prev[0] in ".!?" and prev[1] == " ":
        return max(0.4, random.lognormvariate(math.log(base * random.uniform(12, 25)), 0.4 * randomness))

    if len(prev) == 2 and prev[0] in ",;:" and prev[1] == " " and random.random() < 0.40:
        return random.lognormvariate(math.log(base * random.uniform(5, 10)), 0.3 * randomness)

    if is_word_boundary(text, pos):
        word = word_at_position(text, pos)
        if word in CONJUNCTIONS and random.random() < 0.35:
            return random.lognormvariate(math.log(base * random.uniform(8, 15)), 0.35 * randomness)

    if pos > 0 and text[pos - 1] == "\n" and random.random() < 0.60:
        return max(0.5, random.lognormvariate(math.log(base * random.uniform(15, 30)), 0.4 * randomness))

    if pos > 5 and text[pos].isalpha() and is_word_boundary(text, pos):
        if random.random() < 0.06: return random.uniform(0.3, 0.8)
        if random.random() < 0.015: return random.uniform(0.8, 2.0)

    return 0

def generate_typo(text, pos, prob):
    char = text[pos]
    if not char.isalnum() or random.random() >= prob: return None
    roll = random.random()
    if roll < 0.40: return ("adjacent", get_adjacent_key(char))
    elif roll < 0.65:
        if pos + 1 < len(text) and text[pos + 1].isalnum():
            return ("transposition", (text[pos + 1], char))
        return ("adjacent", get_adjacent_key(char))
    elif roll < 0.80: return ("double", char)
    elif roll < 0.92: return ("skip", None)
    else:
        m = MIRROR_KEYS.get(char.lower())
        return ("mirror", m.upper() if char.isupper() else m) if m else ("adjacent", get_adjacent_key(char))

def execute_typo(text, pos, typo_type, typo_data, base, randomness):
    global _stop_flag
    roll = random.random()
    notice = 0 if roll < 0.50 else (random.randint(1, 2) if roll < 0.80 else (random.randint(3, 5) if roll < 0.90 else -1))

    consumed = 1
    typed = 0

    if typo_type in ("adjacent", "mirror"):
        pyautogui.write(typo_data); typed = 1
    elif typo_type == "transposition":
        pyautogui.write(typo_data[0])
        time.sleep(human_delay(base, randomness) * 0.5)
        pyautogui.write(typo_data[1])
        typed = 2; consumed = 2
    elif typo_type == "double":
        pyautogui.write(typo_data)
        time.sleep(human_delay(base, randomness) * 0.4)
        pyautogui.write(typo_data)
        typed = 2
    elif typo_type == "skip":
        return consumed

    if _stop_flag or notice == -1: return consumed

    extra = 0
    src = pos + consumed
    for _ in range(notice):
        if src >= len(text) or _stop_flag: break
        time.sleep(human_delay(base, randomness))
        pyautogui.write(text[src])
        extra += 1; src += 1; consumed += 1

    if _stop_flag: return consumed
    time.sleep(human_delay(base * 1.5, randomness))
    bs = random.uniform(0.3, 0.6)
    for _ in range(typed + extra):
        if _stop_flag: return consumed
        pyautogui.press('backspace')
        time.sleep(human_delay(base * bs, randomness))
    for j in range(pos, min(pos + consumed, len(text))):
        if _stop_flag: return consumed
        pyautogui.write(text[j])
        time.sleep(human_delay(base * 0.9, randomness))
    return consumed


def _do_type(text, wpm, randomness, typo_prob, target_hwnd):
    global _typing_in_progress, _stop_flag, _last_error, _chars_typed, _total_chars
    try:
        base = 60.0 / (wpm * 5)
        total = len(text)
        with _state_lock:
            _total_chars = total
            _chars_typed = 0

        if target_hwnd:
            _focus_and_click_window(target_hwnd)

        i = 0
        while i < total and not _stop_flag:
            # Every 50 chars, verify we still have the right window focused
            if target_hwnd and i > 0 and i % 50 == 0:
                if not _window_still_focused(target_hwnd):
                    _focus_and_click_window(target_hwnd)
                    time.sleep(0.3)

            char = text[i]
            fat = fatigue_multiplier(i, total)

            if is_word_boundary(text, i):
                time.sleep(inter_word_pause(base, word_at_position(text, i), randomness) * fat)

            tp = thinking_pause(text, i, base, randomness)
            if tp > 0: time.sleep(tp)

            typo = generate_typo(text, i, typo_prob)
            if typo:
                i += execute_typo(text, i, typo[0], typo[1], base, randomness)
                with _state_lock: _chars_typed = i
                continue

            pyautogui.write(char)
            delay = human_delay(base, randomness) * fat * ngram_multiplier(text, i)
            if char in ".!?": delay *= 2.5
            elif char in ",;:": delay *= 1.8
            elif char == "\n": delay *= 3.0
            time.sleep(delay)
            i += 1
            with _state_lock: _chars_typed = i

    except Exception as e:
        with _state_lock: _last_error = str(e)
    finally:
        with _state_lock: _typing_in_progress = False


# ── MCP Tools ─────────────────────────────────────────────────────────────────

@mcp.tool()
def screenshot() -> list:
    """
    Take a screenshot of the entire screen and return it as an image.
    Use this to verify the current state of the screen before and after actions —
    especially before typing to confirm the cursor is in the right place in the doc,
    and after to confirm text appeared correctly.
    """
    img = pyautogui.screenshot()
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    b64 = base64.b64encode(buf.getvalue()).decode()
    return [{"type": "image", "data": b64, "mimeType": "image/png"}]


@mcp.tool()
def move_mouse(x: int, y: int) -> str:
    """Move the mouse cursor to absolute screen coordinates (x, y)."""
    pyautogui.moveTo(x, y, duration=random.uniform(0.1, 0.25))
    return f"Mouse moved to ({x}, {y})"


@mcp.tool()
def click(x: int, y: int, button: str = "left", clicks: int = 1) -> str:
    """
    Click the mouse at absolute screen coordinates.

    Args:
        x, y: Screen coordinates to click.
        button: "left", "right", or "middle".
        clicks: Number of clicks (2 for double-click).
    """
    pyautogui.click(x, y, button=button, clicks=clicks, interval=0.08)
    time.sleep(0.1)
    return f"Clicked {button} x{clicks} at ({x}, {y})"


@mcp.tool()
def scroll(x: int, y: int, amount: int) -> str:
    """
    Scroll at position (x, y). Positive amount scrolls up, negative scrolls down.
    Typical values: 3 to 10.
    """
    pyautogui.scroll(amount, x=x, y=y)
    return f"Scrolled {amount} at ({x}, {y})"


@mcp.tool()
def focus_window(title_contains: str, click_x_pct: float = 0.5, click_y_pct: float = 0.45) -> str:
    """
    Bring a window to the foreground and click into it to ensure keyboard focus.

    Args:
        title_contains: Partial window title (case-insensitive). Use list_windows() to find it.
        click_x_pct: Horizontal click position as a fraction of window width (0.0–1.0). Default 0.5 = center.
        click_y_pct: Vertical click position as a fraction of window height (0.0–1.0). Default 0.45 = slightly above center.
                     For Google Docs, 0.45 lands in the document body. Adjust if needed.
    """
    hwnd, title = _find_window(title_contains)
    if not hwnd:
        return f"ERROR: no window found matching '{title_contains}'. Use list_windows() to see options."
    _focus_and_click_window(hwnd, click_x_pct, click_y_pct)
    left, top, right, bottom = _get_window_rect(hwnd)
    cx = left + int((right - left) * click_x_pct)
    cy = top + int((bottom - top) * click_y_pct)
    return f"Focused '{title}' and clicked at screen position ({cx}, {cy})"


@mcp.tool()
def list_windows() -> str:
    """List all visible windows. Use this to find the right title for other tools."""
    windows = _enum_windows()
    lines = [f"  {title}" for _, title in sorted(windows, key=lambda x: x[1].lower())]
    return "Open windows:\n" + "\n".join(lines)


@mcp.tool()
def get_window_bounds(title_contains: str) -> str:
    """Get the screen position and size of a window (left, top, right, bottom in pixels)."""
    hwnd, title = _find_window(title_contains)
    if not hwnd:
        return f"ERROR: no window found matching '{title_contains}'"
    left, top, right, bottom = _get_window_rect(hwnd)
    return f"Window: '{title}'\nBounds: left={left} top={top} right={right} bottom={bottom}\nSize: {right-left}x{bottom-top}px\nCenter: ({(left+right)//2}, {(top+bottom)//2})"


@mcp.tool()
def start_typing(
    text: str,
    wpm: int = 120,
    randomness: float = 0.5,
    typo_probability: float = 0.02,
    window_title: str = "",
) -> str:
    """
    Start typing text with human-like rhythm. Returns immediately — poll get_typing_status() until idle.
    ALWAYS take a screenshot() before calling this to confirm the cursor is in the right place.

    Args:
        text: Text to type. Use \\n for newlines.
        wpm: Speed in words per minute. 80–160 is realistic human range.
        randomness: 0.1 (steady) to 1.0 (erratic). 0.5 is natural.
        typo_probability: Per-character typo chance. 0.02 is realistic. 0 = none.
        window_title: Partial window title to focus and click into before typing.
                      The tool clicks into the window automatically. Leave empty
                      to type into whatever is currently focused.
    """
    global _typing_in_progress, _stop_flag, _last_error, _chars_typed, _total_chars

    with _state_lock:
        if _typing_in_progress:
            return "ERROR: already typing. Call stop_typing() or wait for get_typing_status() to return idle."
        _typing_in_progress = True
        _stop_flag = False
        _last_error = ""
        _chars_typed = 0
        _total_chars = len(text)

    target_hwnd = None
    if window_title:
        hwnd, found = _find_window(window_title)
        if not hwnd:
            with _state_lock: _typing_in_progress = False
            return f"ERROR: no window matching '{window_title}'. Use list_windows() first."
        target_hwnd = hwnd
        _focus_and_click_window(target_hwnd)

    threading.Thread(
        target=_do_type,
        args=(text, wpm, randomness, typo_probability, target_hwnd),
        daemon=True,
    ).start()

    return f"Typing started — {len(text)} chars at ~{wpm} WPM. Poll get_typing_status() to check progress."


@mcp.tool()
def get_typing_status() -> str:
    """Check whether typing is in progress. Poll this after start_typing() until it returns idle."""
    with _state_lock:
        in_prog = _typing_in_progress
        chars = _chars_typed
        total = _total_chars
        err = _last_error
    if err: return f"error: {err}"
    if not in_prog: return f"idle — finished {chars}/{total} characters"
    pct = int(chars / total * 100) if total > 0 else 0
    return f"typing — {chars}/{total} characters ({pct}% done)"


@mcp.tool()
def stop_typing() -> str:
    """Immediately stop typing in progress."""
    global _stop_flag
    with _state_lock: _stop_flag = True
    return "Stop signal sent."


@mcp.tool()
def press_keys(keys: str, window_title: str = "", force: bool = False) -> str:
    """
    Press a keyboard shortcut or key. Focuses the window first if window_title is given.
    Dangerous combos (ctrl+a, etc.) are blocked unless force=True.

    Common shortcuts for Google Docs:
        ctrl+b / ctrl+i / ctrl+u         → bold / italic / underline
        ctrl+shift+l/e/r/j               → align left/center/right/justify
        ctrl+shift+7 / ctrl+shift+8      → numbered / bulleted list
        ctrl+] / ctrl+[                  → indent / unindent
        ctrl+z / ctrl+y                  → undo / redo
        ctrl+home / ctrl+end             → jump to top / bottom of doc
        ctrl+enter                       → page break
        enter / tab / backspace          → normal keys

    Args:
        keys: Key combo, e.g. "ctrl+b", "enter", "ctrl+shift+l".
        window_title: Optional window to focus before pressing.
        force: Set True to allow dangerous combos like ctrl+a. Use with extreme caution.
    """
    normalized = keys.lower().replace(" ", "")
    if _is_dangerous(normalized) and not force:
        return (
            f"BLOCKED: '{keys}' is a potentially destructive shortcut that could wipe document content. "
            f"If you truly need this, call press_keys with force=True. Double-check your intent first."
        )

    if window_title:
        hwnd, _ = _find_window(window_title)
        if hwnd: _focus_and_click_window(hwnd)

    time.sleep(random.uniform(0.08, 0.18))
    parts = [k.strip() for k in keys.lower().split("+")]
    pyautogui.hotkey(*parts)
    return f"Pressed: {keys}"


@mcp.tool()
def get_screen_size() -> str:
    """Return the screen resolution. Useful for calculating click coordinates."""
    w, h = pyautogui.size()
    return f"Screen size: {w}x{h} pixels"


if __name__ == "__main__":
    mcp.run()
