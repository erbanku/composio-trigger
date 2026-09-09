import base64
import hashlib
import hmac
import json
import time
from types import SimpleNamespace

import httpx
import pytest
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from dify_plugin.errors.trigger import TriggerDispatchError
from provider.composio_trigger import ComposioTrigger, verify
from dify_plugin.entities.trigger import Subscription


SECRET = "webhook-secret"

def signed(payload, *, timestamp=None, signature_secret=SECRET):
    body = json.dumps(payload, separators=(",", ":")).encode()
    timestamp = int(timestamp if timestamp is not None else time.time())
    webhook_id = "msg_test"
    digest = hmac.new(signature_secret.encode(), f"{webhook_id}.{timestamp}.{body.decode()}".encode(), hashlib.sha256).digest()
    signature = "v1," + base64.b64encode(digest).decode()
    builder = EnvironBuilder(method="POST", data=body, headers={"webhook-id": webhook_id, "webhook-timestamp": str(timestamp), "webhook-signature": signature, "Content-Type": "application/json"})
    return Request(builder.get_environ())


def subscription():
    return Subscription(expires_at=-1, endpoint="https://dify.example/trigger", parameters={}, properties={"webhook_secret": SECRET, "subscription_id": "ws_test"})


def test_v3_trigger_message_dispatches_user_and_event():
    payload = {"id": "evt_1", "type": "composio.trigger.message", "metadata": {"trigger_slug": "OUTLOOK_NEW_EMAIL", "trigger_id": "ti_1", "user_id": "user_1"}, "data": {"subject": "hello"}}
    result = ComposioTrigger(runtime=None)._dispatch_event(subscription(), signed(payload))
    assert result.user_id == "user_1"
    assert result.events == ["trigger_message"]
    assert result.response.status_code == 200


def test_expired_account_dispatches_event_user_from_data():
    payload = {"type": "composio.connected_account.expired", "metadata": {}, "data": {"user_id": "user_2", "id": "ca_1"}}
    result = ComposioTrigger(runtime=None)._dispatch_event(subscription(), signed(payload))
    assert result.user_id == "user_2"
    assert result.events == ["connected_account_expired"]


@pytest.mark.parametrize("payload", [
    {"type": "composio.trigger.message", "metadata": {}, "data": {}},
    {"type": "composio.trigger.message", "metadata": {"trigger_slug": "X"}, "data": {}, "missing_user": True},
])
def test_invalid_event_metadata_rejected(payload):
    if payload["metadata"]:
        payload["metadata"]["user_id"] = "user"
    if payload.pop("missing_user", False):
        payload["metadata"].pop("user_id", None)
    with pytest.raises(TriggerDispatchError):
        ComposioTrigger(runtime=None)._dispatch_event(subscription(), signed(payload))


def test_unknown_project_event_acknowledges_without_dispatch():
    result = ComposioTrigger(runtime=None)._dispatch_event(subscription(), signed({"type": "composio.project.updated", "metadata": {}, "data": {}}))
    assert result.events == []
    assert result.response.status_code == 200


@pytest.mark.parametrize("request_factory", [lambda: signed({"type": "x"}, timestamp=time.time() - 301), lambda: signed({"type": "x"}, signature_secret="wrong")])
def test_replay_or_bad_signature_rejected(request_factory):
    with pytest.raises(TriggerDispatchError):
        verify(request_factory(), SECRET)


def test_missing_headers_rejected():
    request = signed({"type": "x"})
    request.environ.pop("HTTP_WEBHOOK_SIGNATURE", None)
    with pytest.raises(TriggerDispatchError):
        verify(request, SECRET)


def test_duplicate_signature_requires_one_valid_signature():
    payload = {"type": "composio.project.updated", "metadata": {}, "data": {}}
    request = signed(payload)
    request.environ["HTTP_WEBHOOK_SIGNATURE"] = "v1,invalid v1," + request.headers["webhook-signature"].split(",", 1)[1]
    assert verify(request, SECRET)["type"] == "composio.project.updated"


def test_raw_body_is_verified_not_reformatted():
    request = signed({"type": "x", "data": {"a": 1}})
    assert verify(request, SECRET)["data"]["a"] == 1
