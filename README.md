# 微信小程序开发调试助手（wechat-miniprogram-devkit）

给 AI Agent（WorkBuddy / Claude Code / Codex 等）使用的微信小程序工程化技能：
**开发 → 浏览 → 调试 → 发布** 全链路，脚本化、可解析、失败有明确指引。

## 能做什么

| 场景 | 命令 | 依赖 |
|---|---|---|
| **开发**：初始化项目 / 生成页面 / 组件 / 云函数，自动维护 app.json 注册 | `scripts/mp_scaffold.py` | 无（Python 3） |
| **浏览**：项目概览、路由表、组件依赖图、包体积、代码搜索、目录树、综合体检 | `scripts/mp_inspect.py` | 无（Python 3） |
| **调试**：驱动开发者工具打开/预览/上传/构建 npm/云开发 | `scripts/mp_cli.py` | 微信开发者工具 + 开启服务端口 |
| **调试**：端到端自动化（点击/输入/断言/截图/抓 console 与 JS 异常） | `scripts/mp_auto.js` | 开发者工具 + `miniprogram-automator` |
| **发布**：免 IDE 预览出码、上传、构建 npm、部署云函数 | `scripts/mp_ci.py` | `miniprogram-ci` + 上传密钥 + IP 白名单 |

## 快速开始

```bash
# 1. 先看懂一个已有项目（最常用入口）
python3 scripts/mp_inspect.py check --project /path/to/miniprogram --md

# 2. 生成页面并自动注册路由
python3 scripts/mp_scaffold.py page --project /path/to/miniprogram --path pages/order/list --title 订单列表

# 3. 打开开发者工具 / 预览出二维码
python3 scripts/mp_cli.py open    --project /path/to/miniprogram
python3 scripts/mp_cli.py preview --project /path/to/miniprogram --qr-format image --qr-output /tmp/qr.png

# 4. 跑一段自动化交互（点击 + 断言 + 截图）
node scripts/mp_auto.js flow --project /path/to/miniprogram \
     --steps assets/examples/steps.example.json --out /tmp/auto

# 5. CI 免 IDE 上传（先干跑看命令）
python3 scripts/mp_ci.py upload --project ./dist --appid wx123 \
     --key ./private.wx123.key --version 1.0.0 --desc "release" --dry-run
```

## 输出约定

所有脚本统一输出 JSON（默认）或 Markdown（`--md`），失败时同样返回结构化结果：

```json
{"ok": false, "error": "...", "hint": "可执行的具体建议"}
```

Agent 可直接解析 `ok` 字段判断成败、按 `hint` 自动修复或向用户求助。

## 环境要求

- Python 3.7+（浏览 / 脚手架 / CLI 封装 / CI 封装）
- Node.js 8+（仅自动化脚本需要，且需 `npm i miniprogram-automator`）
- 微信开发者工具（仅 macOS / Windows；CLI 与自动化能力依赖它，并需在「设置 → 安全设置」开启服务端口）
- `miniprogram-ci`（仅 CI 预览/上传需要：`npm i -g miniprogram-ci`）

在 Linux / CI 环境下，CLI 与自动化命令会自动降级并给出明确指引，不会崩溃。

## 目录结构

```
wechat-miniprogram-devkit/
├── SKILL.md                      # Agent 入口：触发词、能力、工作流
├── README.md
├── scripts/
│   ├── mp_inspect.py             # 浏览与体检
│   ├── mp_scaffold.py            # 开发脚手架
│   ├── mp_cli.py                 # 开发者工具 CLI 封装
│   ├── mp_auto.js                # 端到端自动化调试
│   └── mp_ci.py                  # miniprogram-ci 封装
├── references/
│   ├── dev-guide.md              # 结构 / 配置 / 生命周期 / Skyline
│   ├── cli-and-ci.md             # CLI 与 miniprogram-ci 速查
│   ├── automation-api.md         # automator API 速查
│   └── troubleshooting.md        # 常见报错排查手册
└── assets/examples/
    └── steps.example.json        # 自动化流程示例
```

## 安全边界

- 私钥、appid 仅在用户显式提供时使用，不写入技能包、不打印完整内容
- 只操作用户自己的项目源码，不做他人小程序的反编译、抓包破解等行为
- 上传/发布等不可逆操作前应先与用户确认版本号与备注

## License

MIT
