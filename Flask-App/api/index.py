from flask import Flask, render_template, request, jsonify
import random
import time
import threading
import os

app = Flask(__name__)
app.root_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Global variable to track if typing is in progress
typing_in_progress = False
stop_typing = False

def get_adjacent_key(char):
    """Get a key adjacent to the given character on QWERTY keyboard."""
    qwerty_rows = [
        "`1234567890-=",
        "qwertyuiop[]\\",
        "asdfghjkl;'",
        "zxcvbnm,./"
    ]
    
    # Find the character in the keyboard layout
    for row_idx, row in enumerate(qwerty_rows):
        if char.lower() in row:
            char_idx = row.index(char.lower())
            
            # Get adjacent keys (left, right, up, down)
            adjacent_keys = []
            
            # Same row (left/right)
            if char_idx > 0:
                adjacent_keys.append(row[char_idx - 1])
            if char_idx < len(row) - 1:
                adjacent_keys.append(row[char_idx + 1])
            
            # Upper row
            if row_idx > 0:
                upper_row = qwerty_rows[row_idx - 1]
                if char_idx < len(upper_row):
                    adjacent_keys.append(upper_row[min(char_idx, len(upper_row) - 1)])
            
            # Lower row
            if row_idx < len(qwerty_rows) - 1:
                lower_row = qwerty_rows[row_idx + 1]
                if char_idx < len(lower_row):
                    adjacent_keys.append(lower_row[min(char_idx, len(lower_row) - 1)])
            
            if adjacent_keys:
                typo_char = random.choice(adjacent_keys)
                # Preserve case
                if char.isupper():
                    typo_char = typo_char.upper()
                return typo_char
            
    # If character not found or no adjacent keys, return the original
    return char

def simulate_typing(text, wpm, randomness, typo_probability):
    """
    Instead of actually typing with pyautogui, 
    this function just simulates the timing for Vercel
    """
    global typing_in_progress, stop_typing
    
    typing_in_progress = True
    stop_typing = False
    
    # Calculate base delay between keystrokes (60 seconds / WPM / 5 chars per word)
    base_delay = 60.0 / (wpm * 5)
    
    # Sleep for 5 seconds to allow user to focus on target application
    time.sleep(5)
    
    i = 0
    while i < len(text) and not stop_typing:
        char = text[i]
        
        # Determine if we should make a typo
        make_typo = random.random() < typo_probability
        
        if make_typo and char.isalnum():
            # Simulate typo timing
            time.sleep(base_delay * random.uniform(0.8, 1.2))
            time.sleep(base_delay * 0.5)  # Small delay after backspace
        else:
            # Normal typing simulation
            # Random delay calculation
            if random.random() < 0.05:  # Occasional longer pause (5% chance)
                delay = base_delay * random.uniform(2, 4)
            else:
                # Normal typing with randomness
                variation = base_delay * randomness
                delay = base_delay + random.uniform(-variation, variation)
                
                # Ensure delay is positive
                delay = max(0.01, delay)
            
            # Different delays for different character types
            if char in ".!?":
                delay *= 1.5  # Slightly longer pauses after sentences
            elif char in ",;:":
                delay *= 1.2  # Slightly longer pauses after phrases
            elif char == "\n":
                delay *= 2.0  # Longer pauses for new paragraphs
            
            # Apply the delay
            time.sleep(delay)
        
        i += 1
    
    typing_in_progress = False

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/type', methods=['POST'])
def start_typing():
    global typing_in_progress, stop_typing
    
    if typing_in_progress:
        return jsonify({'status': 'error', 'message': 'Typing already in progress'})
    
    data = request.json
    text = data.get('text', '')
    wpm = int(data.get('wpm', 50))
    randomness = float(data.get('randomness', 0.5))
    typo_probability = float(data.get('typo_probability', 0.02))
    
    if not text:
        return jsonify({'status': 'error', 'message': 'No text provided'})
    
    # In Vercel, we'll return immediately
    # The actual typing functionality won't work in a serverless environment
    return jsonify({
        'status': 'success', 
        'message': 'Typing simulation initiated. Note: Actual keyboard typing requires a local installation.'
    })

@app.route('/api/stop', methods=['POST'])
def stop_typing_route():
    global stop_typing
    
    stop_typing = True
    return jsonify({'status': 'success', 'message': 'Typing stopped'})

@app.route('/api/status', methods=['GET'])
def get_status():
    global typing_in_progress
    
    # For Vercel, we'll always return not in progress
    return jsonify({
        'typing_in_progress': False
    })

# Required for Vercel
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['TEMPLATES_FOLDER'] = os.path.join(app.root_path, 'templates')
app.config['STATIC_FOLDER'] = os.path.join(app.root_path, 'static')