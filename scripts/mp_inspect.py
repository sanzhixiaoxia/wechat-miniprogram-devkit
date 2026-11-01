#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mp_inspect.py — 微信小程序项目浏览与体检工具（纯 Python，无第三方依赖）

用途：让 Agent 在动手改代码前，先看清一个小程序项目的结构、路由、依赖、体积和潜在风险。

子命令：
  summary   项目概览（appid / 编译类型 / 页面数 / 分包 / 渲染引擎）
  routes    路由表：页面文件完整性、tabBar 归属、分包归属、孤立页面
  deps      依赖图：usingComponents 引用校验、组件被引用情况、孤立组件
  size      体积分析：主包 / 分包 / 资源占用，超限告警
  search    代码搜索：关键字或正则，可按扩展名过滤
  tree      目录树
  check     综合体检：汇总所有问题（error/warn/info）+ 修复建议
  all       依次执行 summary/routes/deps/size/check

示例：
  python3 scripts/mp_inspect.py check  --project ./myapp --md
  python3 scripts/mp_inspect.py search --project ./myapp --kw "wx.request" --ext .js
  python3 scripts/mp_inspect.py routes --project ./myapp --json
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

# 体积红线（字节）：微信小程序主包/分包各 2MB，总包 20MB
LIMIT_MAIN_PACKAGE = 2 * 1024 * 1024
LIMIT_SUB_PACKAGE = 2 * 1024 * 1024
LIMIT_TOTAL = 20 * 1024 * 1024

IGNORE_DIRS = {
    "node_modules", "miniprogram_npm", ".git", ".idea", ".vscode",
    "__pycache__", "dist", ".husky", "coverage",
}
CODE_EXTS = {".js", ".ts", ".wxml", ".wxss", ".json", ".less", ".scss", ".wxs"}
ASSET_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".mp3", ".mp4", ".ttf", ".woff"}


# --------------------------------------------------------------------------- #
# 基础工具
# --------------------------------------------------------------------------- #
def fail(error, hint=""):
    """统一错误输出：JSON 到 stdout，退出码 1。"""
    print(json.dumps({"ok": False, "error": error, "hint": hint}, ensure_ascii=False))
    sys.exit(1)


def read_json(path):
    """读取 JSON，容忍 BOM 与注释失败时返回 None。"""
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
        return json.loads(text)
    except Exception:
        return None


def human_size(num):
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024 or unit == "GB":
            return f"{num:.1f}{unit}" if unit != "B" else f"{int(num)}B"
        num /= 1024.0


def resolve_project(project_arg):
    """
    定位项目根目录与小程序根目录。
    返回 dict: {root, mp_root, project_config, app_config, cloud_root, has_project_config, has_app_config}
    """
    p = Path(project_arg).expanduser()
    if not p.exists():
        fail(f"项目路径不存在: {p}", "请检查 --project 参数，必须是包含 project.config.json 或 app.json 的目录")

    # 1) 项目根：含 project.config.json 的目录；允许向下找一层
    root = None
    candidates = [p] + [d for d in p.iterdir() if d.is_dir()] if p.is_dir() else [p]
    for c in candidates:
        if (c / "project.config.json").exists() or (c / "project.private.config.json").exists():
            root = c
            break
    if root is None:
        root = p if p.is_dir() else p.parent

    pcfg = read_json(root / "project.config.json") or {}
    private = read_json(root / "project.private.config.json") or {}
    # 私有配置优先级更高（开发者工具行为一致）
    merged = {**pcfg, **private}

    mp_root = root / (merged.get("miniprogramRoot") or "./")
    mp_root = mp_root.resolve()
    if not mp_root.exists():
        mp_root = root

    app_cfg = read_json(mp_root / "app.json")
    if app_cfg is None and (root / "app.json").exists():
        mp_root = root
        app_cfg = read_json(mp_root / "app.json")

    cloud_rel = merged.get("cloudfunctionRoot")
    cloud_root = (root / cloud_rel).resolve() if cloud_rel else None

    return {
        "root": str(root),
        "mp_root": str(mp_root),
        "project_config": merged,
        "app_config": app_cfg or {},
        "cloud_root": str(cloud_root) if cloud_root else None,
        "has_project_config": bool(pcfg or private),
        "has_app_config": app_cfg is not None,
    }


