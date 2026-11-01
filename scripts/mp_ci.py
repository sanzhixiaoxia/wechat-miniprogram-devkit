#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mp_ci.py — miniprogram-ci 封装（无需打开微信开发者工具，适合 CI / 无人值守场景）

能力：预览出二维码、上传代码、构建 npm、部署云函数。

前置（用户侧一次配置）：
  1) 微信公众平台 → 管理 → 开发管理 → 开发设置 → 小程序代码上传 → 生成「代码上传密钥」（.key 文件）
  2) 同一页面配置 IP 白名单（强烈建议，未配置将无法调用）
  3) 安装：npm i -g miniprogram-ci   （或项目内 npm i miniprogram-ci）

子命令：
  preview  --project DIR --appid wx123 --key ./private.wx123.key --out /tmp/qr.png
           [--page pages/index/index] [--query "id=1"] [--robot 1] [--version 1.0.0] [--desc "备注"]
  upload   --project DIR --appid wx123 --key ./private.wx123.key --version 1.0.0 --desc "备注" [--robot 1]
  build-npm --project DIR --appid wx123 --key ./private.wx123.key
  cloud-function --project DIR --appid wx123 --key ./private.wx123.key --env ENV_ID --name fn --path ./cloudfunctions/fn

通用参数：
  --dry-run   只打印将要执行的命令，不真正执行（推荐 Agent 先跑一次确认）
  --install   自动执行 npm i -g miniprogram-ci
  --timeout   超时秒数，默认 600
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

INSTALL_CMD = "npm i -g miniprogram-ci"

# miniprogram-ci 常见失败 → 可执行建议
ERROR_MAP = [
    ("1004", "IP 白名单未配置或不匹配：到「微信公众平台 → 开发管理 → 开发设置 → 小程序代码上传」把当前公网 IP 加入白名单"),
    ("ip", "IP 白名单问题：确认当前出口 IP 已加入小程序后台的 IP 白名单"),
    ("private key", "密钥文件错误：确认 --key 指向正确的 private.<appid>.key，且与 appid 匹配"),
    ("密钥", "密钥文件错误：确认 --key 路径与 appid 匹配（遗失需在后台重置）"),
    ("appid", "appid 不匹配：确认 --appid 与密钥、project.config.json 一致"),
    ("not found", "命令未找到：先执行 " + INSTALL_CMD),
    ("no such file", "路径不存在：检查 --project / --key 是否为正确路径"),
    ("package size", "代码包超限（主包 2MB / 分包 2MB / 总包 20MB）：压缩资源、开启分包或把图片放 CDN"),
    ("size", "代码包体积超限：主包 2MB / 分包 2MB / 总包 20MB"),
    ("compile", "编译失败：先在本地用开发者工具编译通过，确认 project.config.json 配置正确"),
    ("es6", "编译设置问题：可加 --enable-es6 true 或检查代码中不被支持的语法"),
]


def out(payload, code=0):
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    sys.exit(code)


def check_ci_installed():
    """返回 (bin, source)；bin 为 None 表示不可用。"""
    b = shutil.which("miniprogram-ci")
    if b:
        return b, "global"
    # 本地 node_modules/.bin
    local = Path.cwd() / "node_modules" / ".bin" / "miniprogram-ci"
    if local.exists():
        return str(local), "local"
    return None, "not-found"


def ensure_ci(allow_install, dry_run=False):
    b, source = check_ci_installed()
    if b:
        return b, source
    if dry_run:
        # 干跑只拼命令，允许本机尚未安装
        return "miniprogram-ci", "not-installed(dry-run)"
    if allow_install:
        print(json.dumps({"ok": True, "installing": True, "cmd": INSTALL_CMD}, ensure_ascii=False), flush=True)
        r = subprocess.run(INSTALL_CMD, shell=True, capture_output=True, text=True)
        b, source = check_ci_installed()
        if b:
            return b, "installed"
        out({"ok": False, "error": "miniprogram-ci 安装失败", "stderr": r.stderr[-800:],
             "hint": f"请手动执行 {INSTALL_CMD} 后重试"}, 1)
    out({
        "ok": False,
        "error": "未安装 miniprogram-ci",
        "hint": f"执行 {INSTALL_CMD} 安装，或加 --install 让脚本自动安装；只想看命令可加 --dry-run",
        "docs": "https://developers.weixin.qq.com/miniprogram/dev/devtools/ci.html",
    }, 1)


def validate(project, key, appid=None, ci_bin=None):
    problems = []
    p = Path(project).expanduser().resolve()
    if not p.exists():
        problems.append(f"项目路径不存在: {p}")
    else:
        if not (p / "project.config.json").exists():
            problems.append(f"项目根目录缺少 project.config.json: {p}")
        if not (p / "app.json").exists():
            problems.append(f"未找到 app.json（miniprogramRoot 可能不是项目根）: {p}")
    if key:
        k = Path(key).expanduser().resolve()
        if not k.exists():
            problems.append(f"密钥文件不存在: {k}")
        elif k.suffix != ".key":
            problems.append(f"密钥文件后缀异常（应为 .key）: {k}")
    if appid and not appid.startswith("wx"):
        problems.append(f"appid 格式可疑（应以 wx 开头）: {appid}")
    if ci_bin is None:
        problems.append("miniprogram-ci 未安装")
    return [x for x in problems], p


