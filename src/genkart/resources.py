"""What running Lucida takes from THIS computer, measured now: memory of the web server, of the local model server (Ollama) and of any local
cluster processes (encoder, shard workers). Nothing here estimates: every number is read from the operating system or from Ollama's own report.
"""
from __future__ import annotations

import os
import pathlib
import resource
import subprocess
import sys


def rss_mb(pid: int) -> float | None:
    """Memory a process holds in RAM right now, in megabytes (None if it is gone)."""
    try:
        out = subprocess.run(["ps", "-o", "rss=", "-p", str(int(pid))], capture_output=True, text=True, timeout=3).stdout.strip()
        return round(int(out) / 1024, 1) if out else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def peak_mb() -> float:
    """The most memory this process has held since it started (macOS reports bytes, Linux kilobytes)."""
    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(raw / (1024 * 1024) if sys.platform == "darwin" else raw / 1024, 1)


def snapshot(root: pathlib.Path, ollama_ps: dict | None) -> dict:
    cluster = []
    for f in sorted((root / "data" / "run").glob("*.pid")):
        try:
            mb = rss_mb(int(f.read_text().strip()))
        except (OSError, ValueError):
            continue
        if mb is not None:
            cluster.append({"name": f.stem, "rss_mb": mb})
    models = [{"name": m.get("name", "?"), "size_mb": round(m.get("size", 0) / 1e6), "vram_mb": round(m.get("size_vram", 0) / 1e6)}
              for m in (ollama_ps or {}).get("models", [])]
    total_gb = round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1e9, 1) if hasattr(os, "sysconf") else None
    return {"server": {"rss_mb": rss_mb(os.getpid()), "peak_mb": peak_mb()}, "ollama": models, "cluster": cluster, "computer": {"cpus": os.cpu_count(), "memory_gb": total_gb}}
