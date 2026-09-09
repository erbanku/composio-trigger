# Privacy

This trigger plugin sends the Composio project API key, Dify webhook URL, selected event types, and trigger-management requests to Composio's fixed HTTPS v3.1 API. Incoming signed Composio payloads are delivered to Dify and may be retained in workflow history according to Dify settings.

The webhook secret is used only for local HMAC verification. The plugin does not log raw payloads, store provider tokens, or forward payloads to other services. Event payload data is untrusted and can contain private email, calendar, chat, file, or issue information.

Operators are responsible for Composio trigger scopes, connected-account access, Dify workflow permissions, retention, and secret rotation. Unknown event types are acknowledged without dispatch. No provider event subscription is created until the Dify trigger subscription lifecycle invokes this plugin.
