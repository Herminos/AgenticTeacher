"""Fail fast with an actionable message when an unsupported Python is used."""

import sys


MIN_VERSION = (3, 10)
MAX_VERSION_EXCLUSIVE = (3, 14)


def main() -> int:
    current = sys.version_info[:2]
    if current < MIN_VERSION or current >= MAX_VERSION_EXCLUSIVE:
        print(
            "不支持当前 Python 版本："
            f"{current[0]}.{current[1]}。"
            "本项目要求 Python >=3.10 且 <3.14；推荐 Python 3.11。\n"
            "请使用 `python3.11 -m venv .venv` 创建虚拟环境，"
            "然后激活环境再安装 requirements.txt。",
            file=sys.stderr,
        )
        return 1
    print(f"Python {current[0]}.{current[1]} compatible")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
