"""Daonna Flask app — thin routing layer over the typing engine."""

from flask import Flask, jsonify, render_template, request

from daonna import PRESETS, TypingEngine

app = Flask(__name__)
engine = TypingEngine()


@app.route("/")
def index():
    return render_template("index.html", presets=PRESETS)


@app.route("/api/type", methods=["POST"])
def start():
    data = request.get_json(silent=True) or {}
    text = data.get("text", "")
    if not text:
        return jsonify({"status": "error", "message": "No text provided"}), 400

    preset_name = data.get("preset")
    preset = PRESETS.get(preset_name, {}) if preset_name else {}

    def pick(key, default):
        if key in data and data[key] is not None:
            return data[key]
        return preset.get(key, default)

    try:
        wpm = int(pick("wpm", 80))
        randomness = float(pick("randomness", 0.5))
        typo_probability = float(pick("typo_probability", 0.02))
        momentum = float(pick("momentum", 0.45))
        countdown = float(data.get("countdown", 5.0))
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "Invalid numeric parameter"}), 400

    started = engine.start(
        text=text,
        wpm=wpm,
        randomness=randomness,
        typo_probability=typo_probability,
        momentum=momentum,
        countdown=countdown,
    )
    if not started:
        return jsonify({"status": "error", "message": "Typing already in progress"}), 409

    return jsonify({"status": "success", "message": "Typing started"})


@app.route("/api/stop", methods=["POST"])
def stop():
    engine.stop()
    return jsonify({"status": "success", "message": "Stop requested"})


@app.route("/api/status", methods=["GET"])
def status():
    return jsonify(engine.state.snapshot())


@app.route("/api/presets", methods=["GET"])
def presets():
    return jsonify(PRESETS)


if __name__ == "__main__":
    app.run(debug=True, port=6969)
