import glob
import json
import os

PKG = os.environ.get("PKG_DIR", "/srv/pkg")


def load_examples() -> list[dict]:
    return [json.load(open(f)) for f in sorted(glob.glob(os.path.join(PKG, "examples", "*.jsonld")))]


def load_invalid() -> list[tuple[str, dict, str]]:
    expected = json.load(open(os.path.join(PKG, "invalid", "_esperado.json")))
    return [(name, json.load(open(os.path.join(PKG, "invalid", name + ".jsonld"))), v["deve_falhar_com"]) for name, v in expected.items()]


def without_context(e: dict) -> dict:
    return {k: v for k, v in e.items() if k != "@context"}
