import base64
import pytest
from drama_shot_master.providers import image_gen as IG


def test_doubao_payload_no_refs():
    p = IG.DoubaoImageProvider("k", "https://ark", "seedream")
    body = p._build_payload("画一只猫", [], size="2304x1296", n=2)
    assert body["model"] == "seedream" and body["prompt"] == "画一只猫"
    assert body["size"] == "2304x1296" and body["n"] == 2
    assert "image" not in body          # 无参考图=文生图
    assert body["watermark"] is False   # 默认无水印


def test_doubao_watermark_flag():
    on = IG.DoubaoImageProvider("k", "u", "m", watermark=True)
    off = IG.DoubaoImageProvider("k", "u", "m", watermark=False)
    assert on._build_payload("p", [], size=None, n=1)["watermark"] is True
    assert off._build_payload("p", [], size=None, n=1)["watermark"] is False


def test_doubao_payload_with_refs(tmp_path):
    img = tmp_path / "r.png"; img.write_bytes(b"\x89PNG\r\n")
    p = IG.DoubaoImageProvider("k", "https://ark", "seedream")
    body = p._build_payload("台词", [img], size=None, n=1)
    assert "size" not in body            # size=None 不带
    assert isinstance(body["image"], list) and len(body["image"]) == 1
    assert body["image"][0].startswith("data:image/png;base64,")


def test_doubao_parse_response():
    raw = base64.b64encode(b"IMGBYTES").decode()
    out = IG.DoubaoImageProvider("k", "u", "m")._parse_response(
        {"data": [{"b64_json": raw}]})
    assert out == [b"IMGBYTES"]


def test_factory_picks_provider():
    class C:
        imggen_provider = "doubao"; imggen_base_url = "https://ark"
        imggen_model = "seedream"; api_keys = {"doubao": "k"}
    assert isinstance(IG.make_image_provider(C()), IG.DoubaoImageProvider)
    C.imggen_provider = "runninghub"
    assert isinstance(IG.make_image_provider(C()), IG.RunningHubImageProvider)


def test_runninghub_stub_raises(tmp_path):
    p = IG.RunningHubImageProvider()
    with pytest.raises(IG.ImageGenError):
        p.generate("x", [], size=None, n=1)
