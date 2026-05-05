# AI Paper Radar — 仕様書

> 作成日: 2026-05-05
> 状態: 詳細版（てつてつの確認待ち）

---

## 1. 概要

`plan.md` で確定したアーキテクチャの実装仕様を定義する。Lambda 1関数構成、Claude Haiku 4.5、DynamoDB 1テーブル、CDK Python による IaC が前提。

---

## 2. データソース仕様

### 2.1 HF Daily Papers API

- **エンドポイント**: `https://huggingface.co/api/daily_papers?date=YYYY-MM-DD`
- **認証**: 不要（公開API）
- **レート制限**: 公式記載なし、十分緩い
- **取得対象**: 配信日前日のキュレーション結果（通常10-30本）
- **重要フィールド**:
  - `paper.id` (arXiv ID)
  - `paper.title`
  - `paper.authors[].name`
  - `paper.summary` (abstract)
  - `paper.upvotes`
  - `paper.publishedAt` (ISO8601)
  - `submittedBy.name`

### 2.2 arXiv API

- **エンドポイント**: `http://export.arxiv.org/api/query`
- **クエリパラメータ**:
  ```
  search_query=cat:cs.CL+OR+cat:cs.AI+OR+cat:cs.LG
  sortBy=submittedDate
  sortOrder=descending
  max_results=200
  ```
- **認証**: 不要
- **レート制限**: 3秒に1リクエスト推奨（公式）
- **レスポンス**: Atom XML形式、`feedparser` で解析
- **フィルタ**: `published` が UTC now - 24h より新しいもののみ採用

### 2.3 HF Trending Papers

- **エンドポイント**: `https://huggingface.co/api/papers?sort=trending`
- **取得対象**: トレンド上位50本

### 2.4 重複排除

各ソースから取得した論文は arXiv ID で正規化して重複排除する。
- バージョン番号除去: `2401.13782v2` → `2401.13782`
- HF / arXiv の両方に存在する論文は1件にマージし、`source` 属性に両方を記録

---

## 3. DynamoDB スキーマ

### 3.1 テーブル仕様

- **テーブル名**: `ai-paper-radar-papers`
- **キャパシティモード**: オンデマンド（PAY_PER_REQUEST）
- **暗号化**: AWS owned key（無料）
- **ポイントインタイムリカバリ**: 無効（個人用、削除可）

### 3.2 キー構造

| 種別 | 属性名 | 型 | 内容 |
|------|--------|-----|------|
| Partition Key | `paper_id` | S | arXiv ID（バージョン番号なし） |

### 3.3 Global Secondary Index

| 名前 | PK | SK | 用途 |
|------|----|----|----|
| `gsi_collected_date_score` | `collected_date` (S, YYYY-MM-DD) | `score_padded` (S) | 配信日ごとのスコア降順取得 |

`score_padded` はスコアを3桁ゼロパディングした文字列（例: 087）。DynamoDBは数値SKでも降順取得できるが、文字列で固定桁にする方が後の取り回しが安定するため採用。

### 3.4 項目スキーマ

| 属性 | 型 | 必須 | 説明 |
|------|-----|------|------|
| `paper_id` | S | ○ | PK、arXiv ID |
| `title` | S | ○ | 論文タイトル（英語） |
| `authors` | L (S) | ○ | 著者リスト |
| `abstract` | S | ○ | アブストラクト（英語） |
| `published_at` | S | ○ | arXiv公開日時（ISO8601） |
| `collected_at` | S | ○ | 収集日時（ISO8601） |
| `collected_date` | S | ○ | GSI PK、収集日（YYYY-MM-DD） |
| `source` | SS | ○ | `hf_daily` / `arxiv` / `hf_trending` の集合 |
| `upvotes` | N | △ | HF upvote数（HFソース時のみ） |
| `score` | N | △ | スコア（0-100） |
| `score_padded` | S | △ | GSI SK、`{score:03d}` |
| `score_reason` | S | △ | スコア採用理由（Claude生成） |
| `summary_ja` | S | △ | 日本語3行要約（配信対象のみ生成） |
| `delivered_at` | S | △ | Slack配信日時（ISO8601） |
| `ttl` | N | ○ | UNIXタイムスタンプ、collected_at + 90日 |

