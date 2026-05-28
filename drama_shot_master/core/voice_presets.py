"""配音音色设计快捷提示词：内置默认 + 从 YAML 加载(开发者可更新最佳实践)。"""
from __future__ import annotations

from pathlib import Path

_DEFAULT_NOTE = ("提示：方言靠音色描述不一定生效（Qwen3-TTS 方言走预置音色）；"
                 "湖南话官方未列出。")

_DEFAULTS = [
    ("方言", [
        ("北京话", "用北京话朗读，京味儿胡同腔，自然地道，"),
        ("上海话", "用上海话朗读，吴侬软语，语调婉转，"),
        ("四川话", "用四川话朗读，川渝口音轻快诙谐，"),
        ("粤语", "用粤语朗读，口音正宗自然，"),
        ("南京话", "用南京话朗读，耐心温和，"),
        ("陕西话", "用陕西话朗读，秦腔老陕味道，"),
        ("天津话", "用天津话朗读，相声捧哏味十足，"),
        ("闽南语", "用闽南语/台湾腔朗读，亲切直爽，"),
        ("湖南话", "用湖南话（长沙话）朗读，口音自然浓郁，"),
    ]),
    ("人物身份", [
        ("旁白大叔", "沉稳磁性的中年大叔旁白音，"),
        ("少女", "清亮俏皮的少女声，音调偏高，"),
        ("青年男", "阳光朝气的青年男声，中频清晰，"),
        ("老者", "苍老醇厚的老者声，语速缓慢，"),
        ("御姐", "慵懒高冷的御姐音，气声明显，"),
        ("萝莉", "稚嫩软糯的萝莉音，"),
        ("知性女", "温柔知性的成熟女声，"),
        ("威严男", "低沉威严的男性权威嗓音，"),
    ]),
    ("场合", [
        ("新闻播报", "标准新闻播报腔，吐字清晰语速平稳，"),
        ("有声书", "有声书旁白，娓娓道来富感染力，"),
        ("广告配音", "广告配音，节奏明快富煽动力，"),
        ("客服", "客服音色，亲切耐心微笑感，"),
        ("纪录片", "纪录片解说，沉稳厚重，"),
        ("动画配音", "动画角色配音，夸张生动，"),
    ]),
    ("情感语调", [
        ("温柔", "语气温柔舒缓，"),
        ("激昂", "情绪激昂高亢，语速偏快，"),
        ("悲伤", "悲伤低沉，语速放慢带哽咽感，"),
        ("俏皮", "俏皮活泼，语调上扬，"),
        ("严肃", "严肃郑重，吐字铿锵，"),
        ("慵懒", "慵懒随性，气声放松，"),
        ("紧张", "紧张急促，语速加快，"),
        ("诙谐", "幽默诙谐，带笑意，"),
    ]),
]

_YAML_PATH = Path(__file__).resolve().parent.parent / "assets" / "voice_presets.yaml"


def load_presets(path: Path | None = None) -> tuple[list, str]:
    """返回 (categories, dialect_note)。categories = [(name, [(label,text),...]), ...]。
    读 YAML；缺失/解析失败/结构非法 → 回退内置 _DEFAULTS。"""
    p = path or _YAML_PATH
    try:
        import yaml
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return _DEFAULTS, _DEFAULT_NOTE
        cats = []
        for c in data.get("categories", []) or []:
            name = c.get("name")
            items = [(it["label"], it["text"])
                     for it in (c.get("items") or [])
                     if isinstance(it, dict) and it.get("label") and it.get("text")]
            if name and items:
                cats.append((name, items))
        if not cats:
            return _DEFAULTS, _DEFAULT_NOTE
        return cats, (data.get("dialect_note") or _DEFAULT_NOTE)
    except Exception:
        return _DEFAULTS, _DEFAULT_NOTE


def load_emotion_vectors(path: Path | None = None) -> dict[str, list[float]]:
    """返回 {label: 8 维 list}，仅"情感语调"类别下显式带 vector 字段的项才进。
    YAML 当前没填 vector → 返回空 dict（dub_panel 调用方按 None 兜底）。"""
    p = path or _YAML_PATH
    out: dict[str, list[float]] = {}
    try:
        import yaml
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return out
        for c in data.get("categories", []) or []:
            if c.get("name") != "情感语调":
                continue
            for it in (c.get("items") or []):
                if not isinstance(it, dict):
                    continue
                vec = it.get("vector")
                if isinstance(vec, list) and len(vec) == 8 and it.get("label"):
                    out[it["label"]] = [float(x) for x in vec]
        return out
    except Exception:
        return out
