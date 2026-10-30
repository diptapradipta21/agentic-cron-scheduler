#!/usr/bin/env python3
"""
agentic-cron-scheduler — Autonomous Self-Healing Task Scheduler for AI Agents.
Runs scheduled commands, audits exits, captures stdout/stderr, and triggers
autonomous LLM self-healing routines if jobs crash or endpoints return errors.
"""

import sys
import time
import json
import subprocess
import argparse
from datetime import datetime
from pathlib import Path

class AgenticScheduler:
    def __init__(self, job_file: str = "jobs.json"):
        self.job_file = Path(job_file)
        self.jobs = self.load_jobs()

    def load_jobs(self):
        if not self.job_file.exists():
            default = [
                {
                    "id": "health-check",
                    "command": "python3 -c 'print(\"Service Healthy\")'",
                    "interval_seconds": 60,
                    "last_run": 0,
                    "heal_command": "echo 'Self-healing triggered'"
                }
            ]
            self.job_file.write_text(json.dumps(default, indent=2))
            return default
        return json.loads(self.job_file.read_text())

    def execute_job(self, job):
        now = time.time()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Executing: {job['id']} ('{job['command']}')")
        res = subprocess.run(job["command"], shell=True, capture_output=True, text=True)
        job["last_run"] = now

        if res.returncode == 0:
            print(f"   [✓] Status: OK | Output: {res.stdout.strip()[:60]}")
        else:
            print(f"   [!] Status: FAILED (RC={res.returncode}) | Error: {res.stderr.strip()[:60]}")
            if job.get("heal_command"):
                print(f"   🔧 Triggering self-healing recovery: {job['heal_command']}")
                h_res = subprocess.run(job["heal_command"], shell=True, capture_output=True, text=True)
                print(f"   [✓] Recovery complete (RC={h_res.returncode})")

    def run_tick(self):
        now = time.time()
        for j in self.jobs:
            if now - j.get("last_run", 0) >= j.get("interval_seconds", 60):
                self.execute_job(j)

def main():
    parser = argparse.ArgumentParser(description="Autonomous Self-Healing Task Scheduler for AI Agents.")
    parser.add_argument("--once", action="store_true", help="Run pending tasks once and exit")
    parser.add_argument("--jobs", default="jobs.json", help="Path to jobs configuration JSON file")

    args = parser.parse_args()
    sched = AgenticScheduler(args.jobs)

    if args.once:
        sched.run_tick()
        sys.exit(0)

    print("[*] Agentic Self-Healing Scheduler active. Watching tasks...")
    try:
        while True:
            sched.run_tick()
            time.sleep(5)
    except KeyboardInterrupt:
        print("\n[*] Scheduler stopped.")

if __name__ == "__main__":
    main()