def iter_files(base, ignore_dirs=IGNORE_DIRS):
    """遍历目录下所有文件，跳过忽略目录。"""
    base = Path(base)
    if not base.exists():
        return
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in ignore_dirs and not d.startswith(".")]
        for fn in filenames:
            fp = Path(dirpath) / fn
            yield fp


def page_files_status(mp_root, page_path):
    """检查页面四件套是否存在。"""
    base = Path(mp_root) / page_path
    files = {}
    for ext in (".js", ".ts", ".wxml", ".wxss", ".json"):
        f = base.with_suffix(ext)
        if f.exists():
            files[ext] = str(f.relative_to(mp_root))
    has_logic = ".js" in files or ".ts" in files
    return {
        "path": page_path,
        "exists": bool(files),
        "files": files,
        "missing": [e for e in (".js", ".wxml") if e not in files],
        "complete": has_logic and ".wxml" in files,
    }


def collect_pages(app_cfg):
    """汇总主包 + 全部分包的页面列表，返回 [(page_path, package_name)]"""
    out = []
    for p in app_cfg.get("pages", []) or []:
        out.append((p, "__APP__"))
    for sub in app_cfg.get("subPackages", app_cfg.get("subpackages", []) or []) or []:
        root = (sub.get("root") or "").rstrip("/")
        name = sub.get("name") or root or "__SUB__"
        for p in sub.get("pages", []) or []:
            out.append((f"{root}/{p}".lstrip("/"), name) if root else (p, name))
    return out


def subpackage_roots(app_cfg):
    roots = []
    for sub in app_cfg.get("subPackages", app_cfg.get("subpackages", []) or []) or []:
        r = (sub.get("root") or "").rstrip("/")
        if r:
            roots.append(r)
    return roots


# --------------------------------------------------------------------------- #
# summary
# --------------------------------------------------------------------------- #
def cmd_summary(ctx):
    mp_root = Path(ctx["mp_root"])
    app, pcfg = ctx["app_config"], ctx["project_config"]
    if not ctx["has_app_config"]:
        fail(f"未找到 app.json（已尝试 {mp_root}）", "确认 --project 指向小程序根目录，或 miniprogramRoot 配置正确")

    counts, total_size = {}, 0
    for fp in iter_files(mp_root):
        ext = fp.suffix.lower()
        counts[ext] = counts.get(ext, 0) + 1
        total_size += fp.stat().st_size

    pages = collect_pages(app)
    tabbar = app.get("tabBar", {}) or {}
    return {
        "appid": pcfg.get("appid") or "(未在 project.config.json 中配置)",
        "projectname": pcfg.get("projectname") or mp_root.name,
        "compileType": pcfg.get("compileType", "miniprogram"),
        "libVersion": pcfg.get("libVersion", "(未指定)"),
        "miniprogramRoot": ctx["mp_root"],
        "cloudfunctionRoot": ctx["cloud_root"],
        "renderer": app.get("renderer", "webview"),
        "componentFramework": app.get("componentFramework", "exparser"),
        "lazyCodeLoading": app.get("lazyCodeLoading", "(未开启)"),
        "pageCount": len(pages),
        "tabBarCount": len(tabbar.get("list", []) or []),
        "subPackageCount": len(subpackage_roots(app)),
        "pluginCount": len((app.get("plugins", {}) or {})),
        "fileCounts": {k: v for k, v in sorted(counts.items(), key=lambda x: -x[1])[:10]},
        "totalSize": total_size,
        "totalSizeHuman": human_size(total_size),
        "usingTS": any(f.suffix == ".ts" for f in iter_files(mp_root)) or (mp_root / "tsconfig.json").exists(),
        "hasNpm": (mp_root / "package.json").exists() or (mp_root / "miniprogram_npm").exists(),
        "cloudFunctions": sorted([d.name for d in (Path(ctx["cloud_root"]).iterdir() if ctx["cloud_root"] and Path(ctx["cloud_root"]).exists() else []) if d.is_dir()]),
    }


