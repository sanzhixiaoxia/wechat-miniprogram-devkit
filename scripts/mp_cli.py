#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mp_cli.py — 微信开发者工具命令行（CLI）封装

用途：让 Agent 能直接驱动本机微信开发者工具：打开项目、构建 npm、登录、预览出码、上传代码、
      开启自动化端口、云开发管理。

前提（用户侧一次性配置）：
  1. 安装微信开发者工具（仅 macOS / Windows）
  2. 工具内：设置 → 安全设置 → 开启「服务端口」（CLI/HTTP 调用）

子命令：
  detect                       探测本机 CLI 路径
  open      --project DIR      打开/编译项目
  auto      --project DIR [--port 9420]   开启自动化端口（配合 mp_auto.js）
  preview   --project DIR [--qr-format image|base64|terminal] [--qr-output FILE] [--compile-condition JSON]
  upload    --project DIR --version 1.0.0 --desc "备注" [--info-output FILE]
  build-npm --project DIR [--compile-type miniprogram]
  login     [--qr-format base64] [--qr-output FILE]
  islogin                      查询登录态
  cloud     ...                云开发命令透传（env list / functions list / functions deploy ...）
  cache     --project DIR      清除缓存
  close     --project DIR      关闭项目窗口
  quit                         退出开发者工具
  raw       -- <任意参数>      原样透传

环境变量：
  MP_CLI_PATH   手动指定 CLI 绝对路径（macOS: .../Contents/MacOS/cli，Windows: cli.bat）
  MP_CLI_PORT   指定工具 HTTP 服务端口
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

DOWNLOAD_URL = "https://developers.weixin.qq.com/miniprogram/dev/devtools/download.html"


# --------------------------------------------------------------------------- #
# CLI 路径探测
# --------------------------------------------------------------------------- #
def candidate_paths():
    home = Path.home()
    cands = []

    if sys.platform == "darwin":
        cands += [
            "/Applications/wechatwebdevtools.app/Contents/MacOS/cli",
            str(home / "Applications/wechatwebdevtools.app/Contents/MacOS/cli"),
            "/Applications/微信开发者工具.app/Contents/MacOS/cli",
            "/Applications/wechatwebdevtools.app/Contents/Resources/app.nw/bin/cli",
        ]
    elif sys.platform == "win32":
        for drive in ("C", "D", "E"):
            for pf in ("Program Files (x86)", "Program Files"):
                cands.append(f"{drive}:/{pf}/Tencent/微信web开发者工具/cli.bat")
                cands.append(f"{drive}:/{pf}/Tencent/微信开发者工具/cli.bat")
    else:
        # Linux：官方 Linux 版 + WSL 访问 Windows 安装
        cands += [
            "/opt/wechatwebdevtools/cli",
            "/opt/wechat_web_devtools/cli",
            str(home / ".local/share/wechatwebdevtools/cli"),
            "/mnt/c/Program Files (x86)/Tencent/微信web开发者工具/cli.bat",
            "/mnt/c/Program Files/Tencent/微信web开发者工具/cli.bat",
        ]
    return cands


def detect_cli():
    """返回 (path|None, source)"""
    env = os.environ.get("MP_CLI_PATH")
    if env:
        if Path(env).exists():
            return env, "env:MP_CLI_PATH"
        return None, f"env:MP_CLI_PATH 指向的路径不存在: {env}"

    which = shutil.which("cli") or shutil.which("wxdevtools")
    if which:
        return which, "PATH"

    for c in candidate_paths():
        if Path(c).exists():
            return c, "auto-detect"
    return None, "not-found"


def require_cli():
    path, source = detect_cli()
    if path:
        return path, source
    hint = (
        f"未找到微信开发者工具 CLI（{source}）。请确认：\n"
        f"1) 已安装微信开发者工具（仅 macOS/Windows 提供，下载：{DOWNLOAD_URL}）；\n"
        f"2) 工具内「设置 → 安全设置」已开启服务端口；\n"
        f"3) 若安装在非标准位置，设置环境变量 MP_CLI_PATH 指向 cli（Windows 为 cli.bat）。\n"
        f"本机探测过的路径：\n  " + "\n  ".join(candidate_paths()[:6])
    )
    print(json.dumps({"ok": False, "error": "微信开发者工具 CLI 不可用", "hint": hint,
                      "platform": sys.platform, "candidates": candidate_paths()[:6]},
                     ensure_ascii=False, indent=2))
    sys.exit(2)


