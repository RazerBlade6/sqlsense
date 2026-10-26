from pathlib import Path

from aws_cdk import aws_ecr_assets as ecr_assets
from aws_cdk import aws_lambda as lambda_

REPO = Path(__file__).resolve().parents[2]


def backend_image(handler: str) -> lambda_.DockerImageCode:
    """The backend Lambda image (backend/Dockerfile) with the given handler.

    Every function uses the same build, so CDK publishes the image once.
    """
    return lambda_.DockerImageCode.from_image_asset(
        str(REPO),
        file="backend/Dockerfile",
        platform=ecr_assets.Platform.LINUX_AMD64,
        cmd=[handler],
    )
