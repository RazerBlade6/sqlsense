import hashlib

from aws_cdk import CfnOutput, CustomResource, Duration, RemovalPolicy, Stack
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from aws_cdk import aws_rds as rds
from aws_cdk import custom_resources as cr
from constructs import Construct

from stacks.image import REPO, backend_image

DATABASE_NAME = "sqlsense"
CLUSTER_IDENTIFIER = "sqlsense-corpus"
READER_SECRET_NAME = "sqlsense/db-reader"
EMBEDDING_MODEL = "amazon.titan-embed-text-v2:0"


def corpus_fingerprint() -> str:
    """Changes whenever the documents or the chunking code change, which re-runs ingest."""
    digest = hashlib.sha256()
    files = sorted((REPO / "corpus").rglob("*.md")) + sorted(
        (REPO / "backend" / "app" / "retrieval").glob("*.py")
    )
    for path in files:
        digest.update(path.relative_to(REPO).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


class RetrievalStack(Stack):
    """pgvector on Aurora Serverless v2 (scales to 0 ACU), reached through the RDS Data API.

    Deploying re-indexes the corpus: a custom resource runs the ingest Lambda whenever the
    documents change.
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Isolated subnets only: no NAT gateway or internet route. Clients use the Data API.
        vpc = ec2.Vpc(
            self,
            "Vpc",
            max_azs=2,
            nat_gateways=0,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="db", subnet_type=ec2.SubnetType.PRIVATE_ISOLATED, cidr_mask=24
                )
            ],
        )

        # The index is rebuilt from corpus/ on every deploy, so the cluster is disposable.
        self.cluster = rds.DatabaseCluster(
            self,
            "Corpus",
            cluster_identifier=CLUSTER_IDENTIFIER,
            engine=rds.DatabaseClusterEngine.aurora_postgres(
                version=rds.AuroraPostgresEngineVersion.VER_17_6
            ),
            writer=rds.ClusterInstance.serverless_v2("writer"),
            serverless_v2_min_capacity=0,
            serverless_v2_max_capacity=2,
            serverless_v2_auto_pause_duration=Duration.minutes(10),
            enable_data_api=True,
            default_database_name=DATABASE_NAME,
            credentials=rds.Credentials.from_generated_secret(
                "postgres", secret_name="sqlsense/db-admin"
            ),
            storage_encrypted=True,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
            backup=rds.BackupProps(retention=Duration.days(1)),
            removal_policy=RemovalPolicy.DESTROY,
        )

        # The API connects as this role, which can only SELECT from the chunks table.
        self.reader_secret = rds.DatabaseSecret(
            self, "ReaderSecret", username="sqlsense_reader", secret_name=READER_SECRET_NAME
        )

        ingest = lambda_.DockerImageFunction(
            self,
            "Ingest",
            description="Embed the corpus with Titan and sync it into pgvector",
            code=backend_image("app.retrieval.ingest.handler"),
            memory_size=1024,
            timeout=Duration.minutes(5),
            log_group=logs.LogGroup(
                self,
                "IngestLogs",
                retention=logs.RetentionDays.ONE_MONTH,
                removal_policy=RemovalPolicy.DESTROY,
            ),
            environment={
                "DB_CLUSTER_ARN": self.cluster.cluster_arn,
                "DB_ADMIN_SECRET_ARN": self.cluster.secret.secret_arn,
                "DB_READER_SECRET_ARN": self.reader_secret.secret_arn,
                "DB_NAME": DATABASE_NAME,
                "EMBEDDING_MODEL_ID": EMBEDDING_MODEL,
            },
        )
        self.cluster.grant_data_api_access(ingest)
        self.reader_secret.grant_read(ingest)
        ingest.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel"],
                resources=[f"arn:aws:bedrock:{self.region}::foundation-model/{EMBEDDING_MODEL}"],
            )
        )

        provider = cr.Provider(
            self,
            "IngestProvider",
            on_event_handler=ingest,
            log_group=logs.LogGroup(
                self,
                "IngestProviderLogs",
                retention=logs.RetentionDays.ONE_MONTH,
                removal_policy=RemovalPolicy.DESTROY,
            ),
        )
        index = CustomResource(
            self,
            "CorpusIndex",
            service_token=provider.service_token,
            properties={"CorpusFingerprint": corpus_fingerprint()},
        )
        index.node.add_dependency(self.cluster)

        CfnOutput(self, "ClusterArn", value=self.cluster.cluster_arn)
        CfnOutput(self, "ReaderSecretArn", value=self.reader_secret.secret_arn)
        CfnOutput(self, "IndexedChunks", value=index.get_att_string("chunks"))
