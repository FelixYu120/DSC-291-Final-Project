"""Run step 3 (``cropyield.archive.sampling``) until every planned unit is read.

One sampling run tries each open unit once; a unit that fails stays open. This module repeats the run until
no unit is left, or until three runs in a row read nothing. While it runs it asks Windows not to go to sleep
when idle (the request ends with the process and changes no setting).

With ``--build-at HH:MM`` it builds the database once at that local clock time from what is read so far, while
the reading goes on (a safety copy if the computer closes early). With ``--stop-at HH:MM`` no new unit is started
after that local clock time. With ``--then-build`` it builds the
database and runs the checks when the reading has ended, and the log says which country-years are complete.

Run:   python -m cropyield.archive.download_all --processes 6 --threads 32 --stop-at 15:45 --then-build
Stop:  end the process (its id is in ``staging/samples/download.pid``). A finished unit is one complete file,
       so a stop loses at most the units in flight, and the next start skips everything that is done.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import threading
import time

from cropyield.archive import check, paths, release, sampling

ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001


def stay_awake() -> None:
    """Ask Windows to stay awake while this process lives. Does nothing on other systems."""
    if os.name == "nt":
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)


def stop_epoch(clock: str | None, now: float | None = None) -> float | None:
    """``HH:MM`` of today, local time, as seconds since 1970. A time that has passed already means: stop now."""
    if not clock:
        return None
    now = time.time() if now is None else now
    hour, minute = (int(part) for part in clock.split(":"))
    today = time.localtime(now)
    return time.mktime((today.tm_year, today.tm_mon, today.tm_mday, hour, minute, 0, 0, 0, -1))


def build_and_check(lock: threading.Lock, label: str) -> int:
    """Build the database and run the checks; one build at a time. Returns the number of failed checks."""
    with lock:
        for step in sampling.progress_by_step():
            print(json.dumps(step), flush=True)
        built = release.build()
        failed = check.main()
        print(json.dumps({label: str(built), "megabytes": round(built.stat().st_size / 1e6), "checks_failed": failed,
                          "at": time.strftime("%Y-%m-%d %H:%M:%S")}), flush=True)
        return failed


def schedule_build(at: float, lock: threading.Lock, finished: threading.Event, build=build_and_check) -> threading.Thread:
    """One safety build at clock time ``at`` while the readers go on. Skipped when the reading ends before ``at``."""
    def wait_then_build() -> None:
        if not finished.wait(timeout=max(0.0, at - time.time())):
            build(lock, "safety_build")
    thread = threading.Thread(target=wait_then_build, daemon=True)
    thread.start()
    return thread


def main(threads: int, pause: float = 60.0, then_build: bool = False, processes: int = 1,
         stop_at: str | None = None, build_at: str | None = None) -> int:
    lock, finished = threading.Lock(), threading.Event()
    if build_at:
        schedule_build(stop_epoch(build_at), lock, finished)
    code = read_all(threads, pause, processes, stop_epoch(stop_at))
    finished.set()
    if then_build:
        failed = build_and_check(lock, "built")       # waits for a safety build that is still running
        return failed or (0 if code == 2 else code)
    for step in sampling.progress_by_step():
        print(json.dumps(step), flush=True)
    return code


def read_all(threads: int, pause: float, processes: int, until: float | None = None) -> int:
    staging = paths.staging_dir("samples")
    staging.mkdir(parents=True, exist_ok=True)
    (staging / "download.pid").write_text(str(os.getpid()), encoding="utf-8")
    stay_awake()
    empty_rounds, number = 0, 0
    while empty_rounds < 3:
        if until and time.time() >= until:
            print(json.dumps({"stopped_by_clock": time.strftime("%Y-%m-%d %H:%M:%S")}), flush=True)
            return 2
        number += 1
        result = sampling.run(minutes=0, threads=threads, limit=None, processes=processes, until=until)
        print(json.dumps({"round": number, "at": time.strftime("%Y-%m-%d %H:%M:%S"), **result}), flush=True)
        if result["left"] <= 0:
            return 0
        empty_rounds = empty_rounds + 1 if result["read_now"] == 0 else 0
        if not (until and time.time() >= until):
            time.sleep(pause)
    return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--threads", type=int, default=32, help="threads in each process")
    parser.add_argument("--processes", type=int, default=6)
    parser.add_argument("--then-build", action="store_true", help="build the database and run the checks at the end")
    parser.add_argument("--stop-at", default=None, help="local clock time HH:MM after which no new unit is started")
    parser.add_argument("--build-at", default=None, help="local clock time HH:MM of one safety build while reading")
    arguments = parser.parse_args()
    raise SystemExit(main(arguments.threads, then_build=arguments.then_build, processes=arguments.processes,
                          stop_at=arguments.stop_at, build_at=arguments.build_at))
