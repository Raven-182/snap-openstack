# SPDX-FileCopyrightText: 2026 - Canonical Ltd
# SPDX-License-Identifier: Apache-2.0

"""Tests for the MAAS encrypted compute-storage step."""

from unittest import mock

from sunbeam.core.common import ResultType
from sunbeam.core.compute_storage import ComputeStorageConfig, NodeStorageConfig
from sunbeam.core.juju import ActionFailedException
from sunbeam.provider.maas.steps import MaasConfigureEncryptedStorageStep

NODE = "compute-1.example.com"


def make_config():
    return ComputeStorageConfig(
        vault_offer_url="vault.vault-kv",
        nodes={
            NODE: NodeStorageConfig(
                target="/dev/disk/by-id/wwn-0x1",
                existing_key_secret_id="secret:abc",
            )
        },
    )


def make_step(config=None):
    client = mock.MagicMock()
    client.cluster.get_node_info.return_value = {"machine_id": "5"}
    jhelper = mock.MagicMock()
    jhelper.get_unit_from_machine.return_value = "openstack-hypervisor/0"
    step = MaasConfigureEncryptedStorageStep(
        client, jhelper, "machine-model", config or make_config()
    )
    step.update_status = mock.MagicMock()
    return step, client, jhelper


def test_run_completes():
    step, client, jhelper = make_step()

    with mock.patch("sunbeam.provider.maas.steps.set_vault_kv_offer_url") as set_offer:
        result = step.run(mock.MagicMock())

    assert result.result_type == ResultType.COMPLETED
    set_offer.assert_called_once_with(client, "vault.vault-kv")
    jhelper.grant_secret.assert_called_once_with(
        "machine-model", "secret:abc", "vaultlocker-hypervisor"
    )
    client.cluster.get_node_info.assert_called_once_with(NODE)
    jhelper.get_unit_from_machine.assert_called_once_with(
        "openstack-hypervisor", "5", "machine-model"
    )
    jhelper.run_action.assert_called_once_with(
        "openstack-hypervisor/0",
        "machine-model",
        "configure-encrypted-storage",
        {
            "target": "/dev/disk/by-id/wwn-0x1",
            "existing-key-secret-id": "secret:abc",
        },
        timeout=1800,
    )


def test_run_action_failure_is_reported_with_host():
    step, _client, jhelper = make_step()
    jhelper.run_action.side_effect = ActionFailedException("boom")

    with mock.patch("sunbeam.provider.maas.steps.set_vault_kv_offer_url"):
        result = step.run(mock.MagicMock())

    assert result.result_type == ResultType.FAILED
    assert NODE in result.message


def test_run_rejects_conflicting_offer():
    step, _client, _jhelper = make_step()

    with mock.patch(
        "sunbeam.provider.maas.steps.set_vault_kv_offer_url",
        side_effect=ValueError("different vault-kv offer"),
    ):
        result = step.run(mock.MagicMock())

    assert result.result_type == ResultType.FAILED
