import argparse
import asyncio
import logging
import signal
import sys

from . import hotels
from .client import ApiClient
from .config import Config

TARGETS = {"hotels": hotels}
RUNNERS = (hotels.Runner,)

log = logging.getLogger("sim")


async def seed(cfg: Config, targets: list[str]) -> int:
    async with ApiClient(cfg.api_url, cfg.concurrency) as client:
        for name in targets:
            log.info("seed %s", name)
            await TARGETS[name].seed(client, cfg)
        if client.failures:
            log.error("seed terminou com %d falhas", client.failures)
            return 1
    return 0


async def check(cfg: Config, targets: list[str]) -> int:
    async with ApiClient(cfg.api_url, cfg.concurrency) as client:
        results = [await TARGETS[name].check(client, cfg) for name in targets]
    return 0 if all(results) else 1


async def run(cfg: Config) -> int:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    async with ApiClient(cfg.api_url, cfg.concurrency) as client:
        runners = [cls(client, cfg) for cls in RUNNERS]
        for runner in runners:
            await runner.load()
        log.info("run: ciclo a cada %d s", cfg.interval)
        while not stop.is_set():
            for runner in runners:
                try:
                    await runner.tick()
                except Exception:
                    log.exception("run %s: ciclo falhou", runner.name)
            try:
                await asyncio.wait_for(stop.wait(), cfg.interval)
            except TimeoutError:
                pass
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    choices = [*TARGETS, "all"]
    parser = argparse.ArgumentParser(prog="python -m sim")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("seed", help="cria ou atualiza os dados").add_argument("target", choices=choices)
    sub.add_parser("check", help="verifica o aceite pela API").add_argument("target", choices=choices)
    sub.add_parser("run", help="altera os dados de forma contínua")
    args = parser.parse_args()

    cfg = Config.from_env()
    if args.command == "run":
        return asyncio.run(run(cfg))
    targets = list(TARGETS) if args.target == "all" else [args.target]
    return asyncio.run(seed(cfg, targets) if args.command == "seed" else check(cfg, targets))


if __name__ == "__main__":
    sys.exit(main())
