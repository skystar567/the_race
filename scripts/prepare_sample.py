"""Extract an unchanged textbook section, with a separate provenance record."""

import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="准备《计算机操作系统（第四版）》的真实阅读样本")
    parser.add_argument("textbook", type=Path, help="原始教材 Markdown")
    parser.add_argument("--output-dir", type=Path, default=Path("data/samples"))
    args = parser.parse_args()
    original = args.textbook.read_bytes()
    lines = original.splitlines(keepends=True)
    start = next(i for i, line in enumerate(lines) if line.decode("utf-8").strip() == "## 第二章 进程的描述与控制")
    end = next(i for i in range(start + 1, len(lines)) if lines[i].decode("utf-8").strip() == "## 2.1.2 程序顺序执行")
    sample = b"".join(lines[start:end])
    args.output_dir.mkdir(parents=True, exist_ok=True)
    target = args.output_dir / "计算机操作系统（第四版）_第2章至2.1.1节.md"
    if target.resolve() == args.textbook.resolve():
        parser.error("输出文件不能覆盖原始教材")
    target.write_bytes(sample)
    provenance = {
        "source": args.textbook.name,
        "source_sha256": hashlib.sha256(original).hexdigest(),
        "source_start_line": start + 1,
        "source_end_line": end,
        "sample_sha256": hashlib.sha256(sample).hexdigest(),
        "note": "教材原文逐字节摘录；界面行号相对于该样本文件。",
    }
    target.with_suffix(".source.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(target)
    print(f"原教材第 {start + 1}—{end} 行；原文未改写，原教材未修改。")


if __name__ == "__main__":
    main()
