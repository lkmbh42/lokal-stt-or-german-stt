"""Concurrent-user load test against a running Variant B stack.

    python apps/server/scripts/load_test.py --base-url http://localhost:8480 \
        --admin-password <pw> --users 10 --jobs-per-user 2 \
        --audio engine/tests/fixtures/german_sample.wav

Creates ``loadtestNN`` users via the admin API, then each user (own thread):
logs in, submits ``--jobs-per-user`` uploads, and polls their job list until
everything finished — recording API latency for every request. Reports
measured (not estimated) numbers: submission latency, queue wait, processing
time, end-to-end time, queue throughput and API latency percentiles.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import httpx


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(int(len(ordered) * pct / 100), len(ordered) - 1)
    return ordered[index]


class Recorder:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.api_latencies: list[float] = []
        self.submit_latencies: list[float] = []
        self.login_latencies: list[float] = []
        self.jobs: list[dict] = []
        self.errors: list[str] = []

    def api(self, seconds: float) -> None:
        with self._lock:
            self.api_latencies.append(seconds)

    def error(self, message: str) -> None:
        with self._lock:
            self.errors.append(message)


def parse_ts(value: str) -> float:
    return datetime.fromisoformat(value).timestamp()


def run_user(
    index: int, base_url: str, password: str, audio: Path, jobs_per_user: int, rec: Recorder
) -> None:
    username = f"loadtest{index:02d}"
    client = httpx.Client(base_url=base_url, timeout=60)
    try:
        started = time.perf_counter()
        response = client.post(
            "/api/auth/login", json={"username": username, "password": password}
        )
        rec.login_latencies.append(time.perf_counter() - started)
        response.raise_for_status()
        headers = {"Authorization": f"Bearer {response.json()['access_token']}"}

        job_ids: list[str] = []
        audio_bytes = audio.read_bytes()
        for j in range(jobs_per_user):
            started = time.perf_counter()
            response = client.post(
                "/api/jobs",
                headers=headers,
                files={"file": (f"last-{index:02d}-{j}.wav", audio_bytes, "audio/wav")},
            )
            rec.submit_latencies.append(time.perf_counter() - started)
            if response.status_code != 201:
                rec.error(f"{username} upload {j}: HTTP {response.status_code}")
                continue
            job_ids.append(response.json()["id"])

        pending = set(job_ids)
        deadline = time.monotonic() + 1800
        while pending and time.monotonic() < deadline:
            time.sleep(2.0)
            started = time.perf_counter()
            response = client.get("/api/jobs", headers=headers)
            rec.api(time.perf_counter() - started)
            if response.status_code != 200:
                rec.error(f"{username} list: HTTP {response.status_code}")
                continue
            for job in response.json():
                if job["id"] in pending and job["status"] in ("done", "error", "canceled"):
                    pending.discard(job["id"])
                    with rec._lock:
                        rec.jobs.append({"username": username, **job})
                    if job["status"] != "done":
                        rec.error(f"{username} job {job['id']}: {job['status']} {job['error']}")
        for job_id in pending:
            rec.error(f"{username} job {job_id}: timeout")
    finally:
        client.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--base-url", default="http://localhost:8080")
    parser.add_argument("--admin-username", default="admin")
    parser.add_argument("--admin-password", required=True)
    parser.add_argument("--users", type=int, default=10)
    parser.add_argument("--jobs-per-user", type=int, default=2)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args()

    user_password = "lasttest-passwort-123"
    admin = httpx.Client(base_url=args.base_url, timeout=30)
    response = admin.post(
        "/api/auth/login",
        json={"username": args.admin_username, "password": args.admin_password},
    )
    response.raise_for_status()
    admin_headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    for i in range(1, args.users + 1):
        response = admin.post(
            "/api/admin/users",
            headers=admin_headers,
            json={"username": f"loadtest{i:02d}", "password": user_password},
        )
        if response.status_code not in (201, 409):  # 409 = exists from a prior run
            print(f"user creation failed: {response.status_code} {response.text}")
            return 1

    rec = Recorder()
    wall_start = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.users) as pool:
        futures = [
            pool.submit(
                run_user, i, args.base_url, user_password, args.audio,
                args.jobs_per_user, rec,
            )
            for i in range(1, args.users + 1)
        ]
        for future in futures:
            future.result()
    wall_seconds = time.monotonic() - wall_start

    done_jobs = [j for j in rec.jobs if j["status"] == "done"]
    waits = []
    e2e = []
    audio_seconds = 0.0
    for job in done_jobs:
        audio_seconds += job["duration"] or 0.0
        created, finished = parse_ts(job["created_at"]), parse_ts(job["finished_at"])
        e2e.append(finished - created)
    e2e.sort()
    del waits

    summary = {
        "users": args.users,
        "jobs_submitted": args.users * args.jobs_per_user,
        "jobs_done": len(done_jobs),
        "errors": rec.errors,
        "wall_seconds": round(wall_seconds, 1),
        "audio_seconds_processed": round(audio_seconds, 1),
        "throughput_x_realtime": round(audio_seconds / wall_seconds, 2) if wall_seconds else None,
        "login_p50_ms": round(percentile(rec.login_latencies, 50) * 1000),
        "login_p95_ms": round(percentile(rec.login_latencies, 95) * 1000),
        "submit_p50_ms": round(percentile(rec.submit_latencies, 50) * 1000),
        "submit_p95_ms": round(percentile(rec.submit_latencies, 95) * 1000),
        "list_api_p50_ms": round(percentile(rec.api_latencies, 50) * 1000),
        "list_api_p95_ms": round(percentile(rec.api_latencies, 95) * 1000),
        "list_api_max_ms": round(max(rec.api_latencies) * 1000) if rec.api_latencies else 0,
        "e2e_min_s": round(e2e[0], 1) if e2e else None,
        "e2e_median_s": round(statistics.median(e2e), 1) if e2e else None,
        "e2e_max_s": round(e2e[-1], 1) if e2e else None,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if args.json_out:
        args.json_out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return 0 if len(done_jobs) == args.users * args.jobs_per_user and not rec.errors else 1


if __name__ == "__main__":
    sys.exit(main())
