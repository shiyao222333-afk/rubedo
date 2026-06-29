"""
Rubedo · 凝华 — v0.3.0 时间审计模块
数据格式：data/timelog/YYYY-MM-DD_kujiale_N.json
"""

import json
from datetime import date, datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).parent
TIMELOG_DIR = BASE_DIR / "data" / "timelog"
TIMELOG_DIR.mkdir(parents=True, exist_ok=True)


def _today_str() -> str:
    return date.today().isoformat()


def _now_iso() -> str:
    return datetime.now().isoformat()


def _next_order_id(sop_id: str) -> str:
    """Generate next order ID: YYYY-MM-DD-sop_N."""
    today = _today_str()
    prefix = f"{today}_{sop_id}_"
    existing = sorted(TIMELOG_DIR.glob(f"{today}_{sop_id}_*.json"))
    n = len(existing) + 1
    return f"{prefix}{n}"


def _order_path(order_id: str) -> Path:
    return TIMELOG_DIR / f"{order_id}.json"


# --- Public API ---

def start_order(sop_id: str, sop_file: Path) -> dict:
    """
    Create a new order from SOP definition.
    Returns the order dict (includes order_id, sop, started_at, steps).
    """
    order_id = _next_order_id(sop_id)
    sop_def = json.loads(sop_file.read_text(encoding="utf-8"))

    steps = []
    for stage in sop_def.get("stages", []):
        for step in stage.get("steps", []):
            if step.get("id"):
                steps.append({
                    "id": step["id"],
                    "name": step.get("name", ""),
                    "mode": step.get("mode", "manual"),
                    "started": None,
                    "finished": None,
                    "duration_min": None,
                })

    order = {
        "order_id": order_id,
        "sop": sop_id,
        "started_at": _now_iso(),
        "finished_at": None,
        "steps": steps,
    }
    _write_order(order)
    return order


def start_step(order_id: str, step_id: str) -> dict | None:
    """Mark a step as started. Returns the updated step dict."""
    order = get_order(order_id)
    if not order:
        return None
    for s in order["steps"]:
        if s["id"] == step_id:
            s["started"] = _now_iso()
            s["finished"] = None
            s["duration_min"] = None
            break
    _write_order(order)
    return _find_step(order, step_id)


def finish_step(order_id: str, step_id: str) -> dict | None:
    """Mark a step as finished, calculate duration in minutes. Returns updated step."""
    order = get_order(order_id)
    if not order:
        return None
    for s in order["steps"]:
        if s["id"] == step_id and s["started"]:
            finished = datetime.now()
            started = datetime.fromisoformat(s["started"])
            s["finished"] = finished.isoformat()
            s["duration_min"] = round((finished - started).total_seconds() / 60, 1)
            break
    _write_order(order)
    return _find_step(order, step_id)


def finish_order(order_id: str) -> dict | None:
    """Mark the order as finished."""
    order = get_order(order_id)
    if not order:
        return None
    order["finished_at"] = _now_iso()
    _write_order(order)
    return order


def get_active_order(sop_id: str) -> dict | None:
    """Get the currently active (unfinished) order for a SOP.
    Returns the most recent order whose finished_at is None.
    """
    orders = get_all_orders(sop_id)
    active = [o for o in orders if o.get("finished_at") is None]
    if not active:
        return None
    # Return most recently started
    active.sort(key=lambda o: o.get("started_at", ""), reverse=True)
    return active[0]


def get_order(order_id: str) -> dict | None:
    """Load a single order by ID."""
    fp = _order_path(order_id)
    if not fp.exists():
        return None
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def get_all_orders(sop_id: str) -> list[dict]:
    """Get all orders for a given SOP, sorted newest first."""
    orders = []
    for fp in sorted(TIMELOG_DIR.glob("*.json"), reverse=True):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            if data.get("sop") == sop_id:
                orders.append(data)
        except (json.JSONDecodeError, OSError):
            continue
    return orders


def get_step_stats(sop_id: str) -> dict[str, dict]:
    """
    Aggregate step timing stats across all completed orders.
    Returns dict: step_id -> {"name", "count", "avg_min", "max_min", "total_min"}
    """
    stat: dict[str, dict] = {}
    orders = get_all_orders(sop_id)

    for order in orders:
        for step in order.get("steps", []):
            sid = step["id"]
            dur = step.get("duration_min")
            if dur is None:
                continue
            if sid not in stat:
                stat[sid] = {
                    "name": step.get("name", sid),
                    "count": 0,
                    "total_min": 0.0,
                    "max_min": 0.0,
                }
            stat[sid]["count"] += 1
            stat[sid]["total_min"] += dur
            if dur > stat[sid]["max_min"]:
                stat[sid]["max_min"] = dur

    for sid in stat:
        s = stat[sid]
        s["avg_min"] = round(s["total_min"] / s["count"], 1)

    return stat


def get_all_orders_summary(sop_id: str) -> list[dict]:
    """
    Get a summary of all orders (without full step details).
    Returns list of {order_id, sop, started_at, finished_at, step_count, total_min}.
    """
    orders = get_all_orders(sop_id)
    summaries = []
    for order in orders:
        total_min = sum(
            s.get("duration_min", 0) or 0
            for s in order.get("steps", [])
        )
        summaries.append({
            "order_id": order["order_id"],
            "sop": order["sop"],
            "started_at": order["started_at"],
            "finished_at": order.get("finished_at"),
            "step_count": len(order.get("steps", [])),
            "total_min": round(total_min, 1),
        })
    return summaries


# --- Internal ---

def _find_step(order: dict, step_id: str) -> dict | None:
    for s in order["steps"]:
        if s["id"] == step_id:
            return s
    return None


def _write_order(order: dict) -> None:
    fp = _order_path(order["order_id"])
    fp.write_text(json.dumps(order, ensure_ascii=False, indent=2), encoding="utf-8")
