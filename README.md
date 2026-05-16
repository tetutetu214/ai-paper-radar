# AI Paper Radar

生成AI/LLM分野の注目論文を、毎朝 JST 6:00 に Slack へ自動配信する個人用システム。

## ドキュメント

- [プロジェクト計画](docs/plan.md)
- [仕様書](docs/spec.md)
- [タスク管理](docs/todo.md)
- [知見・決定事項](docs/knowledge.md)
- [プロジェクト固有 Claude 指示](CLAUDE.md)

## 技術スタック

- Python 3.12 + uv
- AWS CDK (Python)
- AWS Lambda / DynamoDB / EventBridge Scheduler / SSM Parameter Store
- Amazon Bedrock 経由 Amazon Nova Pro（`apac.amazon.nova-pro-v1:0`、APAC Cross-Region Inference Profile）
- Hugging Face Daily Papers + arXiv + HF Trending Papers

## セットアップ

```bash
# Python 依存
uv sync

# CDK CLI（プロジェクトローカル）
npm install

# シークレット（~/.secrets/ai-paper-radar.env を作成）
cp .env.example ~/.secrets/ai-paper-radar.env
# エディタで値を埋める

# CDK 動作確認
npx cdk synth
```

詳細は `docs/todo.md` を参照。
