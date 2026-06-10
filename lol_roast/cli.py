from __future__ import annotations

import argparse
import json
import logging
import sys

from . import __version__
from .app import RoastAssistant
from .config import AppConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LOL 选人阶段队友锐评助手")
    parser.add_argument("--config", default="config.json", help="配置文件路径")
    parser.add_argument("--dry-run", action="store_true", help="分析和生成锐评，但不发送")
    parser.add_argument("--once", action="store_true", help="成功处理一局后退出")
    parser.add_argument("--debug", action="store_true", help="输出调试日志")
    parser.add_argument("--print-default-config", action="store_true", help="打印默认配置并退出")
    parser.add_argument("--version", action="version", version=__version__)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = AppConfig.load(args.config)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"配置读取失败: {exc}", file=sys.stderr)
        return 2
    if args.print_default_config:
        print(json.dumps(config.as_dict(), ensure_ascii=False, indent=2))
        return 0
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    return RoastAssistant(config, dry_run=args.dry_run, once=args.once).run()

