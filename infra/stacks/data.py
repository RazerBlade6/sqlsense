from pathlib import Path

import yaml
from aws_cdk import CfnOutput, RemovalPolicy, Size, Stack
from aws_cdk import aws_athena as athena
from aws_cdk import aws_glue as glue
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_deployment as s3deploy
from constructs import Construct

REPO = Path(__file__).resolve().parents[2]
CATALOG = REPO / "catalog" / "retail.yaml"
WAREHOUSE = REPO / "data" / "warehouse"

PARQUET_STORAGE = {
    "input_format": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat",
    "output_format": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat",
    "serde_info": glue.CfnTable.SerdeInfoProperty(
        serialization_library="org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    ),
}

# Athena refuses any query that would scan more than this. The whole warehouse is ~40 MB.
SCAN_LIMIT_BYTES = 100 * 1024 * 1024
WEEK_RANGE = "1,53"
CI_ROLE_NAME = "sqlsense-github-ci"


class DataStack(Stack):
    """S3 data lake, Glue catalog and Athena workgroup for the retail warehouse."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        catalog = yaml.safe_load(CATALOG.read_text())
        database_name = catalog["database"]

        # The data is rebuilt from source by data/build.py, so the bucket is disposable.
        self.bucket = s3.Bucket(
            self,
            "Warehouse",
            bucket_name=f"sqlsense-warehouse-{self.account}-{self.region}",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )
        s3deploy.BucketDeployment(
            self,
            "PublishWarehouse",
            sources=[s3deploy.Source.asset(str(WAREHOUSE / database_name))],
            destination_bucket=self.bucket,
            destination_key_prefix=f"{database_name}/",
            memory_limit=1024,
            ephemeral_storage_size=Size.mebibytes(1024),
        )

        database = glue.CfnDatabase(
            self,
            "Database",
            catalog_id=self.account,
            database_input=glue.CfnDatabase.DatabaseInputProperty(
                name=database_name,
                description="Retail warehouse (The Complete Journey). Defined in catalog/retail.yaml.",
            ),
        )
        for position, table in enumerate(catalog["tables"]):
            self._glue_table(database_name, table, position).node.add_dependency(database)

        self.workgroup = athena.CfnWorkGroup(
            self,
            "WorkGroup",
            name="sqlsense",
            description="Queries from the SQLSense agents; per-query scan limit enforced",
            recursive_delete_option=True,
            state="ENABLED",
            work_group_configuration=athena.CfnWorkGroup.WorkGroupConfigurationProperty(
                enforce_work_group_configuration=True,
                bytes_scanned_cutoff_per_query=SCAN_LIMIT_BYTES,
                publish_cloud_watch_metrics_enabled=True,
                engine_version=athena.CfnWorkGroup.EngineVersionProperty(
                    selected_engine_version="Athena engine version 3"
                ),
                managed_query_results_configuration=athena.CfnWorkGroup.ManagedQueryResultsConfigurationProperty(
                    enabled=True
                ),
            ),
        )

        self.read_policy = self._warehouse_read_policy(database_name)

        CfnOutput(self, "WarehouseBucket", value=self.bucket.bucket_name)
        CfnOutput(self, "AthenaWorkGroup", value=self.workgroup.name)
        CfnOutput(self, "GlueDatabase", value=database_name)
        CfnOutput(self, "WarehouseReadPolicyArn", value=self.read_policy.managed_policy_arn)

    def _glue_table(self, database_name: str, table: dict, position: int) -> glue.CfnTable:
        name = table["name"]
        location = f"s3://{self.bucket.bucket_name}/{database_name}/{name}/"
        partition_key = table.get("partition_by")
        columns = [
            glue.CfnTable.ColumnProperty(name=c["name"], type=c["type"], comment=c["comment"])
            for c in table["columns"]
            if c["name"] != partition_key
        ]
        partition_keys = [
            glue.CfnTable.ColumnProperty(name=c["name"], type=c["type"], comment=c["comment"])
            for c in table["columns"]
            if c["name"] == partition_key
        ]
        # catalog_position keeps the agent's schema text in catalog order (Glue lists tables
        # alphabetically), so the prompt is identical locally and on AWS.
        parameters = {
            "classification": "parquet",
            "grain": table["grain"],
            "catalog_position": str(position),
        }
        if partition_key:
            # Partition projection: Athena computes partitions from the range, so there is no
            # crawler or MSCK REPAIR step after new weeks land.
            parameters |= {
                "projection.enabled": "true",
                f"projection.{partition_key}.type": "integer",
                f"projection.{partition_key}.range": WEEK_RANGE,
                "storage.location.template": f"{location}{partition_key}=${{{partition_key}}}/",
            }
        return glue.CfnTable(
            self,
            f"Table{''.join(part.title() for part in name.split('_'))}",
            catalog_id=self.account,
            database_name=database_name,
            table_input=glue.CfnTable.TableInputProperty(
                name=name,
                description=table["description"],
                table_type="EXTERNAL_TABLE",
                parameters=parameters,
                partition_keys=partition_keys,
                storage_descriptor=glue.CfnTable.StorageDescriptorProperty(
                    columns=columns, location=location, **PARQUET_STORAGE
                ),
            ),
        )

    def _warehouse_read_policy(self, database_name: str) -> iam.ManagedPolicy:
        """Least-privilege, read-only access to the warehouse, for the API and agents."""
        workgroup_arn = (
            f"arn:aws:athena:{self.region}:{self.account}:workgroup/{self.workgroup.name}"
        )
        glue_arns = [
            f"arn:aws:glue:{self.region}:{self.account}:catalog",
            f"arn:aws:glue:{self.region}:{self.account}:database/{database_name}",
            f"arn:aws:glue:{self.region}:{self.account}:table/{database_name}/*",
        ]
        return iam.ManagedPolicy(
            self,
            "WarehouseReadPolicy",
            managed_policy_name="sqlsense-warehouse-read",
            description="Run read-only Athena queries in the sqlsense workgroup over the retail warehouse",
            # CI runs post-deploy smoke tests and Athena evals with this; the role is in Foundation.
            roles=[iam.Role.from_role_name(self, "GitHubCiRole", CI_ROLE_NAME)],
            statements=[
                iam.PolicyStatement(
                    actions=[
                        "athena:StartQueryExecution",
                        "athena:GetQueryExecution",
                        "athena:GetQueryResults",
                        "athena:StopQueryExecution",
                        "athena:GetWorkGroup",
                    ],
                    resources=[workgroup_arn],
                ),
                iam.PolicyStatement(
                    actions=[
                        "glue:GetDatabase",
                        "glue:GetTable",
                        "glue:GetTables",
                        "glue:GetPartitions",
                    ],
                    resources=glue_arns,
                ),
                iam.PolicyStatement(
                    actions=["s3:GetObject"],
                    resources=[self.bucket.arn_for_objects(f"{database_name}/*")],
                ),
                iam.PolicyStatement(
                    actions=["s3:ListBucket", "s3:GetBucketLocation"],
                    resources=[self.bucket.bucket_arn],
                    conditions={
                        "StringLike": {"s3:prefix": [f"{database_name}/*", f"{database_name}/"]}
                    },
                ),
            ],
        )
