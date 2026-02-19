from flask import Flask, request, jsonify
from api.analyze import run_pipeline

app = Flask(__name__)

ALLOWED_ORIGIN = "https://redditmonitor.jaskaranbedi.com"


@app.after_request
def add_cors(response):
    origin = request.headers.get("Origin", "")
    if origin == ALLOWED_ORIGIN or not origin:
        response.headers["Access-Control-Allow-Origin"] = ALLOWED_ORIGIN
    response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


@app.route("/analyze", methods=["POST", "OPTIONS"])
def analyze():
    if request.method == "OPTIONS":
        return "", 200
    body = request.get_json(silent=True)
    if not body or not isinstance(body, dict):
        return jsonify({"error": "Invalid JSON body"}), 400
    client_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    if client_ip:
        client_ip = client_ip.split(",")[0].strip()
    result, status_code = run_pipeline(body, client_ip=client_ip)
    return jsonify(result), status_code


@app.route("/health")
def health():
    return jsonify({"status": "ok"})
