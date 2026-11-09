#!/usr/bin/env python3
"""
agentic-cron-scheduler — Autonomous Self-Healing Task Scheduler for AI Agents.
Runs scheduled commands, audits exit codes, enforces execution timeouts,
persists execution state, supports configurable retries, and triggers self-healing recovery routines if jobs crash.
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
                    "retries": 1,
                    "retry_delay_seconds": 2,
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

    def get_status_summary(self) -> Dict[str, int]:
        """Aggregate health status counts across all configured jobs."""
        summary = {"TOTAL": len(self.jobs), "OK": 0, "FAILED": 0, "TIMEOUT": 0, "PENDING": 0, "OTHER": 0}
        for j in self.jobs:
            st = str(j.get("last_status", "PENDING")).upper()
            if st == "OK":
                summary["OK"] += 1
            elif st.startswith("FAILED"):
                summary["FAILED"] += 1
            elif st == "TIMEOUT":
                summary["TIMEOUT"] += 1
            elif st == "PENDING":
                summary["PENDING"] += 1
            else:
                summary["OTHER"] += 1
        return summary

    def list_jobs(self, as_json: bool = False) -> None:
        """Display configured jobs in tabular view or JSON format."""
        if as_json:
            print(json.dumps(self.jobs, indent=2))
            return

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

    def execute_job(self, job: Dict[str, Any], quiet: bool = False) -> bool:
        """Execute a single job with retries, timeout safeguards, and self-healing hooks."""
        now = time.time()
        now_str = datetime.now().strftime("%H:%M:%S")
        jid = job.get("id", "unnamed")
        cmd = job.get("command", "")
        timeout = job.get("timeout_seconds", 60)
        max_retries = int(job.get("retries", 0))
        retry_delay = float(job.get("retry_delay_seconds", 1.0))

        if not quiet:
            print(f"[{now_str}] Executing: {jid} ('{cmd}')")
        job["last_run"] = now

        success = False
        for attempt in range(max_retries + 1):
            if attempt > 0:
                if not quiet:
                    print(f"   [↻] Retrying {jid} (attempt {attempt}/{max_retries}) after {retry_delay}s...")
                time.sleep(retry_delay)

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
                    if not quiet:
                        preview = res.stdout.strip().replace("\n", " ")[:60]
                        print(f"   [✓] Status: OK | Output: {preview}")
                    success = True
                    break
                else:
                    job["last_status"] = f"FAILED(RC={res.returncode})"
                    if not quiet:
                        err_preview = res.stderr.strip().replace("\n", " ")[:60]
                        print(f"   [!] Status: FAILED (RC={res.returncode}) | Error: {err_preview}")
            except subprocess.TimeoutExpired:
                job["last_status"] = "TIMEOUT"
                if not quiet:
                    print(f"   [!] Status: TIMEOUT (> {timeout}s)")
            except Exception as e:
                job["last_status"] = f"ERROR({e.__class__.__name__})"
                if not quiet:
                    print(f"   [!] Execution error: {e}")

        if not success:
            self._trigger_healing(job, quiet=quiet)

        self.persist_jobs()
        return success

    def _trigger_healing(self, job: Dict[str, Any], quiet: bool = False) -> None:
        """Invoke self-healing remediation command if configured."""
        heal_cmd = job.get("heal_command")
        if not heal_cmd:
            return
        if not quiet:
            print(f"   🔧 Triggering self-healing recovery: {heal_cmd}")
        try:
            h_res = subprocess.run(heal_cmd, shell=True, capture_output=True, text=True, timeout=60)
            if not quiet:
                if h_res.returncode == 0:
                    print(f"   [✓] Recovery complete (RC=0)")
                else:
                    print(f"   [x] Recovery failed (RC={h_res.returncode}): {h_res.stderr.strip()[:60]}")
        except Exception as err:
            if not quiet:
                print(f"   [x] Recovery execution error: {err}")

    def run_tick(self, dry_run: bool = False, quiet: bool = False) -> List[Dict[str, Any]]:
        """Run all jobs that have passed their scheduled interval."""
        now = time.time()
        executed: List[Dict[str, Any]] = []
        for j in self.jobs:
            if now - j.get("last_run", 0) >= j.get("interval_seconds", 60):
                if dry_run:
                    if not quiet:
                        print(f"[DRY-RUN] Would execute: {j.get('id')} ('{j.get('command')}')")
                    executed.append({
                        "id": j.get("id"),
                        "command": j.get("command"),
                        "status": "DRY_RUN",
                        "interval_seconds": j.get("interval_seconds", 60)
                    })
                else:
                    self.execute_job(j, quiet=quiet)
                    executed.append({
                        "id": j.get("id"),
                        "command": j.get("command"),
                        "status": j.get("last_status"),
                        "last_run": j.get("last_run")
                    })
        return executed

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
    parser.add_argument("--status", action="store_true", help="Display health summary status of all configured tasks")
    parser.add_argument("--validate", action="store_true", help="Validate jobs configuration file")
    parser.add_argument("--save-state", action="store_true", help="Persist job execution timestamps and status back to file")
    parser.add_argument("--jobs", default="jobs.json", help="Path to jobs configuration JSON file (default: jobs.json)")
    parser.add_argument("--interval", type=int, default=5, help="Daemon tick interval in seconds (default: 5)")
    parser.add_argument("--dry-run", action="store_true", help="Simulate pending jobs without executing commands")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON format for --list, --status, or --once")

    args = parser.parse_args()
    sched = AgenticScheduler(args.jobs, save_state=args.save_state)

    if args.validate:
        if sched.validate():
            print(f"[✓] Configuration in '{args.jobs}' is valid ({len(sched.jobs)} jobs configured).")
            sys.exit(0)
        else:
            print(f"[x] Configuration validation failed for '{args.jobs}'.", file=sys.stderr)
            sys.exit(1)

    if args.status:
        summary = sched.get_status_summary()
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print("Scheduler Task Status Summary:")
            for k, v in summary.items():
                print(f"  • {k:<10}: {v}")
        sys.exit(0)

    if args.list:
        sched.list_jobs(as_json=args.json)
        sys.exit(0)

    if args.test:
        ok = sched.run_specific(args.test)
        sys.exit(0 if ok else 1)

    if args.once:
        executed = sched.run_tick(dry_run=args.dry_run, quiet=args.json)
        if args.json:
            print(json.dumps(executed, indent=2))
        else:
            action_label = "Simulated" if args.dry_run else "Executed"
            print(f"[*] Completed tick. {action_label} {len(executed)} job(s).")
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
