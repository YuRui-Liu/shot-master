# Shot-Prompt-Backwards

分镜提示词反推 Web App + shot-master 整合工具。

## 安装

```bash
pip install -e ../shot-master   # 先装 shot-master
pip install -e .[dev]
cp .env.example .env            # 编辑填入 API keys
```

## 启动

Windows: 双击 `run.bat`
Linux/Mac: `./run.sh`

浏览器自动打开 http://127.0.0.1:7866

## 测试

```bash
pytest -v
```

## 文档

- 需求规格：`需求.md`
- 实现计划：`docs/superpowers/plans/2026-05-13-shot-prompt-backwards.md`
