"""Independent local worker: python -m campus.worker --data-dir data."""

import argparse
import asyncio
import os
import sys
import traceback
from pathlib import Path

from .jobs import Jobs


async def work(data_dir: Path, once: bool = False) -> None:
    """Poll durable jobs without tying their execution to a browser request."""
    jobs = Jobs(data_dir)
    while True:
        try:
            processed = await jobs.run_once()
        except Exception:
            # A single bad task must not end the worker; the task row keeps its state.
            traceback.print_exc(file=sys.stderr)
            processed = False
            await asyncio.sleep(1.0)
        if once:
            return
        if not processed:
            await asyncio.sleep(1.0)


def main() -> None:
    """Start one worker; duplicate processes cooperate through a database lease."""
    parser = argparse.ArgumentParser(description="执行课程知识整理任务")
    parser.add_argument("--data-dir", type=Path, default=Path(os.getenv("CAMPUS_DATA_DIR", "data")))
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    try:
        asyncio.run(work(args.data_dir, args.once))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
