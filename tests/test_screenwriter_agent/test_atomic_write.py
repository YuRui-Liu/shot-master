from pathlib import Path
import os
import pytest
from screenwriter_agent.core.atomic_write import atomic_write_text


def test_atomic_write_creates_file(tmp_path):
    p = tmp_path / "out.txt"
    atomic_write_text(p, "hello")
    assert p.read_text(encoding="utf-8") == "hello"


def test_atomic_write_overwrite_existing(tmp_path):
    p = tmp_path / "out.txt"
    p.write_text("old", encoding="utf-8")
    atomic_write_text(p, "new")
    assert p.read_text(encoding="utf-8") == "new"


def test_atomic_write_does_not_leave_tmp_on_success(tmp_path):
    p = tmp_path / "out.txt"
    atomic_write_text(p, "x")
    assert not (tmp_path / "out.txt.tmp").exists()
