#!/usr/bin/env python3
"""CDK エントリポイント。"""
from __future__ import annotations

import os

import aws_cdk as cdk

from infra.ai_paper_radar_stack import AiPaperRadarStack

app = cdk.App()

env = cdk.Environment(
    account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
    region=os.environ.get("CDK_DEFAULT_REGION", "us-east-1"),
)

AiPaperRadarStack(
    app,
    "AiPaperRadarStack",
    env=env,
    description="AI Paper Radar - 毎朝 JST 6:00 に AI 論文を Slack 配信",
)

app.synth()
