#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mp_scaffold.py — 微信小程序开发脚手架（纯 Python，无第三方依赖）

用途：快速初始化项目、生成页面 / 自定义组件 / 云函数，并自动维护 app.json 注册。

子命令：
  init       初始化小程序项目
             --dir ./myapp [--appid wx123] [--name MyApp] [--type native|cloud|skyline] [--ts]
  page       生成页面四件套并注册路由
             --project ./myapp --path pages/goods/detail [--subpackage pkgA] [--title 商品详情] [--ts] [--no-register]
  component  生成自定义组件
             --project ./myapp --name goods-card [--dir components] [--ts]
  cloudfunc  生成云函数
             --project ./myapp --name login
  remove     移除页面并注销注册（默认只注销，--files 同时删除文件）
             --project ./myapp --path pages/goods/detail [--files]

所有命令幂等：已存在的文件默认跳过（--force 覆盖）。输出统一 JSON。
"""

import argparse
import json
import sys
from pathlib import Path

WXSS_UNIT = "rpx"


# --------------------------------------------------------------------------- #
# 模板
# --------------------------------------------------------------------------- #
def tpl_app_js():
    return """App({
  onLaunch() {
    // 展示本地存储能力
    const logs = wx.getStorageSync('logs') || []
    logs.unshift(Date.now())
    wx.setStorageSync('logs', logs)
  },
  globalData: {
    userInfo: null
  }
})
"""


def tpl_app_json(name, pages=("pages/index/index",), skyline=False, ts=False):
    cfg = {
        "pages": list(pages),
        "window": {
            "backgroundTextStyle": "light",
            "navigationBarBackgroundColor": "#07C160",
            "navigationBarTitleText": name,
            "navigationBarTextStyle": "white"
        },
        "style": "v2",
        "sitemapLocation": "sitemap.json"
    }
    if skyline:
        cfg["lazyCodeLoading"] = "requiredComponents"
        cfg["renderer"] = "skyline"
        cfg["componentFramework"] = "glass-easel"
        cfg["rendererOptions"] = {
            "skyline": {
                "defaultDisplayBlock": True,
                "defaultContentBox": True,
                "tagNameStyleIsolation": "legacy",
                "enableScrollViewAutoSize": True
            }
        }
    return json.dumps(cfg, ensure_ascii=False, indent=2) + "\n"


def tpl_app_wxss():
    return """page {
  background-color: #f6f6f6;
  font-family: -apple-system, BlinkMacSystemFont, 'Helvetica Neue', Helvetica, sans-serif;
}

.container {
  display: flex;
  flex-direction: column;
  align-items: center;
  box-sizing: border-box;
  padding: 32rpx;
}
"""


def tpl_project_config(appid, name, cloud=False, ts=False):
    cfg = {
        "description": "项目配置文件，详见 https://developers.weixin.qq.com/miniprogram/dev/devtools/projectconfig.html",
        "appid": appid or "touristappid",
        "compileType": "miniprogram",
        "libVersion": "3.5.0",
        "projectname": name,
        "miniprogramRoot": "./",
        "setting": {
            "urlCheck": False,
            "es6": True,
            "enhance": True,
            "postcss": True,
            "minified": True,
            "coverView": True,
            "lazyloadPlaceholderEnable": False,
            "preBackground": False,
            "autoAudits": False,
            "uglifyFileName": False,
            "uploadWithSourceMap": True,
            "useCompilerModule": True,
            "userConfirmedUseCompilerModuleSwitch": False
        },
        "condition": {}
    }
    if cloud:
        cfg["cloudfunctionRoot"] = "cloudfunctions/"
    if ts:
        cfg["setting"]["useCompilerPlugins"] = ["typescript"]
    return json.dumps(cfg, ensure_ascii=False, indent=2) + "\n"


def tpl_sitemap():
    return """{
  "desc": "更多关于 sitemap 的配置请参考：https://developers.weixin.qq.com/miniprogram/dev/framework/sitemap.html",
  "rules": [{
    "action": "allow",
    "page": "*"
  }]
}
"""


def tpl_page_js(title, ts=False):
    return f"""// {title}
