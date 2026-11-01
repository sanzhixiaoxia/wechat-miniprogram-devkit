# 小程序开发速查（结构 / 配置 / 生命周期 / Skyline）

## 1. 标准项目结构

```
myapp/
├── project.config.json        # 项目配置（appid、libVersion、编译设置）
├── project.private.config.json# 个人本地配置（优先级高于 project.config.json）
├── sitemap.json               # 索引配置
├── app.js                     # 全局逻辑 App()
├── app.json                   # 全局配置（页面注册、window、tabBar、分包）
├── app.wxss                   # 全局样式
├── pages/
│   └── index/
│       ├── index.js           # Page()
│       ├── index.json         # 页面配置（可覆盖 window、声明组件）
│       ├── index.wxml         # 视图
│       └── index.wxss         # 样式
├── components/                # 自定义组件（约定目录）
│   └── goods-card/
│       ├── goods-card.js      # Component()
│       ├── goods-card.json    # { "component": true }
│       ├── goods-card.wxml
│       └── goods-card.wxss
├── cloudfunctions/            # 云函数（project.config.json 的 cloudfunctionRoot）
└── miniprogram_npm/           # 「构建 npm」产物，勿手改
```

四件套必须**同名同目录**；路径大小写敏感（Windows 不敏感，真机敏感，容易踩坑）。

## 2. app.json 关键配置

```jsonc
{
  "pages": ["pages/index/index", "pages/my/my"],   // 第一项为首页；未注册的页面无法跳转
  "window": {
    "navigationBarBackgroundColor": "#07C160",
    "navigationBarTitleText": "小程序",
    "navigationBarTextStyle": "white",
    "backgroundColor": "#f6f6f6",
    "enablePullDownRefresh": false
  },
  "tabBar": {
    "color": "#999999", "selectedColor": "#07C160",
    "list": [
      { "pagePath": "pages/index/index", "text": "首页",
        "iconPath": "assets/home.png", "selectedIconPath": "assets/home-on.png" }
    ]
  },
  "subPackages": [                       // 也可写 subpackages
    { "root": "pkgA", "name": "pkgA", "pages": ["detail/detail"] }
  ],
  "plugins": {},                         // 插件
  "usingComponents": {},                 // 全局组件（基础库 2.11+）
  "lazyCodeLoading": "requiredComponents", // 按需注入，强烈建议开启
  "renderer": "webview",                 // webview | skyline
  "componentFramework": "exparser",      // skyline 时必须 glass-easel
  "permission": { "scope.userLocation": { "desc": "用于展示附近门店" } },
  "requiredPrivateInfos": ["getLocation", "chooseLocation"],
  "sitemapLocation": "sitemap.json"
}
```

规则要点：
- `pages` 里的路径**不带后缀**、**不带前导 `/`**
- tabBar 至少 2 项、最多 5 项；`pagePath` 必须在 `pages` 中
- 主包 2MB，单个分包 2MB，总包 20MB（超限无法上传）
- 分包可引用主包资源，**主包不能引用分包资源**

## 3. 页面 / 组件生命周期

**页面 Page**：`onLoad(options)` → `onShow` → `onReady` → `onHide` → `onUnload`
外加 `onPullDownRefresh`、`onReachBottom`、`onShareAppMessage`、`onPageScroll`、`onResize`

**组件 Component**：
- 组件自身：`created` → `attached` → `ready` → `moved` → `detached`（写在 `lifetimes` 中）
- 所在页面：`show` / `hide` / `resize`（写在 `pageLifetimes` 中）

**通信**：
- 父 → 子：`properties` 传值
- 子 → 父：`this.triggerEvent('myevent', {value})`，父用 `bind:myevent`
- 父调子方法：`this.selectComponent('#id').method()`
- 全局：`getApp().globalData`

## 4. setData 性能铁律

```js
// 反例：一次性塞入大列表 / 频繁调用
this.setData({ hugeList: bigArray })          // 超过 256KB 会报错或卡顿

// 正例
this.setData({ ['list[' + i + '].done']: true })   // 只改变化的路径
this.setData({ page: this.data.page + 1 }, () => { /* 渲染完成回调 */ })
```

- 单次 `setData` 数据建议 < 256KB，列表用分页/虚拟列表
- 不要把不在模板中渲染的数据放进 `data`（可挂到 `this` 上）
- 长列表用 `wx:key`，避免全量重渲染

## 5. Skyline 迁移要点

最小化配置：

```jsonc
{
  "lazyCodeLoading": "requiredComponents",
  "renderer": "skyline",
  "componentFramework": "glass-easel",
  "rendererOptions": {
    "skyline": {
      "defaultDisplayBlock": true,
      "defaultContentBox": true,
      "tagNameStyleIsolation": "legacy",
      "enableScrollViewAutoSize": true
    }
  }
}
```

页面级配置（Skyline 无全局滚动、无原生导航栏）：

```jsonc
{ "renderer": "skyline", "componentFramework": "glass-easel",
  "disableScroll": true, "navigationStyle": "custom" }
```

常见适配点：
- 需要滚动的区域用 `<scroll-view type="list" scroll-y>` 包裹
- 默认 `display` 与盒模型与 WebView 不同，用上面的 `rendererOptions` 对齐
- `position: fixed` 行为有差异；WXSS 是 WebView 的子集
- 灰度：通过 We 分析「AB 实验 → 小程序基础库实验」放量，否则真机可能仍走 WebView
- 最低要求：基础库 3.0.0+，开发者工具 1.06.2307260+

## 6. 分包与体积优化

- tabBar 页与公共组件必须在主包，其余页面尽量分包
- 图片/字体放 CDN，不要塞进代码包
- 开启 `minify` 系列压缩（CI 的 `setting` 或工具「本地设置」）
- 用 `mp_inspect.py size` 定期体检，`mp_inspect.py deps` 找孤立组件删掉

## 7. 网络与登录

- `wx.request` 必须 https，且域名要在后台「开发设置 → 服务器域名」配置（本地可勾「不校验合法域名」）
- 登录标准流程：`wx.login` 拿 code → 开发者服务器换 `openid`/`session_key` → 下发自定义登录态
- 获取用户信息用 `<button open-type="getPhoneNumber">` / `getUserProfile` 等授权方式，不能直接静默拉取
