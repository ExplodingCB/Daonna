document.addEventListener('DOMContentLoaded', function() {
    // Get DOM elements
    const textInput = document.getElementById('textInput');
    const wpmSlider = document.getElementById('wpmSlider');
    const randomnessSlider = document.getElementById('randomnessSlider');
    const typoSlider = document.getElementById('typoSlider');
    const startButton = document.getElementById('startButton');
    const clearButton = document.getElementById('clearButton');
    const statusMessage = document.getElementById('statusMessage');
    const progressBar = document.getElementById('progressBar');
    const wpmValue = document.getElementById('wpmValue');
    const randomnessValue = document.getElementById('randomnessValue');
    const typoValue = document.getElementById('typoValue');
    
    // Update slider display values
    wpmSlider.addEventListener('input', () => {
        wpmValue.textContent = wpmSlider.value;
    });
    
    randomnessSlider.addEventListener('input', () => {
        randomnessValue.textContent = randomnessSlider.value;
    });
    
    typoSlider.addEventListener('input', () => {
        typoValue.textContent = typoSlider.value;
    });
    
    // Status checking interval
    let statusInterval = null;
    
    // Start typing functionality
    startButton.addEventListener('click', function() {
        const text = textInput.value.trim();
        
        if (!text) {
            showStatus('Error: No text to type!', 'error');
            return;
        }
        
        const data = {
            text: text,
            wpm: parseInt(wpmSlider.value),
            randomness: parseFloat(randomnessSlider.value),
            typo_probability: parseFloat(typoSlider.value)
        };
        
        // Disable the start button
        startButton.disabled = true;
        startButton.classList.add('disabled');
        
        // Show the progress bar
        progressBar.style.display = 'block';
        
        // Update status
        showStatus('Starting in 5 seconds... Focus on your target application!', 'info');
        
        // Make API call to start typing
        fetch('/api/type', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'error') {
                showStatus(data.message, 'error');
                resetUI();
            } else {
                // Start polling for status
                statusInterval = setInterval(checkStatus, 1000);
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showStatus('Error: Could not connect to server', 'error');
            resetUI();
        });
    });
    
    // Check typing status
    function checkStatus() {
        fetch('/api/status')
        .then(response => response.json())
        .then(data => {
            if (!data.typing_in_progress) {
                clearInterval(statusInterval);
                showStatus('Typing completed!', 'success');
                resetUI();
            } else {
                showStatus('Typing in progress...', 'info');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            clearInterval(statusInterval);
            showStatus('Error: Lost connection to server', 'error');
            resetUI();
        });
    }
    
    // Reset UI elements
    function resetUI() {
        startButton.disabled = false;
        startButton.classList.remove('disabled');
        progressBar.style.display = 'none';
    }
    
    // Display status message
    function showStatus(message, type) {
        statusMessage.textContent = message;
        
        // Remove all status classes
        statusMessage.classList.remove('error', 'info', 'success');
        
        // Add appropriate class
        if (type) {
            statusMessage.classList.add(type);
        }
    }
    
    // Clear functionality
    clearButton.addEventListener('click', function() {
        textInput.value = '';
        showStatus('', '');
        progressBar.style.display = 'none';
    });
    
    // Add CSS classes for status types
    const style = document.createElement('style');
    style.textContent = `
        .status-message.error {
            color: #f44336;
        }
        
        .status-message.info {
            color: #2196f3;
        }
        
        .status-message.success {
            color: #4caf50;
        }
        
        .btn.disabled {
            background-color: #bdbdbd !important;
            color: #757575 !important;
            cursor: not-allowed;
            box-shadow: none !important;
        }
    `;
    document.head.appendChild(style);
});