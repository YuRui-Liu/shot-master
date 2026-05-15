# Shot-Prompt-Backwards

分镜提示词反推**桌面应用**（PySide6）+ shot-master 整合工具。

> v0.2 起从 FastAPI Web App 重构为 PySide6 桌面应用，避免浏览器沙箱限制（无法访问本地文件路径）。

## 安装

```bash
pip install -e ../../shot-master   # 先装 shot-master（位于 Projects/shot-master/）
pip install -e .[dev]
cp .env.example .env               # 编辑填入 API keys（默认豆包视觉理解）
```

## 启动

Windows: 双击 `run.bat`
Linux/Mac: `./run.sh`

或直接 `python -m app.main`

## 测试

```bash
pytest -v
```

## 文档

- 需求规格：`需求.md`
- 实现计划：`docs/superpowers/plans/2026-05-13-shot-prompt-backwards.md`