Page({{
  data: {{
    title: '{title}',
    list: [],
    loading: false
  }},

  onLoad(options) {{
    // 页面创建时执行，options 为路由参数
    console.log('[{title}] onLoad', options)
  }},

  onShow() {{
    // 页面出现在前台时执行
  }},

  onReady() {{
    // 页面首次渲染完毕时执行
  }},

  onHide() {{
    // 页面从前台变为后台时执行
  }},

  onUnload() {{
    // 页面销毁时执行
  }},

  onPullDownRefresh() {{
    // 下拉刷新
    wx.stopPullDownRefresh()
  }},

  onReachBottom() {{
    // 触底加载更多
  }},

  onShareAppMessage() {{
    return {{
      title: '{title}',
      path: '/__PAGE_PATH__'
    }}
  }}
}})
"""


def tpl_page_wxml(title):
    return f"""<!--{title}-->
<view class="page">
  <view class="page__hd">
    <view class="page__title">{title}</view>
    <view class="page__desc">页面说明：{title}</view>
  </view>

  <view class="page__bd">
    <view wx:if="{{{{loading}}}}" class="loading">加载中...</view>
    <block wx:else>
      <view wx:if="{{{{list.length === 0}}}}" class="empty">暂无数据</view>
      <view wx:for="{{{{list}}}}" wx:key="id" class="item">
        {{{{item.name}}}}
      </view>
    </block>
  </view>
</view>
"""


def tpl_page_wxss():
    return """.page {
  padding: 32rpx;
}

.page__hd {
  padding: 40rpx 0;
}

.page__title {
  font-size: 40rpx;
  font-weight: 600;
  color: #1a1a1a;
}

.page__desc {
  margin-top: 12rpx;
  font-size: 26rpx;
  color: #888888;
}

.page__bd {
  margin-top: 24rpx;
}

.item {
  padding: 24rpx;
  margin-bottom: 16rpx;
  background: #ffffff;
  border-radius: 12rpx;
  font-size: 28rpx;
}

.empty,
.loading {
  padding: 60rpx;
  text-align: center;
  color: #999999;
  font-size: 28rpx;
}
"""


def tpl_page_json(title, using=None, skyline=False):
    cfg = {"usingComponents": using or {}}
    if title:
        cfg["navigationBarTitleText"] = title
    if skyline:
        cfg["renderer"] = "skyline"
        cfg["componentFramework"] = "glass-easel"
        cfg["disableScroll"] = True
        cfg["navigationStyle"] = "custom"
    return json.dumps(cfg, ensure_ascii=False, indent=2) + "\n"


def tpl_component_js(name, ts=False):
    camel = to_camel(name)
    return f"""// components/{name}
Component({{
  options: {{
    multipleSlots: true
  }},

  properties: {{
    // 示例属性：外部传入的数据
    text: {{
      type: String,
      value: ''
    }},
    disabled: {{
      type: Boolean,
      value: false
    }}
  }},

  data: {{
    innerCount: 0
  }},

  lifetimes: {{
    attached() {{
      // 组件实例进入页面节点树时执行
    }},
    detached() {{
      // 组件实例被从页面节点树移除时执行
    }}
  }},

  methods: {{
    on{camel}Tap() {{
      if (this.data.disabled) return
      this.setData({{ innerCount: this.data.innerCount + 1 }})
      this.triggerEvent('tap', {{ count: this.data.innerCount }})
    }}
  }}
}})
"""


def tpl_component_wxml(name):
    return f"""<!--components/{name}-->
<view class="{name}" bindtap="on{to_camel(name)}Tap">
  <slot name="prefix"></slot>
  <text class="{name}__text">{{{{text}}}}</text>
  <slot></slot>
</view>
"""


def tpl_component_wxss(name):
    return f""".{name} {{
  display: inline-flex;
  align-items: center;
  padding: 12rpx 24rpx;
}}

.{name}__text {{
  font-size: 28rpx;
  color: #333333;
}}
"""


def tpl_component_json():
    return json.dumps({"component": True, "usingComponents": {}}, ensure_ascii=False, indent=2) + "\n"


def tpl_cloud_func(name):
    return """// 云函数入口文件：%s
const cloud = require('wx-server-sdk')

cloud.init({ env: cloud.DYNAMIC_CURRENT_ENV })

