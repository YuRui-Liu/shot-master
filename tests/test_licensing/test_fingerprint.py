from drama_shot_master.licensing import fingerprint


def test_machine_id_is_10_bytes_and_stable():
    a = fingerprint.machine_id()
    b = fingerprint.machine_id()
    assert isinstance(a, bytes) and len(a) == 10
    assert a == b                              # 同机多次一致


def test_machine_code_roundtrips_to_machine_id():
    mid = fingerprint.machine_id()
    code = fingerprint.machine_code()
    assert "-" in code
    assert fingerprint.decode_machine_code(code) == mid


def test_decode_tolerates_lower_and_spaces():
    code = fingerprint.machine_code()
    assert fingerprint.decode_machine_code(code.lower().replace("-", " ")) \
        == fingerprint.machine_id()


def test_dev_fallback_file_reused(tmp_path, monkeypatch):
    monkeypatch.setattr(fingerprint, "_seed_source", lambda: None)  # 强制走 dev 回退
    monkeypatch.setattr("drama_shot_master.licensing.paths.user_data_dir",
                        lambda: tmp_path)
    a = fingerprint.machine_id()
    b = fingerprint.machine_id()
    assert a == b
    assert (tmp_path / "dev_machine_id").exists()
