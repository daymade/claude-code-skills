#!/usr/bin/env python3
"""
Mock SSE upstream that emits one frame, stays silent N seconds, then emits
a closing frame. Designed for layered-isolation experiments where the
investigator needs a controlled idle-duration trigger — cheaper and more
reproducible than using a real slow production request.

Usage (standalone):
    python3 mock-idle-upstream.py --port 19999 --idle 200

Usage (Docker, running on a lobe-network compose):
    docker run --rm --network lobe-dev_default -p 19999:80 \
      -v $(pwd)/mock-idle-upstream.py:/app/mock.py \
      python:3.12-slim \
      sh -c 'pip install flask -q && python /app/mock.py --port 80 --idle 200'

Then reverse-proxy your test hostname at this port, and run the 3-path
layered experiment (see references/layered-isolation-experiment.md).

What it emits:
    HTTP/1.1 200 OK
    Content-Type: text/event-stream

    event: message_start
    data: {"type":"message_start","message":{"usage":{"input_tokens":10}}}

    <IDLE_SECONDS silence>

    event: message_stop
    data: {"type":"message_stop"}

After IDLE_SECONDS, if the client is still connected, a final frame is sent
and the connection closes cleanly. If the client (or any middlebox) closes
the connection earlier, the server-side logs record the peer-close
timestamp — that is the measurement the experiment needs.

Why Flask: minimal dependency surface, one pip install, deterministic.
Works identically on macOS, Linux, and inside slim Docker images.

Why not http.server / aiohttp / starlette: Flask's streaming generator
pattern with `yield` keeps the code 15 lines and does not require async.
The mock does not need concurrency — one request at a time is enough for
layered comparison.
"""

import argparse
import logging
import sys
import time
from datetime import datetime, timezone

try:
    from flask import Flask, Response, request
except ImportError:
    print("ERROR: flask not installed. Run: pip install flask", file=sys.stderr)
    sys.exit(1)

app = Flask(__name__)
logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s",
    level=logging.INFO,
    stream=sys.stderr,
)
log = logging.getLogger("mock-idle-upstream")


@app.route("/v1/messages", methods=["POST"])
@app.route("/probe-a", methods=["GET", "POST"])
@app.route("/probe-b", methods=["GET", "POST"])
@app.route("/probe-c", methods=["GET", "POST"])
@app.route("/", methods=["GET", "POST"])
def handler():
    idle = app.config["IDLE_SECONDS"]
    label = request.path.lstrip("/") or "root"
    start = time.monotonic()
    ua = request.headers.get("User-Agent", "?")
    src = request.headers.get("Cf-Connecting-Ip") or request.remote_addr
    log.info("OPENED label=%s src=%s ua=%s idle=%ss", label, src, ua[:60], idle)

    def gen():
        # Initial frame — mimics Anthropic message_start to match real
        # SSE traffic shape. Byte count is deliberate: around 100 bytes,
        # matching what real Anthropic proxies emit as the first flush.
        yield (
            b"event: message_start\n"
            b'data: {"type":"message_start","message":{"usage":{"input_tokens":10}}}\n\n'
        )
        log.info("SENT message_start label=%s t=%.2fs", label, time.monotonic() - start)

        # The idle window. If the connection survives this, we will see
        # the closing frame; if not, the server will see a BrokenPipeError
        # which we log from the request teardown hook below.
        time.sleep(idle)

        log.info("IDLE COMPLETE label=%s t=%.2fs — attempting final frame",
                 label, time.monotonic() - start)
        yield (
            b"event: message_stop\n"
            b'data: {"type":"message_stop"}\n\n'
        )
        log.info("SENT message_stop label=%s t=%.2fs FINAL_SENT_OK",
                 label, time.monotonic() - start)

    return Response(gen(), mimetype="text/event-stream")


@app.teardown_request
def log_teardown(exc):
    # When the peer closes before the idle window expires, Flask raises
    # during generator iteration. Record it so the experiment log captures
    # the peer-close moment from the server side (not just the client side).
    if exc is not None:
        log.info("PEER CLOSE or ERROR: %s", exc)


def main():
    ap = argparse.ArgumentParser(
        description="SSE mock upstream for layered-isolation experiments."
    )
    ap.add_argument("--port", type=int, default=19999,
                    help="Port to listen on (default 19999).")
    ap.add_argument("--idle", type=int, default=200,
                    help="Seconds to idle between first frame and final frame "
                         "(default 200, chosen to exceed typical CDN idle "
                         "timeouts of 100-130s).")
    ap.add_argument("--host", default="0.0.0.0",
                    help="Bind address (default 0.0.0.0).")
    args = ap.parse_args()

    app.config["IDLE_SECONDS"] = args.idle
    log.info("Mock idle upstream starting: host=%s port=%s idle=%ss "
             "started_utc=%s", args.host, args.port, args.idle,
             datetime.now(timezone.utc).isoformat())
    # threaded=True so the generator's time.sleep does not block other
    # concurrent probes (needed for Path A/B/C running in parallel).
    app.run(host=args.host, port=args.port, threaded=True, debug=False)


if __name__ == "__main__":
    main()
