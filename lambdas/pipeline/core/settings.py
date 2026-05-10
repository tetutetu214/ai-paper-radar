"""Lambda 環境変数と SSM Parameter Store からの設定読み込み。

詳細仕様は docs/spec.md §4.2, §4.3 を参照。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Final

import boto3


SSM_PARAMETER_PATH_PREFIX_DEFAULT: Final[str] = "/ai-paper-radar/runtime/"


@dataclass(frozen=True)
class RuntimeSettings:
    """Lambda 起動時に必要な設定値。"""

    dynamodb_table_name: str
    ssm_parameter_path_prefix: str
    log_level: str
    max_papers_per_day: int
    top_n_delivery: int
    aws_region: str
    slack_webhook_url: str
    interest_prompt: str


@lru_cache(maxsize=1)
def get_settings() -> RuntimeSettings:
    """Lambda Cold Start 時に SSM から取得し、Warm Start ではキャッシュを返す。"""
    table_name = os.environ["DYNAMODB_TABLE_NAME"]
    ssm_prefix = os.environ.get(
        "SSM_PARAMETER_PATH_PREFIX",
        SSM_PARAMETER_PATH_PREFIX_DEFAULT,
    )
    log_level = os.environ.get("LOG_LEVEL", "INFO")
    max_papers = int(os.environ.get("MAX_PAPERS_PER_DAY", "50"))
    top_n = int(os.environ.get("TOP_N_DELIVERY", "3"))
    # AWS_REGION は Lambda 実行環境で自動セットされる
    aws_region = os.environ.get("AWS_REGION", "ap-northeast-1")

    params = _load_ssm_parameters(ssm_prefix)

    return RuntimeSettings(
        dynamodb_table_name=table_name,
        ssm_parameter_path_prefix=ssm_prefix,
        log_level=log_level,
        max_papers_per_day=max_papers,
        top_n_delivery=top_n,
        aws_region=aws_region,
        slack_webhook_url=params["SLACK_WEBHOOK_URL"],
        interest_prompt=params["INTEREST_PROMPT"],
    )


def _load_ssm_parameters(path_prefix: str) -> dict[str, str]:
    """SSM Parameter Store から SecureString を一括取得。"""
    ssm = boto3.client("ssm")
    paginator = ssm.get_paginator("get_parameters_by_path")

    result: dict[str, str] = {}
    for page in paginator.paginate(
        Path=path_prefix,
        WithDecryption=True,
        Recursive=False,
    ):
        for param in page.get("Parameters", []):
            # /ai-paper-radar/runtime/SLACK_WEBHOOK_URL -> SLACK_WEBHOOK_URL
            key = param["Name"].rsplit("/", 1)[-1]
            result[key] = param["Value"]

    return result
