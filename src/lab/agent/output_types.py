from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from typing import TypedDict


class ActionsDict(TypedDict):
    expressions: list[str] | list[int] | None
    pictures: list[str] | None
    sounds: list[str] | None
    emotion_keys: list[str] | None


@dataclass
class Actions:
    """Represents actions that can be performed alongside text output"""

    expressions: list[str] | list[int] | None = None
    pictures: list[str] | None = None
    sounds: list[str] | None = None
    emotion_keys: list[str] | None = None

    def to_dict(self) -> ActionsDict:
        """Convert Actions object to a dictionary for JSON serialization"""
        return ActionsDict(**asdict(self))


class BaseOutput(ABC):
    """Base class for agent outputs that can be iterated"""

    @abstractmethod
    def __aiter__(self):
        """Make the output iterable"""
        pass


class DisplayTextDict(TypedDict):
    text: str
    name: str | None
    avatar: str | None


@dataclass
class DisplayText:
    """Text to be displayed with optional metadata"""

    text: str
    name: str | None = "AI"  # Keep the name field for frontend display
    avatar: str | None = None

    def to_dict(self) -> DisplayTextDict:
        """Convert to dictionary for JSON serialization"""
        return DisplayTextDict(**asdict(self))

    def __str__(self) -> str:
        """String representation for logging"""
        return f"{self.name}: {self.text}"


@dataclass
class SentenceOutput(BaseOutput):
    """
    Output type for text-based responses.
    Contains a single sentence pair (display and TTS) with associated actions.

    Attributes:
        display_text: Text to be displayed in UI
        tts_text: Text to be sent to TTS engine
        actions: Associated actions (expressions, pictures, sounds)
    """

    display_text: DisplayText  # Changed from str to DisplayText
    tts_text: str  # Text for TTS
    actions: Actions

    async def __aiter__(self):  # type: ignore[override]
        """Yield the sentence pair and actions"""
        yield self.display_text, self.tts_text, self.actions


@dataclass
class AudioOutput(BaseOutput):
    """Output type for audio-based responses"""

    audio_path: str
    display_text: DisplayText  # Changed from str to DisplayText
    transcript: str  # Original transcript
    actions: Actions

    async def __aiter__(self):  # type: ignore[override]
        """Iterate through audio segments and their actions"""
        yield self.audio_path, self.display_text, self.transcript, self.actions
