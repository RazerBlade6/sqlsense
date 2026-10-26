import aws_cdk as cdk

from stacks.application import ApplicationStack
from stacks.data import DataStack
from stacks.foundation import FoundationStack
from stacks.image import REPO
from stacks.retrieval import RetrievalStack

app = cdk.App()
env = cdk.Environment(account=app.node.try_get_context("account"), region="ap-southeast-2")

FoundationStack(
    app,
    "SqlSenseFoundation",
    env=env,
    github_repo=app.node.try_get_context("github_repo"),
    monthly_budget_usd=int(app.node.try_get_context("monthly_budget_usd")),
)
data = DataStack(app, "SqlSenseData", env=env)
retrieval = RetrievalStack(app, "SqlSenseRetrieval", env=env)
application = ApplicationStack(
    app,
    "SqlSenseApp",
    env=env,
    retrieval=retrieval,
    site_dir=REPO / "frontend" / "out",
)
# The API role attaches the warehouse read policy by name.
application.add_stack_dependency(data)

cdk.Tags.of(app).add("project", "sqlsense")
app.synth()
