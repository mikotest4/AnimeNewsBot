from flask import Flask, jsonify
import logging

# Suppress Flask's default logging to reduce console noise
logging.getLogger('werkzeug').setLevel(logging.ERROR)

app = Flask(__name__)

@app.route("/")
def root_route_handler():
    return jsonify({
        "message": "DARKXSIDE78 - The darkness shall follow my command",
        "status": "running",
        "service": "AnimeNewsBot"
    })

@app.route("/health")
def health_check():
    return jsonify({
        "status": "OK",
        "service": "AnimeNewsBot",
        "version": "3.0"
    })

@app.route("/status")
def bot_status():
    return jsonify({
        "bot": "AnimeNewsBot",
        "version": "3.0",
        "status": "active",
        "developer": "DARKXSIDE78"
    })

def start_webhook():
    try:
        print("Starting webhook server on port 8000...")
        app.run(host="0.0.0.0", port=8000, threaded=True, debug=False)
    except Exception as e:
        print(f"Webhook server error: {e}")
