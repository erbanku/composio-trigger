from __future__ import annotations

from pathlib import Path

import yaml

PLUGIN_DIR = Path(__file__).resolve().parent.parent


def test_manifest_has_required_fields() -> None:
    manifest = yaml.safe_load((PLUGIN_DIR / "manifest.yaml").read_text(encoding="utf-8"))
    for key in [
        "author", "name", "type", "label", "description", "icon", "plugins", "resource", "version", "created_at"
    ]:
        assert key in manifest, f"manifest missing: {key}"
    runner = manifest.get("meta", {}).get("runner", {})
    assert runner.get("language") == "python"
    assert str(runner.get("version")).startswith("3.")
    assert runner.get("entrypoint") == "main"
    assert "triggers" in manifest["plugins"]


def test_generated_yaml_files_exist() -> None:
    expected = ['events/connected_account_expired.yaml', 'events/trigger_message.yaml', 'provider/composio_trigger.yaml']
    for rel in expected:
        assert (PLUGIN_DIR / rel).exists(), f"missing YAML file: {rel}"
