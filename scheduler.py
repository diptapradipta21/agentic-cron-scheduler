#!/usr/bin/env python3
"""
agentic-cron-scheduler — Autonomous Self-Healing Task Scheduler for AI Agents.
Runs scheduled commands, audits exit codes, enforces execution timeouts,
persists execution state, and triggers self-healing recovery routines if jobs crash.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class AgenticScheduler:
    def __init__(self, job_file: str = "jobs.json", save_state: bool = False):
        self.job_path = Path(job_file)
        self.save_state = save_state
        self.jobs: List[Dict[str, Any]] = self.load_jobs()

    def load_jobs(self) -> List[Dict[str, Any]]:
        """Load jobs from file or create a default template if not found."""
        if not self.job_path.exists():
            default = [
                {
                    "id": "health-check",
                    "command": "python3 -c 'print(\"Service Healthy\")'",
                    "interval_seconds": 60,
                    "timeout_seconds": 30,
                    "last_run": 0,
                    "last_status": "PENDING",
                    "heal_command": "echo 'Self-healing triggered'"
                }
            ]
            self.job_path.write_text(json.dumps(default, indent=2))
            return default

        try:
            data = json.loads(self.job_path.read_text())
            if not isinstance(data, list):
                raise ValueError("Job file root must be a JSON array.")
            return data
        except Exception as e:
            print(f"[!] Error reading {self.job_path}: {e}", file=sys.stderr)
            sys.exit(1)

    def persist_jobs(self) -> None:
        """Persist updated last_run and status to disk if save_state is enabled."""
        if not self.save_state:
            return
        try:
            self.job_path.write_text(json.dumps(self.jobs, indent=2))
        except OSError as e:
            print(f"[!] Warning: Could not save job state: {e}", file=sys.stderr)

    def validate(self) -> bool:
        """Validate job schema."""
        required = ["id", "command"]
        for idx, job in enumerate(self.jobs):
            if not isinstance(job, dict):
                print(f"[x] Job #{idx} is not an object", file=sys.stderr)
                return False
            for req in required:
                if req not in job:
                    print(f"[x] Job #{idx} missing required key '{req}'", file=sys.stderr)
                    return False
        return True

    def list_jobs(self) -> None:
        """Display configured jobs in tabular view."""
        print(f"{'ID':<20} {'INTERVAL':<10} {'TIMEOUT':<10} {'STATUS':<12} {'LAST RUN':<20} {'COMMAND'}")
        print("-" * 90)
        for j in self.jobs:
            jid = j.get("id", "unnamed")
            interval = f"{j.get('interval_seconds', 60)}s"
            timeout = f"{j.get('timeout_seconds', 60)}s"
            status = j.get("last_status", "PENDING")
            last_run_ts = j.get("last_run", 0)
            last_run_str = datetime.fromtimestamp(last_run_ts).strftime("%Y-%m-%d %H:%M") if last_run_ts > 0 else "Never"
            cmd = j.get("command", "")
            if len(cmd) > 30:
                cmd = cmd[:27] + "..."
            print(f"{jid:<20} {interval:<10} {timeout:<10} {status:<12} {last_run_str:<20} {cmd}")

    def execute_job(self, job: Dict[str, Any]) -> bool:
        """Execute a single job with timeout safeguards and self-healing hooks."""
        now = time.time()
        now_str = datetime.now().strftime("%H:%M:%S")
        jid = job.get("id", "unnamed")
        cmd = job.get("command", "")
        timeout = job.get("timeout_seconds", 60)

        print(f"[{now_str}] Executing: {jid} ('{cmd}')")
        job["last_run"] = now

        success = False
        try:
            res = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            if res.returncode == 0:
                job["last_status"] = "OK"
                preview = res.stdout.strip().replace("\n", " ")[:60]
                print(f"   [✓] Status: OK | Output: {preview}")
                success = True
            else:
                job["last_status"] = f"FAILED(RC={res.returncode})"
                err_preview = res.stderr.strip().replace("\n", " ")[:60]
                print(f"   [!] Status: FAILED (RC={res.returncode}) | Error: {err_preview}")
                self._trigger_healing(job)
        except subprocess.TimeoutExpired:
            job["last_status"] = "TIMEOUT"
            print(f"   [!] Status: TIMEOUT (> {timeout}s)")
            self._trigger_healing(job)
        except Exception as e:
            job["last_status"] = f"ERROR({e.__class__.__name__})"
            print(f"   [!] Execution error: {e}")
            self._trigger_healing(job)

        self.persist_jobs()
        return success

    def _trigger_healing(self, job: Dict[str, Any]) -> None:
        """Invoke self-healing remediation command if configured."""
        heal_cmd = job.get("heal_command")
        if not heal_cmd:
            return
        print(f"   🔧 Triggering self-healing recovery: {heal_cmd}")
        try:
            h_res = subprocess.run(heal_cmd, shell=True, capture_output=True, text=True, timeout=60)
            if h_res.returncode == 0:
                print(f"   [✓] Recovery complete (RC=0)")
            else:
                print(f"   [x] Recovery failed (RC={h_res.returncode}): {h_res.stderr.strip()[:60]}")
        except Exception as err:
            print(f"   [x] Recovery execution error: {err}")

    def run_tick(self) -> int:
        """Run all jobs that have passed their scheduled interval."""
        now = time.time()
        executed_count = 0
        for j in self.jobs:
            if now - j.get("last_run", 0) >= j.get("interval_seconds", 60):
                self.execute_job(j)
                executed_count += 1
        return executed_count

    def run_specific(self, job_id: str) -> bool:
        """Run a single job by id immediately."""
        target = next((j for j in self.jobs if j.get("id") == job_id), None)
        if not target:
            print(f"[!] Job with ID '{job_id}' not found.", file=sys.stderr)
            return False
        return self.execute_job(target)


def main() -> None:
    parser = argparse.ArgumentParser(description="Autonomous Self-Healing Task Scheduler for AI Agents.")
    parser.add_argument("--once", action="store_true", help="Run pending tasks once and exit")
    parser.add_argument("--list", action="store_true", help="List all configured jobs and exit")
    parser.add_argument("--test", metavar="JOB_ID", help="Run a specific job immediately by ID")
    parser.add_argument("--validate", action="store_true", help="Validate jobs configuration file")
    parser.add_argument("--save-state", action="store_true", help="Persist job execution timestamps and status back to file")
    parser.add_argument("--jobs", default="jobs.json", help="Path to jobs configuration JSON file (default: jobs.json)")
    parser.add_argument("--interval", type=int, default=5, help="Daemon tick interval in seconds (default: 5)")

    args = parser.parse_args()
    sched = AgenticScheduler(args.jobs, save_state=args.save_state)

    if args.validate:
        if sched.validate():
            print(f"[✓] Configuration in '{args.jobs}' is valid ({len(sched.jobs)} jobs configured).")
            sys.exit(0)
        else:
            print(f"[x] Configuration validation failed for '{args.jobs}'.", file=sys.stderr)
            sys.exit(1)

    if args.list:
        sched.list_jobs()
        sys.exit(0)

    if args.test:
        ok = sched.run_specific(args.test)
        sys.exit(0 if ok else 1)

    if args.once:
        count = sched.run_tick()
        print(f"[*] Completed tick. Executed {count} job(s).")
        sys.exit(0)

    print(f"[*] Agentic Self-Healing Scheduler active ({len(sched.jobs)} jobs loaded). Watching tasks...")
    try:
        while True:
            sched.run_tick()
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n[*] Scheduler stopped.")


if __name__ == "__main__":
    main()
