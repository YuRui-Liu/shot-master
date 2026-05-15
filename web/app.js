// app.js — 顶层路由：监听 tab-changed，把 web/tabs/<name>.html 注入 #tab-content
const TAB_BASE = "/static/tabs";
const tabCache = {};

// 通过 innerHTML 注入的 <script> 标签浏览器不会执行（HTML 标准）。
// 需要遍历找到这些 <script>，手动 new Script + 替换，才会触发执行。
function runInlineScripts(container) {
  const scripts = container.querySelectorAll("script");
  scripts.forEach((old) => {
    const fresh = document.createElement("script");
    if (old.src) fresh.src = old.src;
    if (old.type) fresh.type = old.type;
    fresh.text = old.textContent;
    old.parentNode.replaceChild(fresh, old);
  });
}

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
  root.innerHTML = html;
  // 先把 inline <script> 跑起来（定义 xxxTab() 函数到 window）
  runInlineScripts(root);
  // 再让 Alpine 扫描节点上的 x-data / x-bind 指令
  if (window.Alpine) {
    try {
      window.Alpine.initTree(root);
    } catch (e) {
      console.error("Alpine.initTree failed:", e);
    }
  } else {
    // Alpine 还没加载完，等一下再试
    setTimeout(() => {
      if (window.Alpine) window.Alpine.initTree(root);
    }, 100);
  }
}

window.addEventListener("tab-changed", (e) => loadTab(e.detail));

// 初始加载默认 tab
window.addEventListener("DOMContentLoaded", () => {
  loadTab("inference");
});

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
      // 兜底：老浏览器或 http 非 localhost 下没 clipboard 权限
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    }
  },
};
