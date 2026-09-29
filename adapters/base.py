from __future__ import annotations

from abc import ABC, abstractmethod


class IntentAdapter(ABC):
    @abstractmethod
    def compile_intent(self, prompt: str, previz_context: dict, screenshot: str | None = None) -> dict:
        raise NotImplementedError

