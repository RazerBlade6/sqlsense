from aws_cdk import CfnOutput, CfnParameter, Duration, Stack
from aws_cdk import aws_budgets as budgets
from aws_cdk import aws_iam as iam
from constructs import Construct

# Bedrock models the app and CI may call. Cross-Region inference profiles route to
# foundation models in other Regions, hence the wildcard Region on model ARNs.
BEDROCK_MODELS = [
    "amazon.nova-pro-v1:0",
    "amazon.nova-micro-v1:0",
    "amazon.titan-embed-text-v2:0",
    "anthropic.claude-sonnet-5-5",
    "anthropic.claude-haiku-5-5",
]
INFERENCE_PROFILES = [
    "apac.amazon.nova-pro-v1:0",
    "apac.amazon.nova-micro-v1:0",
    "au.anthropic.claude-sonnet-5-5",
    "au.anthropic.claude-haiku-5-5",
]

# Kept in SSM rather than the repo, which is public.
BUDGET_EMAIL_PARAMETER = "/sqlsense/budget-email"


class FoundationStack(Stack):
    """Account-level guardrails and the OIDC roles GitHub Actions assumes for CI and CD."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        github_repo: str,
        monthly_budget_usd: int,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        budget_email = CfnParameter(
            self,
            "BudgetEmail",
            type="AWS::SSM::Parameter::Value<String>",
            default=BUDGET_EMAIL_PARAMETER,
            description="SSM parameter holding the budget alert email",
        )
        self._budget(monthly_budget_usd, budget_email.value_as_string)

        provider = iam.OidcProviderNative(
            self,
            "GitHubOidc",
            url="https://token.actions.githubusercontent.com",
            client_ids=["sts.amazonaws.com"],
        )
        ci_role = self._github_role(
            provider,
            "GitHubCiRole",
            role_name="sqlsense-github-ci",
            description="GitHub Actions CI (branches and pull requests): invoke Bedrock models",
            subjects=[f"repo:{github_repo}:ref:refs/heads/*", f"repo:{github_repo}:pull_request"],
        )
        ci_role.add_to_policy(self._bedrock_invoke_statement())
        # Read-only access for `cdk diff` on pull requests (no change sets, no deploy role).
        ci_role.add_to_policy(
            iam.PolicyStatement(
                actions=["cloudformation:DescribeStacks", "cloudformation:GetTemplate"],
                resources=[
                    f"arn:aws:cloudformation:{self.region}:{self.account}:stack/SqlSense*/*"
                ],
            )
        )
        ci_role.add_to_policy(
            iam.PolicyStatement(
                actions=["ssm:GetParameter"],
                resources=[
                    f"arn:aws:ssm:{self.region}:{self.account}:parameter/cdk-bootstrap/hnb659fds/version"
                ],
            )
        )

        deploy_role = self._github_role(
            provider,
            "GitHubDeployRole",
            role_name="sqlsense-github-deploy",
            description="GitHub Actions CD (production environment only): run cdk deploy",
            subjects=[f"repo:{github_repo}:environment:production"],
        )
        # Deploy through the CDK bootstrap roles rather than granting resource permissions here.
        deploy_role.add_to_policy(
            iam.PolicyStatement(
                actions=["sts:AssumeRole"],
                resources=[
                    f"arn:aws:iam::{self.account}:role/cdk-hnb659fds-*-{self.account}-{self.region}"
                ],
            )
        )
        CfnOutput(self, "GitHubCiRoleArn", value=ci_role.role_arn)
        CfnOutput(self, "GitHubDeployRoleArn", value=deploy_role.role_arn)

    def _github_role(
        self,
        provider: iam.IOidcProvider,
        construct_id: str,
        *,
        role_name: str,
        description: str,
        subjects: list[str],
    ) -> iam.Role:
        return iam.Role(
            self,
            construct_id,
            role_name=role_name,
            description=description,
            max_session_duration=Duration.hours(1),
            assumed_by=iam.WebIdentityPrincipal(
                provider.oidc_provider_arn,
                conditions={
                    "StringEquals": {
                        "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
                    },
                    "StringLike": {"token.actions.githubusercontent.com:sub": subjects},
                },
            ),
        )

    def _bedrock_invoke_statement(self) -> iam.PolicyStatement:
        return iam.PolicyStatement(
            actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
            resources=[f"arn:aws:bedrock:*::foundation-model/{m}" for m in BEDROCK_MODELS]
            + [
                f"arn:aws:bedrock:{self.region}:{self.account}:inference-profile/{p}"
                for p in INFERENCE_PROFILES
            ],
        )

    def _budget(self, limit_usd: int, email: str) -> None:
        subscribers = [
            budgets.CfnBudget.SubscriberProperty(subscription_type="EMAIL", address=email)
        ]
        budgets.CfnBudget(
            self,
            "MonthlyBudget",
            budget=budgets.CfnBudget.BudgetDataProperty(
                budget_name="sqlsense-monthly",
                budget_type="COST",
                time_unit="MONTHLY",
                budget_limit=budgets.CfnBudget.SpendProperty(amount=limit_usd, unit="USD"),
            ),
            notifications_with_subscribers=[
                budgets.CfnBudget.NotificationWithSubscribersProperty(
                    notification=budgets.CfnBudget.NotificationProperty(
                        notification_type=notification_type,
                        comparison_operator="GREATER_THAN",
                        threshold=threshold,
                        threshold_type="PERCENTAGE",
                    ),
                    subscribers=subscribers,
                )
                for notification_type, threshold in [
                    ("ACTUAL", 50),
                    ("ACTUAL", 100),
                    ("FORECASTED", 100),
                ]
            ],
        )
