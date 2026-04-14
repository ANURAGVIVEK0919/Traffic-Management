"""Trace the simulation result flow end-to-end without changing project code.

Run from the backend folder:
    python debug_result_flow.py
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.chdir(PROJECT_ROOT)

DB_FILE = PROJECT_ROOT / "traffic_sim.db"


from backend.controllers import simulation_controller as controller  # noqa: E402
from backend.database.db import get_connection  # noqa: E402
from backend.database.models import create_tables  # noqa: E402
from backend.routers import simulation as simulation_router  # noqa: E402
from backend.routers.simulation import SubmitLogRequest  # noqa: E402
from backend.services import results_service, simulation_service  # noqa: E402
from backend.services.simulation_service import create_session  # noqa: E402


def now_ts() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def log_step(message: str) -> None:
    print(f"[{now_ts()}] {message}")


def dump_value(value: Any) -> str:
    try:
        return json.dumps(value, indent=2, sort_keys=True, default=str)
    except TypeError:
        return repr(value)


@dataclass
class TraceState:
    expected_session_id: str
    submit_called: bool = False
    submit_session_id: str | None = None
    handle_submit_called: bool = False
    save_called: bool = False
    cache_called: bool = False
    get_called: bool = False
    save_return: Any = None
    cache_return: Any = None
    get_return: Any = None
    observed_session_ids: list[str] = field(default_factory=list)


def patch_attr(module: Any, attr_name: str, replacement: Callable[..., Any], originals: list[tuple[Any, str, Any]]) -> None:
    originals.append((module, attr_name, getattr(module, attr_name)))
    setattr(module, attr_name, replacement)


def ensure_session(session_id: str | None, timer_duration: int) -> str:
    if session_id:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM simulation_session WHERE id = ?", (session_id,))
        row = cursor.fetchone()
        if row is None:
            created_at = datetime.utcnow().isoformat()
            cursor.execute(
                """
                INSERT INTO simulation_session (id, timer_duration, created_at, status)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, timer_duration, created_at, "running"),
            )
            conn.commit()
        conn.close()
        return session_id

    return create_session(timer_duration)


def build_test_events() -> list[dict[str, Any]]:
    base_ms = int(time.time() * 1000)
    return [
        {
            "eventType": "rl_decision",
            "laneId": "north",
            "timestamp": base_ms,
            "payload": {
                "tick": 0,
                "snapshot": {
                    "lane_states": [
                        {
                            "lane_id": "north",
                            "vehicle_count": 4,
                            "normalized_vehicle_count": 0.4,
                            "has_ambulance": False,
                            "avg_wait_time": 12.0,
                            "normalized_avg_wait_time": 0.4,
                        },
                        {
                            "lane_id": "east",
                            "vehicle_count": 2,
                            "normalized_vehicle_count": 0.2,
                            "has_ambulance": False,
                            "avg_wait_time": 8.0,
                            "normalized_avg_wait_time": 0.27,
                        },
                        {
                            "lane_id": "south",
                            "vehicle_count": 0,
                            "normalized_vehicle_count": 0.0,
                            "has_ambulance": False,
                            "avg_wait_time": 0.0,
                            "normalized_avg_wait_time": 0.0,
                        },
                        {
                            "lane_id": "west",
                            "vehicle_count": 1,
                            "normalized_vehicle_count": 0.1,
                            "has_ambulance": False,
                            "avg_wait_time": 3.0,
                            "normalized_avg_wait_time": 0.1,
                        },
                    ]
                },
                "raw_lane_state": {},
                "smoothed_lane_state": {},
                "average_confidence": 0.95,
                "confidence_filtered": False,
                "low_confidence_streak": 0,
                "confidence_hold_ticks": 1,
                "decision": {
                    "lane": "north",
                    "duration": 15,
                    "debug": {
                        "strategy": "debug-trace",
                        "reason": "manual-trace",
                    },
                },
                "source": "debug_result_flow.py",
            },
        }
    ]


