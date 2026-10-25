#!/usr/bin/env sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
if [ ! -x .venv/bin/python ]; then
  echo "请先按 README 创建 .venv 并安装 Python 依赖。" >&2
  exit 1
fi
exec .venv/bin/python -m campus "$@"
