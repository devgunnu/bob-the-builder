"""Load the operator's provider credentials before Settings is constructed."""

import json
import os

import boto3


def load_secret_into_env(arn: str) -> None:
    result = boto3.client("secretsmanager").get_secret_value(SecretId=arn)
    if "SecretString" not in result:
        raise ValueError("Bob's secret must be a JSON string")
    values = json.loads(result["SecretString"])
    if not isinstance(values, dict) or any(
        not isinstance(k, str) or not isinstance(v, str) for k, v in values.items()
    ):
        raise ValueError("Bob's secret must be a JSON object of string values")
    for key, value in values.items():
        os.environ[key] = value
