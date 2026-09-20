"""
A stand-in for a local model server, used ONLY by the browser E2E run.

It speaks the OpenAI-compatible protocol (POST /v1/chat/completions), which is what the
platform's Ollama / openai_compatible providers use, and answers the way a well-behaved,
purely extractive model would: objectives and questions built from sentences that really
appear in the material it was sent, each with a verbatim source quote. The platform still
verifies every quote, so this exercises the real pipeline, review and publish code.

    POST /__mode   {"fail": true}    -> answer 503 until switched off (simulates an outage)

Reporting requests are answered by the faithful_report double of tests/foundation/fakes.py (one cited claim per finding).
Grading requests (the platform's grading agent for written answers) are answered by the overlap grader of
tests/foundation/fakes.py: the share of the expected answer's longer words found in the learner's answer.
It is a test double for the model, nothing more.

Run:  python scripts/e2e/fake_llm_server.py 8199
"""

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "services" / "api")]

from tests.foundation.fakes import (  # noqa: E402
    extractive_analysis, extractive_questions, faithful_report, grading_fields, material_from_prompt, overlap_grade, reporting_package,
)

STATE = {"fail": False, "calls": 0}


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self):  # noqa: N802
        self._send(200, {"ok": True, **STATE})

    def do_POST(self):  # noqa: N802
        if self.path == "/__mode":
            STATE["fail"] = bool(self._body().get("fail"))
            return self._send(200, STATE)

        if not self.path.endswith("/chat/completions"):
            return self._send(404, {"error": "not found"})
        request = self._body()
        STATE["calls"] += 1
        if STATE["fail"]:
            return self._send(503, {"error": {"message": "model server is down"}})

        messages = request.get("messages", [])
        system = messages[0]["content"] if messages else ""
        first_user = next((m["content"] for m in messages if m["role"] == "user"), "")
        if "reporting analyst" in system:
            STATE["reports"] = STATE.get("reports", 0) + 1
            payload = faithful_report(reporting_package(first_user))
        elif "You are a grading assistant" in system:
            STATE["gradings"] = STATE.get("gradings", 0) + 1
            payload = overlap_grade(grading_fields(first_user))
        else:
            material = material_from_prompt(first_user)
            payload = extractive_analysis(material) if "instructional designer" in system else extractive_questions(material)
        self._send(200, {
            "model": "fake-extractive",
            "choices": [{"message": {"role": "assistant", "content": json.dumps(payload)}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0},
        })

    def log_message(self, *args):  # keep the console quiet
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8199
    print(f"fake LLM listening on {port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
