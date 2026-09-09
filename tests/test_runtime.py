import pytest

from provider.composio_trigger import ComposioTriggerSubscriptionConstructor


def test_real_sdk_provider_validation_uses_api_key_only():
    constructor = ComposioTriggerSubscriptionConstructor(runtime=None)
    constructor.validate_api_key({"api_key": "test-key"})


def test_real_sdk_provider_validation_rejects_missing_api_key():
    constructor = ComposioTriggerSubscriptionConstructor(runtime=None)
    with pytest.raises(Exception, match="api_key is required"):
        constructor.validate_api_key({})


def test_real_event_handlers_are_instantiable():
    from events.trigger_message import TriggerMessageEvent
    from events.connected_account_expired import ConnectedAccountExpiredEvent

    for event_class in (TriggerMessageEvent, ConnectedAccountExpiredEvent):
        event = event_class(runtime=None)
        assert event._on_event(None, {}, {"subject": "test"}).variables["payload"] == {"subject": "test"}
