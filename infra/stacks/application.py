from pathlib import Path

from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_deployment as s3deploy
from constructs import Construct

from stacks.foundation import bedrock_invoke_statement
from stacks.image import backend_image
from stacks.retrieval import DATABASE_NAME, RetrievalStack

SESSIONS_TABLE = "sqlsense-sessions"
WAREHOUSE_READ_POLICY = "sqlsense-warehouse-read"
# The public endpoint calls Bedrock, so cap both the daily questions and the concurrency.
DAILY_QUESTION_LIMIT = 300
API_CONCURRENCY = 10


class ApplicationStack(Stack):
    """The API (FastAPI on Lambda behind a Function URL), its session memory, and the
    static frontend on S3 + CloudFront."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        retrieval: RetrievalStack,
        site_dir: Path,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        sessions = dynamodb.TableV2(
            self,
            "Sessions",
            table_name=SESSIONS_TABLE,
            partition_key=dynamodb.Attribute(name="session_id", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="sk", type=dynamodb.AttributeType.STRING),
            billing=dynamodb.Billing.on_demand(),
            time_to_live_attribute="expires_at",
            removal_policy=RemovalPolicy.DESTROY,
        )

        site_bucket = s3.Bucket(
            self,
            "SiteBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )
        distribution = cloudfront.Distribution(
            self,
            "Site",
            comment="SQLSense frontend",
            default_root_object="index.html",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(site_bucket),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                response_headers_policy=cloudfront.ResponseHeadersPolicy.SECURITY_HEADERS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
            ),
            error_responses=[
                cloudfront.ErrorResponse(
                    http_status=403, response_http_status=404, response_page_path="/404.html"
                )
            ],
        )
        site_origin = f"https://{distribution.distribution_domain_name}"

        api = lambda_.DockerImageFunction(
            self,
            "Api",
            description="SQLSense API: planner, retrieval, SQL agent and synthesizer",
            code=backend_image("app.lambda_handler.handler"),
            memory_size=2048,
            timeout=Duration.minutes(2),
            reserved_concurrent_executions=API_CONCURRENCY,
            log_group=logs.LogGroup(
                self,
                "ApiLogs",
                retention=logs.RetentionDays.ONE_MONTH,
                removal_policy=RemovalPolicy.DESTROY,
            ),
            environment={
                "WAREHOUSE": "athena",
                "RETRIEVAL_STORE": "pgvector",
                "DB_CLUSTER_ARN": retrieval.cluster.cluster_arn,
                "DB_SECRET_ARN": retrieval.reader_secret.secret_arn,
                "DB_NAME": DATABASE_NAME,
                "MEMORY_STORE": "dynamodb",
                "SESSIONS_TABLE": sessions.table_name,
                "DAILY_QUESTION_LIMIT": str(DAILY_QUESTION_LIMIT),
                "CORS_ORIGINS": site_origin,
            },
        )
        # Least privilege: read the warehouse, invoke the listed models, run statements as the
        # read-only database role, and touch only its own table items.
        api.role.add_managed_policy(
            iam.ManagedPolicy.from_managed_policy_name(self, "WarehouseRead", WAREHOUSE_READ_POLICY)
        )
        api.add_to_role_policy(bedrock_invoke_statement(self))
        api.add_to_role_policy(
            iam.PolicyStatement(
                actions=["rds-data:ExecuteStatement"], resources=[retrieval.cluster.cluster_arn]
            )
        )
        retrieval.reader_secret.grant_read(api)
        sessions.grant(api, "dynamodb:Query", "dynamodb:PutItem", "dynamodb:UpdateItem")

        api_url = api.add_function_url(auth_type=lambda_.FunctionUrlAuthType.NONE)

        # The API URL is only known at deploy time, so the site reads it from config.json.
        s3deploy.BucketDeployment(
            self,
            "PublishSite",
            sources=[
                s3deploy.Source.asset(str(site_dir)),
                s3deploy.Source.json_data("config.json", {"apiUrl": api_url.url}),
            ],
            destination_bucket=site_bucket,
            distribution=distribution,
            distribution_paths=["/*"],
        )

        CfnOutput(self, "SiteUrl", value=site_origin)
        CfnOutput(self, "ApiUrl", value=api_url.url)
