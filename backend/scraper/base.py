from abc import ABC, abstractmethod
from typing import Any


class AbstractScraper(ABC):
    @abstractmethod
    def fetch(self) -> list[dict[str, Any]]:
        """Return raw source records. Never raises; logs and returns [] on failure."""
        ...

    @property
    @abstractmethod
    def source_name(self) -> str:
        ...
