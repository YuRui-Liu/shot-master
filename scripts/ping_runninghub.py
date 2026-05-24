"""快速诊断 RunningHub API key + 端点可达性。

用法（在项目根目录）：
    python scripts/ping_runninghub.py YOUR_API_KEY
或者:
    python scripts/ping_runninghub.py YOUR_API_KEY https://www.runninghub.cn

会按顺序跑 3 个测试：
  1. 当前代码的 query_task("__spb_probe__")
     —— 这是 UI 里测试连接按钮目前用的逻辑（已知会假报"不可达"）
  2. accountStatus 端点（裸 httpx 调用）
     —— RunningHub 文档推荐的鉴权探测端点；这是修复后会用的逻辑
  3. /object_info（任意 GET，验证 base_url 可达）
     —— 完全不需要 key 的探测，验证网络/域名

根据 3 个测试的成功/失败组合可以判断：
  - 1 失败、2 成功 → 代码问题；走修复（用 accountStatus 替换 query_task）
  - 1 失败、2 失败、3 成功 → API key 错；去 RunningHub 后台重生成 key
  - 全失败                  → 网络/域名问题（公司代理 / VPN / DNS）
"""
from __future__ import annotations

import sys
from pathlib import Path

# 让脚本能 import drama_shot_master.* 包
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx

from drama_shot_master.providers.runninghub import RunningHubClient, RunningHubUnavailable


def test_1_old_probe(api_key: str, base_url: str):
    """当前 UI 用的探测：query_task 一个虚 ID。"""
    print("=" * 60)
    print("[1] 当前 UI 用的探测：RunningHubClient.query_task('__spb_probe__')")
    print("-" * 60)
    try:
        with RunningHubClient(api_key, base_url=base_url) as c:
            r = c.query_task("__spb_probe__")
            print(f"  → 没抛异常，返回: {r}")
            print("  → 结论：'测试连接' 应该显示鉴权通过")
    except RunningHubUnavailable as e:
        print(f"  → RunningHubUnavailable: {e}")
        print("  → 这就是你看到的 '✗ 不可达：query_task code=None msg=None'")
    except Exception as e:
        print(f"  → 意外异常 {type(e).__name__}: {e}")


def test_2_account_status(api_key: str, base_url: str):
    """RunningHub 推荐的鉴权探测：POST /uc/openapi/accountStatus。"""
    print()
    print("=" * 60)
    print("[2] 修复后会用的探测：POST /uc/openapi/accountStatus")
    print("-" * 60)
    url = f"{base_url.rstrip('/')}/uc/openapi/accountStatus"
    try:
        resp = httpx.post(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Host": "www.runninghub.cn",
            },
            json={"apikey": api_key},
            timeout=15.0,
        )
        print(f"  HTTP {resp.status_code}")
        body_preview = resp.text[:600]
        print(f"  Body: {body_preview}")
        try:
            data = resp.json()
            if data.get("code") == 0:
                d = data.get("data", {})
                print(
                    "  → 鉴权通过！剩余积分:",
                    d.get("remainCoins"),
                    " 余额:", d.get("remainMoney"), d.get("currency"),
                    " API 类型:", d.get("apiType"),
                )
                print("  → 修复方案有效：UI 用这个端点重写探测即可")
            else:
                print(
                    f"  → 业务错: code={data.get('code')} msg={data.get('msg')}")
                print("  → 大概率 API key 失效或 base_url 错")
        except Exception as e:
            print(f"  → JSON 解析失败: {e}")
    except httpx.HTTPError as e:
        print(f"  → 网络错: {type(e).__name__}: {e}")
        print("  → 端点不可达 → 检查 base_url / 网络代理 / 防火墙")


def test_3_anonymous(base_url: str):
    """完全不带 key 的探测：GET /object_info（任意公开 endpoint）。"""
    print()
    print("=" * 60)
    print("[3] 网络/域名可达性（不带 key）：GET /object_info")
    print("-" * 60)
    url = f"{base_url.rstrip('/')}/object_info"
    try:
        resp = httpx.get(url, timeout=10.0)
        print(f"  HTTP {resp.status_code}")
        print(f"  Body length: {len(resp.text)} bytes")
        if resp.status_code < 500:
            print("  → 域名 + 端口可达；网络/DNS/代理都正常")
        else:
            print("  → 5xx：服务器异常但域名可达")
    except httpx.HTTPError as e:
        print(f"  → 网络错: {type(e).__name__}: {e}")
        print("  → 完全连不上 → DNS / 防火墙 / VPN 问题")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print()
        print("缺参数。用法：")
        print(f"  python {Path(__file__).name} <API_KEY> [BASE_URL]")
        sys.exit(2)

    api_key = sys.argv[1]
    base_url = sys.argv[2] if len(sys.argv) > 2 else "https://www.runninghub.cn"

    print(f"探测 base_url = {base_url}")
    print(f"API key 长度 = {len(api_key)} 字符（首末 4 位 {api_key[:4]}…{api_key[-4:]}）")
    print()

    test_1_old_probe(api_key, base_url)
    test_2_account_status(api_key, base_url)
    test_3_anonymous(base_url)

    print()
    print("=" * 60)
    print("结果对照表：")
    print("  [1] FAIL + [2] OK   → 代码问题，走修复（accountStatus 替换 query_task）")
    print("  [1] FAIL + [2] FAIL + [3] OK → API key 错或失效")
    print("  全 FAIL              → 网络 / DNS / VPN 问题")


if __name__ == "__main__":
    main()
