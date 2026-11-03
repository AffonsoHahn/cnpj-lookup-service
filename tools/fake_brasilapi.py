"""Local stand-in for BrasilAPI, for demos and tests when the real API is rate limiting you.

Returns FAKE sample data. Never use it as a real data source.

Usage:
    python tools/fake_brasilapi.py                 # runs on http://127.0.0.1:9000
    python tools/fake_brasilapi.py --fail-first 2  # first 2 calls per path return 429, then succeed
                                                   # (shows the retry with backoff in action)

Special case: CNPJ 11222333000181 always returns 404 (to demo the "not found" path).
"""
import argparse
import json
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, HTTPServer

CALLS = defaultdict(int)


def make_handler(fail_first: int):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, body: dict):
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path = self.path.split("?")[0]
            CALLS[path] += 1

            if CALLS[path] <= fail_first:
                return self._send(429, {"message": "Too Many Requests (simulated)"})

            parts = path.strip("/").split("/")  # e.g. ['api', 'cnpj', 'v1', '00000000000191']
            if len(parts) == 4 and parts[1] == "cnpj":
                cnpj = parts[3]
                if cnpj == "11222333000181":
                    return self._send(404, {"message": "CNPJ not found (simulated)"})
                return self._send(200, {
                    "cnpj": cnpj,
                    "razao_social": "EMPRESA DE EXEMPLO LTDA (FAKE)",
                    "nome_fantasia": "EXEMPLO",
                    "uf": "RS",
                    "municipio": "SAO LEOPOLDO",
                    "descricao_situacao_cadastral": "ATIVA",
                })
            if len(parts) == 4 and parts[1] == "cep":
                return self._send(200, {
                    "cep": parts[3],
                    "state": "SP",
                    "city": "Sao Paulo",
                    "neighborhood": "Se",
                    "street": "Praca da Se (FAKE)",
                })
            self._send(404, {"message": "unknown route"})

        def log_message(self, fmt, *args):
            print("[fake-brasilapi]", fmt % args)

    return Handler


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--fail-first", type=int, default=0, help="return 429 for the first N calls of each path")
    args = parser.parse_args()
    print(f"Fake BrasilAPI on http://127.0.0.1:{args.port}/api  (fail-first={args.fail_first})")
    HTTPServer(("127.0.0.1", args.port), make_handler(args.fail_first)).serve_forever()