def query_db(session_id: str) -> list[tuple[Any, ...]]:
    conn = sqlite3.connect(str(DB_FILE))
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT system_type, avg_wait_time, total_vehicles_crossed, co2_estimate,
               avg_green_utilization, ambulance_avg_wait_time, created_at
        FROM simulation_result
        WHERE session_id = ?
        ORDER BY id ASC
        """,
        (session_id,),
    )
    rows = cursor.fetchall()
    conn.close()
    return rows


def run_debug(session_id: str | None, timer_duration: int, wait_after_submit: float) -> int:
    create_tables()

    chosen_session_id = ensure_session(session_id, timer_duration)
    state = TraceState(expected_session_id=chosen_session_id)
    originals: list[tuple[Any, str, Any]] = []

    original_controller_handle_submit = controller.handle_submit_log
    original_save_simulation_results = simulation_service.save_simulation_results
    original_cache_simulation_results = simulation_service.cache_simulation_results
    original_get_simulation_results = results_service.get_simulation_results

    def wrapped_handle_submit_log(submitted_session_id: str, events: list[dict[str, Any]]) -> Any:
        state.handle_submit_called = True
        state.submit_called = True
        state.submit_session_id = submitted_session_id
        state.observed_session_ids.append(submitted_session_id)
        log_step(f"[STEP] handle_submit_log entered session_id={submitted_session_id}")
        log_step(f"[STEP] handle_submit_log events_is_none={events is None}")
        log_step(f"[STEP] handle_submit_log events_count={len(events) if events is not None else 'None'}")
        return original_controller_handle_submit(submitted_session_id, events)

    def wrapped_save_simulation_results(submitted_session_id: str, dynamic_metrics: Any, static_metrics: Any) -> Any:
        state.save_called = True
        state.observed_session_ids.append(submitted_session_id)
        log_step(f"[STEP] save_simulation_results called session_id={submitted_session_id}")
        log_step(f"[STEP] save_simulation_results dynamic_is_none={dynamic_metrics is None}")
        log_step(f"[STEP] save_simulation_results static_is_none={static_metrics is None}")
        log_step(f"[STEP] save_simulation_results dynamic={dump_value(dynamic_metrics)}")
        log_step(f"[STEP] save_simulation_results static={dump_value(static_metrics)}")
        try:
            result = original_save_simulation_results(submitted_session_id, dynamic_metrics, static_metrics)
            state.save_return = result
            log_step(f"[STEP] save_simulation_results returned {dump_value(result)}")
            return result
        except Exception as exc:  # pragma: no cover - diagnostic path
            state.save_return = exc
            log_step(f"[ERROR] save_simulation_results raised {exc!r}")
            raise

    def wrapped_cache_simulation_results(submitted_session_id: str, dynamic_row: Any, static_row: Any) -> Any:
        state.cache_called = True
        state.observed_session_ids.append(submitted_session_id)
        log_step(f"[STEP] cache_simulation_results called session_id={submitted_session_id}")
        log_step(f"[STEP] cache_simulation_results dynamic_is_none={dynamic_row is None}")
        log_step(f"[STEP] cache_simulation_results static_is_none={static_row is None}")
        log_step(f"[STEP] cache_simulation_results dynamic={dump_value(dynamic_row)}")
        log_step(f"[STEP] cache_simulation_results static={dump_value(static_row)}")
        result = original_cache_simulation_results(submitted_session_id, dynamic_row, static_row)
        state.cache_return = result
        log_step("[STEP] cache_simulation_results completed")
        return result

    def wrapped_get_simulation_results(submitted_session_id: str) -> Any:
        state.get_called = True
        state.observed_session_ids.append(submitted_session_id)
        log_step(f"[STEP] get_simulation_results entered session_id={submitted_session_id}")
        result = original_get_simulation_results(submitted_session_id)
        state.get_return = result
        log_step(f"[STEP] get_simulation_results returned {dump_value(result)}")
        return result

    patch_attr(controller, "handle_submit_log", wrapped_handle_submit_log, originals)
    patch_attr(controller, "save_simulation_results", wrapped_save_simulation_results, originals)
    patch_attr(controller, "get_simulation_results", wrapped_get_simulation_results, originals)
    patch_attr(simulation_router, "handle_submit_log", wrapped_handle_submit_log, originals)
    patch_attr(simulation_service, "save_simulation_results", wrapped_save_simulation_results, originals)
    patch_attr(simulation_service, "cache_simulation_results", wrapped_cache_simulation_results, originals)
    patch_attr(results_service, "cache_simulation_results", wrapped_cache_simulation_results, originals)
    patch_attr(results_service, "get_simulation_results", wrapped_get_simulation_results, originals)

    try:
        events = build_test_events()
        log_step(f"[STEP] submit-log received session_id={chosen_session_id}")
        log_step(f"[STEP] submit-log events_is_none={events is None}")
        log_step(f"[STEP] submit-log events_count={len(events)}")

        request = SubmitLogRequest(session_id=chosen_session_id, events=events)
        submit_result = simulation_router.submit_log(request)
        log_step(f"[STEP] submit-log returned {dump_value(submit_result)}")

        if state.submit_session_id and state.submit_session_id != chosen_session_id:
            log_step(
                f"[ERROR] SESSION ID MISMATCH: expected={chosen_session_id} received={state.submit_session_id}"
            )

        if wait_after_submit > 0:
            time.sleep(wait_after_submit)

        print("[STATE] results_store =")
        print(dump_value(results_service.results_store))

        db_rows = query_db(chosen_session_id)
        print(f"[STATE] sqlite_rows_for_session_id={chosen_session_id}")
        print(dump_value(db_rows))
        print(f"[STATE] db_row_exists={bool(db_rows)}")

        print(f"[STATE] direct_get_simulation_results(session_id={chosen_session_id})")
        direct_result = results_service.get_simulation_results(chosen_session_id)
        print(dump_value(direct_result))

        retry_result: Any = direct_result
        if isinstance(direct_result, dict) and direct_result.get("error"):
            time.sleep(0.25)
            retry_result = results_service.get_simulation_results(chosen_session_id)
            print("[STATE] retry_get_simulation_results =")
            print(dump_value(retry_result))

        root_cause = None
        if not state.submit_called or not state.save_called:
            root_cause = "RESULT NOT SAVED: save_simulation_results not called"
        elif not state.cache_called or chosen_session_id not in results_service.results_store:
            root_cause = "CACHE MISS: cache_simulation_results not storing data"
        elif not db_rows:
            root_cause = "DB WRITE FAILED: no record found in SQLite"
        elif state.submit_session_id and state.submit_session_id != chosen_session_id:
            root_cause = "SESSION ID MISMATCH"
        elif isinstance(direct_result, dict) and direct_result.get("error") and isinstance(retry_result, dict) and not retry_result.get("error"):
            root_cause = "TIMING ISSUE: GET called before save completes"

        if root_cause:
            print(f"ROOT CAUSE: {root_cause}")
        else:
            print("ROOT CAUSE: none detected")

        return 0
    finally:
        for module, attr_name, original_value in reversed(originals):
            setattr(module, attr_name, original_value)


def main() -> int:
    parser = argparse.ArgumentParser(description="Trace traffic simulation result flow")
    parser.add_argument("--session-id", default="", help="Optional existing session id to inspect")
    parser.add_argument("--timer-duration", type=int, default=60, help="Timer duration used when creating a test session")
    parser.add_argument(
        "--wait-after-submit",
        type=float,
        default=0.0,
        help="Optional delay in seconds before reading cache and SQLite after submit",
    )
    args = parser.parse_args()

    session_id = args.session_id.strip() or None
    return run_debug(session_id, max(1, args.timer_duration), max(0.0, args.wait_after_submit))


if __name__ == "__main__":
    raise SystemExit(main())