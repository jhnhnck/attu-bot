# SPDX-License-Identifier: Apache-2.0
"""nova_core.manifest | feature manifest dataclass."""

from collections.abc import Callable
from dataclasses import dataclass, field

from discord import Bot
from pydantic import BaseModel

from nova_core.tasks.base import BaseTask


@dataclass
class FeatureManifest:
    """Manifest declaring all wiring for a loadable feature package."""

    name: str
    tasks: list[BaseTask] = field(default_factory=list)
    event_handlers: dict[str, Callable] = field(default_factory=dict)
    setup: Callable[[Bot], None] | None = None
    guild_config_key: str | None = None
    guild_config_model: type[BaseModel] | None = None
    document_classes: list[type] = field(default_factory=list)
    repository_classes: list[type] = field(default_factory=list)
    migrations: list = field(default_factory=list)
