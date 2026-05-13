// app.js — 顶层路由：监听 tab-changed，把 web/tabs/<name>.html 注入 #tab-content
const TAB_BASE = "/static/tabs";
const tabCache = {};

async function loadTab(name) {
  let html = tabCache[name];
  if (!html) {
    const resp = await fetch(`${TAB_BASE}/${name}.html`);
    if (!resp.ok) {
      document.getElementById("tab-content").innerHTML = `<div class="card alert-err">加载 ${name} 失败</div>`;
      return;
    }
    html = await resp.text();
    tabCache[name] = html;
  }
  document.getElementById("tab-content").innerHTML = html;
  // 让 Alpine 处理新插入的节点
  if (window.Alpine) window.Alpine.initTree(document.getElementById("tab-content"));
}

window.addEventListener("tab-changed", (e) => loadTab(e.detail));

// 初始加载默认 tab
window.addEventListener("DOMContentLoaded", () => {
  loadTab("inference");
});

// ============== 共用工具 ==============
window.api = {
  async get(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
    return r.json();
  },
  async post(url, body) {
    const r = await fetch(url, {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
    return r.json();
  },
  async put(url, body) {
    const r = await fetch(url, {
      method: "PUT", headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
    return r.json();
  },
  async del(url) {
    const r = await fetch(url, {method: "DELETE"});
    if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
    return r.json();
  },
  copy(text) {
    navigator.clipboard.writeText(text);
  },
};