// 云函数入口函数
exports.main = async (event, context) => {
  const wxContext = cloud.getWXContext()
  return {
    event,
    openid: wxContext.OPENID,
    appid: wxContext.APPID,
    unionid: wxContext.UNIONID
  }
}
""" % name


def tpl_cloud_pkg(name):
    return json.dumps({
        "name": name,
        "version": "1.0.0",
        "description": f"{name} 云函数",
        "main": "index.js",
        "dependencies": {"wx-server-sdk": "~2.6.3"}
    }, ensure_ascii=False, indent=2) + "\n"


def to_camel(name):
    parts = re_split(name)
    return "".join(p.capitalize() for p in parts)


def re_split(name):
    out, cur = [], ""
    for ch in name:
        if ch.isalnum():
            cur += ch
        else:
            if cur:
                out.append(cur)
            cur = ""
    if cur:
        out.append(cur)
    return out or [name]


# --------------------------------------------------------------------------- #
# 工具
# --------------------------------------------------------------------------- #
def out(payload, code=0):
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    sys.exit(code)


def write_file(path: Path, content: str, force=False):
    """写文件；存在且非 force 时跳过。返回 created / updated / skipped。"""
    existed = path.exists()
    if existed and not force:
        return "skipped"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return "updated" if existed else "created"


def load_app_json(mp_root: Path):
    p = mp_root / "app.json"
    if not p.exists():
        out({"ok": False, "error": f"未找到 app.json: {p}",
             "hint": "确认 --project 指向小程序根目录；新项目可先执行 init"})
    cfg = None
    try:
        cfg = json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception as e:
        out({"ok": False, "error": f"app.json 解析失败: {e}", "hint": "检查是否有注释或多余逗号"})
    return p, cfg


def save_app_json(path: Path, cfg):
    path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def register_page(mp_root: Path, page_path: str, subpackage: str = None):
    """把页面注册进 app.json（主包或指定分包），返回 (changed, note)"""
    path, cfg = load_app_json(mp_root)
    page_path = page_path.lstrip("/")
    key = None
    for k in ("subPackages", "subpackages"):
        if k in cfg:
            key = k
    target_list = cfg.setdefault("pages", [])

    if subpackage:
        subs = cfg.setdefault(key or "subPackages", [])
        hit = None
        for s in subs:
            root = (s.get("root") or "").rstrip("/")
            if root == subpackage.rstrip("/") or s.get("name") == subpackage:
                hit = s
                break
        if hit is None:
            return False, f"分包 {subpackage} 不存在，已跳过注册（请先在 app.json 的 subPackages 中创建）"
        root = (hit.get("root") or "").rstrip("/")
        if page_path.startswith(root + "/"):
            rel = page_path[len(root) + 1:]
        else:
            rel = page_path
        if rel in hit.setdefault("pages", []):
            return False, "已注册（跳过）"
        hit["pages"].append(rel)
    else:
        if page_path in target_list:
            return False, "已注册（跳过）"
        target_list.append(page_path)

    save_app_json(path, cfg)
    return True, f"已写入 {path}"


def unregister_page(mp_root: Path, page_path: str):
    path, cfg = load_app_json(mp_root)
    page_path = page_path.lstrip("/")
    removed = False
    if page_path in cfg.get("pages", []):
        cfg["pages"].remove(page_path)
        removed = True
    for k in ("subPackages", "subpackages"):
        for s in cfg.get(k, []) or []:
            root = (s.get("root") or "").rstrip("/")
            rel = page_path[len(root) + 1:] if root and page_path.startswith(root + "/") else page_path
            if rel in s.get("pages", []):
                s["pages"].remove(rel)
                removed = True
    if removed:
        save_app_json(path, cfg)
    return removed


def add_using_components(mp_root: Path, page_json: Path, comp_name: str, comp_path: str):
    """在页面 json 的 usingComponents 中登记组件"""
    cfg = {}
    if page_json.exists():
        try:
            cfg = json.loads(page_json.read_text(encoding="utf-8-sig"))
        except Exception:
            cfg = {}
    cfg.setdefault("usingComponents", {})[comp_name] = comp_path
    page_json.parent.mkdir(parents=True, exist_ok=True)
    page_json.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- #
# 子命令
# --------------------------------------------------------------------------- #
def cmd_init(args):
    root = Path(args.dir).expanduser().resolve()
    if root.exists() and any(root.iterdir()) and not args.force:
        out({"ok": False, "error": f"目录非空: {root}", "hint": "换一个目录，或加 --force 覆盖写入"})

    name = args.name or root.name
    created = []
    created.append({"file": "app.js", "status": write_file(root / "app.js", tpl_app_js(), args.force)})
    created.append({"file": "app.json", "status": write_file(
        root / "app.json", tpl_app_json(name, skyline=(args.type == "skyline"), ts=args.ts), args.force)})
    created.append({"file": "app.wxss", "status": write_file(root / "app.wxss", tpl_app_wxss(), args.force)})
    created.append({"file": "project.config.json", "status": write_file(
        root / "project.config.json", tpl_project_config(args.appid, name, cloud=(args.type == "cloud"), ts=args.ts), args.force)})
    created.append({"file": "sitemap.json", "status": write_file(root / "sitemap.json", tpl_sitemap(), args.force)})

    # 首页
    idx = root / "pages" / "index"
    created.append({"file": "pages/index/index.wxml",
                    "status": write_file(idx / "index.wxml", tpl_page_wxml(name), args.force)})
    created.append({"file": "pages/index/index.wxss",
                    "status": write_file(idx / "index.wxss", tpl_page_wxss(), args.force)})
    js = tpl_page_js(name).replace("__PAGE_PATH__", "pages/index/index")
    created.append({"file": "pages/index/index.js", "status": write_file(idx / "index.js", js, args.force)})
    created.append({"file": "pages/index/index.json",
                    "status": write_file(idx / "index.json", tpl_page_json(name), args.force)})

    if args.type == "cloud":
        cf = root / "cloudfunctions" / "quickstart"
        created.append({"file": "cloudfunctions/quickstart/index.js",
                        "status": write_file(cf / "index.js", tpl_cloud_func("quickstart"), args.force)})
        created.append({"file": "cloudfunctions/quickstart/package.json",
                        "status": write_file(cf / "package.json", tpl_cloud_pkg("quickstart"), args.force)})

    out({
        "ok": True,
        "command": "init",
        "project": str(root),
        "type": args.type,
        "files": created,
        "next": [
            f"用微信开发者工具打开 {root}（或 mp_cli.py open --project {root}）",
            f"体检：python3 scripts/mp_inspect.py check --project {root} --md",
            "新增页面：mp_scaffold.py page --project %s --path pages/list/list" % root,
        ],
    })


def cmd_page(args):
    mp_root = Path(args.project).expanduser().resolve()
    page_path = args.path.strip("/")
    if "/" not in page_path:
        out({"ok": False, "error": "页面路径需形如 pages/goods/detail",
             "hint": "小程序页面必须位于某个目录下，例如 pages/index/index"})
    if not page_path.startswith("pages/") and not args.subpackage:
        # 允许自定义，但给出提示
        pass

    title = args.title or Path(page_path).name
    base = mp_root / page_path
    ext_js = ".ts" if args.ts else ".js"
    js = tpl_page_js(title, args.ts).replace("__PAGE_PATH__", page_path)

    files = {
        f"{page_path}.wxml": tpl_page_wxml(title),
        f"{page_path}.wxss": tpl_page_wxss(),
        f"{page_path}{ext_js}": js,
        f"{page_path}.json": tpl_page_json(title, skyline=args.skyline),
    }
    result = [{"file": k, "status": write_file(mp_root / k, v, args.force)} for k, v in files.items()]

    registered, note = (False, "已按 --no-register 跳过注册")
    if not args.no_register:
        registered, note = register_page(mp_root, page_path, args.subpackage)

    out({
        "ok": True,
        "command": "page",
        "page": page_path,
        "dir": str(base),
        "files": result,
        "registered": registered,
        "note": note,
        "next": f"打开 {page_path}.wxml 编写视图，{page_path}{ext_js} 编写逻辑",
    })


def cmd_component(args):
    mp_root = Path(args.project).expanduser().resolve()
    dir_name = args.dir.strip("/") or "components"
    comp_dir = mp_root / dir_name / args.name
    ext_js = ".ts" if args.ts else ".js"

    files = {
        f"{dir_name}/{args.name}/{args.name}.wxml": tpl_component_wxml(args.name),
        f"{dir_name}/{args.name}/{args.name}.wxss": tpl_component_wxss(args.name),
        f"{dir_name}/{args.name}/{args.name}{ext_js}": tpl_component_js(args.name, args.ts),
        f"{dir_name}/{args.name}/{args.name}.json": tpl_component_json(),
    }
    result = [{"file": k, "status": write_file(mp_root / k, v, args.force)} for k, v in files.items()]

    registered_in = None
    if args.register:
        page_json = mp_root / args.register
        # 从 json 所在目录回到项目根需要 "../" * 目录深度
        depth = len([p for p in Path(args.register).parent.parts if p not in (".", "")])
        rel_path = ("../" * depth) + f"{dir_name}/{args.name}/{args.name}"
        if depth == 0:
            rel_path = f"./{dir_name}/{args.name}/{args.name}"
        add_using_components(mp_root, page_json, args.name, rel_path)
        registered_in = args.register

    out({
        "ok": True,
        "command": "component",
        "name": args.name,
        "dir": str(comp_dir),
        "files": result,
        "registeredIn": registered_in,
        "usage": '<%s text="hello" bind:tap="onTap" />' % args.name,
    })


def cmd_cloudfunc(args):
    mp_root = Path(args.project).expanduser().resolve()
    proj_cfg_path = mp_root / "project.config.json"
    cloud_root = None
    if proj_cfg_path.exists():
        try:
            cloud_root = json.loads(proj_cfg_path.read_text(encoding="utf-8-sig")).get("cloudfunctionRoot")
        except Exception:
            cloud_root = None
    cloud_root = cloud_root or "cloudfunctions/"
    fn_dir = mp_root / cloud_root / args.name

    result = [
        {"file": str(fn_dir / "index.js"), "status": write_file(fn_dir / "index.js", tpl_cloud_func(args.name), args.force)},
        {"file": str(fn_dir / "package.json"), "status": write_file(fn_dir / "package.json", tpl_cloud_pkg(args.name), args.force)},
    ]
    out({
        "ok": True,
        "command": "cloudfunc",
        "name": args.name,
        "dir": str(fn_dir),
        "files": result,
        "next": [
            f"在 {fn_dir} 下执行 npm install（或开发者工具右键「上传并部署：云端安装依赖」）",
            f"部署：python3 scripts/mp_cli.py cloud functions deploy --project {mp_root} --env <环境ID> --names {args.name}",
        ],
    })


def cmd_remove(args):
    mp_root = Path(args.project).expanduser().resolve()
    page_path = args.path.strip("/")
    removed = unregister_page(mp_root, page_path)
    deleted = []
    if args.files:
        for ext in (".js", ".ts", ".wxml", ".wxss", ".json"):
            f = mp_root / (page_path + ext)
            if f.exists():
                f.unlink()
                deleted.append(str(f.relative_to(mp_root)))
        d = mp_root / page_path
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()
            deleted.append(str(d.relative_to(mp_root)) + "/")
    out({
        "ok": True,
        "command": "remove",
        "page": page_path,
        "unregistered": removed,
        "deleted": deleted,
        "hint": "" if args.files else "仅注销注册，加 --files 可同时删除文件",
    })


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="微信小程序开发脚手架")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="初始化项目")
    p.add_argument("--dir", required=True)
    p.add_argument("--appid", default="")
    p.add_argument("--name", default="")
    p.add_argument("--type", choices=["native", "cloud", "skyline"], default="native")
    p.add_argument("--ts", action="store_true")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("page", help="生成页面")
    p.add_argument("--project", "-p", required=True)
    p.add_argument("--path", required=True, help="如 pages/goods/detail")
    p.add_argument("--subpackage", default="", help="注册到指定分包（root 或 name）")
    p.add_argument("--title", default="")
    p.add_argument("--ts", action="store_true")
    p.add_argument("--skyline", action="store_true", help="页面 json 使用 Skyline 配置")
    p.add_argument("--no-register", action="store_true")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_page)

    p = sub.add_parser("component", help="生成自定义组件")
    p.add_argument("--project", "-p", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--dir", default="components")
    p.add_argument("--ts", action="store_true")
    p.add_argument("--register", default="", help="顺便注册到某个页面 json，如 pages/index/index.json")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_component)

    p = sub.add_parser("cloudfunc", help="生成云函数")
    p.add_argument("--project", "-p", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_cloudfunc)

    p = sub.add_parser("remove", help="移除页面")
    p.add_argument("--project", "-p", required=True)
    p.add_argument("--path", required=True)
    p.add_argument("--files", action="store_true")
    p.set_defaults(func=cmd_remove)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
