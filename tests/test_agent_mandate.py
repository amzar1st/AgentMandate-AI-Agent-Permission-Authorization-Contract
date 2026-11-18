import json
from datetime import datetime, timezone

import pytest

CONTRACT = "contracts/agent_mandate.py"
CATEGORY = "PRODUCTIVITY"
PRODUCT = "taskboard-team"
AMOUNT = 2900
PRODUCTS = {
    PRODUCT: {
        "merchant": "TaskBoard",
        "plan": "Team Monthly",
        "terms": "One month only, automatic renewal disabled.",
        "evidence": "Shared project boards, sprint planning, and team task assignment.",
        "amount_cents": AMOUNT,
    }
}


@pytest.fixture
def mandate(direct_deploy, direct_vm, direct_alice, direct_bob):
    direct_vm.warp("2026-11-18T00:00:00Z")
    contract = direct_deploy(CONTRACT, sdk_version="v0.2.16")
    from genlayer import Address
    contract.create_mandate(
        Address(direct_alice), Address(direct_bob), "Project planning for the business only.",
        [CATEGORY], 4999, 5000, int(datetime(2026, 11, 18, 1, tzinfo=timezone.utc).timestamp()), json.dumps(PRODUCTS),
    )
    return contract


def request(contract, vm, agent, nonce=1):
    with vm.prank(agent):
        contract.request_action(nonce, PRODUCT, CATEGORY, AMOUNT)


def mock_label(vm, label):
    vm.mock_llm(r"Evaluate the purchase", json.dumps({"classification": label}))


def test_allow_and_consume_once(mandate, direct_vm, direct_alice, direct_bob):
    request(mandate, direct_vm, direct_alice)
    mock_label(direct_vm, CATEGORY)
    mandate.evaluate_action(1)
    permit = mandate.get_authorization(1)
    assert permit["decision"] == "ALLOW"
    assert permit["product"] == PRODUCTS[PRODUCT]
    assert len(permit["receipt"]) == 64
    assert direct_vm.run_validator()
    with direct_vm.prank(direct_alice), direct_vm.expect_revert("executor required"):
        mandate.consume_authorization(1, permit["receipt"])
    with direct_vm.prank(direct_bob):
        with direct_vm.expect_revert("receipt mismatch"):
            mandate.consume_authorization(1, "wrong")
        mandate.consume_authorization(1, permit["receipt"])
        with direct_vm.expect_revert("permit unavailable"):
            mandate.consume_authorization(1, permit["receipt"])
    assert mandate.get_authorization(1)["consumed"]
    assert mandate.get_mandate()["spent_cents"] == AMOUNT


@pytest.mark.parametrize("label,decision", [
    ("GAMBLING", "DENY"), ("POLICY_VIOLATION", "DENY"),
    ("DEVELOPER_TOOLS", "DENY"), ("UNCERTAIN", "REVIEW"),
    ("unexpected", "REVIEW"),
])
def test_non_allow_has_no_receipt(mandate, direct_vm, direct_alice, label, decision):
    request(mandate, direct_vm, direct_alice)
    mock_label(direct_vm, label)
    mandate.evaluate_action(1)
    permit = mandate.get_authorization(1)
    assert permit["decision"] == decision
    assert permit["receipt"] == ""


def test_validator_rejects_conflicting_classification(mandate, direct_vm, direct_alice):
    request(mandate, direct_vm, direct_alice)
    mock_label(direct_vm, CATEGORY)
    mandate.evaluate_action(1)
    direct_vm.clear_mocks()
    mock_label(direct_vm, "PERSONAL_ENTERTAINMENT")
    assert direct_vm.run_validator() is False


def test_budget_rechecked_at_consumption(mandate, direct_vm, direct_alice, direct_bob):
    mock_label(direct_vm, CATEGORY)
    for nonce in (1, 2):
        request(mandate, direct_vm, direct_alice, nonce)
        mandate.evaluate_action(nonce)
        assert mandate.get_authorization(nonce)["decision"] == "ALLOW"
    first = mandate.get_authorization(1)
    second = mandate.get_authorization(2)
    assert first["receipt"] != second["receipt"]
    with direct_vm.prank(direct_bob):
        mandate.consume_authorization(1, first["receipt"])
        with direct_vm.expect_revert("budget exceeded"):
            mandate.consume_authorization(2, second["receipt"])
    assert not mandate.get_authorization(2)["consumed"]


def test_revocation_blocks_outstanding_permits(mandate, direct_vm, direct_alice, direct_bob):
    request(mandate, direct_vm, direct_alice)
    mock_label(direct_vm, CATEGORY)
    mandate.evaluate_action(1)
    with direct_vm.prank(direct_alice), direct_vm.expect_revert("owner required"):
        mandate.revoke_mandate()
    mandate.revoke_mandate()
    with direct_vm.prank(direct_bob), direct_vm.expect_revert("mandate inactive"):
        mandate.consume_authorization(1, mandate.get_authorization(1)["receipt"])


def test_agent_cannot_change_quote_or_replay_nonce(mandate, direct_vm, direct_alice):
    with direct_vm.expect_revert("agent required"):
        mandate.request_action(1, PRODUCT, CATEGORY, AMOUNT)
    with direct_vm.prank(direct_alice), direct_vm.expect_revert("amount outside mandate or quote"):
        mandate.request_action(1, PRODUCT, CATEGORY, AMOUNT - 1)
    request(mandate, direct_vm, direct_alice)
    with direct_vm.expect_revert("unexpected nonce"):
        request(mandate, direct_vm, direct_alice)


def test_expiry_blocks_use_and_evaluation(mandate, direct_vm, direct_alice, direct_bob):
    request(mandate, direct_vm, direct_alice)
    request(mandate, direct_vm, direct_alice, 2)
    mock_label(direct_vm, CATEGORY)
    mandate.evaluate_action(1)
    direct_vm.warp("2026-11-18T00:15:00Z")
    with direct_vm.prank(direct_bob), direct_vm.expect_revert("permit expired"):
        mandate.consume_authorization(1, mandate.get_authorization(1)["receipt"])
    with direct_vm.expect_revert("action expired"):
        mandate.evaluate_action(2)
    direct_vm.warp("2026-11-18T01:00:00Z")
    with direct_vm.expect_revert("mandate expired"):
        request(mandate, direct_vm, direct_alice, 3)
