from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from collections.abc import Mapping
from typing import Any

import httpx
from werkzeug import Request, Response

from dify_plugin.entities.provider_config import CredentialType
from dify_plugin.entities.trigger import EventDispatch, Subscription, UnsubscribeResult
from dify_plugin.errors.trigger import SubscriptionError, TriggerDispatchError, TriggerProviderCredentialValidationError
from dify_plugin.interfaces.trigger import Trigger, TriggerSubscriptionConstructor


BASE_URL = "https://backend.composio.dev/api/v3.1"
MAX_BODY_BYTES = 8 * 1024 * 1024
MAX_CLOCK_SKEW = 300
HTTP = httpx.Client(timeout=httpx.Timeout(30, connect=10), follow_redirects=False, trust_env=False)


def secret(credentials: Mapping[str, Any], name: str) -> str:
    value = credentials.get(name)
    if not isinstance(value, str) or not value.strip():
        raise TriggerProviderCredentialValidationError(f"{name} is required.")
    return value.strip()


def api_request(method: str, path: str, credentials: Mapping[str, Any], payload: dict | None = None) -> dict:
    try:
        response = HTTP.request(method, BASE_URL + path, headers={"x-api-key": secret(credentials, "api_key")}, json=payload)
        if not 200 <= response.status_code < 300:
            raise SubscriptionError(f"Composio trigger management request failed with HTTP {response.status_code}.")
        result = response.json()
        if not isinstance(result, dict):
            raise SubscriptionError("Composio returned an invalid trigger management response.")
        return result
    except httpx.HTTPError:
        raise SubscriptionError("Composio trigger management request failed or timed out.") from None
    except ValueError:
        raise SubscriptionError("Composio returned invalid JSON for trigger management.") from None


def verify(request: Request, signing_secret: str) -> dict:
    if not isinstance(signing_secret, str) or not signing_secret:
        raise TriggerDispatchError("Webhook signing secret is missing.")
    raw = request.get_data(cache=False, as_text=False)
    if len(raw) > MAX_BODY_BYTES:
        raise TriggerDispatchError("Webhook payload exceeds the 8 MiB limit.")
    webhook_id = request.headers.get("webhook-id", "")
    timestamp = request.headers.get("webhook-timestamp", "")
    signature_header = request.headers.get("webhook-signature", "")
    if not webhook_id or not timestamp or not signature_header:
        raise TriggerDispatchError("Missing Composio webhook signature headers.")
    try:
        timestamp_value = int(timestamp)
    except ValueError:
        raise TriggerDispatchError("Invalid Composio webhook timestamp.") from None
    if abs(time.time() - timestamp_value) > MAX_CLOCK_SKEW:
        raise TriggerDispatchError("Expired Composio webhook timestamp.")
    expected = base64.b64encode(hmac.new(signing_secret.encode(), f"{webhook_id}.{timestamp}.{raw.decode('utf-8')}".encode(), hashlib.sha256).digest()).decode()
    signatures = [item.split(",", 1)[1] if "," in item else item for item in signature_header.split()]
    if not any(hmac.compare_digest(expected, item) for item in signatures):
        raise TriggerDispatchError("Invalid Composio webhook signature.")
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise TriggerDispatchError("Composio webhook body is not valid JSON.") from None
    if not isinstance(payload, dict):
        raise TriggerDispatchError("Composio webhook body must be a JSON object.")
    return payload


class ComposioTrigger(Trigger):
    def _dispatch_event(self, subscription: Subscription, request: Request) -> EventDispatch:
        payload = verify(request, subscription.properties["webhook_secret"])
        event_type = payload.get("type")
        metadata = payload.get("metadata") or {}
        data = payload.get("data") or {}
        if event_type == "composio.trigger.message":
            slug = metadata.get("trigger_slug")
            if not isinstance(slug, str) or not slug:
                raise TriggerDispatchError("Composio trigger message is missing metadata.trigger_slug.")
            events = ["trigger_message"]
            user_id = str(metadata.get("user_id") or "")
        elif event_type == "composio.connected_account.expired":
            events = ["connected_account_expired"]
            user_id = str(data.get("user_id") or metadata.get("user_id") or "")
        else:
            return EventDispatch(user_id=str(metadata.get("user_id") or ""), events=[], response=Response('{"ok":true}', 200, mimetype="application/json"))
        if not user_id:
            raise TriggerDispatchError("Composio webhook is missing the event user ID.")
        return EventDispatch(user_id=user_id, events=events, response=Response('{"ok":true}', 200, mimetype="application/json"))


class ComposioTriggerSubscriptionConstructor(TriggerSubscriptionConstructor):
    def _validate_api_key(self, credentials: Mapping[str, Any]) -> None:
        secret(credentials, "api_key")

    def _create_subscription(self, endpoint: str, parameters: Mapping[str, Any], credentials: Mapping[str, Any], credential_type: CredentialType) -> Subscription:
        try:
            trigger_slug = str(parameters.get("trigger_slug") or "OUTLOOK_MESSAGE_TRIGGER")
            trigger_payload = {
                "connected_account_id": parameters.get("connected_account_id"),
                "user_id": parameters.get("user_id"),
                "trigger_config": parameters.get("trigger_config") or {},
            }
            trigger_payload = {key: value for key, value in trigger_payload.items() if value not in (None, "")}
            trigger_result = api_request("POST", f"/trigger_instances/{trigger_slug}/upsert", credentials, trigger_payload)
            trigger_id = trigger_result.get("trigger_id") or trigger_result.get("id")
            if not trigger_id:
                raise SubscriptionError("Composio did not return a trigger instance ID.")
            result = api_request("POST", "/webhook_subscriptions", credentials, {"webhook_url": endpoint, "enabled_events": ["composio.trigger.message", "composio.connected_account.expired"]})
            returned_secret = result.get("webhook_secret") or result.get("secret") or credentials.get("webhook_secret")
            if not isinstance(returned_secret, str) or not returned_secret:
                raise SubscriptionError("Composio returned no signing secret; configure the subscription secret before receiving events.")
            properties = {"webhook_secret": returned_secret or "", "subscription_id": result.get("id", ""), "trigger_id": trigger_id, "trigger_slug": trigger_slug}
            if not properties["subscription_id"]:
                raise SubscriptionError("Composio did not return a webhook subscription ID.")
            return Subscription(expires_at=-1, endpoint=endpoint, parameters=dict(parameters), properties=properties)
        except SubscriptionError:
            raise
    
    def _delete_subscription(self, subscription: Subscription, credentials: Mapping[str, Any], credential_type: CredentialType) -> UnsubscribeResult:
        subscription_id = subscription.properties.get("subscription_id")
        if not subscription_id:
            return UnsubscribeResult(success=False, message="Missing Composio webhook subscription ID.")
        api_request("DELETE", f"/webhook_subscriptions/{subscription_id}", credentials)
        trigger_id = subscription.properties.get("trigger_id")
        if trigger_id:
            api_request("DELETE", f"/trigger_instances/manage/{trigger_id}", credentials)
        return UnsubscribeResult(success=True, message="Composio webhook subscription removed.")

    def _refresh_subscription(self, subscription: Subscription, credentials: Mapping[str, Any], credential_type: CredentialType) -> Subscription:
        return subscription
