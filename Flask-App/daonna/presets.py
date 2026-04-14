"""Named typing profiles."""

PRESETS = {
    "casual": {
        "wpm": 65,
        "randomness": 0.55,
        "typo_probability": 0.025,
        "momentum": 0.45,
    },
    "focused": {
        "wpm": 95,
        "randomness": 0.35,
        "typo_probability": 0.01,
        "momentum": 0.55,
    },
    "tired": {
        "wpm": 45,
        "randomness": 0.75,
        "typo_probability": 0.05,
        "momentum": 0.35,
    },
    "sprint": {
        "wpm": 140,
        "randomness": 0.3,
        "typo_probability": 0.015,
        "momentum": 0.6,
    },
}
