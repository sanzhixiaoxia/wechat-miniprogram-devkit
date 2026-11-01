#!/usr/bin/env node
/**
 * mp_auto.js — 微信小程序端到端自动化调试（基于官方 miniprogram-automator）
 *
 * 用途：让 Agent 能真正「操作」小程序：打开页面 → 点击/输入/断言 → 截图 → 抓 console 与 JS 异常。
 *
 * 前提：
 *   1) 本机安装微信开发者工具，并在「设置 → 安全设置」开启服务端口
 *   2) npm i miniprogram-automator --save-dev（脚本会检测并提示）
 *
 * 命令：
 *   node scripts/mp_auto.js screenshot --project /path/to/mp [--page /pages/index/index] --out /tmp/shot.png
 *   node scripts/mp_auto.js logs       --project /path/to/mp [--page ...] --seconds 10
 *   node scripts/mp_auto.js data       --project /path/to/mp --page ... [--data-path list]
 *   node scripts/mp_auto.js wxml       --project /path/to/mp --page ... --selector ".box"
 *   node scripts/mp_auto.js flow       --project /path/to/mp --steps /tmp/steps.json --out /tmp/auto
 *
 * 连接：
 *   --port 9420   连接已开启自动化的工具（mp_cli.py auto --port 9420）
 *   默认          自行 launch（内部调用 cli auto）
 *
 * steps.json 支持的 action：
 *   waitFor {selector|ms|fn}        等待元素出现/等待毫秒
 *   tap {selector}                  点击
 *   longpress {selector}            长按
 *   input {selector, value}         输入文本（input/textarea）
 *   trigger {selector, type, detail}触发自定义事件
 *   setData {data}                  直接改页面 data
 *   callMethod {method, args}       调用页面方法
 *   assertText {selector, expect}   断言元素文本包含 expect
 *   assertData {path, expect}       断言 data 值相等
 *   assertExist {selector}          断言元素存在
 *   mockWx {method, result}         mock wx.xxx 返回值
 *   restoreWx {method}              取消 mock
 *   navigate {url, type}            跳转（navigateTo/reLaunch/redirectTo/switchTab）
 *   wait {ms}                       等待
 *   screenshot {name}               截图保存到 --out 目录
 *   wxml {selector}                 抓取元素 WXML
 *   scroll {top}                    页面滚动
 */

const fs = require('fs');
const path = require('path');

// --------------------------------------------------------------------------- //
// 参数
// --------------------------------------------------------------------------- //
function parseArgs(argv) {
  const args = { _: [] };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a.startsWith('--')) {
      const key = a.slice(2);
      const next = argv[i + 1];
      if (next === undefined || next.startsWith('--')) {
        args[key] = true;
      } else {
        args[key] = next;
        i++;
      }
    } else {
      args._.push(a);
    }
  }
  return args;
}

const args = parseArgs(process.argv.slice(2));
const command = args._[0];
const PROJECT = args.project || args.p;
const OUT = args.out || args.o || path.join(process.cwd(), '.mp-auto');

function finish(payload, code = 0) {
  // 同步写 fd 1 后再退出：既保证管道场景输出不被截断，也保证 die() 之后代码不再继续执行
  const text = JSON.stringify(payload, null, 2) + '\n';
  try {
    fs.writeSync(1, text);
  } catch (e) {
    process.stdout.write(text);
  }
  process.exit(code);
}

function die(error, hint) {
  finish({ ok: false, error, hint }, 1);
}

if (!command) {
  die('缺少命令', '可用命令：screenshot | logs | data | wxml | flow');
}
if (!PROJECT) {
  die('缺少 --project', '例：--project /path/to/miniprogram');
}
const projectPath = path.resolve(PROJECT);
if (!fs.existsSync(projectPath)) {
  die(`项目路径不存在: ${projectPath}`, '请传入正确的绝对路径');
}

// 依赖检测
let automator;
try {
  automator = require('miniprogram-automator');
} catch (e) {
  die(
    '未安装 miniprogram-automator',
    '请在项目或全局安装：npm i miniprogram-automator --save-dev（Node >= 8，开发者工具需开启服务端口）'
  );
}

// --------------------------------------------------------------------------- //
// 连接 / 启动
// --------------------------------------------------------------------------- //
async function connect() {
  const timeout = Number(args.timeout || 30000);
  if (args.port) {
    const ws = `ws://localhost:${args.port}`;
    try {
      const mp = await automator.connect({ wsEndpoint: ws });
      return { mp, mode: 'connect', ws };
    } catch (e) {
      die(`连接自动化端口失败: ${ws}`,
        '请先执行 mp_cli.py auto --project <项目> --port ' + args.port + ' 开启自动化端口，再重试');
    }
  }
  try {
    const mp = await automator.launch({
      projectPath,
      cliPath: typeof args['cli-path'] === 'string' ? args['cli-path'] : undefined,
      timeout,
    });
    return { mp, mode: 'launch' };
  } catch (e) {
    die(`启动开发者工具自动化失败: ${e.message}`,
      '确认已安装微信开发者工具并开启「设置 → 安全设置 → 服务端口」；' +
      '也可用 --cli-path 指定 CLI 路径，或先 mp_cli.py auto 再用 --port 连接');
  }
}

