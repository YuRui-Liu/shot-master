// app.js — 顶层路由：监听 tab-changed，把 web/tabs/<name>.html 注入 #tab-content
const TAB_BASE = "/static/tabs";
const tabCache = {};

// 关键：Alpine 通过 MutationObserver 监听 document，innerHTML 注入时立刻看到 x-data
// 但此时 inline <script> 还没执行 → x-data="inferenceTab()" 找不到函数 → 永久失败。
//
// 解决：先在游离 DOM 解析（Alpine 不监听游离节点），抽出 <script> 全局执行（把
// inferenceTab/splitTab/... 挂到 window），然后才 append 纯 markup 到真实 DOM。
// 这时 Alpine 看到 x-data 时函数已经定义，自动初始化就成功。
async function loadTab(name) {
  const root = document.getElementById("tab-content");
  let html = tabCache[name];
  if (!html) {
    try {
      const resp = await fetch(`${TAB_BASE}/${name}.html`);
      if (!resp.ok) {
        root.innerHTML = `<div class="card alert-err">加载 ${name} 失败：HTTP ${resp.status}</div>`;
        return;
      }
      html = await resp.text();
      tabCache[name] = html;
    } catch (e) {
      root.innerHTML = `<div class="card alert-err">加载 ${name} 失败：${e}</div>`;
      return;
    }
  }

  // 清空旧内容
  root.innerHTML = "";

  // 游离 div 解析 HTML
  const tmp = document.createElement("div");
  tmp.innerHTML = html;

  // 1) 收集所有 inline <script>，从游离 DOM 移除（避免重复）
  const scripts = Array.from(tmp.querySelectorAll("script"));
  scripts.forEach((s) => s.remove());

  // 2) 把脚本内容包装成新的 <script> 节点 append 到 body 让它执行
  //    （innerHTML 内的 script 不会执行；只有"插入文档树"的新 script 才会执行）
  scripts.forEach((old) => {
    const fresh = document.createElement("script");
    if (old.src) fresh.src = old.src;
    if (old.type) fresh.type = old.type;
    fresh.text = old.textContent;
    document.head.appendChild(fresh);
    document.head.removeChild(fresh); // 跑完即移除，保持 head 干净
  });

  // 3) 此时函数已挂到 window，把纯 markup 移入真实 DOM
  //    Alpine 的 MutationObserver 会自动发现 x-data 并初始化 — 此时函数已存在
  while (tmp.firstChild) {
    root.appendChild(tmp.firstChild);
  }
}

window.addEventListener("tab-changed", (e) => loadTab(e.detail));

// 等 Alpine 自身先初始化好（监听 DOM）再首次 loadTab
function _bootInitialTab() {
  if (window.Alpine) {
    loadTab("inference");
  } else {
    setTimeout(_bootInitialTab, 30);
  }
}
window.addEventListener("DOMContentLoaded", _bootInitialTab);

// ============== 共用工具 ==============
async function _parseError(r) {
  try {
    const data = await r.json();
    return data.detail || JSON.stringify(data);
  } catch {
    return r.statusText;
  }
}

window.api = {
  async get(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error(await _parseError(r));
    return r.json();
  },
  async post(url, body) {
    const r = await fetch(url, {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error(await _parseError(r));
    return r.json();
  },
  async put(url, body) {
    const r = await fetch(url, {
      method: "PUT", headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error(await _parseError(r));
    return r.json();
  },
  async del(url) {
    const r = await fetch(url, {method: "DELETE"});
    if (!r.ok) throw new Error(await _parseError(r));
    return r.json();
  },
  copy(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text);
    } else {
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    }
  },
};
