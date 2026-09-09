# Composio Trigger

`erbanku/composio-trigger` receives Composio trigger events in Dify workflows. It uses Composio API v3.1 to create one project webhook subscription per Dify trigger subscription, verifies every delivery with HMAC-SHA256 and a 300-second replay window, and dispatches V3 trigger and account-expiry events.

## Setup

1. Install `artifacts/composio-trigger-0.0.1.difypkg`.
2. Configure a Composio project API key.
3. Configure the webhook secret returned by Composio when the webhook subscription is created. Keep it in Dify credentials; never place it in event payloads or URLs.
4. Configure the Composio trigger instance separately through Composio's trigger API/SDK. A trigger instance needs a user ID, trigger type slug, trigger config, and optionally a specific connected-account ID.
5. Let Dify create the webhook subscription for the trigger. The plugin registers `composio.trigger.message` and `composio.connected_account.expired` for the Dify endpoint.

The Composio project webhook URL must be publicly reachable. Composio signs requests with `webhook-id`, `webhook-timestamp`, and `webhook-signature`. The plugin rejects missing headers, invalid signatures, old timestamps, malformed JSON, oversized bodies, and trigger messages without a user ID.

## Events

- `trigger_message`: V3 `composio.trigger.message`; event data remains in the event payload and metadata identifies the trigger slug, trigger instance, connected account, auth config, and user.
- `connected_account_expired`: V3 `composio.connected_account.expired`; use it to start a reconnect or notification workflow without trusting expired credentials.

Unknown Composio project events receive a safe 200 acknowledgement but are not dispatched to Dify. This prevents retry storms for lifecycle events the plugin does not expose.

## Lifecycle

Subscription creation calls `POST /api/v3.1/webhook_subscriptions` with the Dify endpoint and the two supported event types, then stores the returned subscription ID. Unsubscribe calls `DELETE /api/v3.1/webhook_subscriptions/{id}`. Refresh is a no-op because Composio webhook subscriptions do not expire. Trigger instance creation, enable/disable, and deletion remain Composio API responsibilities.

The plugin does not automatically create or delete Composio trigger instances. That separation avoids silently subscribing users to provider events and allows operators to choose exact toolkit trigger slugs and configs. Use Composio's current trigger type schema before creating an instance; trigger payload schemas can change with toolkit versions.

## Security notes

Use a dedicated project API key with only required trigger-management permissions. Do not log webhook secrets, raw payloads, authorization URLs, or provider data. Rotate the Composio webhook secret if it leaks, update Dify credentials, and recreate/refresh the subscription. The plugin performs no automatic retries after dispatch failures; Composio should retry its delivery according to its delivery policy.

The package pins and bundles `dify-plugin==0.6.0`, which provides native trigger subscription and event interfaces. No fallback classes or mocked SDK modules are used. Regression tests exercise credential verification through the real SDK's stdin/stdout request protocol, including missing credentials.

## References

- https://docs.composio.dev/docs/triggers
- https://docs.composio.dev/docs/setting-up-triggers/creating-triggers
- https://docs.composio.dev/docs/setting-up-triggers/subscribing-to-events
- https://docs.composio.dev/reference/api-reference/webhook-subscriptions
- https://docs.composio.dev/reference/api-reference/triggers
