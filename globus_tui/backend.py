"""Data access. GlobusBackend talks to the Transfer (and Flows) APIs via the
Globus SDK; DemoBackend fakes a plausible account so the UI can be tried
without logging in (``globus-tui --demo``)."""
from __future__ import annotations

import json
import os
import random
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

TASK_STATUSES = ("ACTIVE", "INACTIVE", "FAILED", "SUCCEEDED")
TASK_TYPES = ("TRANSFER", "DELETE")

# Globus' own tutorial/example native-app client. Fine for personal use;
# register your own at https://app.globus.org/settings/developers and set
# GLOBUS_TUI_CLIENT_ID if you prefer a client that is yours.
DEFAULT_CLIENT_ID = "61338d24-54d5-408f-a10d-66c06b59f6d2"
APP_NAME = "globus-tui"


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(Path.home(), ".config")
    return Path(base) / "globus-tui" / "config.json"


def load_config() -> dict:
    p = config_path()
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return {}
    return {}


# --------------------------------------------------------------------------
# Live backend
# --------------------------------------------------------------------------
class GlobusBackend:
    name = "globus"

    def __init__(self, client_id: Optional[str] = None, flows: bool = True):
        import globus_sdk

        cfg = load_config()
        self.client_id = (
            client_id
            or os.environ.get("GLOBUS_TUI_CLIENT_ID")
            or cfg.get("client_id")
            or DEFAULT_CLIENT_ID
        )
        app_config = globus_sdk.GlobusAppConfig(request_refresh_tokens=True)
        self.app = globus_sdk.UserApp(APP_NAME, client_id=self.client_id, config=app_config)
        # construct every client before login so one consent covers all scopes
        self.tc = globus_sdk.TransferClient(app=self.app)
        self.ac = globus_sdk.AuthClient(app=self.app)
        self.fc = globus_sdk.FlowsClient(app=self.app) if flows else None
        self._identity: Optional[str] = None

    # auth -----------------------------------------------------------------
    def login_required(self) -> bool:
        return self.app.login_required()

    def login(self, force: bool = False) -> None:
        self.app.login(force=force)

    def logout(self) -> None:
        self.app.logout()

    def identity(self) -> str:
        if self._identity is None:
            try:
                me = self.ac.userinfo()
                self._identity = f"{me.get('name', '')} ({me.get('email') or me.get('preferred_username', '')})".strip()
            except Exception:
                self._identity = "signed in"
        return self._identity

    # tasks ----------------------------------------------------------------
    @staticmethod
    def _filter(types, statuses, since: Optional[datetime]) -> str:
        parts = []
        if types:
            parts.append("type:" + ",".join(types))
        if statuses:
            parts.append("status:" + ",".join(statuses))
        if since is not None:
            parts.append("request_time:" + _iso(since) + ",")
        return "/".join(parts)

    def list_tasks(self, types=TASK_TYPES, statuses=TASK_STATUSES,
                   since: Optional[datetime] = None, limit: int = 100) -> list[dict]:
        if not types or not statuses:
            return []
        resp = self.tc.task_list(
            limit=limit,
            filter=self._filter(types, statuses, since),
            orderby="request_time DESC",
        )
        return [dict(t) for t in resp]

    def count_tasks(self, statuses, since: Optional[datetime] = None) -> int:
        resp = self.tc.task_list(limit=1, filter=self._filter(TASK_TYPES, statuses, since))
        return int(resp.get("total", 0))

    def get_task(self, task_id: str) -> dict:
        return dict(self.tc.get_task(task_id))

    def events(self, task_id: str, limit: int = 200) -> list[dict]:
        try:
            return [dict(e) for e in self.tc.task_event_list(task_id, limit=limit)]
        except Exception as exc:  # history deleted after 30 days, etc.
            return [{"code": "ERROR", "description": "could not load events",
                     "details": str(exc), "is_error": True, "time": ""}]

    def cancel(self, task_id: str) -> str:
        r = self.tc.cancel_task(task_id)
        return f"{r.get('code')}: {r.get('message')}"

    def set_label(self, task_id: str, label: str) -> None:
        self.tc.update_task(task_id, {"DATA_TYPE": "task", "label": label})

    # flows ----------------------------------------------------------------
    def flow_runs(self, since: Optional[datetime] = None, limit: int = 10) -> Optional[list[dict]]:
        if self.fc is None:
            return None
        try:
            resp = self.fc.list_runs(query_params={"orderby": "start_time DESC", "per_page": limit})
            runs = []
            for r in resp:
                if since is not None:
                    st = r.get("start_time")
                    if st and datetime.fromisoformat(st.replace("Z", "+00:00")) < since:
                        continue
                runs.append(dict(r))
                if len(runs) >= limit:
                    break
            return runs
        except Exception:
            return None


