"""手动连通测试：用 .env 里的 DOUBAO_API_KEY 真打豆包 Ark，验证我们的
OpenAICompatProvider 实现（Chat Completions 流派 + base64 dataURL）能正确识图。

用法：
    cd shot-prompt-backwards
    # 确保 .env 里有 DOUBAO_API_KEY=ARK xxxx
    python scripts/ping_doubao.py [path/to/image.png] [model_name]

不指定 image 路径时用 PIL 生成一张 64×64 红方块。
不指定模型时用 doubao-seed-2-0-pro-260215。
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

# 让脚本能从项目根找到 drama_shot_master/
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image

from drama_shot_master.config import load_config
from drama_shot_master.providers import factory
import drama_shot_master.providers  # noqa: F401  触发注册


def make_test_image(path: Path) -> Path:
    img = Image.new("RGB", (64, 64), (220, 60, 60))
    img.save(path)
    return path


def main():
    img_arg = sys.argv[1] if len(sys.argv) >= 2 else None
    model = sys.argv[2] if len(sys.argv) >= 3 else "doubao-seed-2-0-pro-260215"

    cfg = load_config()
    if "doubao" not in cfg.api_keys:
        print("ERROR: .env 里没找到 DOUBAO_API_KEY")
        print("提示：豆包官方示例用 ARK_API_KEY；本程序读 DOUBAO_API_KEY。请在 .env 加：")
        print("  DOUBAO_API_KEY=<你的 ARK key>")
        return 2

    if img_arg:
        img_path = Path(img_arg)
        if not img_path.exists():
            print(f"ERROR: image not found: {img_path}")
            return 2
    else:
        img_path = ROOT / "drama_shot_master" / ".cache" / "ping_test.png"
        img_path.parent.mkdir(parents=True, exist_ok=True)
        make_test_image(img_path)
        print(f"[INFO] 已生成测试图：{img_path}")

    print(f"[INFO] 调用 doubao via openai_compat (Chat Completions API)")
    print(f"       base_url = {cfg.base_urls.get('doubao', 'preset default')}")
    print(f"       model    = {model}")
    print(f"       image    = {img_path}")
    print()

    try:
        provider = factory.build_provider(cfg, provider_name="doubao", model=model)
        out = provider.generate(
            images=[img_path],
            system_prompt="你是一个图像识别助手。",
            user_supplement="请用一句话描述这张图。",
        )
    except Exception as e:
        print(f"FAIL: {type(e).__name__}: {e}")
        return 1

    print("=" * 60)
    print("豆包返回：")
    print(out)
    print("=" * 60)
    print()
    print("✅ 连通成功。Chat Completions API + base64 dataURL 在豆包上正常工作。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
