"""Reach data collectors for various sources."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Union

from ..models import ReachData

__all__ = ["BaseCollector"]


class BaseCollector(ABC):
    """Abstract base class for all reach data collectors."""

    source: str

    @abstractmethod
    def fetch(self, reach_id: Union[str, int]) -> Optional[ReachData]:
        """Fetch a reach by ID from the remote source."""
        ...

    @abstractmethod
    def from_file(self, path: Path) -> Optional[ReachData]:
        """Load a reach from a local fixture file."""
        ...

    @abstractmethod
    def _normalize(self, raw: dict) -> ReachData:
        """Normalize source-specific raw dict to ReachData."""
        ...
