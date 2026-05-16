# AI Paper Radar — プロジェクト固有の Claude 指示

> このファイルはグローバル `~/.claude/CLAUDE.md` を補完するプロジェクト固有設定。

---

## プロジェクト概要

生成AI/LLM分野の注目論文を、毎朝SlackへJST 6:00に自動配信する個人用システム。詳細は `docs/plan.md` 参照。

## 技術スタック

- **言語**: Python 3.12
- **IaC**: AWS CDK (Python)
- **クラウド**: AWS（リージョン: ap-northeast-1）
- **主要サービス**:
  - AWS Lambda（Python 3.12ランタイム）
  - Amazon DynamoDB（オンデマンドモード）
  - Amazon EventBridge Scheduler
  - AWS Systems Manager (SSM) Parameter Store standard（SecureString）
  - Amazon CloudWatch Logs / Billing Alarm
- **外部API**:
  - Amazon Bedrock 経由 Amazon Nova Pro（IAM 認証、`apac.amazon.nova-pro-v1:0` APAC Cross-Region Inference Profile、Converse API 経由）
  - Hugging Face Daily Papers API
  - arXiv API
  - Slack Incoming Webhook

## ディレクトリ構成（予定）

```
ai-paper-radar/
├── CLAUDE.md              # このファイル
├── README.md              # プロジェクト紹介（Phase 1完了後に作成）
├── docs/
│   ├── plan.md            # プロジェクト計画
│   ├── spec.md            # 仕様書
│   ├── todo.md            # タスク管理
│   └── knowledge.md       # 知見・決定事項
├── cdk/                   # CDK スタック
│   ├── app.py
│   ├── stacks/
│   └── cdk.json
├── lambdas/               # Lambda 関数本体
│   └── pipeline/          # 単一関数構成
│       ├── lambda_function.py
│       ├── core/
│       │   ├── collector.py
│       │   ├── scorer.py
│       │   └── notifier.py
│       └── requirements.txt
├── tests/                 # pytest
├── pyproject.toml
├── .env.example
└── .gitignore
```

## シークレット管理

実体は `~/.secrets/ai-paper-radar.env` に保存し、リポジトリには `.env.example` のみコミットする。

管理対象:
- `SLACK_WEBHOOK_URL`
- `INTEREST_PROMPT`（興味記述、Phase 1で固定値、Phase 2で更新可能化）

本番では SSM Parameter Store から取得（パス `/ai-paper-radar/runtime/*`）。ローカル開発時のみ `~/.secrets/ai-paper-radar.env` から読み込む。

Amazon Nova Pro は Amazon Bedrock 経由で呼ぶため API キー管理は不要（Lambda 実行ロールの `bedrock:InvokeModel` 権限で認証）。

## 開発ルール（プロジェクト固有）

### コード品質
- 型ヒント必須（`mypy --strict` 通過を目標）
- フォーマッタ: `ruff format`
- リンタ: `ruff check`
- テスト: `pytest` + `moto`（AWS モック）

### Lambda 関数の構造
- ハンドラは薄く、ロジックは `core/` 配下に分離
- 外部API呼び出しは必ずリトライ可能な形にする（tenacity推奨）
- 単体テストでLambda外部依存をモック化

### CDK
- スタック構成: `AiPaperRadarStack` 1スタック（リソース小規模のため分割しない）
- スナップショットテスト必須
- `cdk diff` でレビューしてから `cdk deploy`

### Git運用（グローバル設定上書きなし）
- ブランチ運用: `feature/<機能名>` 単位でPR
- コミット規約: Conventional Commits（日本語）
- コミット → プッシュは1セット

### CDKデプロイの確認ルール
- `cdk deploy` 実行前にてつてつへ承認を求める（破壊的影響の可能性あり）
- スタック削除（`cdk destroy`）は必ず確認

## 注意事項

- AWS識別情報（アカウントID、IAMユーザー名等）は `docs/` に書かない（`~/.secrets/` 管理）
- パブリックリポジトリで作成するため、論文の興味プロンプト・Slack Webhook URLは絶対にコミットしない
- 配信内容自体（論文タイトル等）は公開情報なのでログに残してOK

## 関連リンク（一次ソース）

- HF Daily Papers: https://huggingface.co/papers
- HF Daily Papers Blog: https://huggingface.co/blog/daily-papers
- arXiv API: https://info.arxiv.org/help/api/index.html
- Amazon Bedrock Converse API: https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html
- Amazon Nova ユーザーガイド: https://docs.aws.amazon.com/nova/latest/userguide/
- AWS CDK Python: https://docs.aws.amazon.com/cdk/api/v2/python/
