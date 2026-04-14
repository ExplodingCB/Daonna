(() => {
    const $ = (id) => document.getElementById(id);

    const textInput = $('textInput');
    const charCount = $('charCount');

    const sliders = {
        wpm: { el: $('wpmSlider'), out: $('wpmValue'), fmt: (v) => v },
        randomness: { el: $('randomnessSlider'), out: $('randomnessValue'), fmt: (v) => (+v).toFixed(2) },
        typo: { el: $('typoSlider'), out: $('typoValue'), fmt: (v) => (+v).toFixed(3) },
        momentum: { el: $('momentumSlider'), out: $('momentumValue'), fmt: (v) => (+v).toFixed(2) },
        countdown: { el: $('countdownSlider'), out: $('countdownValue'), fmt: (v) => v },
    };

    const startBtn = $('startButton');
    const stopBtn = $('stopButton');
    const statusMsg = $('statusMessage');
    const statusStats = $('statusStats');
    const statusPill = $('statusPill');
    const progressFill = $('progressFill');

    const overlay = $('countdownOverlay');
    const countdownNum = $('countdownNum');
    const cancelCountdown = $('cancelCountdown');

    const presetButtons = document.querySelectorAll('.preset');

    let pollTimer = null;
    let activePresetName = '';

    // --- slider display binding ---
    Object.values(sliders).forEach((s) => {
        const update = () => (s.out.textContent = s.fmt(s.el.value));
        s.el.addEventListener('input', () => {
            update();
            markCustomPreset();
        });
        update();
    });

    textInput.addEventListener('input', () => {
        charCount.textContent = `${textInput.value.length} chars`;
    });

    // --- presets ---
    let presetData = {};
    fetch('/api/presets').then((r) => r.json()).then((data) => { presetData = data; });

    function markCustomPreset() {
        presetButtons.forEach((b) => b.classList.toggle('active', b.dataset.preset === ''));
        activePresetName = '';
    }

    presetButtons.forEach((btn) => {
        btn.addEventListener('click', () => {
            const name = btn.dataset.preset;
            presetButtons.forEach((b) => b.classList.remove('active'));
            btn.classList.add('active');
            activePresetName = name;
            if (!name) return;
            const p = presetData[name];
            if (!p) return;
            sliders.wpm.el.value = p.wpm;
            sliders.randomness.el.value = p.randomness;
            sliders.typo.el.value = p.typo_probability;
            sliders.momentum.el.value = p.momentum;
            Object.values(sliders).forEach((s) => (s.out.textContent = s.fmt(s.el.value)));
        });
    });

    // --- status helpers ---
    function setStatus(text, cls) {
        statusMsg.textContent = text;
        statusMsg.classList.remove('error', 'info', 'success');
        if (cls) statusMsg.classList.add(cls);
        setPill(cls);
    }

    function setPill(cls) {
        statusPill.classList.remove('running', 'done', 'error', 'muted');
        if (cls === 'info') { statusPill.classList.add('running'); statusPill.textContent = 'running'; }
        else if (cls === 'success') { statusPill.classList.add('done'); statusPill.textContent = 'done'; }
        else if (cls === 'error') { statusPill.classList.add('error'); statusPill.textContent = 'error'; }
        else { statusPill.classList.add('muted'); statusPill.textContent = 'idle'; }
    }

    function setProgress(pct) {
        progressFill.style.width = `${Math.min(100, Math.max(0, pct * 100))}%`;
    }

    function setRunning(running) {
        startBtn.disabled = running;
        stopBtn.disabled = !running;
    }

    // --- countdown overlay ---
    let countdownTimer = null;
    function showCountdown(seconds) {
        overlay.classList.remove('hidden');
        let remaining = seconds;
        countdownNum.textContent = remaining;
        clearInterval(countdownTimer);
        countdownTimer = setInterval(() => {
            remaining -= 1;
            if (remaining <= 0) {
                clearInterval(countdownTimer);
                overlay.classList.add('hidden');
            } else {
                countdownNum.textContent = remaining;
            }
        }, 1000);
    }

    function hideCountdown() {
        clearInterval(countdownTimer);
        overlay.classList.add('hidden');
    }

    cancelCountdown.addEventListener('click', () => {
        stopTyping();
        hideCountdown();
    });

    // --- start / stop ---
    startBtn.addEventListener('click', () => {
        const text = textInput.value;
        if (!text.trim()) {
            setStatus('Add some text first.', 'error');
            return;
        }

        const countdown = parseInt(sliders.countdown.el.value, 10);
        const payload = {
            text,
            wpm: parseInt(sliders.wpm.el.value, 10),
            randomness: parseFloat(sliders.randomness.el.value),
            typo_probability: parseFloat(sliders.typo.el.value),
            momentum: parseFloat(sliders.momentum.el.value),
            countdown,
        };
        if (activePresetName) payload.preset = activePresetName;

        setRunning(true);
        setProgress(0);
        setStatus('Starting...', 'info');
        showCountdown(countdown);

        fetch('/api/type', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        })
            .then((r) => r.json().then((d) => ({ ok: r.ok, body: d })))
            .then(({ ok, body }) => {
                if (!ok) {
                    setStatus(body.message || 'Failed to start', 'error');
                    setRunning(false);
                    hideCountdown();
                    return;
                }
                startPolling();
            })
            .catch((err) => {
                console.error(err);
                setStatus('Could not reach server', 'error');
                setRunning(false);
                hideCountdown();
            });
    });

    stopBtn.addEventListener('click', stopTyping);

    function stopTyping() {
        fetch('/api/stop', { method: 'POST' }).catch(() => {});
    }

    function startPolling() {
        clearInterval(pollTimer);
        pollTimer = setInterval(pollStatus, 250);
    }

    function pollStatus() {
        fetch('/api/status')
            .then((r) => r.json())
            .then((s) => {
                setProgress(s.progress || 0);
                const stats = s.total
                    ? `${s.position} / ${s.total} · ${(s.elapsed || 0).toFixed(1)}s`
                    : '';
                statusStats.textContent = stats;

                if (s.running) {
                    // Hide countdown once we're past the "Focus..." message.
                    if (!s.message.startsWith('Focus')) hideCountdown();
                    setStatus(s.message || 'Typing...', 'info');
                } else {
                    clearInterval(pollTimer);
                    hideCountdown();
                    setRunning(false);
                    const done = (s.message || '').toLowerCase().includes('done');
                    setStatus(s.message || 'Idle', done ? 'success' : 'info');
                    if (done) setProgress(1);
                }
            })
            .catch(() => {
                clearInterval(pollTimer);
                setRunning(false);
                hideCountdown();
                setStatus('Lost connection', 'error');
            });
    }

    // Keyboard: Esc cancels, Ctrl+Enter starts
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !stopBtn.disabled) {
            stopTyping();
        } else if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && !startBtn.disabled) {
            startBtn.click();
        }
    });

    // Initial status fetch in case a run is in progress (e.g. page reload).
    pollStatus();
})();
