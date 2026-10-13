from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .models import Component


@dataclass(frozen=True)
class ComponentKey:
    category: str
    manufacturer: str
    part_no: str

    @classmethod
    def from_mapping(cls, value: Any) -> ComponentKey:
        if not isinstance(value, dict): raise ValueError("Each component preference must be an object.")
        unknown = set(value) - {"category", "manufacturer", "part_no"}
        if unknown: raise ValueError(f"Unsupported component preference fields: {', '.join(sorted(unknown))}")
        fields = {key: str(value.get(key, "")).strip() for key in ("category", "manufacturer", "part_no")}
        if not all(fields.values()):
            raise ValueError("Component preferences require category, manufacturer, and part_no.")
        return cls(**fields)

    @classmethod
    def from_component(cls, component: Component) -> ComponentKey:
        return cls(component.category, component.manufacturer, component.part_no)

    def normalized(self) -> tuple[str, str, str]:
        return tuple(value.casefold() for value in (self.category, self.manufacturer, self.part_no))

    def matches(self, component: Component) -> bool:
        return self.normalized() == self.from_component(component).normalized()

    def serialize(self) -> dict[str, str]:
        return {
            "category": self.category,
            "manufacturer": self.manufacturer,
            "part_no": self.part_no,
        }


@dataclass
class Preferences:
    favorite_manufacturers: list[str]       = field(default_factory=list)
    favorite_components: list[ComponentKey] = field(default_factory=list)

    @classmethod
    def from_mapping(cls, value: Any) -> Preferences:
        if not isinstance(value, dict): raise ValueError("Preferences must be a JSON object.")
        unknown = set(value) - {"favorite_manufacturers", "favorite_components"}
        if unknown: raise ValueError(f"Unsupported preference fields: {', '.join(sorted(unknown))}")
        manufacturers = value.get("favorite_manufacturers", [])
        components    = value.get("favorite_components", [])
        if not isinstance(manufacturers, list): raise ValueError("favorite_manufacturers must be an array.")
        if not isinstance(components, list): raise ValueError("favorite_components must be an array.")

        unique_manufacturers: dict[str, str] = {}
        for item in manufacturers:
            if not isinstance(item, str) or not item.strip():
                raise ValueError("Favorite manufacturer names must be non-empty strings.")
            unique_manufacturers.setdefault(item.strip().casefold(), item.strip())

        unique_components: dict[tuple[str, str, str], ComponentKey] = {}
        for item in components:
            key = ComponentKey.from_mapping(item)
            unique_components.setdefault(key.normalized(), key)
        return cls(list(unique_manufacturers.values()), list(unique_components.values()))

    def serialize(self) -> dict[str, Any]:
        return {
            "favorite_manufacturers": self.favorite_manufacturers,
            "favorite_components": [item.serialize() for item in self.favorite_components],
        }

    def score(self, components: Iterable[Component]) -> tuple[int, list[str]]:
        favorite_manufacturers = {item.casefold() for item in self.favorite_manufacturers}
        favorite_components    = {item.normalized() for item in self.favorite_components}
        score                  = 0
        matches                = []
        for component in components:
            if component.manufacturer.casefold() in favorite_manufacturers:
                score += 1
                matches.append(f"Manufacturer: {component.manufacturer}")
            if ComponentKey.from_component(component).normalized() in favorite_components:
                score += 2
                matches.append(f"Part: {component.manufacturer} {component.part_no}")
        return score, list(dict.fromkeys(matches))


class PreferenceRepository:

    def __init__(self, path: Path):
        self.path = Path(path) / "preferences.json"

    def load(self) -> Preferences:
        if not self.path.exists(): return Preferences()
        try:
            return Preferences.from_mapping(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError, ValueError):
            return Preferences()

    def save(self, preferences: Preferences) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(preferences.serialize(), handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, self.path)
