import argparse
import os
import subprocess
import sys
from pathlib import Path

import uvicorn

from .api import create_app


def main():
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="启动本机课程学习空间")
    parser.add_argument("--data-dir", type=Path, default=Path(os.environ.get("CAMPUS_DATA_DIR", root / "data")))
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if not (root / "dist/index.html").is_file():
        parser.error("尚未构建前端，请先运行 npm run build")
    # A separate process survives browser disconnection. Never execute model text.
    worker = subprocess.Popen(
        [sys.executable, "-m", "campus.worker", "--data-dir", str(args.data_dir.resolve())],
        cwd=root,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    try:
        uvicorn.run(create_app(args.data_dir, static_dir=root / "dist"), host="127.0.0.1", port=args.port)
    finally:
        worker.terminate()
        try:
            worker.wait(timeout=5)
        except subprocess.TimeoutExpired:
            worker.kill()
            worker.wait()


if __name__ == "__main__":
    main()
