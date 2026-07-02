from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from sextant.common.observability import MetricsRegistry, render_prometheus_metrics


def start_worker_metrics_server(
    metrics: MetricsRegistry,
    *,
    host: str,
    port: int,
) -> ThreadingHTTPServer:
    class WorkerMetricsHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path != "/metrics":
                self.send_response(HTTPStatus.NOT_FOUND)
                self.end_headers()
                return

            body = render_prometheus_metrics(metrics.snapshot()).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("content-type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer((host, port), WorkerMetricsHandler)
    Thread(target=server.serve_forever, daemon=True).start()
    return server
