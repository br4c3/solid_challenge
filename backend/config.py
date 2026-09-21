from __future__ import annotations

import json
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Mapping, TypeVar

BACKEND_DIR         = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = BACKEND_DIR / "config.json"
ConfigType          = TypeVar("ConfigType", bound="ConfigSection")


@dataclass(frozen=True)
class ConfigSection:

    @classmethod
    def from_mapping(cls: type[ConfigType], values: Mapping[str, Any]) -> ConfigType:
        allowed = {item.name for item in fields(cls)}
        unknown = set(values) - allowed
        if unknown: raise ValueError(f"Unsupported {cls.__name__} fields: {', '.join(sorted(unknown))}")
        return cls(**values)


@dataclass(frozen=True)
class PipelineConfig(ConfigSection):
    offline: bool  = False
    limit: int     = 0
    part_no: str   = ""
    workers: int   = 4
    discover: bool = True

    def validate(self) -> None:
        if type(self.offline) is not bool: raise ValueError("pipeline.offline must be a boolean.")
        if type(self.limit) is not int or self.limit < 0:
            raise ValueError("pipeline.limit must be a non-negative integer.")
        if not isinstance(self.part_no, str): raise ValueError("pipeline.part_no must be a string.")
        if type(self.workers) is not int or self.workers < 1:
            raise ValueError("pipeline.workers must be a positive integer.")
        if type(self.discover) is not bool: raise ValueError("pipeline.discover must be a boolean.")


@dataclass(frozen=True)
class ServerConfig(ConfigSection):
    start_after_pipeline: bool = False
    host: str                  = "127.0.0.1"
    port: int                  = 5000
    debug: bool                = False

    def validate(self) -> None:
        if type(self.start_after_pipeline) is not bool:
            raise ValueError("server.start_after_pipeline must be a boolean.")
        if not isinstance(self.host, str) or not self.host.strip():
            raise ValueError("server.host must be a non-empty string.")
        if type(self.port) is not int or not 1 <= self.port <= 65535:
            raise ValueError("server.port must be an integer between 1 and 65535.")
        if type(self.debug) is not bool: raise ValueError("server.debug must be a boolean.")


@dataclass(frozen=True)
class ProjectConfig:
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)
    server: ServerConfig     = field(default_factory=ServerConfig)


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> ProjectConfig:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Configuration file was not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Configuration file contains invalid JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict): raise ValueError("Configuration root must be a JSON object.")
    unknown = set(payload) - {"pipeline", "server"}
    if unknown: raise ValueError(f"Unsupported configuration sections: {', '.join(sorted(unknown))}")
    pipeline_values = payload.get("pipeline", {})
    server_values   = payload.get("server", {})
    if not isinstance(pipeline_values, dict): raise ValueError("pipeline must be a JSON object.")
    if not isinstance(server_values, dict): raise ValueError("server must be a JSON object.")
    pipeline = PipelineConfig.from_mapping(pipeline_values)
    server   = ServerConfig.from_mapping(server_values)
    pipeline.validate()
    server.validate()
    return ProjectConfig(pipeline, server)
