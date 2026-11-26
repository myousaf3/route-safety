"""Lightweight concurrent load smoke test for the Spotter API.

Usage:
    python scripts/load_test.py --base-url http://127.0.0.1:8000 --users 20 --requests 50
"""

from __future__ import annotations

import argparse
import json
import random
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor


ROUTES = [
    ("Chicago, IL", "Denver, CO"),
    ("Seattle, WA", "Salt Lake City, UT"),
    ("Dallas, TX", "Atlanta, GA"),
]


def worker(base_url: str, results: list[dict], lock: threading.Lock) -> None:
    origin, destination = random.choice(ROUTES)
    payload = {
        "origin": origin,
        "destination": destination,
        "departure": time.strftime("%Y-%m-%dT%H:00:00Z", time.gmtime(time.time() + 3600)),
        "load_weight_lb": random.choice([20000, 42000, 80000]),
        "spacing_miles": random.choice([10, 25, 50]),
    }
    started = time.perf_counter()
    try:
        req = urllib.request.Request(
            f"{base_url}/api/v1/analyses/",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read()
            elapsed = time.perf_counter() - started
            with lock:
                results.append({"status": resp.status, "elapsed": elapsed, "bytes": len(body)})
    except Exception as exc:  # pragma: no cover - reporting path
        elapsed = time.perf_counter() - started
        with lock:
            results.append({"status": 0, "elapsed": elapsed, "error": str(exc)})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--users", type=int, default=10)
    parser.add_argument("--requests", type=int, default=20)
    args = parser.parse_args()

    results: list[dict] = []
    lock = threading.Lock()
    started = time.perf_counter()

    with ThreadPoolExecutor(max_workers=args.users) as pool:
        futures = [pool.submit(worker, args.base_url, results, lock) for _ in range(args.requests)]
        for future in futures:
            future.result()

    total = time.perf_counter() - started
    statuses = {}
    for r in results:
        statuses[r["status"]] = statuses.get(r["status"], 0) + 1
    latencies = sorted(r["elapsed"] for r in results)
    print(f"requests={len(results)} total_time={total:.2f}s rps={len(results)/total:.2f}")
    print(f"statuses={statuses}")
    print(f"latency p50={latencies[len(latencies)//2]:.2f}s p95={latencies[int(0.95*(len(latencies)-1))]:.2f}s max={latencies[-1]:.2f}s")


if __name__ == "__main__":
    main()
