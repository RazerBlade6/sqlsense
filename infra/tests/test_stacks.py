import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Match, Template

from stacks.data import SCAN_LIMIT_BYTES, WAREHOUSE, DataStack
from stacks.foundation import FoundationStack

ENV = cdk.Environment(account="123456789012", region="ap-southeast-2")


@pytest.fixture(scope="module")
def data_template() -> Template:
    if not (WAREHOUSE / "retail").exists():
        pytest.skip("run data/build.py first")
    return Template.from_stack(DataStack(cdk.App(), "Data", env=ENV))


@pytest.fixture(scope="module")
def foundation_template() -> Template:
    stack = FoundationStack(
        cdk.App(), "Foundation", env=ENV, github_repo="owner/repo", monthly_budget_usd=25
    )
    return Template.from_stack(stack)


def test_workgroup_enforces_scan_limit(data_template: Template) -> None:
    data_template.has_resource_properties(
        "AWS::Athena::WorkGroup",
        {
            "WorkGroupConfiguration": Match.object_like(
                {
                    "EnforceWorkGroupConfiguration": True,
                    "BytesScannedCutoffPerQuery": SCAN_LIMIT_BYTES,
                }
            )
        },
    )


def test_warehouse_bucket_is_private_and_tls_only(data_template: Template) -> None:
    data_template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "PublicAccessBlockConfiguration": {
                "BlockPublicAcls": True,
                "BlockPublicPolicy": True,
                "IgnorePublicAcls": True,
                "RestrictPublicBuckets": True,
            }
        },
    )
    data_template.has_resource_properties(
        "AWS::S3::BucketPolicy",
        {
            "PolicyDocument": {
                "Statement": Match.array_with(
                    [
                        Match.object_like(
                            {
                                "Effect": "Deny",
                                "Condition": {"Bool": {"aws:SecureTransport": "false"}},
                            }
                        )
                    ]
                )
            }
        },
    )


def test_read_policy_grants_no_writes(data_template: Template) -> None:
    policies = data_template.find_resources("AWS::IAM::ManagedPolicy")
    statements = [
        statement
        for policy in policies.values()
        for statement in policy["Properties"]["PolicyDocument"]["Statement"]
    ]
    actions = [
        action
        for statement in statements
        for action in (
            statement["Action"] if isinstance(statement["Action"], list) else [statement["Action"]]
        )
    ]
    assert actions
    assert not [a for a in actions if a.split(":")[1].startswith(("Put", "Delete", "Create"))]


def test_deploy_role_trusts_only_production_environment(foundation_template: Template) -> None:
    foundation_template.has_resource_properties(
        "AWS::IAM::Role",
        {
            "RoleName": "sqlsense-github-deploy",
            "AssumeRolePolicyDocument": {
                "Statement": [
                    Match.object_like(
                        {
                            "Condition": {
                                "StringEquals": {
                                    "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
                                },
                                "StringLike": {
                                    "token.actions.githubusercontent.com:sub": [
                                        "repo:owner/repo:environment:production"
                                    ]
                                },
                            }
                        }
                    )
                ]
            },
        },
    )
