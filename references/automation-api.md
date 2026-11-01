# miniprogram-automator API 速查（端到端自动化）

安装：`npm i miniprogram-automator --save-dev`
前提：开发者工具「设置 → 安全设置」开启 CLI/HTTP 调用；基础库 ≥ 2.7.3；工具 ≥ 1.02.1907232

## 连接

```js
const automator = require('miniprogram-automator')

// 方式一：自行启动（内部调用 cli auto）
const mp = await automator.launch({
  cliPath: 'path/to/cli',      // 可选，默认探测 Mac/Win 标准路径
  projectPath: 'path/to/project', // 必填
  timeout: 30000, port: 9420, account: 'openid',
  projectConfig: { setting: { autoAudits: true } },
})

// 方式二：连接已开启自动化的工具（先 cli auto --auto-port 9420）
const mp2 = await automator.connect({ wsEndpoint: 'ws://localhost:9420' })
```

## MiniProgram

| 方法 | 说明 |
|---|---|
| `navigateTo(url)` / `redirectTo(url)` / `reLaunch(url)` / `switchTab(url)` / `navigateBack()` | 路由跳转，返回 Page |
| `currentPage()` / `pageStack()` | 当前页 / 页面栈 |
| `systemInfo()` | 系统信息 |
| `callWxMethod(method, ...args)` | 调用 `wx.xxx`（异步方法不用传 success/fail） |
| `mockWxMethod(method, result\|fn)` / `restoreWxMethod(method)` | mock 与还原 wx API |
| `evaluate(fnOrString, ...args)` | 在 AppService 注入执行（不能闭包引用外部变量） |
| `exposeFunction(name, fn)` | 向小程序暴露方法（用于监听事件） |
| `pageScrollTo(top)` | 页面滚动 |
| `screenshot({path})` | 截图（不传 path 返回 base64） |
| `remote(auto)` | 开启真机调试（打印二维码，扫码后继续） |
| `testAccounts()` | 多账号调试用户列表 |
| `stopAudits({path})` | 停止体验评分并取报告 |
| `close()` / `disconnect()` | 关闭窗口 / 仅断开 |

**事件**：`mp.on('console', msg => {})`（`msg.type` / `msg.args`）、`mp.on('exception', err => {})`（`err.message` / `err.stack`）

## Page

| 成员 | 说明 |
|---|---|
| `path` / `query` | 页面路径 / 参数 |
| `$(selector)` / `$$(selector)` | 取元素 / 元素数组（**不能穿透自定义组件**，需用 `element.$`） |
| `waitFor(string\|number\|Function)` | 选择器出现 / 等待 ms / 断言函数为真 |
| `data(path?)` / `setData(obj)` | 读/写渲染数据 |
| `size()` / `scrollTop()` | 页面尺寸 / 滚动位置 |
| `callMethod(method, ...args)` | 调用页面方法 |

## Element

| 成员 | 说明 |
|---|---|
| `tagName` | 小写标签名 |
| `$` / `$$` | 元素内查找 |
| `text()` / `value()` / `wxml()` / `outerWxml()` | 文本 / 值 / WXML |
| `attribute(name)` / `property(name)` / `style(name)` | 特性 / 属性 / 样式值 |
| `size()` / `offset()` | 尺寸 / 绝对坐标 |
| `tap()` / `longpress()` | 点击 / 长按 |
| `input(value)` | 输入（仅 input、textarea） |
| `trigger(type, detail)` | 触发自定义事件（不改变组件状态） |
| `touchstart/touchmove/touchend({touches, changedTouches})` | 触摸序列 |
| `callMethod(method, ...args)` / `data(path?)` / `setData(obj)` | 自定义组件实例方法/数据 |
| `scrollTo(x,y)` / `scrollWidth()` / `scrollHeight()` | scroll-view |
| `swipeTo(index)` / `slideTo(value)` / `moveTo(x,y)` / `callContextMethod()` | swiper / slider / movable-view / video |

## 典型脚本

```js
const automator = require('miniprogram-automator')

;(async () => {
  const mp = await automator.launch({ projectPath: '/path/to/project' })
  const logs = []
  mp.on('console', (m) => logs.push(`[${m.type}] ${m.args.join(' ')}`))
  mp.on('exception', (e) => logs.push(`[error] ${e.message}`))

  const page = await mp.reLaunch('/pages/index/index')
  await page.waitFor('.goods-item')
  await (await page.$('#buy')).tap()
  await page.setData({ count: 1 })
  await mp.mockWxMethod('getLocation', { latitude: 39.9, longitude: 116.4 })
  await mp.screenshot({ path: './shot.png' })

  console.log(JSON.stringify({ logs }, null, 2))
  await mp.close()
})()
```

## 真机自动化

`mp.remote()` 后扫码连接，或 `mp.remote(true)` 自动调起（Android 微信 7.0.6+ / iOS 6.6.7+）。
真机模式下 `screenshot` 不可用（仅模拟器支持）。

## 排错

| 现象 | 处理 |
|---|---|
| launch 超时 | 确认已开启服务端口；加 `--timeout`；或改用 `cli auto` + `connect` |
| `$` 取不到元素 | 自定义组件内部节点需 `page.$('my-comp')` 后再 `element.$('.inner')` |
| 元素已渲染但操作无效 | 先 `page.waitFor(selector)` 等渲染完成 |
| mock 不生效 | 确认基础库 ≥ 2.9.5；用完 `restoreWxMethod` |
| 选择器不支持 | 仅支持部分 CSS 选择器（同 WXSS） |
