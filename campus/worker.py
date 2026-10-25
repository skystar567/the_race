"""Independent local worker: python -m campus.worker --data-dir data."""

import argparse
import asyncio
import os
import sys
import traceback
from pathlib import Path

from .jobs import Jobs, LEASE_SECONDS


async def work(data_dir: Path, once: bool = False, *, lease_seconds: float = LEASE_SECONDS) -> None:
    """Poll durable jobs without tying their execution to a browser request."""
    jobs = Jobs(data_dir, lease_seconds=lease_seconds)
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
    parser.add_argument("--lease-seconds", type=float, default=LEASE_SECONDS,
                        help="租约期限，默认45秒，中断后过期接管；至少2秒，过短会增加误接管风险")
    args = parser.parse_args()
    try:
        asyncio.run(work(args.data_dir, args.once, lease_seconds=args.lease_seconds))
    except KeyboardInterrupt:
        pass
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
