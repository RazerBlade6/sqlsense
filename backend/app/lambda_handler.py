"""AWS Lambda entry point: the FastAPI app behind a Lambda Function URL."""

import logging

from mangum import Mangum

from app.api import app

logging.getLogger().setLevel(logging.INFO)

handler = Mangum(app, lifespan="off")
