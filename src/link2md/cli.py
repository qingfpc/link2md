"""Command line entry: ``link2md <url>``, ``link2md init``, ``link2md doctor``."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from link2md import __version__
from link2md.config import default_config_path, example_config_text, load_config
from link2md.errors import Link2mdError
from link2md.log import get_logger, setup_logging
from link2md.pipeline import save_link


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.target[:1] == ["init"]:
            return _cmd_init(args)
        if args.target[:1] == ["doctor"]:
            return _cmd_doctor(args)
        if not args.target:
            parser.print_help()
            return 2
        return _cmd_save(args)
    except Link2mdError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("已取消。", file=sys.stderr)
        return 130


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="link2md",
        description="把社交平台或网页链接整理成 Obsidian Markdown 笔记。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  link2md init\n"
            "  link2md doctor\n"
            '  link2md "https://www.bilibili.com/video/BVxxxx"\n'
            '  link2md "【分享】https://www.xiaoyuzhoufm.com/episode/xxxx"\n'
            "  link2md --no-llm --update <url>\n"
        ),
    )
    parser.add_argument("target", nargs="*", help="链接、分享文案，或子命令 init / doctor")
    parser.add_argument("--config", help="配置文件路径。默认是用户配置目录里的 config.yaml")
    parser.add_argument("--vault", help="本次运行使用的 Obsidian 仓库路径，覆盖配置")
    parser.add_argument("--asr", choices=["faster-whisper", "dashscope"], help="本次运行使用的转写后端")
    parser.add_argument("--no-llm", action="store_true", help="不调用模型，直接保存提取到的正文")
    parser.add_argument("--update", action="store_true", help="同一链接已存在时覆盖原笔记")
    parser.add_argument("--force", action="store_true", help="配合 init：覆盖已有配置文件")
    parser.add_argument("-v", "--verbose", action="store_true", help="输出调试日志")
    parser.add_argument("--version", action="version", version=f"link2md {__version__}")
    return parser


def _cmd_save(args: argparse.Namespace) -> int:
    config = _load(args)
    if args.vault:
        config.vault.path = args.vault
    if args.asr:
        config.asr.backend = args.asr
    _setup(config, verbose=args.verbose)
    text = " ".join(args.target)
    result = save_link(text, config, no_llm=args.no_llm, update=args.update)
    if result.status == "skipped":
        print(f"已跳过：这个链接保存过了（{result.path}）。如需覆盖，请加 --update")
    elif result.status == "updated":
        print(f"已更新：{result.path}")
    else:
        print(f"已保存：{result.path}")
    return 0


def _cmd_init(args: argparse.Namespace) -> int:
    path = Path(args.config).expanduser() if args.config else default_config_path()
    if path.exists() and not args.force:
        print(f"配置文件已存在：{path}")
        print("如需覆盖，请加 --force。")
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(example_config_text(), encoding="utf-8")
    print(f"已写入配置：{path}")
    print("请填写 vault.path，并把 API Key 放到环境变量里。")
    return 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    config = _load(args)
    _setup(config, verbose=args.verbose)
    problems = 0
    print(f"link2md {__version__}")
    if config.config_path:
        print(f"配置文件：{config.config_path}")
    else:
        print(f"配置文件：未找到，使用默认值（link2md init 可生成 {default_config_path()}）")

    vault = (config.vault.path or "").strip()
    if not vault:
        print("仓库路径：未配置。请设置 vault.path 或环境变量 LINK2MD_VAULT。")
        problems += 1
    else:
        root = Path(vault).expanduser()
        if root.is_dir():
            print(f"仓库路径：{root}")
        else:
            print(f"仓库路径：{root}（目录不存在）")
            problems += 1

    print(f"笔记目录：{config.vault.notes_dir}")
    print(f"附件目录：{config.vault.attachments_dir}")
    print(f"缓存目录：{config.cache_path()}")
    print(f"ASR 后端：{config.asr.backend}")
    print(f"模型：{config.llm.provider} / {config.llm.model} / {config.llm.base_url}")
    print(f"ffmpeg：{'已安装' if shutil.which('ffmpeg') else '未找到（云端转写和部分音频处理需要它）'}")
    print(f"yt-dlp：{'可导入' if _importable('yt_dlp') else '未安装'}")
    print(f"faster-whisper：{'可导入' if _importable('faster_whisper') else '未安装（pip install \"link2md[asr]\"）'}")
    print(f"dashscope：{'可导入' if _importable('dashscope') else '未安装（pip install \"link2md[cloud]\"）'}")
    print(f"{config.llm.api_key_env}：{'已设置' if config.llm_api_key() else '未设置'}")
    print(f"{config.asr.dashscope.api_key_env}：{'已设置' if config.dashscope_api_key() else '未设置'}")
    if config.llm.api_key.strip() or config.asr.dashscope.api_key.strip():
        print("提示：配置文件里写了 api_key。更稳妥的做法是只放在环境变量中。")
    for name in ("bilibili", "douyin", "xiaohongshu"):
        raw = getattr(config.cookies, name, "") or ""
        if not str(raw).strip():
            label = "未配置"
        elif Path(str(raw)).expanduser().is_file():
            label = "文件存在"
        else:
            label = "文件不存在"
            problems += 1
        extra = ""
        if name != "bilibili":
            extra = "（v2 预留）"
        print(f"cookies.{name}：{label}{extra}")
    if problems:
        print(f"检查结束，有 {problems} 项需要处理。")
        return 1
    print("检查通过。")
    return 0


def _load(args: argparse.Namespace):
    if args.config:
        return load_config(args.config, require_file=True)
    return load_config()


def _setup(config, *, verbose: bool) -> None:
    level = "DEBUG" if verbose else config.log_level
    cache = config.cache_path()
    cache.mkdir(parents=True, exist_ok=True)
    setup_logging(level, cache / "link2md.log")
    get_logger().debug("日志文件：%s", cache / "link2md.log")


def _importable(module: str) -> bool:
    try:
        __import__(module)
    except ImportError:
        return False
    return True
