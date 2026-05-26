from sound_track_agent.provider import (
    build_soundtrack_provider, DEFAULT_MODEL, REQUEST_TIMEOUT,
)


class _Cfg:
    """模拟宿主 Config 的最小子集。"""
    def __init__(self, **kw):
        self.api_keys = kw.get("api_keys", {})
        self.base_urls = kw.get("base_urls", {})
        for k, v in kw.items():
            if k not in ("api_keys", "base_urls"):
                setattr(self, k, v)


def test_default_model_is_doubao_lite():
    assert DEFAULT_MODEL == "doubao-seed-2-0-lite-260215"


def test_build_uses_doubao_creds_from_base_urls():
    cfg = _Cfg(api_keys={"doubao": "k-doubao"},
               base_urls={"doubao": "https://ark.example/api/v3"})
    p = build_soundtrack_provider(cfg)
    assert p.config.api_key == "k-doubao"
    assert p.config.base_url == "https://ark.example/api/v3"
    assert p.config.model == DEFAULT_MODEL
    assert p.config.timeout == REQUEST_TIMEOUT


def test_soundtrack_overrides_take_priority():
    cfg = _Cfg(api_keys={"doubao": "k-doubao"},
               base_urls={"doubao": "https://ark.example/api/v3"},
               soundtrack_api_key="k-st",
               soundtrack_base_url="https://st.example/v1",
               soundtrack_model="doubao-custom")
    p = build_soundtrack_provider(cfg)
    assert p.config.api_key == "k-st"
    assert p.config.base_url == "https://st.example/v1"
    assert p.config.model == "doubao-custom"


def test_falls_back_to_refine_when_no_soundtrack_or_doubao():
    cfg = _Cfg(refine_api_key="k-refine",
               refine_base_url="https://ark.example/api/v3",
               refine_model="doubao-seed-2-0-lite-260215")
    p = build_soundtrack_provider(cfg)
    assert p.config.api_key == "k-refine"
    assert p.config.base_url == "https://ark.example/api/v3"
    assert p.config.model == "doubao-seed-2-0-lite-260215"


def test_refine_takes_priority_over_doubao_envkeys():
    cfg = _Cfg(api_keys={"doubao": "k-doubao"},
               base_urls={"doubao": "https://doubao.example/v3"},
               refine_api_key="k-refine",
               refine_base_url="https://refine.example/v3")
    p = build_soundtrack_provider(cfg)
    assert p.config.api_key == "k-refine"
    assert p.config.base_url == "https://refine.example/v3"