---

## 4. Lambda 関数仕様

### 4.1 関数定義

- **関数名**: `ai-paper-radar-pipeline`
- **ランタイム**: Python 3.12
- **メモリ**: 1024 MB
- **タイムアウト**: 300秒（5分）
- **アーキテクチャ**: arm64（コスト削減）
- **ハンドラ**: `lambda_function.handler`

### 4.2 環境変数

| 変数名 | 内容 |
|--------|------|
| `SECRETS_NAME` | Secrets Manager のシークレット名 |
| `DYNAMODB_TABLE_NAME` | テーブル名 |
| `LOG_LEVEL` | `INFO` または `DEBUG` |
| `MAX_PAPERS_PER_DAY` | 1日あたりの収集上限（デフォルト 50） |
| `TOP_N_DELIVERY` | 配信本数（デフォルト 3） |

### 4.3 Secrets Manager 構造

シークレット名: `ai-paper-radar/runtime`

```json
{
  "ANTHROPIC_API_KEY": "sk-ant-...",
  "SLACK_WEBHOOK_URL": "https://hooks.slack.com/services/...",
  "INTEREST_PROMPT": "私はクラウドアーキテクト兼開発者です。..."
}
```

### 4.4 入出力

- **入力**: EventBridge Scheduler のイベント（中身は使わない）
- **戻り値**:
  ```json
  {
    "collected": 47,
    "scored": 47,
    "delivered": 3,
    "errors": []
  }
  ```

### 4.5 処理フロー（疑似コード）

```python
def handler(event, context):
    secrets = load_secrets(SECRETS_NAME)
    table = dynamodb.Table(DYNAMODB_TABLE_NAME)

    # Step 1: 収集
    papers = collector.fetch_all()  # HF Daily + arXiv + HF Trending
    papers = collector.deduplicate(papers)
    collector.upsert_dynamodb(table, papers)

    # Step 2: スコアリング（バッチ10本ずつ）
    unscored = scorer.fetch_unscored(table, today)
    for batch in chunks(unscored, 10):
        scores = scorer.score_with_claude(batch, secrets["INTEREST_PROMPT"])
        scorer.update_scores(table, scores)

    # Step 3: 配信
    top_n = notifier.fetch_top_n(table, today, n=TOP_N_DELIVERY)
    summaries = notifier.summarize_with_claude(top_n)
    notifier.post_to_slack(summaries, secrets["SLACK_WEBHOOK_URL"])
    notifier.mark_delivered(table, top_n)

    return {"collected": ..., "scored": ..., "delivered": ...}
```

### 4.6 エラーハンドリング方針

| 失敗箇所 | 挙動 |
|----------|------|
| HF API 失敗 | warning ログ、arXiv のみで継続 |
| arXiv API 失敗 | warning ログ、HF のみで継続 |
| 全ソース失敗 | DLQ送信、Slack に通知（管理者向け） |
| Claude API 失敗 | tenacity で 3回リトライ、それでも失敗なら該当論文をskip |
| Slack 投稿失敗 | tenacity 3回リトライ、失敗時は CloudWatch Logs にエラー出力 |

---

## 5. Claude API プロンプト設計

### 5.1 スコアリング用プロンプト（バッチ処理）

**システムプロンプト**:
```
あなたは生成AI/LLM分野の論文を、ユーザーの興味に対して0-100点で評価するアシスタントです。
ユーザーの興味は以下の通りです。

{INTEREST_PROMPT}

各論文のタイトルとアブストラクトを読み、以下の観点で評価してください。
- ユーザーの興味領域との関連性（最重要）
- 実装・評価・アーキテクチャ提案を含むかどうか
- 新規性、実用性

出力は必ずJSON配列のみ。各要素は {"paper_id": "...", "score": 0-100, "reason": "日本語1-2文"} の形式。
余計な説明は一切付けないこと。
```

