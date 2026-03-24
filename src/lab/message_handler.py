from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from collections.abc import Callable


class MessageHandler:
    def __init__(self):
        self._response_events: dict[str, dict[str, asyncio.Event]] = defaultdict(dict)
        self._response_data: dict[str, dict[str, dict[Any, Any]]] = defaultdict(dict)

    async def wait_for_response(
        self,
        client_uid: str,
        response_type: str,
        timeout: float | None = None,
        response_filter: Callable[[dict[Any, Any]], bool] | None = None,
    ) -> dict[Any, Any] | None:
        """
        Wait for a response of specific type from a client.

        Args:
            client_uid: Client identifier
            response_type: Type of response to wait for
            timeout: Optional timeout in seconds. If None, wait indefinitely

        Returns:
            Optional[dict]: Response data if received, None if timeout
        """
        event = asyncio.Event()
        self._response_events[client_uid][response_type] = event

        try:
            while True:
                if timeout is not None:
                    await asyncio.wait_for(event.wait(), timeout)
                else:
                    await event.wait()

                response = self._response_data[client_uid].pop(response_type, None)
                event.clear()
                if response is None:
                    continue
                if response_filter is None or response_filter(response):
                    return response
        except TimeoutError:
            logger.warning(f"Timeout waiting for {response_type} from {client_uid}")
            return None
        finally:
            self._response_events[client_uid].pop(response_type, None)

    def handle_message(self, client_uid: str, message: dict[Any, Any]) -> None:
        """
        Process an incoming message with a response event waiting.

        Args:
            client_uid: Client identifier
            message: Message data dictionary
        """
        msg_type = message.get("type")
        if not msg_type:
            return

        if client_uid in self._response_events and msg_type in self._response_events[client_uid]:
            self._response_data[client_uid][msg_type] = message
            self._response_events[client_uid][msg_type].set()

    def cleanup_client(self, client_uid: str) -> None:
        """
        Cleanup all events and cached data for a given client.

        Args:
            client_uid: Client identifier
        """
        if client_uid in self._response_events:
            for event in self._response_events[client_uid].values():
                event.set()
            self._response_events.pop(client_uid)
            self._response_data.pop(client_uid, None)


message_handler = MessageHandler()
