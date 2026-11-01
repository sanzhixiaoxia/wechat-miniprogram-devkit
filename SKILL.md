---
name: wechat-miniprogram-devkit
displayName: 微信小程序开发调试助手
slug: wxapp-devkit
version: 1.0.1
summary: 面向微信小程序的一站式开发、浏览（项目体检/路由/依赖分析）与调试（开发者工具 CLI、自动化 E2E、预览上传）能力
license: MIT
tags: [微信小程序, 小程序, 开发, 调试, 自动化, CI, miniprogram]
description: >-
  微信小程序（Mini Program）全生命周期工具箱：开发脚手架、项目浏览体检、真机预览与上传、端到端自动化调试。
  当用户提到「微信小程序 / 小程序 / wxapp / miniprogram / 小程序项目 / app.json / wxml / wxss / 小程序页面 / 小程序组件 /
  小程序预览 / 小程序上传 / 小程序调试 / 小程序自动化 / 小程序截图 / 云开发 / Skyline / 分包」等意图时使用本技能。
  能力包括：初始化项目与生成页面/组件/云函数（mp_scaffold.py）、解析路由与依赖并输出体检报告（mp_inspect.py）、
  调用微信开发者工具 CLI 打开项目/构建 npm/登录/预览/上传（mp_cli.py）、
  用 miniprogram-automator 跑端到端交互并截图抓日志（mp_auto.js）、用 miniprogram-ci 免 IDE 预览上传（mp_ci.py）。
---

# 微信小程序开发调试助手

给 Agent 使用的小程序工程化工具箱：**开发 → 浏览 → 调试 → 发布**全覆盖。

## 触发场景

- **开发**：新建小程序项目、加页面/组件/云函数、改造已有项目、Skyline 迁移
- **浏览**：看懂一个陌生小程序项目（路由表、分包、组件依赖、体积、孤立文件、配置风险）
- **调试**：打开开发者工具、真机预览、抓 console/异常日志、自动化点击流程并截图、定位报错
- **发布**：构建 npm、上传体验版/正式版、CI 免 IDE 预览

## 环境前提

| 能力 | 依赖 | 缺失时的行为 |
|---|---|---|
| 项目浏览 / 脚手架 | 无（纯 Python 3） | 始终可用 |
| 开发者工具 CLI、自动化 | 本机安装「微信开发者工具」+ 设置 → 安全设置 → 开启服务端口 | 脚本给出明确安装/开启指引，不崩溃 |
| CI 预览 / 上传 | `miniprogram-ci` + 代码上传密钥 + IP 白名单 | 提示安装命令与密钥获取路径 |

> 微信开发者工具只支持 macOS / Windows。Linux（含本沙箱）只能跑「浏览 / 脚手架 / CI」三类能力，
> CLI 与自动化类命令会自动降级并提示原因，Agent 应据此改用其他能力或请用户在本地机器上执行。

## 脚本总览

所有脚本统一约定：`--json` 输出结构化 JSON（默认），`--md` 输出 Markdown 表格（给人看）。
失败时同样输出 JSON 且退出码非 0，字段为 `{"ok": false, "error": "...", "hint": "..."}`。

### 1. 浏览与体检：`scripts/mp_inspect.py`

```bash
python3 scripts/mp_inspect.py summary  --project /path/to/mp [--json|--md]
python3 scripts/mp_inspect.py routes   --project /path/to/mp          # 路由表 / tabBar / 分包 / 文件完整性
python3 scripts/mp_inspect.py deps     --project /path/to/mp          # 组件依赖图 / 未注册组件 / 孤立组件
python3 scripts/mp_inspect.py size     --project /path/to/mp          # 主包/分包/资源体积与超限告警
python3 scripts/mp_inspect.py search   --project /path/to/mp --kw "setStorage" [--ext .js] [--regex]
python3 scripts/mp_inspect.py tree     --project /path/to/mp [--depth 3]
python3 scripts/mp_inspect.py check    --project /path/to/mp          # 综合体检：问题清单 + 修复建议
python3 scripts/mp_inspect.py all      --project /path/to/mp --md
```

`check` 会输出 `issues[]`（含 severity / file / message / fix），Agent 应优先按 `error` 级别修复。

### 2. 开发脚手架：`scripts/mp_scaffold.py`

```bash
python3 scripts/mp_scaffold.py init  --dir ./myapp --appid wx123 --name MyApp [--type native|cloud|skyline] [--ts]
python3 scripts/mp_scaffold.py page  --project ./myapp --path pages/goods/detail [--subpackage pkgA] [--ts] [--title 商品详情]
python3 scripts/mp_scaffold.py component --project ./myapp --name goods-card [--dir components] [--ts]
python3 scripts/mp_scaffold.py cloudfunc --project ./myapp --name login
python3 scripts/mp_scaffold.py remove --project ./myapp --path pages/goods/detail
```

约定：生成页面/组件时**自动写入 app.json 注册**（`--no-register` 可关闭），幂等（已存在则跳过并提示）。

### 3. 开发者工具控制：`scripts/mp_cli.py`