# --------------------------------------------------------------------------- #
# 错误处理：把工具输出翻译成可执行建议
# --------------------------------------------------------------------------- #
ERROR_HINTS = [
    ("服务端口", "请在开发者工具「设置 → 安全设置」中开启服务端口（CLI/HTTP 调用）后重试"),
    ("服务端口已关闭", "请在开发者工具「设置 → 安全设置」中开启服务端口（CLI/HTTP 调用）后重试"),
    ("port", "可能是工具 HTTP 服务端口被占用或未开启：加 --port 指定端口，或在安全设置中开启服务端口"),
    ("ECONNREFUSED", "工具未启动或端口不通：先执行 mp_cli.py open，再重试"),
    ("login", "未登录：先执行 mp_cli.py login 扫码登录，或 mp_cli.py islogin 检查"),
    ("未登录", "未登录：先执行 mp_cli.py login 扫码登录"),
    ("project.config.json", "项目路径不正确：--project 必须是含 project.config.json 的目录，且路径用绝对路径"),
    ("not a directory", "--project 不是有效目录，请使用绝对路径"),
    ("appid", "project.config.json 缺少有效 appid，上传/预览需要正式 AppID"),
    ("ESCAPE", ""),
]


def classify_error(text):
    for key, hint in ERROR_HINTS:
        if key and key.lower() in text.lower():
            return hint
    return ""


def run_cli(cli_path, argv, timeout=300, cwd=None):
    """执行 CLI；Windows 的 cli.bat 用 shell 方式调用。"""
    use_shell = str(cli_path).lower().endswith(".bat") or sys.platform == "win32"
    cmdline = [cli_path] + argv
    try:
        proc = subprocess.run(
            cmdline if not use_shell else subprocess.list2cmdline(cmdline),
            capture_output=True, text=True, timeout=timeout,
            cwd=cwd, shell=use_shell, encoding="utf-8", errors="replace",
        )
        return {"argv": cmdline, "returncode": proc.returncode,
                "stdout": (proc.stdout or "").strip(), "stderr": (proc.stderr or "").strip()}
    except subprocess.TimeoutExpired:
        return {"argv": cmdline, "returncode": -1, "stdout": "",
                "stderr": f"命令执行超时（>{timeout}s）；预览/上传较慢时可加 --timeout 调大"}
    except FileNotFoundError:
        return {"argv": cmdline, "returncode": -1, "stdout": "",
                "stderr": f"无法执行 {cli_path}，请检查 MP_CLI_PATH"}


def emit(result, extra=None):
    payload = {"ok": result["returncode"] == 0, **result}
    if result["returncode"] != 0:
        payload["hint"] = classify_error(result["stderr"] + result["stdout"]) or \
            "参考 references/cli-and-ci.md 排查，或加 --debug 查看详细输出"
    if extra:
        payload.update(extra)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    sys.exit(0 if payload["ok"] else result["returncode"] or 1)


