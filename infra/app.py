import aws_cdk as cdk

from stacks.foundation import FoundationStack

app = cdk.App()
env = cdk.Environment(account=app.node.try_get_context("account"), region="ap-southeast-2")

FoundationStack(
    app,
    "SqlSenseFoundation",
    env=env,
    github_repo=app.node.try_get_context("github_repo"),
    monthly_budget_usd=int(app.node.try_get_context("monthly_budget_usd")),
)

cdk.Tags.of(app).add("project", "sqlsense")
app.synth()
