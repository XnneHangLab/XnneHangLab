from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass
class _ResponseWaiter:
    future: asyncio.Future[dict[Any, Any]]
    response_filter: Callable[[dict[Any, Any]], bool] | None = None


class MessageHandler:
    _NON_REPLAYABLE_MESSAGE_TYPES = {"interrupt-signal"}

    def __init__(self):
        self._response_waiters: dict[str, dict[str, list[_ResponseWaiter]]] = defaultdict(lambda: defaultdict(list))
        self._pending_messages: dict[str, dict[str, deque[dict[Any, Any]]]] = defaultdict(lambda: defaultdict(deque))

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
        pending_messages = self._pending_messages[client_uid][response_type]
        if pending_messages:
            matched_message = self._pop_matching_message(pending_messages, response_filter)
            if matched_message is not None:
                return matched_message

        future: asyncio.Future[dict[Any, Any]] = asyncio.get_running_loop().create_future()
        waiter = _ResponseWaiter(future=future, response_filter=response_filter)
        self._response_waiters[client_uid][response_type].append(waiter)

        try:
            if timeout is not None:
                return await asyncio.wait_for(future, timeout)
            return await future
        except TimeoutError:
            logger.warning(f"Timeout waiting for {response_type} from {client_uid}")
            return None
        finally:
            waiters = self._response_waiters.get(client_uid, {}).get(response_type)
            if waiters is not None:
                self._response_waiters[client_uid][response_type] = [
                    existing_waiter for existing_waiter in waiters if existing_waiter is not waiter
                ]
                if not self._response_waiters[client_uid][response_type]:
                    self._response_waiters[client_uid].pop(response_type, None)
            if client_uid in self._response_waiters and not self._response_waiters[client_uid]:
                self._response_waiters.pop(client_uid, None)
            if client_uid in self._pending_messages and not self._pending_messages[client_uid]:
                self._pending_messages.pop(client_uid, None)

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

        waiters = self._response_waiters.get(client_uid, {}).get(msg_type)
        if waiters:
            for waiter in list(waiters):
                if waiter.future.done():
                    continue
                if waiter.response_filter is None or waiter.response_filter(message):
                    waiter.future.set_result(message)
                    return

        if msg_type in self._NON_REPLAYABLE_MESSAGE_TYPES:
            return

        self._pending_messages[client_uid][msg_type].append(message)

    def cleanup_client(self, client_uid: str) -> None:
        """
        Cleanup all events and cached data for a given client.

        Args:
            client_uid: Client identifier
        """
        waiter_types = self._response_waiters.pop(client_uid, {})
        for waiters in waiter_types.values():
            for waiter in waiters:
                if not waiter.future.done():
                    waiter.future.cancel()

        self._pending_messages.pop(client_uid, None)

    def clear_pending_messages(self, client_uid: str, response_type: str | None = None) -> None:
        """Drop pending replayable messages for a client."""
        if response_type is None:
            self._pending_messages.pop(client_uid, None)
            return

        client_pending = self._pending_messages.get(client_uid)
        if client_pending is None:
            return

        client_pending.pop(response_type, None)
        if not client_pending:
            self._pending_messages.pop(client_uid, None)

    @staticmethod
    def _pop_matching_message(
        pending_messages: deque[dict[Any, Any]],
        response_filter: Callable[[dict[Any, Any]], bool] | None,
    ) -> dict[Any, Any] | None:
        kept_messages: deque[dict[Any, Any]] = deque()
        matched_message: dict[Any, Any] | None = None

        while pending_messages:
            candidate = pending_messages.popleft()
            if matched_message is None and (response_filter is None or response_filter(candidate)):
                matched_message = candidate
                continue
            kept_messages.append(candidate)

        pending_messages.extend(kept_messages)
        return matched_message


message_handler = MessageHandler()