**ユーザーメッセージ**: 10本の論文情報をまとめて投入
```
評価対象の論文（{N}本）:

[1] paper_id: 2401.13782
title: Tweets to Citations: ...
abstract: ...

[2] paper_id: 2402.00123
title: ...
abstract: ...
...
```

### 5.2 要約用プロンプト

**システムプロンプト**:
```
あなたは論文を日本語で簡潔に要約するアシスタントです。
英語のタイトルとアブストラクトから、以下のJSON形式で要約を返してください。

{
  "title_ja": "日本語タイトル（30文字以内）",
  "summary_ja": ["要点1", "要点2", "要点3"]
}

各要点は1文・40文字程度。技術用語は無理に和訳せず、原語または通称（例：RAG、Agentic AI）を残してよい。
余計な説明は一切付けないこと。
```

### 5.3 JSON強制方法

Anthropic Messages API の `tool_choice` を使った function calling 形式でstructured outputを強制する。

```python
response = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=2048,
    system=SYSTEM_PROMPT,
    tools=[{
        "name": "submit_scores",
        "description": "論文スコアの結果を返す",
        "input_schema": {
            "type": "object",
            "properties": {
                "results": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "paper_id": {"type": "string"},
                            "score": {"type": "integer", "minimum": 0, "maximum": 100},
                            "reason": {"type": "string"}
                        },
                        "required": ["paper_id", "score", "reason"]
                    }
                }
            },
            "required": ["results"]
        }
    }],
    tool_choice={"type": "tool", "name": "submit_scores"},
    messages=[{"role": "user", "content": user_message}]
)
```

`prompt_caching` を有効化し、システムプロンプトと興味プロンプトをキャッシュする（コスト削減）。

---

## 6. Slack 配信フォーマット

Slack Incoming Webhook に Block Kit 形式で投稿する。

### 6.1 メッセージ構造

```json
{
  "blocks": [
    {
      "type": "header",
      "text": {"type": "plain_text", "text": "📚 AI Paper Radar — 2026-05-05"}
    },
    {
      "type": "section",
      "text": {"type": "mrkdwn", "text": "本日の注目論文 *3本* をお届けします。"}
    },
    {"type": "divider"},
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "*[1位 / score: 87]* <https://arxiv.org/abs/2401.13782|Tweets to Citations: Unveiling the Impact of Social Media Influencers on AI Research Visibility>\n_AIインフルエンサーがAI研究の可視性に与える影響_\n\n• AKとAran氏のXツイートが被引用数に与える因果的影響を定量分析\n• AI/ML分野ではSNSインフルエンサーがcitationsの早期指標となる\n• 市民社会のジャーナリストに類似した役割を果たす\n\n*採用理由*: ユーザーの「LLM評価手法」と「ソーシャルシグナル」への関心に直接該当する実証研究"
      }
    },
    {"type": "divider"},
    // 2位、3位...
    {
      "type": "context",
      "elements": [
        {"type": "mrkdwn", "text": "🤖 Powered by Claude Haiku 4.5 | <https://huggingface.co/papers|HF Daily Papers> + arXiv"}
      ]
    }
  ]
}
```

### 6.2 投稿方針

- スレッド化はしない（読み取りやすさ優先）
- メンションなし（個人用）
- 失敗時は CloudWatch Logs にレスポンスボディを記録

---

## 7. CDK スタック構成

### 7.1 スタック定義

- **スタック名**: `AiPaperRadarStack`
- **構成**: 1スタックに全リソースを含める（小規模のため分割しない）

### 7.2 リソース一覧

| リソース | CDK コンストラクト | 主要プロパティ |
|----------|-------------------|----------------|
| DynamoDB Table | `aws_dynamodb.Table` | PAY_PER_REQUEST、TTL `ttl`、GSI 1個、削除保護: 開発時OFF |
| Secrets Manager | `aws_secretsmanager.Secret` | 値は CDK には含めず、デプロイ後に手動投入 |
| Lambda Function | `aws_lambda.Function` | Python 3.12、arm64、1024MB、5分、環境変数3個 |
| Lambda Layer | `aws_lambda_python_alpha.PythonLayerVersion` | requirements.txt から自動構築 |
| IAM Role (Lambda) | `aws_iam.Role` | DynamoDB R/W、Secrets Manager Read、CloudWatch Logs |
| EventBridge Schedule | `aws_scheduler.CfnSchedule` | cron(0 21 * * ? *)、ターゲット: Lambda |
| CloudWatch Alarm | `aws_cloudwatch.Alarm` | Estimated Charges > $10、SNS通知（任意） |
| CloudWatch Log Group | `aws_logs.LogGroup` | 保持期間 30日 |

