# 开发者工具 CLI 与 miniprogram-ci 速查

## 一、开发者工具 CLI（依赖本机 IDE）

**位置**
- macOS：`/Applications/wechatwebdevtools.app/Contents/MacOS/cli`
- Windows：`C:/Program Files (x86)/Tencent/微信web开发者工具/cli.bat`
- 前置：设置 → 安全设置 → **开启服务端口**；返回码 0 正常，-1 错误
- 帮助：`cli -h`，中文帮助：`cli --lang zh -h`

**命令索引**

| 分类 | 命令 | 说明 |
|---|---|---|
| 登录 | `cli login` / `cli islogin` | 扫码登录 / 查询登录态 |
| 预览 | `cli preview --project <dir>` | 生成预览二维码 |
| 自动预览 | `cli auto-preview --project <dir>` | 无需扫码，自动推送到已登录微信 |
| 上传 | `cli upload --project <dir> -v 1.0.0 -d "备注"` | 上传代码（需登录） |
| 自动化 | `cli auto --project <dir> --auto-port 9420` | 开启自动化 WebSocket 端口 |
| 构建 npm | `cli build-npm --project <dir>` | 生成 miniprogram_npm |
| 清缓存 | `cli cache --clean all --project <dir>` | 编译异常时先清缓存 |
| 窗口 | `cli open/close/quit` | 打开项目 / 关闭项目 / 退出工具 |
| 云开发 | `cli cloud env list`、`cli cloud functions list/deploy/inc-deploy/download` | 云环境与云函数管理 |

**常用参数**

| 参数 | 说明 |
|---|---|
| `--project` | 项目绝对路径（不能是相对路径） |
| `--appid` / `--ext-appid` | 第三方平台场景（有 `--project` 时忽略） |
| `--lang zh\|en` | 输出语言 |
| `--port` | 工具 HTTP 服务端口 |
| `--qr-format terminal\|image\|base64` | 二维码格式 |
| `--qr-output <path>` | 二维码输出路径 |
| `--info-output <path>` | 上传/预览附加信息（包体积等）JSON |
| `--compile-condition '<json>'` | 自定义编译条件，如 `{"pathName":"pages/index/index","query":"id=1"}` |
| `--version/-v`、`--desc/-d` | 上传版本号与备注 |

**示例**

```bash
cli open --project /Users/me/demo
cli build-npm --project /Users/me/demo
cli preview --project /Users/me/demo --qr-format image --qr-output /tmp/qr.jpg
cli upload  --project /Users/me/demo -v 1.2.0 -d "修复首页白屏" -i /tmp/info.json
cli auto    --project /Users/me/demo --auto-port 9420
cli cloud functions deploy --project /Users/me/demo --env prod-xxx --names login --remote-npm-install
```

## 二、miniprogram-ci（免 IDE，CI/CD 首选）

**安装**：`npm i -g miniprogram-ci`（或项目内 `npm i miniprogram-ci`）

**前置**
1. 微信公众平台 → 管理 → 开发管理 → 开发设置 → 小程序代码上传 → 生成密钥（`.key`）
2. 同一页面配置 **IP 白名单**（未配置会调用失败）
3. 密钥不明文保存，遗失必须重置

**CLI 参数**

| 参数 | 说明 |
|---|---|
| `--pp` | 项目路径 |
| `--pkp` | 私钥（.key）路径 |
| `--appid` | 小程序 appid |
| `--uv` | 版本号（upload 必填） |
| `--ud` | 备注 |
| `-r` | CI 机器人编号 1~30（并发不冲突） |
| `--qrcode-format` / `--qrcode-output-dest` | 二维码格式 / 输出路径 |
| `--page-path` / `--search-query` | 预览启动页与参数 |
| `--enable-es6` | ES6 转 ES5 |

```bash
miniprogram-ci preview --pp ./dist --pkp ./private.wx123.key --appid wx123 \
  --qrcode-format image --qrcode-output-dest ./qr.jpg --page-path pages/index/index

miniprogram-ci upload --pp ./dist --pkp ./private.wx123.key --appid wx123 \
  --uv 1.2.0 --ud "release" -r 1 --enable-es6 true

miniprogram-ci build-npm --pp ./dist --pkp ./private.wx123.key --appid wx123
```

**Node API**

```js
const ci = require('miniprogram-ci')
const project = new ci.Project({
  appid: 'wx123', type: 'miniProgram',
  projectPath: './dist', privateKeyPath: './private.wx123.key',
  ignores: ['node_modules/**/*'],
})
await ci.upload({ project, version: '1.2.0', desc: 'release', robot: 1,
  setting: { es6: true, minify: true }, onProgressUpdate: console.log })
await ci.preview({ project, qrcodeFormat: 'image', qrcodeOutputDest: './qr.jpg', robot: 2 })
await ci.buildNpm({ project })
```

返回 `subPackageInfo`（`__FULL__` / `__APP__` / 各分包体积）与 `pluginInfo`。

## 三、两者怎么选

| 维度 | 开发者工具 CLI | miniprogram-ci |
|---|---|---|
| 依赖 | 必须装 IDE | 独立运行 |
| 认证 | IDE 登录态 | 密钥 + IP 白名单 |
| 自动化/云开发 | 完整支持 | 支持云函数/托管上传 |
| 场景 | 本地开发、E2E 测试 | 流水线发布、无人值守 |

## 四、常见失败码

| 现象 | 原因 | 处理 |
|---|---|---|
| 返回 -1 且提示服务端口 | 未开启服务端口 | 设置 → 安全设置 → 开启 |
| `ECONNREFUSED` | 工具未启动 | 先 `cli open` |
| 提示未登录 | 登录态失效 | `cli login` 扫码 |
| 1004 | IP 白名单 | 后台添加当前公网 IP |
| 密钥错误 | key 与 appid 不匹配 | 重新下载密钥 |
| 包体积超限 | 主包 > 2MB | 分包 + 资源 CDN |