# --------------------------------------------------------------------------- #
# routes
# --------------------------------------------------------------------------- #
def cmd_routes(ctx):
    mp_root = Path(ctx["mp_root"])
    app = ctx["app_config"]
    if not ctx["has_app_config"]:
        fail("未找到 app.json，无法解析路由")

    tab_pages = set()
    tabbar = app.get("tabBar", {}) or {}
    for item in tabbar.get("list", []) or []:
        if item.get("pagePath"):
            tab_pages.add(item["pagePath"].lstrip("/"))

    registered = []
    for page_path, pkg in collect_pages(app):
        st = page_files_status(mp_root, page_path)
        st["package"] = pkg
        st["tabBar"] = page_path.lstrip("/") in tab_pages
        registered.append(st)

    # 磁盘上存在但 app.json 未注册的页面（孤立页面）
    reg = {r["path"].lstrip("/") for r in registered}
    subs = subpackage_roots(app)
    orphans = []
    for fp in iter_files(mp_root):
        if fp.suffix not in (".wxml",):
            continue
        rel = fp.relative_to(mp_root).with_suffix("").as_posix()
        if rel in reg:
            continue
        # 排除组件（components 目录常见约定）
        parts = rel.split("/")
        if any(x in ("components", "component", "custom-tab-bar") for x in parts[:-1]):
            continue
        # 排除被模板/import 引用的片段
        orphans.append(rel)

    return {
        "entry": collect_pages(app)[0][0] if collect_pages(app) else None,
        "tabBar": tabbar.get("list", []),
        "pages": registered,
        "orphanPages": orphans,
        "stats": {
            "total": len(registered),
            "complete": sum(1 for r in registered if r["complete"]),
            "incomplete": [r["path"] for r in registered if not r["complete"]],
            "byPackage": {pkg: sum(1 for _, pkg2 in collect_pages(app) if pkg2 == pkg)
                          for pkg in {p for _, p in collect_pages(app)}},
        },
    }


# --------------------------------------------------------------------------- #
# deps（组件依赖）
# --------------------------------------------------------------------------- #
def resolve_component_path(mp_root, referrer_json_dir, value):
    """解析 usingComponents 的值，返回 (类型, 绝对路径或 None)"""
    if value.startswith("plugin://"):
        return "plugin", None
    if value.startswith("/"):
        return "abs", Path(mp_root) / value.lstrip("/")
    return "rel", (referrer_json_dir / value).resolve()


def cmd_deps(ctx):
    mp_root = Path(ctx["mp_root"])
    graph, broken, isolated = {}, [], []

    json_files = [fp for fp in iter_files(mp_root) if fp.suffix == ".json"]
    defined_components = {}

    for jf in json_files:
        cfg = read_json(jf)
        if not cfg:
            continue
        uses = cfg.get("usingComponents", {}) or {}
        if not uses:
            continue
        referrer = jf.relative_to(mp_root).with_suffix("").as_posix()
        graph[referrer] = {}
        for name, val in uses.items():
            kind, apath = resolve_component_path(mp_root, jf.parent, val)
            if kind == "plugin":
                graph[referrer][name] = {"type": "plugin", "ref": val, "exists": True}
                continue
            ok = apath is not None and any((apath.with_suffix(e)).exists() for e in (".js", ".ts", ".wxml", ".json"))
            rel = apath.relative_to(mp_root).as_posix() if apath and str(apath).startswith(str(mp_root)) else str(apath)
            graph[referrer][name] = {"type": kind, "ref": val, "resolved": rel, "exists": ok}
            if not ok:
                broken.append({"referrer": referrer, "component": name, "value": val, "expected": rel})
            defined_components.setdefault(rel.rstrip("/"), set()).add(referrer)

    # 反向：组件目录是否被引用（只看 components 约定目录下的组件）
    for d in iter_files(mp_root):
        if d.suffix not in (".js", ".ts"):
            continue
        if "components" not in d.parts:
            continue
        rel = d.relative_to(mp_root).with_suffix("").as_posix()
        if rel not in defined_components:
            isolated.append(rel)

    # wxml 中的 import / include
    wxml_refs = []
    for wf in iter_files(mp_root):
        if wf.suffix != ".wxml":
            continue
        try:
            text = wf.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for m in re.finditer(r'<(?:import|include)\s+src="([^"]+)"', text):
            src = m.group(1)
            target = (wf.parent / src).resolve() if not src.startswith("/") else (mp_root / src.lstrip("/"))
            wxml_refs.append({
                "from": wf.relative_to(mp_root).as_posix(),
                "src": src,
                "exists": target.exists(),
            })

    return {
        "graph": graph,
        "brokenRefs": broken,
        "isolatedComponents": isolated,
        "wxmlImports": [r for r in wxml_refs if not r["exists"]] or wxml_refs,
        "stats": {
            "referrers": len(graph),
            "components": sum(len(v) for v in graph.values()),
            "broken": len(broken),
            "isolated": len(isolated),
        },
    }


