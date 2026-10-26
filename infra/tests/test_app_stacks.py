import json
from pathlib import Path

import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Match, Template

from stacks.application import API_CONCURRENCY, DAILY_QUESTION_LIMIT, ApplicationStack
from stacks.retrieval import RetrievalStack

ENV = cdk.Environment(account="123456789012", region="ap-southeast-2")


@pytest.fixture(scope="module")
def stacks(tmp_path_factory: pytest.TempPathFactory) -> tuple[Template, Template]:
    site: Path = tmp_path_factory.mktemp("site")
    (site / "index.html").write_text("<html></html>")
    app = cdk.App()
    retrieval = RetrievalStack(app, "Retrieval", env=ENV)
    application = ApplicationStack(app, "App", env=ENV, retrieval=retrieval, site_dir=site)
    return Template.from_stack(retrieval), Template.from_stack(application)


def test_aurora_scales_to_zero_behind_the_data_api(stacks) -> None:
    retrieval, _ = stacks
    retrieval.has_resource_properties(
        "AWS::RDS::DBCluster",
        {
            "EnableHttpEndpoint": True,
            "StorageEncrypted": True,
            "ServerlessV2ScalingConfiguration": Match.object_like({"MinCapacity": 0}),
        },
    )


def test_no_nat_gateways(stacks) -> None:
    for template in stacks:
        template.resource_count_is("AWS::EC2::NatGateway", 0)
        template.resource_count_is("AWS::EC2::InternetGateway", 0)


def test_public_api_is_capped(stacks) -> None:
    _, application = stacks
    application.has_resource_properties("AWS::Lambda::Url", {"AuthType": "NONE"})
    application.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "ReservedConcurrentExecutions": API_CONCURRENCY,
            "Environment": {
                "Variables": Match.object_like(
                    {"DAILY_QUESTION_LIMIT": str(DAILY_QUESTION_LIMIT), "WAREHOUSE": "athena"}
                )
            },
        },
    )


def test_api_reads_only_the_reader_secret(stacks) -> None:
    """The API connects as the SELECT-only database role, never as the admin user."""
    _, application = stacks
    policies = application.find_resources("AWS::IAM::Policy")
    api_policy = next(p for name, p in policies.items() if name.startswith("ApiServiceRole"))
    statements = api_policy["Properties"]["PolicyDocument"]["Statement"]
    secret_reads = [s for s in statements if "secretsmanager:GetSecretValue" in s["Action"]]
    assert len(secret_reads) == 1
    assert "ReaderSecret" in json.dumps(secret_reads[0]["Resource"])
    actions = json.dumps([s["Action"] for s in statements])
    assert "dynamodb:DeleteItem" not in actions and "dynamodb:Scan" not in actions
    assert "rds-data:BatchExecuteStatement" not in actions


def test_site_is_private_behind_cloudfront(stacks) -> None:
    _, application = stacks
    application.has_resource_properties(
        "AWS::S3::Bucket",
        {"PublicAccessBlockConfiguration": Match.object_like({"BlockPublicPolicy": True})},
    )
    application.resource_count_is("AWS::CloudFront::OriginAccessControl", 1)
    application.has_resource_properties(
        "AWS::CloudFront::Distribution",
        {
            "DistributionConfig": Match.object_like(
                {
                    "DefaultCacheBehavior": Match.object_like(
                        {"ViewerProtocolPolicy": "redirect-to-https"}
                    )
                }
            )
        },
    )
