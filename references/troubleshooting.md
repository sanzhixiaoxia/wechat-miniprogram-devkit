# 小程序常见报错排查手册

## 1. 路由与页面

| 报错 / 现象 | 原因 | 处理 |
|---|---|---|
| `pages/xxx/xxx not found` / `page "pages/xxx" is not found` | 页面未在 `app.json` 的 `pages` 注册，或路径写错 | 注册页面并确认路径无后缀、无前导 `/`；用 `mp_inspect.py routes` 核对 |
| `navigateTo:fail page "..." is not found` | 目标页未注册 / 跳到了 tabBar 页 | tabBar 页必须用 `switchTab` |
| `switchTab:fail page "..." is not found` | 目标不是 tabBar 页 | 只能跳 tabBar 中配置的页面 |
| `navigateTo:fail webview count limit exceed` | 页面栈超过 10 层 | 用 `redirectTo` 或 `reLaunch`；长流程改路由设计 |
| 页面白屏但无报错 | onLoad 抛错被吞 / data 未初始化 / 组件渲染阻塞 | 先看 Console 与 `mp_auto.js logs` 抓异常 |
| 修改代码模拟器无变化 | 文件监听失效或缓存 | `cli reset-fileutils --project <dir>` 或 `cli cache --clean all` |

## 2. 组件

| 报错 | 原因 | 处理 |
|---|---|---|
| `Component "xxx" is not found in path "..."` | `usingComponents` 路径错误或文件缺失 | 路径大小写敏感；确认 `.json` 里 `component: true`；`mp_inspect.py deps` 检查断链 |
| 组件样式不生效 | 样式隔离 | 用 `options: { styleIsolation: 'apply-shared' }`，或把样式写到页面 wxss |
| 自定义组件事件不触发 | `triggerEvent` 名与 `bind:` 不一致 | 事件名统一小写，用 `bind:myevent` |
| slot 不显示 | 未开启多 slot | `options: { multipleSlots: true }` 并给 slot 命名 |
| 组件内 `this.data` 拿不到父传值 | properties 未声明 | 在 `properties` 声明类型与默认值 |

## 3. 数据与渲染

| 报错 | 原因 | 处理 |
|---|---|---|
| `setData:fail data exceed max size` | 单次数据过大 | 按路径更新、分页加载、列表用虚拟列表 |
| 数据更新但视图不变 | 直接改 `this.data.x` 未走 setData | 必须用 `this.setData({x})` |
| `wx:key` 警告 | 列表缺 key 或重复 | 给唯一字段 `wx:key="id"`，或用 `*this` |
| WXML 里函数不可用 | WXML 不支持直接调用 JS 方法 | 用 `wxs` 模块或提前算好放进 data |

## 4. 网络与域名

| 报错 | 原因 | 处理 |
|---|---|---|
| `url not in domain list` | 域名未在后台配置 | 后台「开发设置 → 服务器域名」添加；本地调试勾「不校验合法域名」 |
| `request:fail ssl hand shake error` | 证书问题 | 必须是受信任 CA 的 https 证书，TLS ≥ 1.2 |
| `request:fail -102:net::ERR_...` | 网络不通 / 代理 | 检查网络与代理；`ci.proxy()` 可给 CI 配代理 |
| 本地能请求、真机失败 | 真机走正式域名校验 | 关闭「不校验合法域名」前先配好域名 |

## 5. 登录与授权

| 现象 | 原因 | 处理 |
|---|---|---|
| `wx.login` 返回 code 但换不到 openid | 后端未用 appsecret 调 code2Session | 校验 appid/appsecret 与请求参数 |
| `getUserInfo` 返回匿名数据 | 旧接口已调整 | 用 `wx.getUserProfile` 或 `open-type="chooseAvatar"` 等授权方式 |
| 手机号拿不到 | 需企业主体 + `getPhoneNumber` | `<button open-type="getPhoneNumber" bindgetphonenumber>` 后端解密 |
| 真机提示「不在以下 request 合法域名」 | 同上域名问题 | — |

## 6. 构建与 npm

| 报错 | 原因 | 处理 |
|---|---|---|
| `npm 包未找到` / `module not found` | 未构建 npm | `cli build-npm` 或工具菜单「构建 npm」；确认有 package.json |
| 构建 npm 后仍报错 | 未开 `useCompilerModule` 或目录不对 | 检查 project.config.json 的 `packNpmManually`/`packNpmRelationList` |
| `miniprogram_npm` 缺失 | 构建产物未生成 | 删除后重新构建；CI 用 `miniprogram-ci build-npm` |

## 7. 云开发

| 报错 | 原因 | 处理 |
|---|---|---|
| `cloud init error` / 环境不存在 | 未初始化或 env 错 | `wx.cloud.init({ env })`；CLI `cloud env list` 查真实环境 ID |
| 云函数调用 -501000 | 未部署或函数名错 | `cli cloud functions deploy` 重新部署 |
| 依赖缺失 | 本地 node_modules 未上传 | 部署时加 `--remote-npm-install` |
| 数据库权限拒绝 | 集合权限设置 | 控制台改权限为「所有用户可读，仅创建者可读写」等 |

## 8. 体积与上传

| 报错 | 原因 | 处理 |
|---|---|---|
| 主包超过 2MB | 资源/页面过多 | 分包、图片 CDN、删除未引用组件（`mp_inspect.py deps`） |
| 上传成功但代码包异常大 | miniprogram_npm 或资源混入 | `ignores: ['node_modules/**/*']`，检查 top files（`mp_inspect.py size`） |
| CI 返回 1004 | IP 白名单 | 后台添加出口 IP |
| CI 报密钥错误 | key 与 appid 不匹配 | 重新生成密钥 |
| `invalid appid` | appid 填错或测试号 | 用正式 AppID；`touristappid` 无法上传 |

## 9. Skyline

| 现象 | 原因 | 处理 |
|---|---|---|
| 真机仍是 WebView | 受 We 分析 AB 实验影响 | 配置 AB 实验白名单，或关闭实验默认启用 Skyline |
| 页面无法滚动 | Skyline 无全局滚动 | 用 `scroll-view type="list" scroll-y` 包裹 |
| 样式表现不一致 | WXSS 是子集、盒模型不同 | 加 `rendererOptions.skyline` 对齐项；检查 `position: fixed` 用法 |
| 导航栏样式丢失 | 不支持原生导航栏 | `navigationStyle: custom` 自定义导航栏 |

## 10. 调试技巧

- 抓日志：`mp_auto.js logs --project <dir> --seconds 10`（含 console 与 JS 异常）
- 断链路 widget：真机调试可查看实时 WXML 结构与样式
- 体验评分：开发者工具 Audits 面板，`autoAudits: true` 时可用 `stopAudits()` 取报告
- 编译异常先清缓存：`cli cache --clean all --project <dir>`
- 想快速定位项目问题：`mp_inspect.py check --project <dir> --md`