# --------------------------------------------------------------------------- #
# size
# --------------------------------------------------------------------------- #
def cmd_size(ctx):
    mp_root = Path(ctx["mp_root"])
    app = ctx["app_config"]
    subs = subpackage_roots(app)

    def classify(rel_posix):
        for s in subs:
            if rel_posix.startswith(s + "/") or rel_posix == s:
                return s
        return "__APP__"

    buckets = {"__APP__": {"size": 0, "files": 0, "assets": 0}}
    for s in subs:
        buckets[s] = {"size": 0, "files": 0, "assets": 0}
    big = []

    for fp in iter_files(mp_root):
        rel = fp.relative_to(mp_root).as_posix()
        b = classify(rel)
        size = fp.stat().st_size
        buckets[b]["size"] += size
        buckets[b]["files"] += 1
        if fp.suffix.lower() in ASSET_EXTS:
            buckets[b]["assets"] += size
        big.append({"file": rel, "size": size, "human": human_size(size), "package": b})

    big.sort(key=lambda x: -x["size"])
    total = sum(v["size"] for v in buckets.values())
    warnings = []
    if buckets["__APP__"]["size"] > LIMIT_MAIN_PACKAGE:
        warnings.append(f"主包 {human_size(buckets['__APP__']['size'])} 超过 2MB 限制，需分包或压缩资源")
    for s in subs:
        if buckets[s]["size"] > LIMIT_SUB_PACKAGE:
            warnings.append(f"分包 {s} {human_size(buckets[s]['size'])} 超过 2MB 限制")
    if total > LIMIT_TOTAL:
        warnings.append(f"总包 {human_size(total)} 超过 20MB 限制")

    return {
        "total": total,
        "totalHuman": human_size(total),
        "main": {**buckets["__APP__"], "human": human_size(buckets["__APP__"]["size"]),
                 "limit": LIMIT_MAIN_PACKAGE, "over": buckets["__APP__"]["size"] > LIMIT_MAIN_PACKAGE},
        "subPackages": {k: {**v, "human": human_size(v["size"]), "over": v["size"] > LIMIT_SUB_PACKAGE}
                        for k, v in buckets.items() if k != "__APP__"},
        "topFiles": big[:15],
        "warnings": warnings,
        "tip": "图片/字体建议放 CDN；主包只保留 tabBar 页与公共组件",
    }


# --------------------------------------------------------------------------- #
# search
# --------------------------------------------------------------------------- #
def cmd_search(ctx, kw, ext=None, regex=False, limit=50, ignore_case=True):
    mp_root = Path(ctx["mp_root"])
    if not kw:
        fail("缺少 --kw", "例：--kw \"wx.request\" [--ext .js]")
    flags = re.I if ignore_case else 0
    try:
        pattern = re.compile(kw if regex else re.escape(kw), flags)
    except re.error as e:
        fail(f"无效的正则: {e}")

    hits, scanned = [], 0
    for fp in iter_files(mp_root):
        if ext and fp.suffix.lower() != ext.lower():
            continue
        if fp.suffix.lower() not in CODE_EXTS:
            continue
        scanned += 1
        try:
            lines = fp.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            continue
        for i, line in enumerate(lines, 1):
            if pattern.search(line):
                hits.append({
                    "file": fp.relative_to(mp_root).as_posix(),
                    "line": i,
                    "text": line.strip()[:200],
                })
                if len(hits) >= limit:
                    break
        if len(hits) >= limit:
            break
    return {"keyword": kw, "regex": regex, "scannedFiles": scanned, "hits": hits, "truncated": len(hits) >= limit}