### 7.3 IAMポリシー（Lambda実行ロール、最小権限）

```python
table.grant_read_write_data(lambda_function)
secret.grant_read(lambda_function)
# CloudWatch Logs は basic execution role に含まれる
```

### 7.4 デプロイコマンド

```bash
cdk synth           # テンプレート確認
cdk diff            # 差分確認
cdk deploy          # デプロイ（てつてつ承認後）
```

### 7.5 シークレット投入手順（デプロイ後）

```bash
aws secretsmanager put-secret-value \
  --secret-id ai-paper-radar/runtime \
  --secret-string file://~/.secrets/ai-paper-radar-secret.json
```

---

## 8. ローカル開発・テスト

### 8.1 ディレクトリ構成

```
ai-paper-radar/
├── cdk/
│   ├── app.py
│   ├── stacks/ai_paper_radar_stack.py
│   └── cdk.json
├── lambdas/pipeline/
│   ├── lambda_function.py
│   ├── core/
│   │   ├── collector.py
│   │   ├── scorer.py
│   │   ├── notifier.py
│   │   └── settings.py
│   └── requirements.txt
├── tests/
│   ├── test_collector.py
│   ├── test_scorer.py
│   ├── test_notifier.py
│   └── test_cdk_snapshot.py
├── pyproject.toml
└── README.md
```

### 8.2 依存パッケージ（要点）

```
# lambdas/pipeline/requirements.txt
boto3
anthropic
requests
feedparser
tenacity
```

```toml
# pyproject.toml の dev-dependencies
pytest
pytest-cov
moto[dynamodb,secretsmanager]
mypy
ruff
aws-cdk-lib
constructs
```

### 8.3 テスト方針

- **collector**: `requests-mock` で HF/arXiv API をモック化、固定レスポンスで検証
- **scorer**: Anthropic SDK の `Anthropic.messages.create` を `unittest.mock` でパッチ、JSON応答を返す
- **notifier**: Slack Webhook URL を `requests-mock` で受け、Block Kit構造を検証
- **DynamoDB**: `moto` の `mock_aws` デコレータでローカル動作
- **CDK**: `aws_cdk.assertions.Template` でリソース有無・プロパティを検証

### 8.4 ローカル実行

```bash
# 環境変数を ~/.secrets/ai-paper-radar.env から読み込み
set -a && . ~/.secrets/ai-paper-radar.env && set +a

# Lambda ハンドラを直接実行
python -m lambdas.pipeline.lambda_function
```

---

## 9. 未確定事項（実装中に決める）

- arXiv API のレート制限（3秒/リクエスト）への対応方式（sleepか tenacity の wait_fixed か）
- HF Daily Papers の `submittedBy` をスコアリングの補助シグナルに使うか（Phase 2候補）
- DynamoDB の `score_padded` を3桁にするか4桁にするか（要件次第）
- CloudWatch Billing Alarm の通知先（メール か Slack か、ひとまずメール）

---

## 10. 確認をお願いしたい点

1. DynamoDB のキー構造（PK = paper_id、GSI = collected_date + score_padded）でよいか
2. Secrets Manager のキー名（`ANTHROPIC_API_KEY` / `SLACK_WEBHOOK_URL` / `INTEREST_PROMPT`）でよいか
3. Lambda メモリ 1024MB / タイムアウト 5分でよいか（過剰なら 512MB / 3分に絞る）
4. Slack 投稿フォーマット（Block Kit、上記サンプル）でよいか
5. CDK スタック1個構成でよいか（基盤層分離はしない）
6. 1日あたり収集上限 50本 / 配信3本 でよいか

確認後、CDK プロジェクト初期化と実装着手に進む。