function attachListeners(mp, sink) {
  mp.on('console', (msg) => {
    sink.logs.push({ type: msg.type, args: String(msg.args && msg.args.length ? msg.args.join(' ') : '') });
  });
  mp.on('exception', (err) => {
    sink.errors.push({ message: err.message, stack: (err.stack || '').split('\n').slice(0, 5).join('\n') });
  });
}

async function getPage(mp) {
  const target = args.page || args.launch;
  if (target) {
    return await mp.reLaunch(target.startsWith('/') ? target : '/' + target);
  }
  return await mp.currentPage();
}

function truncate(s, n = 2000) {
  if (typeof s !== 'string') return s;
  return s.length > n ? s.slice(0, n) + `...[截断 ${s.length - n} 字符]` : s;
}

// --------------------------------------------------------------------------- //
// 单步执行
// --------------------------------------------------------------------------- //
async function runStep(mp, page, step, sink, outDir) {
  const started = Date.now();
  const rec = { action: step.action, ok: true, detail: '' };

  try {
    switch (step.action) {
      case 'waitFor': {
        if (step.selector) await page.waitFor(step.selector);
        else if (step.ms) await page.waitFor(Number(step.ms));
        else await page.waitFor(1000);
        rec.detail = `等待 ${step.selector || step.ms + 'ms'} 完成`;
        break;
      }
      case 'wait': {
        await page.waitFor(Number(step.ms || 500));
        rec.detail = `等待 ${step.ms || 500}ms`;
        break;
      }
      case 'tap': {
        const el = await page.$(step.selector);
        if (!el) throw new Error(`未找到元素: ${step.selector}`);
        await el.tap();
        rec.detail = `已点击 ${step.selector}`;
        break;
      }
      case 'longpress': {
        const el = await page.$(step.selector);
        if (!el) throw new Error(`未找到元素: ${step.selector}`);
        await el.longpress();
        rec.detail = `已长按 ${step.selector}`;
        break;
      }
      case 'input': {
        const el = await page.$(step.selector);
        if (!el) throw new Error(`未找到元素: ${step.selector}`);
        await el.input(String(step.value ?? ''));
        rec.detail = `已向 ${step.selector} 输入 "${step.value}"`;
        break;
      }
      case 'trigger': {
        const el = await page.$(step.selector);
        if (!el) throw new Error(`未找到元素: ${step.selector}`);
        await el.trigger(step.type, step.detail || {});
        rec.detail = `已触发 ${step.selector} 的 ${step.type} 事件`;
        break;
      }
      case 'setData': {
        await page.setData(step.data || {});
        rec.detail = '已 setData: ' + JSON.stringify(step.data);
        break;
      }
      case 'callMethod': {
        const r = await page.callMethod(step.method, ...(step.args || []));
        rec.detail = `调用 ${step.method} 返回: ${truncate(JSON.stringify(r), 500)}`;
        rec.value = r;
        break;
      }
      case 'assertText': {
        const el = await page.$(step.selector);
        if (!el) throw new Error(`未找到元素: ${step.selector}`);
        const text = await el.text();
        rec.actual = text;
        if (!String(text).includes(String(step.expect))) {
          rec.ok = false;
          rec.detail = `断言失败：期望包含 "${step.expect}"，实际为 "${text}"`;
        } else {
          rec.detail = `断言通过："${text}"`;
        }
        break;
      }
      case 'assertData': {
        const val = await page.data(step.path);
        rec.actual = val;
        const pass = JSON.stringify(val) === JSON.stringify(step.expect) || String(val) === String(step.expect);
        rec.ok = pass;
        rec.detail = pass ? `断言通过：${step.path} = ${JSON.stringify(val)}`
          : `断言失败：期望 ${JSON.stringify(step.expect)}，实际 ${JSON.stringify(val)}`;
        break;
      }
      case 'assertExist': {
        const el = await page.$(step.selector);
        rec.ok = !!el;
        rec.detail = el ? `元素存在: ${step.selector}` : `元素不存在: ${step.selector}`;
        break;
      }
      case 'mockWx': {
        await mp.mockWxMethod(step.method, step.result);
        rec.detail = `已 mock wx.${step.method}`;
        break;
      }
      case 'restoreWx': {
        await mp.restoreWxMethod(step.method);
        rec.detail = `已恢复 wx.${step.method}`;
        break;
      }
      case 'navigate': {
        const type = step.type || 'navigateTo';
        const url = step.url;
        if (!mp[type]) throw new Error(`不支持的跳转类型: ${type}`);
        const p = await mp[type](url);
        if (p) page = p;
        rec.detail = `${type} → ${url}`;
        rec.page = p ? p.path : undefined;
        break;
      }
      case 'scroll': {
        await mp.pageScrollTo(Number(step.top || 0));
        rec.detail = `已滚动到 ${step.top}px`;
        break;
      }
      case 'screenshot': {
        fs.mkdirSync(outDir, { recursive: true });
        const file = path.join(outDir, `${step.name || 'step-' + Date.now()}.png`);
        await mp.screenshot({ path: file });
        rec.detail = file;
        rec.file = file;
        sink.screenshots.push(file);
        break;
      }
      case 'wxml': {
        if (!step.selector) throw new Error('wxml 需要 selector');
        const el = await page.$(step.selector);
        if (!el) throw new Error(`未找到元素: ${step.selector}`);
        const wxml = await el.outerWxml();
        rec.detail = truncate(wxml, 1500);
        rec.wxml = truncate(wxml, 1500);
        break;
      }
      case 'evaluate': {
        // fn 必须是「函数表达式字符串」，如 "() => getApp().globalData.userInfo"
        const fnBody = typeof step.fn === 'string' ? step.fn : step.code;
        if (!fnBody) throw new Error('evaluate 需要 fn（函数表达式字符串）');
        const r = await mp.evaluate(new Function(`return (${fnBody})`)());
        rec.value = r;
        rec.detail = truncate(JSON.stringify(r), 800);
        break;
      }
      default:
        rec.ok = false;
        rec.detail = `未知 action: ${step.action}`;
    }
  } catch (e) {
    rec.ok = false;
    rec.detail = `${e.message || e}`;
  }

  rec.ms = Date.now() - started;
  return { rec, page };
}

