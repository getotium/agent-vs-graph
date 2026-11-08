"""Local settings: the committed defaults, overridden key by key by a machine's local.toml."""

from pathlib import Path

import pytest

from avg import config

DEFAULT = Path(__file__).resolve().parents[1] / "local.default.toml"


def test_committed_defaults_load_and_pin_no_device(tmp_path):
    local = config.load(DEFAULT, tmp_path / "absent.toml")
    assert local.device == "", "the committed file names no machine's GPU"
    assert local.harness_ctx == 65536 and local.llama_server.endswith("llama-server")


def test_local_file_overrides_only_its_keys(tmp_path):
    (tmp_path / "local.toml").write_text('device = "X9"\nharness_ctx = 32768\n', encoding="utf-8")
    local = config.load(DEFAULT, tmp_path / "local.toml")
    assert (local.device, local.harness_ctx) == ("X9", 32768)
    assert local.large_gguf == config.load(DEFAULT, tmp_path / "absent.toml").large_gguf


def test_unknown_key_is_refused(tmp_path):
    (tmp_path / "local.toml").write_text('devcie = "X9"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="unknown key"):
        config.load(DEFAULT, tmp_path / "local.toml")