def abs_project(p):
    path = Path(p).expanduser().resolve()
    if not path.exists():
        print(json.dumps({"ok": False, "error": f"项目路径不存在: {path}",
                          "hint": "--project 必须是绝对路径且真实存在"}, ensure_ascii=False, indent=2))
        sys.exit(1)
    return str(path)


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="微信开发者工具 CLI 封装")
    ap.add_argument("command", choices=["detect", "open", "auto", "preview", "upload", "build-npm",
                                        "login", "islogin", "cloud", "cache", "close", "quit", "raw"])
    ap.add_argument("--project", "-p", help="小程序项目目录（绝对路径）")
    ap.add_argument("--port", type=int, help="工具 HTTP 服务端口")
    ap.add_argument("--auto-port", type=int, default=9420, help="自动化端口，默认 9420")
    ap.add_argument("--version", help="upload 版本号")
    ap.add_argument("--desc", help="upload 备注")
    ap.add_argument("--qr-format", default="image", choices=["terminal", "image", "base64"])
    ap.add_argument("--qr-output", help="二维码输出路径")
    ap.add_argument("--info-output", help="上传/预览附加信息输出路径（JSON）")
    ap.add_argument("--compile-condition", help='编译条件 JSON，如 {"pathName":"pages/index/index","query":"id=1"}')
    ap.add_argument("--compile-type", help="build-npm 编译类型：miniprogram|plugin")
    ap.add_argument("--lang", default="zh", choices=["zh", "en"])
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("rest", nargs=argparse.REMAINDER, help="cloud/raw 的其余参数")
    args = ap.parse_args()

    if args.command == "detect":
        path, source = detect_cli()
        print(json.dumps({
            "ok": bool(path),
            "cliPath": path,
            "source": source,
            "platform": sys.platform,
            "candidates": candidate_paths(),
            "hint": "" if path else f"请安装微信开发者工具（{DOWNLOAD_URL}）并开启服务端口，或设置 MP_CLI_PATH",
        }, ensure_ascii=False, indent=2))
        sys.exit(0 if path else 2)

    cli_path, source = require_cli()
    argv = ["--lang", args.lang]
    if args.port or os.environ.get("MP_CLI_PORT"):
        argv += ["--port", str(args.port or os.environ.get("MP_CLI_PORT"))]
    if args.debug:
        argv.append("--debug")

    if args.command == "open":
        argv += ["open", "--project", abs_project(args.project or ".")]
    elif args.command == "auto":
        argv += ["auto", "--project", abs_project(args.project or "."), "--auto-port", str(args.auto_port)]
    elif args.command == "preview":
        argv += ["preview", "--project", abs_project(args.project or "."), "--qr-format", args.qr_format]
        if args.qr_output:
            argv += ["--qr-output", str(Path(args.qr_output).expanduser().resolve())]
        if args.info_output:
            argv += ["--info-output", str(Path(args.info_output).expanduser().resolve())]
        if args.compile_condition:
            argv += ["--compile-condition", args.compile_condition]
    elif args.command == "upload":
        if not args.version:
            print(json.dumps({"ok": False, "error": "upload 必须提供 --version",
                              "hint": "例：--version 1.0.0 --desc \"修复登录问题\""}, ensure_ascii=False, indent=2))
            sys.exit(1)
        argv += ["upload", "--project", abs_project(args.project or "."), "--version", args.version]
        if args.desc:
            argv += ["--desc", args.desc]
        if args.info_output:
            argv += ["--info-output", str(Path(args.info_output).expanduser().resolve())]
    elif args.command == "build-npm":
        argv += ["build-npm", "--project", abs_project(args.project or ".")]
        if args.compile_type:
            argv += ["--compile-type", args.compile_type]
    elif args.command == "login":
        argv += ["login", "--qr-format", args.qr_format]
        if args.qr_output:
            argv += ["--qr-output", str(Path(args.qr_output).expanduser().resolve())]
    elif args.command == "islogin":
        argv += ["islogin"]
    elif args.command == "cache":
        argv += ["cache", "--clean", "all", "--project", abs_project(args.project or ".")]
    elif args.command == "close":
        argv += ["close", "--project", abs_project(args.project or ".")]
    elif args.command == "quit":
        argv += ["quit"]
    elif args.command == "cloud":
        if args.project:
            argv += ["cloud"] + args.rest + ["--project", abs_project(args.project)]
        else:
            argv += ["cloud"] + args.rest
    elif args.command == "raw":
        argv += args.rest

    result = run_cli(cli_path, argv, timeout=args.timeout)
    extra = {"cliPath": cli_path, "source": source}

    if args.command == "preview" and args.qr_output and result["returncode"] == 0:
        extra["qrcode"] = str(Path(args.qr_output).expanduser().resolve())
        extra["hint"] = "二维码已生成，可直接展示给用户扫码真机预览"
    if args.command == "auto" and result["returncode"] == 0:
        extra["wsEndpoint"] = f"ws://localhost:{args.auto_port}"
        extra["hint"] = f"自动化端口已开启，可用 mp_auto.js --port {args.auto_port} 连接"

    emit(result, extra)


if __name__ == "__main__":
    main()