// --------------------------------------------------------------------------- //
// 命令实现
// --------------------------------------------------------------------------- //
(async () => {
  const { mp, mode, ws } = await connect();
  const sink = { logs: [], errors: [], screenshots: [] };
  attachListeners(mp, sink);

  let page;
  let result = { ok: true, command, project: projectPath, mode, wsEndpoint: ws };

  try {
    page = await getPage(mp);
    result.page = page ? page.path : null;

    if (command === 'screenshot') {
      fs.mkdirSync(path.dirname(path.resolve(OUT)), { recursive: true });
      const file = path.resolve(OUT);
      await mp.screenshot({ path: file });
      result.screenshot = file;
      result.hint = '截图已保存，可直接查看';
    } else if (command === 'logs') {
      const seconds = Number(args.seconds || 10);
      await page.waitFor(seconds * 1000);
      result.seconds = seconds;
    } else if (command === 'data') {
      const d = await page.data(args['data-path'] || undefined);
      result.data = d;
    } else if (command === 'wxml') {
      if (!args.selector) die('wxml 命令需要 --selector', '例：--selector ".goods-item"');
      const el = await page.$(args.selector);
      if (!el) die(`未找到元素: ${args.selector}`, '确认选择器正确；自定义组件内部元素需先从 page.$ 取组件再 element.$');
      result.wxml = truncate(await el.outerWxml(), 3000);
    } else if (command === 'flow') {
      const stepsFile = args.steps;
      if (!stepsFile) die('flow 命令需要 --steps', '传入声明式步骤 JSON 文件路径');
      const raw = JSON.parse(fs.readFileSync(path.resolve(stepsFile), 'utf-8'));
      const steps = Array.isArray(raw) ? raw : raw.steps || [];
      if (raw.launch || raw.page) {
        page = await mp.reLaunch(String(raw.launch || raw.page).replace(/^\/?/, '/'));
        result.page = page.path;
      }
      fs.mkdirSync(OUT, { recursive: true });
      const records = [];
      for (const st of steps) {
        const { rec, page: newPage } = await runStep(mp, page, st, sink, OUT);
        page = newPage || page;
        records.push(rec);
        if (!rec.ok && args['stop-on-error'] === true || (!rec.ok && args.stop)) break;
      }
      result.steps = records;
      result.passed = records.filter((r) => r.ok).length;
      result.failed = records.filter((r) => !r.ok).length;
      result.ok = result.failed === 0;
      result.screenshots = sink.screenshots;
    } else {
      die(`未知命令: ${command}`, '可用命令：screenshot | logs | data | wxml | flow');
    }
  } catch (e) {
    result.ok = false;
    result.error = e.message || String(e);
    result.hint = '确认页面路径存在于 app.json；确认开发者工具已开启服务端口';
  }

  // 给异步到达的 console / exception 事件一个落地机会（mock 与慢设备上尤其需要）
  await new Promise((r) => setTimeout(r, 50));

  result.logs = sink.logs.slice(-200);
  result.errors = sink.errors;
  result.systemInfo = await mp.systemInfo().catch(() => null);

  await mp.close().catch(() => {});
  finish(result, result.ok ? 0 : 1);
})().catch((e) => {
  finish({ ok: false, error: e.message || String(e) }, 1);
});
