# AgentMandate

AgentMandate is a standalone GenLayer Intelligent Contract that lets a human delegate a limited set of business purchases to an AI agent. An independent executor consumes a permit before performing the corresponding purchase.

## How it works

1. The deployer calls `create_mandate` once with the agent and executor wallets, allowed categories, spending caps, expiry, and a catalog of product quotes and evidence. The policy hash commits to all of those inputs.
2. The agent calls `request_action` with the next nonce, catalog product ID, proposed category, and quoted USD amount in cents.
3. The owner, agent, or executor calls `evaluate_action`. The leader and validators independently classify the locked product evidence against the policy. The equivalence check requires the same normalized classification. GenLayer resolves disagreements through its consensus process. The contract then maps the accepted classification to `ALLOW`, `DENY`, or `REVIEW`.
4. The executor reads `get_authorization` from finalized state and checks the approved product, plan, terms, amount, and expiry against the actual purchase. It submits `consume_authorization` and waits for that transaction to finalize successfully before executing the purchase. The receipt is bound to the chain, contract, policy, nonce, and action. Only the designated executor can use it.
5. The owner can permanently call `revoke_mandate` to block new requests and invalidate outstanding permits.

The three allowed categories are `PRODUCTIVITY`, `DEVELOPER_TOOLS`, and `BUSINESS_OPERATIONS`. Evidence of gambling, cryptocurrency, personal entertainment, a policy violation, or a category mismatch yields `DENY`. Ambiguous evidence and unsupported model output yield `REVIEW`, which issues no permit.

## Try it in Studio

Load [contracts/agent_mandate.py](contracts/agent_mandate.py) into [GenLayer Studio](https://studio.genlayer.com/) and deploy with no constructor arguments. Use three accounts for the owner, agent, and executor.

For the example policy, pass `4999` as the inclusive per-purchase cap to enforce “under $50”, `10000` as the total budget, `["PRODUCTIVITY"]` as the categories, a future Unix timestamp in seconds as `expires_at`, and the following JSON **as a string** in `catalog_json`. The owner supplies the policy text, for example “Purchase project management tools for business use only.”

```json
{
  "taskboard-team": {
    "merchant": "TaskBoard",
    "plan": "Team Monthly",
    "terms": "One month only, automatic renewal disabled.",
    "evidence": "Shared project boards, sprint planning, and task assignment for teams.",
    "amount_cents": 2900
  }
}
```

As the agent, call `request_action(1, "taskboard-team", "PRODUCTIVITY", 2900)`. Evaluate nonce 1, read its receipt with `get_authorization(1)`, and consume it from the executor account. Use `get_mandate()` to inspect remaining capacity and the next nonce. Wait for writes to finalize between steps.

## Executor responsibilities

The catalog is an owner-curated evidence snapshot. Validators interpret it, and the executor verifies the real checkout against the snapshot, including taxes, fees, currency, billing period, and renewal terms. Use actionable evidence and keep private data out of the public contract. Renewals require their own permits.

Requests expire 15 minutes after submission or at mandate expiry, whichever comes first. Evaluation does not reserve funds. Successful consumption rechecks the budget and charges it atomically with marking the permit used. A failed checkout still uses that budget and receipt. Use the receipt as the merchant idempotency key where supported, and reconcile uncertain payment results before retrying. The executor is responsible for enforcing permits and performing purchases off-chain.

## Tests

Requires Python 3.12 or later.

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

The GenLayer Direct Mode suite uses mocked classifications and exercises permit consumption, validator disagreement, access control, replay prevention, revocation, and budget contention.

## Studionet deployment

Deployed on 2026-11-18 using GenLayer Studio in Normal (Full Consensus) mode.

- [Explorer contract](https://explorer-studio.genlayer.com/address/0xE2E6D6e64BC093f60940a8E7E222E2Bd3785e365)
- [Deployment transaction](https://explorer-studio.genlayer.com/tx/0xd864549a416d8665de011dea257d65e7340ceb02a13062fbc5bfb7e613ff3e17)
- Contract address: `0xE2E6D6e64BC093f60940a8E7E222E2Bd3785e365`

The deployed source is visible in Explorer. This instance has an unconfigured mandate. Deployment verifies construction and schema loading. Semantic purchase evaluation has been tested in Direct Mode with mocked LLM responses.
