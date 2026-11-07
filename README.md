# ⏱️ Agentic Cron Scheduler

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Self Healing](https://img.shields.io/badge/Architecture-Self%20Healing-brightgreen.svg)](#)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Zero Dependencies](https://img.shields.io/badge/dependencies-0-brightgreen.svg)](#)

> **Autonomous self-healing task scheduler for AI agent swarms and daemon pipelines. Monitors task exit codes, enforces execution timeouts, persists state, and automatically executes remediation scripts when services fail.**

---

## ⚡ Core Features

- 🔄 **Self-Healing Triggers:** Executes an automated `heal_command` (e.g. agent LLM fix, worker restart, webhook alert) whenever a job exits with a non-zero status code or times out.
- ⏱️ **Per-Job Execution Timeouts:** Prevents runaway background processes from locking down scheduled agent pipelines.
- 💾 **State Persistence:** Optional `--save-state` tracks real-time execution timestamps and success/failure status in `jobs.json`.
- 🔍 **Targeted Execution & Validation:** `--list` for tabular overview, `--test <id>` for immediate manual trigger, and `--validate` for schema safety.
- 🧪 **Dry-Run & Agent JSON Output:** `--dry-run` to preview pending schedules without execution; `--json` for machine-readable output by agent tool callers.
- 🪶 **Zero Dependencies:** Pure Python standard library implementation.

---

## 🚀 Quick Start

### 1. View Configured Jobs
```bash
# Tabular view
python3 scheduler.py --list

# Machine-readable JSON output for agent tools
python3 scheduler.py --list --json
```

### 2. Validate Configuration File
```bash
python3 scheduler.py --validate
```

### 3. Run a Single Tick or Specific Job
```bash
# Preview pending jobs without executing commands
python3 scheduler.py --once --dry-run

# Execute only pending scheduled tasks once and output JSON
python3 scheduler.py --once --json

# Test a specific job on demand
python3 scheduler.py --test health-check
```

### 4. Run Continuously with State Persistence
```bash
python3 scheduler.py --save-state --interval 5
```

---

## ⚙️ Configuration (`jobs.json`)

```json
[
  {
    "id": "health-check",
    "command": "curl -sf http://localhost:8080/health || exit 1",
    "interval_seconds": 60,
    "timeout_seconds": 15,
    "last_run": 0,
    "last_status": "PENDING",
    "heal_command": "python3 heal_worker.py --target health-check"
  },
  {
    "id": "vault-sync",
    "command": "python3 -m vault_rag --sync",
    "interval_seconds": 3600,
    "timeout_seconds": 120,
    "last_run": 0,
    "last_status": "PENDING",
    "heal_command": "python3 alert_dev.py --job vault-sync"
  }
]
```

---

## 🧪 Testing

```bash
python3 -m unittest discover tests
```

---

## 📄 License
MIT License - Copyright (c) 2026 Fajar Indra Pradipta Gajah.
