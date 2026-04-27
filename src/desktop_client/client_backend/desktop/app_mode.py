from __future__ import annotations

from enum import Enum


class DesktopAppMode(str, Enum):
    UNIFIED = "unified"
    SERVER = "server"
    CLIENT = "client"

    @classmethod
    def from_cli_target(cls, target: str) -> "DesktopAppMode":
        mapping = {
            "desktop": cls.UNIFIED,
            "desktop-server": cls.SERVER,
            "desktop-client": cls.CLIENT,
        }
        return mapping.get(target, cls.UNIFIED)
