"""端到端 smoke：模拟用户从浏览启动 → 选模板 → 单图反推 → 编辑 → 保存。
所有 vision 调用 mock；shot-master 真实跑（不 mock）。"""
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from PIL import Image
from fastapi.testclient import TestClient
from app.main import create_app


FAKE_OUTPUT = """## 1. global_prompt
```
夕阳下少女转身
```
## 5. max_frames
```
192
```
"""


def test_e2e_full_loop(tmp_path, monkeypatch):
    # 准备 env + 模板
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "single.md").write_text(
        "---\nname: Single\nsuggest_when: image_count == 1\nvariables: []\n---\nbody",
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text(
        "DEFAULT_PROVIDER=gemini\nDEFAULT_MODEL=gemini-2.5-pro\nGEMINI_API_KEY=k\n"
    )
    monkeypatch.chdir(tmp_path)

    img = tmp_path / "shot.png"
    Image.new("RGB", (200, 200), (100, 100, 200)).save(img)

    app = create_app()
    client = TestClient(app)

    # 1. 健康检查
    assert client.get("/api/health").status_code == 200

    # 2. 列模板
    tpls = client.get("/api/templates").json()
    assert any(t["id"] == "single" for t in tpls)

    # 3. 推荐模板
    rec = client.get("/api/templates/recommend?image_count=1").json()
    assert rec["id"] == "single"

    # 4. 列文件夹
    folder_list = client.get(
        "/api/files/list", params={"folder": str(tmp_path)}
    ).json()
    assert any(it["name"] == "shot.png" for it in folder_list["items"])

    # 5. 单次反推
    with patch("app.providers.gemini.genai") as mock_genai:
        mock_genai.Client.return_value.models.generate_content.return_value = MagicMock(text=FAKE_OUTPUT)
        infer = client.post("/api/inference", json={
            "images": [str(img)],
            "template_id": "single",
            "supplement": {},
        }).json()
    assert infer["global_prompt"] == "夕阳下少女转身"
    assert infer["max_frames"] == 192
    md_path = Path(infer["md_path"])
    json_path = Path(infer["json_path"])
    assert md_path.exists() and json_path.exists()

    # 6. 编辑后保存
    edited = client.post("/api/inference/save", json={
        "md_path": str(md_path),
        "json_path": str(json_path),
        "fields": {**infer, "global_prompt": "EDITED"},
        "meta": infer["meta"],
    }).json()
    assert "EDITED" in Path(edited["md_path"]).read_text(encoding="utf-8")

    # 7. 拆图（用 shot-master 真实跑）
    preview = client.post("/api/grid/preview", json={
        "image_path": str(img),
        "src_rows": 2, "src_cols": 2,
        "sub_rows": 1, "sub_cols": 1,
    }).json()
    assert len(preview["tiles"]) == 4

    # 8. 设置 GET/PUT
    settings = client.get("/api/settings").json()
    assert settings["current_provider"] == "gemini"
    client.put("/api/settings", json={"current_model": "gemini-3-pro-preview"})
    assert client.get("/api/settings").json()["current_model"] == "gemini-3-pro-preview"
