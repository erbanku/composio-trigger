from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dify_plugin.interfaces.trigger import Event
from dify_plugin.entities.trigger import Variables


class ConnectedAccountExpiredEvent(Event):
    def _on_event(
        self,
        request,
        parameters: Mapping[str, Any],
        payload: Mapping[str, Any],
    ) -> Variables:
        return Variables(variables={"event": "connected_account_expired", "payload": dict(payload), "parameters": dict(parameters)})
