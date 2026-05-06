"""settings モジュールのテスト。"""
from __future__ import annotations

import boto3
import pytest
from moto import mock_aws


@pytest.fixture
def aws_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """moto 用の擬似 AWS 認証情報と Lambda 環境変数を設定。"""
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-northeast-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("DYNAMODB_TABLE_NAME", "test-papers")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("MAX_PAPERS_PER_DAY", "30")
    monkeypatch.setenv("TOP_N_DELIVERY", "5")


@mock_aws
def test_get_settings_loads_from_ssm(aws_env: None) -> None:
    """SSM Parameter Store から SecureString を取得して RuntimeSettings に詰める。"""
    ssm = boto3.client("ssm", region_name="ap-northeast-1")
    for key, value in [
        ("ANTHROPIC_API_KEY", "sk-ant-test"),
        ("SLACK_WEBHOOK_URL", "https://hooks.slack.com/test"),
        ("INTEREST_PROMPT", "テスト用興味プロンプト"),
    ]:
        ssm.put_parameter(
            Name=f"/ai-paper-radar/runtime/{key}",
            Value=value,
            Type="SecureString",
        )

    from core import settings as settings_module

    # lru_cache を初期化
    settings_module.get_settings.cache_clear()

    s = settings_module.get_settings()
    assert s.dynamodb_table_name == "test-papers"
    assert s.log_level == "DEBUG"
    assert s.max_papers_per_day == 30
    assert s.top_n_delivery == 5
    assert s.anthropic_api_key == "sk-ant-test"
    assert s.slack_webhook_url == "https://hooks.slack.com/test"
    assert s.interest_prompt == "テスト用興味プロンプト"


@mock_aws
def test_get_settings_uses_default_prefix(aws_env: None) -> None:
    """SSM_PARAMETER_PATH_PREFIX 未設定時はデフォルト値が使われる。"""
    ssm = boto3.client("ssm", region_name="ap-northeast-1")
    for key, value in [
        ("ANTHROPIC_API_KEY", "k"),
        ("SLACK_WEBHOOK_URL", "u"),
        ("INTEREST_PROMPT", "p"),
    ]:
        ssm.put_parameter(
            Name=f"/ai-paper-radar/runtime/{key}",
            Value=value,
            Type="SecureString",
        )

    from core import settings as settings_module

    settings_module.get_settings.cache_clear()
    s = settings_module.get_settings()
    assert s.ssm_parameter_path_prefix == "/ai-paper-radar/runtime/"
