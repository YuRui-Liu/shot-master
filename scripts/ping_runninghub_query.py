"""诊断 RunningHub V2 query 端点的真实 body shape。

用法（项目根目录）：
    python scripts/ping_runninghub_query.py YOUR_API_KEY

会真实创建一个 dummy 任务（用最小 workflow，会立刻 fail，但能拿到 taskId）
然后用 3 种不同的 body shape 调 V2 query，对比哪种能正常返回 {code:0, ...}：

  A. body = {"taskId": ...}                   ← 当前代码用的
  B. body = {"apikey": ..., "taskId": ...}    ← 假设 V2 也需要 apikey
  C. body = {"apiKey": ..., "taskId": ...}    ← 万一是 camelCase

结合返回判断：
  - A 失败、B 成功 → V2 query 需要 lowercase apikey；修 RunningHubClient.query_task
  - A 失败、C 成功 → V2 query 需要 camelCase apiKey；修同上
  - 全失败          → 端点行为更复杂，需进一步排查
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx


def post(url: str, headers: dict, body: dict, label: str):
    print(f"\n--- {label} ---")
    print(f"  URL: {url}")
    print(f"  body keys: {list(body.keys())}")
    try:
        r = httpx.post(url, headers=headers, json=body, timeout=15.0)
        print(f"  HTTP {r.status_code}")
        print(f"  raw body: {r.text[:500]}")
        try:
            data = r.json()
            top_keys = list(data.keys())
            print(f"  json top-level keys: {top_keys}")
            if "code" in data:
                print(f"  code={data['code']!r}  msg={data.get('msg')!r}")
                if data.get("code") == 0:
                    d = data.get("data")
                    if isinstance(d, dict):
                        print(f"  data keys: {list(d.keys())}")
                        if "status" in d:
                            print(f"  ★ STATUS = {d['status']}")
                    else:
                        print(f"  data: {d!r}")
                    print(f"  → ★ 这个 body shape 正确返回 V2 dict！修复方案确定。")
                    return True
            else:
                print(f"  ⚠ 响应里没有 'code' 字段——可能是别的端点行为")
        except Exception as e:
            print(f"  json parse fail: {e}")
    except httpx.HTTPError as e:
        print(f"  HTTP error: {type(e).__name__}: {e}")
    return False


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    api_key = sys.argv[1]
    base_url = "https://www.runninghub.cn"

    print(f"[1] 先发起一个 dummy 任务（用空 nodeInfoList 引一个不存在的 workflow_id，会立刻失败但能拿到 taskId 用于探测）")
    create_url = f"{base_url}/task/openapi/create"
    create_resp = httpx.post(
        create_url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Host": "www.runninghub.cn",
        },
        json={
            "apiKey": api_key,
            "workflowId": "1904136902449209346",   # 文档示例 ID（大概率不属于你账号，会立刻失败）
            "addMetadata": False,
        },
        timeout=15.0,
    )
    print(f"  create HTTP {create_resp.status_code}")
    print(f"  create body: {create_resp.text[:400]}")
    try:
        cd = create_resp.json()
        if cd.get("code") != 0:
            print(f"  create 业务错（这是预期的——示例 workflow_id 不属于你）")
            print(f"  跳到 [3] 用一个**已知不存在**的 task_id 当探测目标，"
                  f"哪个 body shape 能返回正确 'code:0' 才是对的。")
            task_id = "0000000000000000000"
        else:
            task_id = str(cd["data"]["taskId"])
            print(f"  create 成功！taskId={task_id}")
            time.sleep(2)  # 给 RunningHub 一点点索引时间
    except Exception as e:
        print(f"  create 解析失败: {e}")
        task_id = "0000000000000000000"

    print(f"\n[2] 用 task_id={task_id} 测 V2 query 3 种 body shape")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Host": "www.runninghub.cn",
    }
    query_url = f"{base_url}/openapi/v2/query"

    ok_a = post(query_url, headers, {"taskId": task_id},
                "A) {taskId} 当前代码用的")
    ok_b = post(query_url, headers, {"apikey": api_key, "taskId": task_id},
                "B) {apikey + taskId} 推测的修复方案 (lowercase)")
    ok_c = post(query_url, headers, {"apiKey": api_key, "taskId": task_id},
                "C) {apiKey + taskId} 万一是 camelCase")

    print("\n" + "=" * 60)
    print("结论：")
    print(f"  A: {'✓' if ok_a else '✗'}  B: {'✓' if ok_b else '✗'}  C: {'✓' if ok_c else '✗'}")
    if ok_b and not ok_a:
        print("  → 修复：query_task 加 'apikey' 到 body 里")
    elif ok_c and not ok_a:
        print("  → 修复：query_task 加 'apiKey' (camelCase) 到 body 里")
    elif ok_a:
        print("  → 当前代码本应工作，问题在别处——把上面输出贴给 Claude 继续查")
    else:
        print("  → 三种都失败；可能端点变化或本身 task_id 太离谱被拒绝；贴输出继续查")


if __name__ == "__main__":
    main()