```bash
python3 scripts/mp_cli.py detect                                   # 探测本机 cli 路径（macOS/Win/WSL/Linux）
python3 scripts/mp_cli.py open      --project /path/to/mp
python3 scripts/mp_cli.py auto      --project /path/to/mp --port 9420   # 开启自动化端口
python3 scripts/mp_cli.py preview   --project /path/to/mp --qr-format image --qr-output /tmp/qr.png
python3 scripts/mp_cli.py upload    --project /path/to/mp --version 1.0.0 --desc "修复若干问题"
python3 scripts/mp_cli.py build-npm --project /path/to/mp
python3 scripts/mp_cli.py login     [--qr-format base64 --qr-output /tmp/qr.txt]
python3 scripts/mp_cli.py islogin
python3 scripts/mp_cli.py cloud env list --project /path/to/mp
python3 scripts/mp_cli.py quit
python3 scripts/mp_cli.py raw -- --lang zh -h                      # 任意命令透传
```

CLI 路径可用环境变量 `MP_CLI_PATH` 覆盖；找不到时返回可执行指引，不抛异常。

### 4. 端到端自动化调试：`scripts/mp_auto.js`

需先 `npm i miniprogram-automator`（脚本会检测并提示）。

```bash
node scripts/mp_auto.js screenshot --project /path/to/mp --page /pages/index/index --out /tmp/shot.png
node scripts/mp_auto.js logs       --project /path/to/mp --page /pages/index/index --seconds 10
node scripts/mp_auto.js data       --project /path/to/mp --selector ".list" --data-path list
node scripts/mp_auto.js flow       --project /path/to/mp --steps /tmp/steps.json --out /tmp/autotest
```

`--steps` 支持声明式流程（推荐）：

```json
{
  "launch": "/pages/index/index",
  "steps": [
    {"action": "waitFor", "selector": ".goods-item"},
    {"action": "tap", "selector": "#buy-btn"},
    {"action": "input", "selector": "input", "value": "iphone"},
    {"action": "assertText", "selector": ".title", "expect": "确认订单"},
    {"action": "mockWx", "method": "getLocation", "result": {"latitude": 39.9, "longitude": 116.4}},
    {"action": "screenshot", "name": "after-tap"},
    {"action": "navigate", "url": "/pages/order/confirm", "type": "navigateTo"},
    {"action": "wxml", "selector": ".box"}
  ]
}
```

支持的 action：`waitFor / tap / longpress / input / trigger / setData / callMethod / assertText / assertData /
assertExist / mockWx / restoreWx / navigate / wait / screenshot / wxml / scroll`。
输出 JSON 报告：每步 ok/耗时/实际值，console 日志与页面 JS 异常单独汇总。

### 5. 免 IDE 预览与上传：`scripts/mp_ci.py`

```bash
python3 scripts/mp_ci.py preview --project ./myapp --appid wx123 --key ./private.wx123.key \
        --out /tmp/qr.png [--page pages/index/index] [--query "id=1"] [--robot 1]
python3 scripts/mp_ci.py upload  --project ./myapp --appid wx123 --key ./private.wx123.key \
        --version 1.0.0 --desc "首次上传" [--robot 1]
python3 scripts/mp_ci.py build-npm --project ./myapp --appid wx123 --key ./private.wx123.key
python3 scripts/mp_ci.py cloud-function --project ./myapp --appid wx123 --key ./private.wx123.key \
        --env prod-1a2b --name login --path ./cloudfunctions/login
```

前置检查：项目目录、project.config.json、私钥文件、miniprogram-ci 是否安装，缺什么直接说清楚。

## 推荐工作流

1. **接手陌生项目** → `mp_inspect.py check`（先看清结构，再动手改）
2. **写新功能** → `mp_scaffold.py page/component` 生成骨架 → 填充业务代码 → `mp_inspect.py check` 复查
3. **本地调试** → `mp_cli.py open` 打开工具 → `mp_auto.js flow` 跑交互验证 + 截图
   （或 `mp_cli.py preview` 出二维码真机看）
4. **提测/发布** → `mp_cli.py build-npm` → `mp_ci.py upload`（CI 场景免 IDE）

## 常见报错快查

遇到具体报错时读 `references/troubleshooting.md`，覆盖：`page not found`、路由跳转失败、组件未注册、
`setData` 数据量过大、request 合法域名、登录态失效、npm 构建失败、Skyline 样式异常、包体积超限、
云函数部署失败、CI 上传 1004/密钥 IP 白名单等高频问题。

## 参考资料

- `references/dev-guide.md` — 项目结构、app.json/page.json 全配置、生命周期、Skyline 迁移要点
- `references/cli-and-ci.md` — 开发者工具 CLI 与 miniprogram-ci 完整命令速查
- `references/automation-api.md` — miniprogram-automator（MiniProgram/Page/Element）API 速查
- `references/troubleshooting.md` — 报错排查手册

## 安全与边界

- 私钥（`.key`）、appid 等敏感信息只在用户显式提供时使用，不写入 Skill 包、不打印完整内容
- 仅操作用户自己的项目源码；**不做** 他人小程序的反编译、抓包破解、绕过审核等行为
- 涉及上传/发布等不可逆操作前，先向用户确认版本号与备注