def hint_for(text):
    for key, msg in ERROR_MAP:
        if key.lower() in text.lower():
            return msg
    return "参见 references/cli-and-ci.md 或官方文档 https://developers.weixin.qq.com/miniprogram/dev/devtools/ci.html"


def run(cmd, timeout, dry_run, success_hint="", warnings=None):
    if dry_run:
        payload = {"ok": True, "dryRun": True, "cmd": subprocess.list2cmdline(cmd),
                   "hint": "干跑未真正执行；确认无误后去掉 --dry-run",
                   "expected": success_hint}
        if warnings:
            payload["warnings"] = warnings
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        sys.exit(0)
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                          encoding="utf-8", errors="replace")
    payload = {
        "ok": proc.returncode == 0,
        "cmd": subprocess.list2cmdline(cmd),
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "").strip()[-4000:],
        "stderr": (proc.stderr or "").strip()[-4000:],
    }
    if proc.returncode == 0:
        payload["hint"] = success_hint
    else:
        payload["hint"] = hint_for((proc.stderr or "") + (proc.stdout or ""))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    sys.exit(0 if proc.returncode == 0 else proc.returncode)


def main():
    ap = argparse.ArgumentParser(description="miniprogram-ci 封装")
    ap.add_argument("command", choices=["preview", "upload", "build-npm", "cloud-function"])
    ap.add_argument("--project", "-p", required=True)
    ap.add_argument("--appid", required=True, help="小程序 appid（微信公众平台获取，wx 开头，示例见文档，勿填真实值到本文件）")
    ap.add_argument("--key", required=True, help="代码上传密钥 private.<appid>.key 路径")
    ap.add_argument("--out", help="preview 二维码输出路径")
    ap.add_argument("--page", help="预览启动页面，如 pages/index/index")
    ap.add_argument("--query", help="预览页面参数，如 id=1&from=ci")
    ap.add_argument("--version", help="版本号（upload 必填）")
    ap.add_argument("--desc", default="", help="版本备注")
    ap.add_argument("--robot", default="1", help="CI 机器人编号 1~30，默认 1")
    ap.add_argument("--env", help="云环境 ID（cloud-function）")
    ap.add_argument("--name", help="云函数名（cloud-function）")
    ap.add_argument("--path", help="云函数目录（cloud-function）")
    ap.add_argument("--threads", default="1")
    ap.add_argument("--enable-es6", default="true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--timeout", type=int, default=600)
    args = ap.parse_args()

    ci_bin, source = ensure_ci(args.install, dry_run=args.dry_run)
    problems, project = validate(args.project, args.key, args.appid, ci_bin)
    # 干跑只看命令，前置问题降级为 warning；真正执行时才阻断
    warnings = problems if args.dry_run else []
    if problems and not args.dry_run:
        out({"ok": False, "error": "前置校验未通过", "problems": problems,
             "hint": "修正后再执行；加 --dry-run 可先看将要执行的命令"}, 1)

    key = str(Path(args.key).expanduser().resolve())
    cmd = [ci_bin, args.command, "--pp", str(project), "--pkp", key, "--appid", args.appid]

    if args.command == "preview":
        qr = str(Path(args.out or "./preview-qrcode.jpg").expanduser().resolve())
        cmd += ["--qrcode-format", "image", "--qrcode-output-dest", qr]
        if args.page:
            cmd += ["--page-path", args.page]
        if args.query:
            cmd += ["--search-query", args.query]
        if args.version:
            cmd += ["--uv", args.version]
        if args.desc:
            cmd += ["--ud", args.desc]
        cmd += ["-r", str(args.robot), "--enable-es6", args.enable_es6]
        run(cmd, args.timeout, args.dry_run, f"二维码已生成：{qr}，可展示给用户扫码预览", warnings)

    elif args.command == "upload":
        if not args.version:
            out({"ok": False, "error": "upload 必须提供 --version",
                 "hint": "例：--version 1.0.0 --desc \"修复登录\""}, 1)
        cmd += ["--uv", args.version, "--ud", args.desc or args.version,
                "-r", str(args.robot), "--threads", str(args.threads),
                "--enable-es6", args.enable_es6]
        run(cmd, args.timeout, args.dry_run, "上传成功，到小程序后台「版本管理」可看到该版本", warnings)

    elif args.command == "build-npm":
        run(cmd, args.timeout, args.dry_run, "npm 构建完成，miniprogram_npm 已生成", warnings)

    elif args.command == "cloud-function":
        if not (args.env and args.name and args.path):
            out({"ok": False, "error": "cloud-function 需要 --env --name --path"}, 1)
        cmd[1] = "cloud-function-deploy"
        cmd += ["--env", args.env, "--name", args.name, "--path", str(Path(args.path).expanduser().resolve())]
        run(cmd, args.timeout, args.dry_run, "云函数已部署，可在云开发控制台查看", warnings)


if __name__ == "__main__":
    main()
