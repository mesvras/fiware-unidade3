import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

KEYS = {name: rsa.generate_private_key(public_exponent=65537, key_size=2048) for name in ("k1", "k2", "other")}
PUBLISHED = ["k1"]
LOCK = threading.Lock()


def jwk(kid: str) -> dict:
    data = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(KEYS[kid].public_key()))
    return {**data, "kid": kid, "use": "sig", "alg": "RS256"}


class Handler(BaseHTTPRequestHandler):
    def reply(self, status: int, body, content_type: str = "application/json") -> None:
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/health":
            self.reply(200, {"status": "ok"})
        elif self.path == "/jwks.json":
            with LOCK:
                self.reply(200, {"keys": [jwk(k) for k in PUBLISHED]})
        elif self.path == "/public.pem":
            pem = KEYS["k1"].public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
            self.reply(200, pem, "application/x-pem-file")
        else:
            self.reply(404, {"error": "not found"})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        if self.path == "/token":
            key = body.get("key", "k1")
            kid = body.get("kid", key)
            headers = {"kid": kid} if kid else {}
            token = jwt.encode(body.get("claims", {}), KEYS[key], algorithm="RS256", headers=headers)
            if not kid:
                header, payload, signature = token.split(".")
                token = ".".join((jwt.utils.base64url_encode(json.dumps({"alg": "RS256", "typ": "JWT"}).encode()).decode(), payload, signature))
            self.reply(200, {"token": token})
        elif self.path == "/rotate":
            with LOCK:
                if "k2" not in PUBLISHED:
                    PUBLISHED.append("k2")
            self.reply(200, {"kid": "k2"})
        else:
            self.reply(404, {"error": "not found"})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