# --------------------------------------------------------------------------
# Demo backend
# --------------------------------------------------------------------------
class DemoBackend:
    """A fake account that resembles the screenshots and keeps moving."""

    name = "demo"

    def __init__(self):
        now = datetime.now(timezone.utc)
        self._t0 = time.time()
        self._tasks: dict[str, dict] = {}

        def mk(label, status, minutes_ago, typ="TRANSFER", sync=None, **extra):
            tid = str(uuid.uuid4())
            req = now - timedelta(minutes=minutes_ago)
            done = status in ("SUCCEEDED", "FAILED")
            t = {
                "DATA_TYPE": "task", "task_id": tid, "type": typ, "status": status,
                "label": label, "owner_string": "Demo User (demo@example.org)",
                "request_time": _iso(req),
                "completion_time": _iso(req + timedelta(minutes=random.randint(1, 9))) if done else None,
                "deadline": _iso(req + timedelta(days=3)),
                "source_endpoint_display_name": "MOHCCN CANDIG_VM",
                "destination_endpoint_display_name": "alliancecan#fir-globus",
                "sync_level": sync, "encrypt_data": True, "verify_checksum": True,
                "preserve_timestamp": False, "delete_destination_extra": False,
                "skip_source_errors": False, "fail_on_quota_errors": True,
                "files": 16, "directories": 0, "files_skipped": 0, "files_transferred": 16 if done else 0,
                "subtasks_total": 18, "subtasks_succeeded": 18 if done else 2,
                "subtasks_pending": 0 if done else 16, "subtasks_failed": 0,
                "faults": 0, "bytes_transferred": 0, "total_estimated_bytes": 0,
                "effective_bytes_per_second": 0, "nice_status": None if done else "OK",
                "nice_status_short_description": None, "is_paused": False,
                "fatal_error": None, "history_deleted": False,
                "source_base_path": None, "destination_base_path": None,
                "command": "API 0.10", "events_": [],
            }
            t.update(extra)
            self._tasks[tid] = t
            return t

        mk("fleet-msg-frontenac-to-fir-20261029T121415Z_from_frontenac_ack-kq0030-cleanup-and-kq0034-live-transfer-independentl-e2c0b97011c0",
           "SUCCEEDED", 41, sync=3, files=1, files_transferred=1, bytes_transferred=2048, total_estimated_bytes=2048)
        mk("fleet-msg-fir-to-frontenac-20261029T121145Z_from_fir_v106-kq0030-reclaimed-cleanup-job1125406-completed-tarremoved297621821",
           "SUCCEEDED", 43, sync=3, files=1, files_transferred=1, bytes_transferred=1024, total_estimated_bytes=1024)
        self._active = mk("nas-fastq-20261026-KQ0034-stage", "ACTIVE", 46,
                          bytes_transferred=54_820_000_000, total_estimated_bytes=353_070_000_000,
                          effective_bytes_per_second=21_100_000)
        mk("fleet-msg-frontenac-to-fir-20261029T120927Z_from_frontenac_kq0030-retention-succeeded-report-cleanup-slurm-job-and--ba0cacb810c1",
           "SUCCEEDED", 45, sync=3, files=1, files_transferred=1, bytes_transferred=900, total_estimated_bytes=900)
        mk("Fir v106 cleanup followup state", "SUCCEEDED", 58, files=3, files_transferred=3,
           bytes_transferred=48_000, total_estimated_bytes=48_000)
        mk("fleet-msg-frontenac-to-fir-20261029T114744Z_from_frontenac_ack-v106-kq0030-retention-active-continue-verified-clean-08cbc92a1ca5",
           "SUCCEEDED", 68, sync=3, files=1, files_transferred=1, bytes_transferred=700, total_estimated_bytes=700)
        mk("Fir v106 first retention task metadata", "SUCCEEDED", 75, files=2, files_transferred=2,
           bytes_transferred=12_000, total_estimated_bytes=12_000)
        mk("old-run-cleanup", "SUCCEEDED", 60 * 30, typ="DELETE", files=240, directories=12, subtasks_total=252,
           subtasks_succeeded=252, destination_endpoint_display_name=None)
        mk("wgs-batch7-to-cedar", "FAILED", 60 * 26, files=42, files_transferred=17,
           bytes_transferred=210_000_000_000, total_estimated_bytes=640_000_000_000,
           fatal_error={"code": "CANCELED", "description": "canceled by user"})
        mk("kq0031-bam-restage", "INACTIVE", 60 * 5, files=8, bytes_transferred=12_000_000_000,
           total_estimated_bytes=90_000_000_000, nice_status="Creds Expired",
           nice_status_short_description="Credentials expired", subtasks_succeeded=1, subtasks_pending=9)

        # synthetic progress events for the active task
        ev = []
        start = now - timedelta(minutes=43)
        for i in range(43):
            mbps = random.gauss(168, 9)
            if i in (8, 13):
                mbps = random.uniform(220, 300)
            ev.append({"code": "PROGRESS", "description": "progress", "is_error": False,
                       "time": _iso(start + timedelta(minutes=i)),
                       "details": json.dumps({"bytes_transferred": int(1.27e9 * (i + 1)),
                                              "mbps": round(mbps, 2), "duration": 60.0})})
        ev.insert(0, {"code": "STARTED", "description": "started", "is_error": False,
                      "time": _iso(start),
                      "details": json.dumps({"type": "GridFTP Transfer", "concurrency": 2,
                                             "parallelism": 4, "pipelining": 20})})
        self._active["events_"] = list(reversed(ev))

    # --- same interface as GlobusBackend ---
    def login_required(self): return False
    def login(self, force=False): pass
    def logout(self): pass
    def identity(self): return "Demo User (demo@example.org)"

    def _advance(self):
        t = self._active
        if t["status"] != "ACTIVE":
            return
        elapsed = time.time() - self._t0
        t["bytes_transferred"] = min(t["total_estimated_bytes"],
                                     54_820_000_000 + int(elapsed * 21_100_000))
        t["effective_bytes_per_second"] = 21_100_000 + random.randint(-400_000, 400_000)
        if t["bytes_transferred"] >= t["total_estimated_bytes"]:
            t["status"] = "SUCCEEDED"
            t["completion_time"] = _iso(datetime.now(timezone.utc))

    def list_tasks(self, types=TASK_TYPES, statuses=TASK_STATUSES, since=None, limit=100):
        self._advance()
        out = [dict(t) for t in self._tasks.values()
               if t["type"] in types and t["status"] in statuses
               and (since is None or datetime.fromisoformat(t["request_time"]) >= since)]
        out.sort(key=lambda t: t["request_time"], reverse=True)
        return out[:limit]

    def count_tasks(self, statuses, since=None):
        return len(self.list_tasks(statuses=statuses, since=since, limit=10_000))

    def get_task(self, task_id):
        self._advance()
        return dict(self._tasks[task_id])

    def events(self, task_id, limit=200):
        return list(self._tasks[task_id].get("events_") or [
            {"code": "SUCCEEDED", "description": "succeeded", "is_error": False,
             "time": self._tasks[task_id]["completion_time"] or "",
             "details": json.dumps({"files_succeeded": self._tasks[task_id]["files"]})}])

    def cancel(self, task_id):
        t = self._tasks[task_id]
        if t["status"] in ("ACTIVE", "INACTIVE"):
            t["status"] = "FAILED"
            t["fatal_error"] = {"code": "CANCELED", "description": "canceled by user"}
            t["completion_time"] = _iso(datetime.now(timezone.utc))
            return "Canceled: The task has been cancelled successfully."
        return "TaskComplete: The task was already complete."

    def set_label(self, task_id, label):
        self._tasks[task_id]["label"] = label

    def flow_runs(self, since=None, limit=10):
        return []


def make_backend(demo: bool = False, client_id: Optional[str] = None, flows: bool = True):
    return DemoBackend() if demo else GlobusBackend(client_id=client_id, flows=flows)
