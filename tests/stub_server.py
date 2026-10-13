"""Tiny local server that speaks the System One 'choice' shape, for testing the
custom-URL path without a real key. Picks a category from keywords in the filename,
else from the extension. Run: py tests/stub_server.py [port]"""

import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

EXT = {".pdf": "Documents", ".docx": "Documents", ".txt": "Documents", ".png": "Images", ".jpg": "Images",
       ".zip": "Archives", ".exe": "Installers", ".xlsx": "Spreadsheets", ".pptx": "Presentations",
       ".mp4": "Videos", ".m4a": "Audio"}
KEYWORDS = {"screenshot": "Screenshots"}
VARY = False  # screenshots only: spread confidence over 0.62-0.97 instead of a flat 0.95


class Handler(BaseHTTPRequestHandler):
    last_auth = None

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Handler.last_auth = self.headers.get("Authorization")
        crit = body["questions"]["folder"]["criteria"]
        st = body["state"]
        name = st.get("name", "").lower()
        want = next((v for k, v in KEYWORDS.items() if k in name), EXT.get(st.get("ext", ""), "__stay__"))
        choice = want if want in crit else "__stay__"
        conf = 0.62 + (sum(map(ord, name)) % 36) / 100 if VARY else 0.95
        rest = (1 - conf) / max(1, len(crit) - 1)
        probs = {k: rest for k in crit}
        probs[choice] = conf
        out = {"answers": {"folder": {"choice": choice, "confidence": conf, "probabilities": probs}},
               "usage": {"input_tokens": 500, "output_tokens": 5}}
        data = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


def serve(port=0):
    srv = HTTPServer(("127.0.0.1", port), Handler)
    return srv


if __name__ == "__main__":
    s = serve(int(sys.argv[1]) if len(sys.argv) > 1 else 8080)
    print("listening", s.server_address)
    s.serve_forever()
