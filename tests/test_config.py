import json

import pytest

from backend.config import DEFAULT_CONFIG_PATH, PipelineConfig, load_config


def test_repository_config_is_valid():
    config = load_config(DEFAULT_CONFIG_PATH)

    assert isinstance(config.pipeline, PipelineConfig)
    assert config.pipeline.workers == 4
    assert config.server.port == 5000


def test_config_uses_defaults_for_missing_fields(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"pipeline": {"offline": True}}), encoding="utf-8")

    config = load_config(path)

    assert config.pipeline.offline is True
    assert config.pipeline.workers == 4
    assert config.server.host == "127.0.0.1"


def test_config_rejects_unknown_fields(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"pipeline": {"threads": 4}}), encoding="utf-8")

    with pytest.raises(ValueError, match="threads"):
        load_config(path)


def test_config_rejects_invalid_values(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"pipeline": {"workers": 0}}), encoding="utf-8")

    with pytest.raises(ValueError, match="workers"):
        load_config(path)
