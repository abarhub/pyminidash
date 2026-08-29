"""Providers système : espace disque et processus les plus gourmands."""
from __future__ import annotations

import shutil
import time

import psutil

from pyminidash.models import (
    Record, StatusLevel, bytes_, number, status, text, title, FieldRole,
)
from pyminidash.registry import provider


def _level_for_percent(pct: float) -> StatusLevel:
    if pct >= 90:
        return StatusLevel.ERROR
    if pct >= 75:
        return StatusLevel.WARN
    return StatusLevel.OK


@provider("disk_usage")
def disk_usage(paths: list[str]) -> list[Record]:
    records: list[Record] = []
    for path in paths:
        u = shutil.disk_usage(path)
        pct = round(u.used / u.total * 100) if u.total else 0
        records.append(Record(
            title("mount", "Disque", path),
            status("percent", "%", f"{pct} %", level=_level_for_percent(pct),
                   summary=True),
            bytes_("free", "Libre", u.free, summary=True),
            bytes_("total", "Total", u.total),
            bytes_("used", "Utilisé", u.used),
        ))
    return records


def _processes_to_records(samples: list[dict], limit: int) -> list[Record]:
    ordered = sorted(samples, key=lambda s: s["cpu"], reverse=True)[:limit]
    return [
        Record(
            title("name", "Processus", s["name"]),
            number("cpu", "CPU %", round(s["cpu"], 1), role=FieldRole.BADGE,
                   summary=True),
            bytes_("memory", "Mémoire", s["memory"], summary=True),
            number("pid", "PID", s["pid"]),
            text("username", "Utilisateur", s["username"]),
            text("status", "État", s["status"]),
        )
        for s in ordered
    ]


@provider("top_processes")
def top_processes(limit: int = 10) -> list[Record]:
    procs = list(psutil.process_iter(["pid", "name", "username", "status"]))
    for p in procs:
        try:
            p.cpu_percent(None)  # 1re mesure (renvoie 0.0)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    time.sleep(0.1)

    samples: list[dict] = []
    for p in procs:
        try:
            info = p.info
            samples.append({
                "pid": info["pid"],
                "name": info["name"] or "?",
                "username": info["username"] or "?",
                "status": info["status"] or "?",
                "cpu": p.cpu_percent(None),
                "memory": p.memory_info().rss,
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return _processes_to_records(samples, limit)