# --------------------------------------------------------------------------- #
# tree
# --------------------------------------------------------------------------- #
def cmd_tree(ctx, depth=3):
    mp_root = Path(ctx["mp_root"])
    lines, max_files = [], 400

    def walk(d, prefix, level):
        if level > depth or len(lines) > max_files:
            return
        items = sorted([p for p in d.iterdir() if p.name not in IGNORE_DIRS and not p.name.startswith(".")],
                       key=lambda p: (p.is_file(), p.name))
        for idx, p in enumerate(items):
            last = idx == len(items) - 1
            lines.append(f"{prefix}{'└── ' if last else '├── '}{p.name}{'/' if p.is_dir() else ''}")
            if p.is_dir():
                walk(p, prefix + ("    " if last else "│   "), level + 1)

    lines.append(f"{mp_root.name}/")
    walk(mp_root, "", 1)
    return {"root": str(mp_root), "depth": depth, "tree": "\n".join(lines)}


# --------------------------------------------------------------------------- #
# check（综合体检）
# --------------------------------------------------------------------------- #
def cmd_check(ctx):
    issues = []
    app, pcfg = ctx["app_config"], ctx["project_config"]
    mp_root = Path(ctx["mp_root"])

    def add(sev, cat, msg, fix, file=None):
        issues.append({"severity": sev, "category": cat, "file": file, "message": msg, "fix": fix})

    if not ctx["has_project_config"]:
        add("warn", "配置", "未找到 project.config.json",
            "用微信开发者工具打开一次项目会自动生成，或 python3 scripts/mp_scaffold.py init 创建")
    if not ctx["has_app_config"]:
        add("error", "配置", "未找到 app.json，无法识别小程序根目录",
            "确认 --project 指向含 app.json 的目录，或修正 project.config.json 的 miniprogramRoot")
        return {"issues": issues, "counts": {"error": 1, "warn": 0, "info": 0}}

    # 1. 路由完整性
    for r in cmd_routes(ctx)["pages"]:
        if not r["exists"]:
            add("error", "路由", f"页面 {r['path']} 已注册但目录下无任何文件",
                "补齐 .js/.wxml/.json 四件套，或从 app.json 的 pages 中移除", r["path"])
        elif not r["complete"]:
            add("error", "路由", f"页面 {r['path']} 缺少必要文件: {', '.join(r['missing'])}",
                "补齐缺失文件；页面至少要有 .wxml 与 .js", r["path"])

    # 2. 依赖
    deps = cmd_deps(ctx)
    for b in deps["brokenRefs"]:
        add("error", "组件", f"{b['referrer']} 引用的组件 <{b['component']}> 解析失败: {b['value']}",
            "检查 usingComponents 路径大小写与实际文件是否存在（小程序路径大小写敏感）", b["referrer"])
    for iso in deps["isolatedComponents"][:20]:
        add("info", "组件", f"组件 {iso} 未被任何页面引用",
            "确认是否冗余；确认无用可删除以减小包体积", iso)

    # 3. 体积
    sz = cmd_size(ctx)
    for w in sz["warnings"]:
        add("error" if "主包" in w or "总包" in w else "warn", "体积", w,
            "图片走 CDN、开启分包、删除未引用文件、开启 minify")

    # 4. tabBar 资源
    for item in (app.get("tabBar", {}) or {}).get("list", []) or []:
        for key in ("iconPath", "selectedIconPath"):
            v = item.get(key)
            if v and not (mp_root / v.lstrip("/")).exists():
                add("error", "tabBar", f"tabBar 图标缺失: {v}", "补齐图片资源（建议 81x81 png，不超过 40KB）", v)
        if item.get("pagePath") and item["pagePath"] not in [p for p, _ in collect_pages(app)]:
            add("error", "tabBar", f"tabBar 页 {item['pagePath']} 未在 pages 中注册",
                "把该页面加入 app.json 的 pages 数组", item["pagePath"])

    # 5. appid
    aid = str(pcfg.get("appid", ""))
    if not aid:
        add("warn", "配置", "project.config.json 未配置 appid", "填入正式 AppID，测试号无法上传/发布")
    elif "tourist" in aid:
        add("warn", "配置", "当前为测试号 appid（touristappid）", "上传、预览与真机调试受限，请换成正式 AppID")

    # 6. 明文 http 请求
    http_hits = cmd_search(ctx, r"(?:http://)[\w.-]+", regex=True, limit=10)["hits"]
    for h in http_hits:
        if "w3.org" in h["text"] or "localhost" in h["text"]:
            continue
        add("warn", "网络", f"{h['file']}:{h['line']} 使用了 http 明文地址",
            "小程序要求 https；或在开发者工具勾选「不校验合法域名」仅用于本地调试", h["file"])

    # 7. console 残留
    console_hits = cmd_search(ctx, r"console\.(log|debug)", regex=True, limit=10)["hits"]
    if console_hits:
        add("info", "代码", f"发现 {len(console_hits)} 处 console.log/debug（示例：{console_hits[0]['file']}:{console_hits[0]['line']}）",
            "发布前清理或接入统一日志开关")

    # 8. 未开启按需注入
    if app.get("lazyCodeLoading") != "requiredComponents":
        add("info", "性能", "未开启 lazyCodeLoading: requiredComponents",
            "在 app.json 加入 \"lazyCodeLoading\": \"requiredComponents\" 可显著加快启动")

    # 9. 孤立页面
    routes = cmd_routes(ctx)
    for o in routes["orphanPages"][:10]:
        add("info", "路由", f"页面文件 {o} 未在 app.json 注册（可能是模板片段或冗余页面）",
            "若为真实页面请注册到 pages；若为模板可忽略", o)

    counts = {s: sum(1 for i in issues if i["severity"] == s) for s in ("error", "warn", "info")}
    return {
        "issues": sorted(issues, key=lambda x: {"error": 0, "warn": 1, "info": 2}[x["severity"]]),
        "counts": counts,
        "healthy": counts["error"] == 0,
    }


