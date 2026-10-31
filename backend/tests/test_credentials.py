"""Bedrock credentials (llm/credentials.py) with real STS calls.

The assume-role success path needs a real BobBedrockAccess role: set BOB_TEST_ROLE_ARN (and
BOB_TEST_EXTERNAL_ID) to run it. Without it, the test is skipped (no fake role, no fake credentials).
"""

import os

import pytest

from bob.core.models import BedrockAccess
from bob.llm.credentials import bedrock_runtime, refreshable_credentials, session_name, verify_access


def test_session_name_limits():
    assert session_name("abc") == "bob-abc"
    assert len(session_name("x" * 100)) == 64
    assert session_name("a b/c") == "bob-a-b-c"


def test_default_chain_verify_real():
    res = verify_access(BedrockAccess(mode="default", region="us-east-1"), "local")
    assert res["ok"], res
    assert res["identity"].startswith("arn:aws:")


def test_assume_role_exact_error_real():
    """A role that does not exist: STS returns AccessDenied; verify passes the exact error on."""
    ident = verify_access(BedrockAccess(mode="default", region="us-east-1"), "local")["identity"]
    account = ident.split(":")[4]
    access = BedrockAccess(
        mode="assume_role",
        role_arn=f"arn:aws:iam::{account}:role/BobTestRoleThatDoesNotExist",
        external_id="00000000-0000-4000-8000-000000000000",
        region="us-east-1",
    )
    res = verify_access(access, "local")
    assert res["ok"] is False
    assert "AccessDenied" in res["error"] and "AssumeRole" in res["error"]


@pytest.mark.skipif(not os.environ.get("BOB_TEST_ROLE_ARN"), reason="needs a real BobBedrockAccess role")
def test_assume_role_refreshable_real():
    access = BedrockAccess(
        mode="assume_role",
        role_arn=os.environ["BOB_TEST_ROLE_ARN"],
        external_id=os.environ.get("BOB_TEST_EXTERNAL_ID"),
        region="us-east-1",
    )
    creds = refreshable_credentials(access, "cred-test")
    assert creds.get_frozen_credentials().token
    assert creds._advisory_refresh_timeout == 300
    client = bedrock_runtime(access, "cred-test")
    r = client.converse(
        modelId="global.anthropic.claude-haiku-5-5",
        messages=[{"role": "user", "content": [{"text": "Say ok."}]}],
        inferenceConfig={"maxTokens": 20},
    )
    assert r["output"]["message"]["content"]
