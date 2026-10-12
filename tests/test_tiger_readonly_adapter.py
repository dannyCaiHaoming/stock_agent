from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from product.broker.tiger.adapter import (
    ALL_ORDER_STATES,
    TigerAdapterError,
    TigerReadOnlyAdapter,
    load_capability_manifest,
)
from product.broker.tiger.config import TigerConfigError, preflight_config


class FakeTigerClient:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def _record(self, name, kwargs, result):
        self.calls.append((name, kwargs))
        return result

    def get_managed_accounts(self, **kwargs):
        return self._record("get_managed_accounts", kwargs, [object()])

    def get_prime_assets(self, **kwargs):
        return self._record("get_prime_assets", kwargs, object())

    def get_positions(self, **kwargs):
        return self._record("get_positions", kwargs, [])

    def get_analytics_asset(self, **kwargs):
        return self._record("get_analytics_asset", kwargs, {"history": []})

    def get_orders(self, **kwargs):
        return self._record("get_orders", kwargs, [])

    def get_order(self, **kwargs):
        return self._record("get_order", kwargs, object())

    def get_transactions(self, **kwargs):
        return self._record("get_transactions", kwargs, [])

    def get_fund_details(self, **kwargs):
        return self._record("get_fund_details", kwargs, [])

    def get_funding_history(self, **kwargs):
        return self._record("get_funding_history", kwargs, [])

    def place_order(self, **kwargs):
        raise AssertionError("write method must never be called")


class TigerReadonlyAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.repository = self.base / "repo"
        self.repository.mkdir(mode=0o700)

    def tearDown(self):
        self.temporary.cleanup()

    def config_dir(self, *, license_value="TBHK", token="local-token", private_key_field="private_key_pk8") -> Path:
        value = self.base / "private-config"
        value.mkdir(mode=0o700)
        config = value / "tiger_openapi_config.properties"
        config.write_text(
            "tiger_id=local-id\naccount=private-account\n"
            f"{private_key_field}=private-key-material\n"
            f"license={license_value}\n",
            encoding="utf-8",
        )
        token_file = value / "tiger_openapi_token.properties"
        token_file.write_text(f"token={token}\n", encoding="utf-8")
        os.chmod(config, 0o600)
        os.chmod(token_file, 0o600)
        return value

    def test_preflight_returns_only_status_metadata(self):
        config_dir = self.config_dir()
        result = preflight_config(config_dir, repository_root=self.repository).to_dict()
        self.assertEqual(result["status"], "READY")
        self.assertEqual(result["license"], "TBHK")
        serialized = json.dumps(result)
        self.assertNotIn("private-account", serialized)
        self.assertNotIn("private-key-material", serialized)
        self.assertNotIn("local-token", serialized)
        self.assertNotIn(str(config_dir), serialized)

        for field in ("private_key", "private_key_pk1", "private_key_pk8"):
            alternate = self.base / f"private-{field}"
            alternate.mkdir(mode=0o700)
            config = alternate / "tiger_openapi_config.properties"
            config.write_text(
                f"tiger_id=x\naccount=x\n{field}=key\nlicense=TBHK\n",
                encoding="utf-8",
            )
            token = alternate / "tiger_openapi_token.properties"
            token.write_text("token=x\n", encoding="utf-8")
            os.chmod(config, 0o600)
            os.chmod(token, 0o600)
            self.assertEqual(preflight_config(alternate, repository_root=self.repository).status, "READY")

    def test_preflight_fail_closed_for_path_permissions_and_license(self):
        inside = self.repository / "config"
        inside.mkdir(mode=0o700)
        for name, body in (
            ("tiger_openapi_config.properties", "tiger_id=x\naccount=x\nprivate_key=x\nlicense=TBHK\n"),
            ("tiger_openapi_token.properties", "token=x\n"),
        ):
            path = inside / name
            path.write_text(body, encoding="utf-8")
            os.chmod(path, 0o600)
        with self.assertRaisesRegex(TigerConfigError, "INSIDE_REPOSITORY"):
            preflight_config(inside, repository_root=self.repository)

        wrong_license = self.config_dir(license_value="TBSG")
        result = preflight_config(wrong_license, repository_root=self.repository)
        self.assertEqual((result.status, result.code), ("BLOCKED", "TIGER_LICENSE_NOT_TBHK"))

        os.chmod(wrong_license / "tiger_openapi_config.properties", 0o644)
        with self.assertRaisesRegex(TigerConfigError, "PERMISSIONS_TOO_OPEN"):
            preflight_config(wrong_license, repository_root=self.repository)

    def test_preflight_rejects_symlink_and_missing_token(self):
        config_dir = self.config_dir()
        linked = self.base / "linked"
        linked.symlink_to(config_dir, target_is_directory=True)
        with self.assertRaisesRegex(TigerConfigError, "SYMLINK_REJECTED"):
            preflight_config(linked, repository_root=self.repository)
        (config_dir / "tiger_openapi_token.properties").unlink()
        with self.assertRaisesRegex(TigerConfigError, "TOKEN_FILE_MISSING"):
            preflight_config(config_dir, repository_root=self.repository)

        missing_private = self.base / "missing-private"
        missing_private.mkdir(mode=0o700)
        config = missing_private / "tiger_openapi_config.properties"
        config.write_text("tiger_id=x\naccount=x\nlicense=TBHK\npublic_key=not-a-private-key\n", encoding="utf-8")
        token = missing_private / "tiger_openapi_token.properties"
        token.write_text("token=x\n", encoding="utf-8")
        os.chmod(config, 0o600)
        os.chmod(token, 0o600)
        result = preflight_config(missing_private, repository_root=self.repository)
        self.assertEqual((result.status, result.code), ("BLOCKED", "TIGER_CONFIG_FIELDS_MISSING"))
        self.assertEqual(result.missing_fields, ("private_key",))

    def test_manifest_and_wrapper_expose_only_fixed_reads(self):
        manifest = load_capability_manifest()
        allowed = {item["sdk_method"] for item in manifest["capabilities"]}
        forbidden = set(manifest["forbidden_sdk_methods"])
        self.assertFalse(allowed & forbidden)
        self.assertTrue(all(item["read_only"] for item in manifest["capabilities"]))
        self.assertEqual(manifest["sdk_version"], "3.8.0")
        self.assertEqual(len(manifest["sdk_wheel_sha256"]), 64)

        fake = FakeTigerClient()
        adapter = TigerReadOnlyAdapter(fake, sdk_version="3.8.0", manifest=manifest)
        adapter.orders(start_time="2026-01-01", end_time="2026-04-01", page_token="next")
        self.assertEqual(fake.calls[0][0], "get_orders")
        self.assertEqual(tuple(fake.calls[0][1]["states"]), ALL_ORDER_STATES)
        self.assertEqual(fake.calls[0][1]["page_token"], "next")
        with self.assertRaisesRegex(TigerAdapterError, "METHOD_NOT_ALLOWED"):
            adapter.call("place_order", symbol="AAPL")
        self.assertEqual(len(fake.calls), 1)
        for method in forbidden | {"unknown_method"}:
            self.assertFalse(hasattr(adapter, method), method)
        self.assertFalse(hasattr(adapter, "client"))

    def test_sdk_version_mismatch_is_rejected_before_use(self):
        with self.assertRaisesRegex(TigerAdapterError, "VERSION_MISMATCH"):
            TigerReadOnlyAdapter(FakeTigerClient(), sdk_version="3.7.2")

    def test_sdk_constructor_rejects_environment_credential_override(self):
        config_dir = self.config_dir()
        with mock.patch.dict(os.environ, {"TIGEROPEN_TOKEN": "must-not-use"}, clear=False):
            with self.assertRaisesRegex(TigerAdapterError, "ENV_CREDENTIALS_REJECTED"):
                TigerReadOnlyAdapter.from_config(config_dir, repository_root=self.repository)


if __name__ == "__main__":
    unittest.main()