# --------------------------------------------------------------------------- #
# Markdown 渲染
# --------------------------------------------------------------------------- #
def to_markdown(command, data):
    out = []
    if command == "summary":
        out.append("## 项目概览\n")
        out.append("| 项 | 值 |\n|---|---|")
        for k in ("appid", "projectname", "compileType", "libVersion", "renderer",
                  "componentFramework", "lazyCodeLoading", "pageCount", "tabBarCount",
                  "subPackageCount", "totalSizeHuman", "usingTS", "hasNpm"):
            if k in data:
                out.append(f"| {k} | {data[k]} |")
        if data.get("cloudFunctions"):
            out.append(f"\n云函数：{', '.join(data['cloudFunctions'])}")
    elif command == "routes":
        out.append("## 路由表\n")
        out.append("| 页面路径 | 分包 | tabBar | 文件完整性 |\n|---|---|---|---|")
        for p in data["pages"]:
            out.append(f"| `{p['path']}` | {p['package']} | {'是' if p['tabBar'] else ''} | "
                       f"{'完整' if p['complete'] else '缺 ' + ','.join(p['missing'])} |")
        out.append(f"\n共 {data['stats']['total']} 个页面，完整 {data['stats']['complete']} 个。")
        if data["orphanPages"]:
            out.append(f"\n未注册页面（疑似）：{', '.join(data['orphanPages'][:10])}")
    elif command == "deps":
        out.append("## 依赖分析\n")
        out.append("| 引用方 | 组件 | 解析结果 | 存在 |\n|---|---|---|---|")
        for ref, comps in data["graph"].items():
            for name, info in comps.items():
                out.append(f"| `{ref}` | {name} | `{info.get('resolved', info.get('ref'))}` | {'✓' if info['exists'] else '✗'} |")
        if data["brokenRefs"]:
            out.append("\n**断链引用**\n")
            for b in data["brokenRefs"]:
                out.append(f"- `{b['referrer']}` → <{b['component']}> = `{b['value']}`")
        if data["isolatedComponents"]:
            out.append(f"\n未被引用组件：{', '.join(data['isolatedComponents'][:10])}")
    elif command == "size":
        out.append("## 体积分析\n")
        out.append("| 包 | 大小 | 文件数 | 资源占比 | 超限 |\n|---|---|---|---|---|")
        m = data["main"]
        out.append(f"| 主包 | {m['human']} | {m['files']} | {human_size(m['assets'])} | {'⚠ 是' if m['over'] else '否'} |")
        for k, v in data["subPackages"].items():
            out.append(f"| {k} | {v['human']} | {v['files']} | {human_size(v['assets'])} | {'⚠ 是' if v['over'] else '否'} |")
        out.append(f"\n总计：{data['totalHuman']}")
        if data["warnings"]:
            out.append("\n**告警**\n" + "\n".join(f"- {w}" for w in data["warnings"]))
        out.append("\n最大的文件\n\n| 文件 | 大小 | 包 |\n|---|---|---|")
        for f in data["topFiles"][:10]:
            out.append(f"| `{f['file']}` | {f['human']} | {f['package']} |")
    elif command == "search":
        out.append(f"## 搜索 `{data['keyword']}`\n")
        if not data["hits"]:
            out.append("无匹配结果。")
        for h in data["hits"]:
            out.append(f"- `{h['file']}:{h['line']}` — `{h['text']}`")
    elif command == "tree":
        out.append("## 目录结构\n\n```\n" + data["tree"] + "\n```")
    elif command == "check":
        out.append("## 项目体检\n")
        c = data["counts"]
        out.append(f"error **{c['error']}** · warn **{c['warn']}** · info **{c['info']}**\n")
        if not data["issues"]:
            out.append("未发现问题。")
        out.append("| 级别 | 分类 | 说明 | 修复建议 |\n|---|---|---|---|")
        for i in data["issues"]:
            out.append(f"| {i['severity']} | {i['category']} | {i['message']} | {i['fix']} |")
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="微信小程序项目浏览与体检")
    ap.add_argument("command", choices=["summary", "routes", "deps", "size", "search", "tree", "check", "all"])
    ap.add_argument("--project", "-p", required=True, help="小程序项目根目录")
    ap.add_argument("--kw", help="search 关键字")
    ap.add_argument("--ext", help="search 限定扩展名，如 .js")
    ap.add_argument("--regex", action="store_true", help="search 使用正则")
    ap.add_argument("--depth", type=int, default=3, help="tree 深度")
    ap.add_argument("--limit", type=int, default=50, help="search 结果上限")
    ap.add_argument("--json", action="store_true", help="输出 JSON（默认）")
    ap.add_argument("--md", action="store_true", help="输出 Markdown")
    args = ap.parse_args()

    ctx = resolve_project(args.project)

    if args.command == "summary":
        data = cmd_summary(ctx)
    elif args.command == "routes":
        data = cmd_routes(ctx)
    elif args.command == "deps":
        data = cmd_deps(ctx)
    elif args.command == "size":
        data = cmd_size(ctx)
    elif args.command == "search":
        data = cmd_search(ctx, args.kw, args.ext, args.regex, args.limit)
    elif args.command == "tree":
        data = cmd_tree(ctx, args.depth)
    elif args.command == "check":
        data = cmd_check(ctx)
    else:  # all
        result = {
            "summary": cmd_summary(ctx) if ctx["has_app_config"] else {"error": "no app.json"},
            "routes": cmd_routes(ctx) if ctx["has_app_config"] else {},
            "deps": cmd_deps(ctx),
            "size": cmd_size(ctx),
            "check": cmd_check(ctx),
        }
        if args.md:
            for k, v in result.items():
                print(to_markdown(k, v) if k != "routes" else to_markdown("routes", v))
                print()
        else:
            print(json.dumps({"ok": True, "project": ctx["root"], "data": result}, ensure_ascii=False, indent=2))
        return

    if args.md:
        print(to_markdown(args.command, data))
    else:
        print(json.dumps({"ok": True, "command": args.command, "project": ctx["root"], "data": data},
                         ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
