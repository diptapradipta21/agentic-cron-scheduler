import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Ensure repo root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scheduler import AgenticScheduler


class TestAgenticScheduler(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.jobs_file = Path(self.test_dir) / "test_jobs.json"

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_default_jobs_generation_when_missing(self):
        sched = AgenticScheduler(job_file=str(self.jobs_file))
        self.assertTrue(self.jobs_file.exists())
        self.assertEqual(len(sched.jobs), 1)
        self.assertEqual(sched.jobs[0]["id"], "health-check")

    def test_validation_success_and_failure(self):
        valid_jobs = [
            {"id": "j1", "command": "echo 1"}
        ]
        self.jobs_file.write_text(json.dumps(valid_jobs))
        sched = AgenticScheduler(job_file=str(self.jobs_file))
        self.assertTrue(sched.validate())

        invalid_jobs = [
            {"id": "j2"} # Missing 'command'
        ]
        self.jobs_file.write_text(json.dumps(invalid_jobs))
        sched = AgenticScheduler(job_file=str(self.jobs_file))
        self.assertFalse(sched.validate())

    def test_execute_job_success(self):
        job = {
            "id": "echo-job",
            "command": "echo 'Hello Scheduler'",
            "interval_seconds": 10,
            "timeout_seconds": 5,
            "last_run": 0
        }
        sched = AgenticScheduler(job_file=str(self.jobs_file))
        success = sched.execute_job(job, quiet=True)
        self.assertTrue(success)
        self.assertEqual(job["last_status"], "OK")

    def test_execute_job_failure_triggers_healing(self):
        heal_target = Path(self.test_dir) / "healed.txt"
        job = {
            "id": "failing-job",
            "command": "exit 1",
            "interval_seconds": 10,
            "timeout_seconds": 5,
            "last_run": 0,
            "heal_command": f"echo 'remediated' > {heal_target}"
        }
        sched = AgenticScheduler(job_file=str(self.jobs_file))
        success = sched.execute_job(job, quiet=True)
        self.assertFalse(success)
        self.assertTrue(job["last_status"].startswith("FAILED"))
        self.assertTrue(heal_target.exists())
        self.assertIn("remediated", heal_target.read_text())

    def test_execute_job_retries(self):
        # Flaky job that succeeds on second try
        counter_file = Path(self.test_dir) / "flaky_counter.txt"
        counter_file.write_text("0")
        cmd = f'python3 -c "from pathlib import Path; p = Path(\'{counter_file}\'); n = int(p.read_text()); p.write_text(str(n+1)); exit(0 if n >= 1 else 1)"'
        job = {
            "id": "flaky-job",
            "command": cmd,
            "interval_seconds": 10,
            "timeout_seconds": 5,
            "retries": 2,
            "retry_delay_seconds": 0.05,
            "last_run": 0
        }
        sched = AgenticScheduler(job_file=str(self.jobs_file))
        success = sched.execute_job(job, quiet=True)
        self.assertTrue(success)
        self.assertEqual(job["last_status"], "OK")
        self.assertEqual(int(counter_file.read_text()), 2)

    def test_status_summary(self):
        jobs = [
            {"id": "j1", "command": "echo 1", "last_status": "OK"},
            {"id": "j2", "command": "exit 1", "last_status": "FAILED(RC=1)"},
            {"id": "j3", "command": "sleep 10", "last_status": "TIMEOUT"},
            {"id": "j4", "command": "echo pending", "last_status": "PENDING"}
        ]
        self.jobs_file.write_text(json.dumps(jobs))
        sched = AgenticScheduler(job_file=str(self.jobs_file))
        summary = sched.get_status_summary()
        self.assertEqual(summary["TOTAL"], 4)
        self.assertEqual(summary["OK"], 1)
        self.assertEqual(summary["FAILED"], 1)
        self.assertEqual(summary["TIMEOUT"], 1)
        self.assertEqual(summary["PENDING"], 1)

    def test_run_tick_dry_run(self):
        jobs = [
            {
                "id": "dry-job",
                "command": "touch /tmp/should_not_exist_ever.test",
                "interval_seconds": 10,
                "timeout_seconds": 5,
                "last_run": 0
            }
        ]
        self.jobs_file.write_text(json.dumps(jobs))
        sched = AgenticScheduler(job_file=str(self.jobs_file))
        executed = sched.run_tick(dry_run=True, quiet=True)
        self.assertEqual(len(executed), 1)
        self.assertEqual(executed[0]["status"], "DRY_RUN")


if __name__ == "__main__":
    unittest.main()
