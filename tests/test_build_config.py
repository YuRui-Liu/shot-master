"""打包脚本一致性守护：含必需包/模板，排除 license/tests/个人配置。"""
from pathlib import Path

_BAT = Path(__file__).resolve().parents[1] / "build" / "build_client.bat"


def _txt() -> str:
    return _BAT.read_text(encoding="utf-8")


def test_includes_required_packages():
    t = _txt()
    for pkg in ("drama_shot_master", "screenwriter_agent", "sound_track_agent"):
        assert f"--include-package={pkg}" in t, f"缺打包 {pkg}"


def test_includes_prompt_templates():
    t = _txt()
    assert "drama_shot_master/templates=drama_shot_master/templates" in t
    assert "screenwriter_agent/templates=screenwriter_agent/templates" in t


def test_excludes_license_admin_and_tests():
    t = _txt()
    assert "--nofollow-import-to=license_admin" in t
    assert "--nofollow-import-to=tests" in t


def test_does_not_bundle_personal_config():
    """绝不显式把 .env / settings.json 打进包（防 api_key / 项目文件泄露）。

    只检查没有 --include-data-* 把它们收录；注释里提及（说明被排除）是允许的。
    """
    for line in _txt().splitlines():
        s = line.strip()
        if s.startswith("REM") or s.startswith("@"):
            continue                       # 注释行允许提及
        if "--include-data" in s:
            assert ".env" not in s, f"误打包 .env: {s}"
            assert "settings.json" not in s, f"误打包 settings.json: {s}"
