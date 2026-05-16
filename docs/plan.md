# AI Paper Radar — プロジェクト計画書

> 作成日: 2026-05-05
> 状態: 確定（てつてつ承認済み）

---

## 1. 目的

生成AI/LLM分野の注目論文を、毎朝SlackへJST 6:00に自動配信する個人用システムを構築する。判断材料の対象領域は、てつてつの実務に直結するRAGアーキテクチャ、Agentic AI設計、LLM評価、ベクトルDB、AWS/Google Cloudの生成AIサービスとする。

## 2. 背景と設計思想

調査レポート（`docs/knowledge.md` 参照）から得られた以下の知見を設計の出発点とする。

第一に、生成AI論文は3〜12ヶ月で陳腐化するため、Citation-basedの注目度判定は原理的に間に合わない。第二に、単一サービス依存はsystematic bias（HF AKの個人嗜好、AlphaSignalの非公開アルゴリズム、LLMのMatthew効果増幅）を招く。第三に、最もロバストな構成は「コミュニティUpvote × 専門家Xシグナル × 自分のContent-based filter」の三点合議である。

加えて、裏どりの結果、Paper Espresso（arXiv:2604.04562）が我々の構想とほぼ同一のアーキテクチャを採用しており、35ヶ月運用で得た知見「最も新しいトピックは2倍のupvoteを集める」「新トピックは中央値8ヶ月でピーク到達、1ヶ月で半分の注目を失う」が、速報性の重要性を裏付けている。

## 3. ユースケース

毎朝6:00（JST）にSlackで前日分の注目論文上位3本を受信する。各論文は、arXivリンク、英語タイトル、日本語3行要約、スコア（0-100）、採用理由を含む。過去の配信ログはDynamoDBに蓄積され、将来の検索や類似論文推薦の基盤として再利用可能とする。

## 4. システム構成

### 4.1 アーキテクチャ概要

```
┌─────────────────────────────────────────────────────┐
│ EventBridge Scheduler                                 │
│   cron(0 21 * * ? *)  = 毎日 UTC 21:00 = JST 6:00     │
└─────────────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│ Lambda: ai-paper-radar-pipeline（単一関数）            │
│ ─────────────────────────────────────────────────── │
│ Step 1: 収集（core/collector.py）                       │
│   ・HF Daily Papers API（前日分のキュレーション結果）    │
│   ・arXiv API（cs.CL, cs.AI, cs.LG の過去24h新着）     │
│   ・HF Trending Papers（旧Papers with Code 移行先）    │
│   → 重複排除して DynamoDB に upsert                    │
│                                                       │
│ Step 2: スコアリング（core/scorer.py）                  │
│   ・Amazon Nova Pro でユーザー興味プロンプトに対し       │
│     各論文を 0-100 で評価（バッチ処理 10本/呼び出し）    │
│   ・HF upvote数を補助シグナルとして加点                  │
│   → スコアと採用理由を DynamoDB に書き戻し              │
│                                                       │
│ Step 3: 配信（core/notifier.py）                        │
│   ・上位3本を選択                                        │
│   ・Amazon Nova Pro で日本語3行要約を生成               │
│   ・Slack Webhook へ Block Kit 形式で投稿               │
│   → DynamoDB に delivered_at を記録                    │
└─────────────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│ DynamoDB: ai-paper-radar-papers                       │
│ （論文メタデータ + スコア + 配信履歴を一元管理、TTL 90日）│
└─────────────────────────────────────────────────────┘
```

### 4.2 採用技術と根拠

| 技術 | 採用理由 |
|------|----------|
| AWS CDK (Python) | リソース数が小規模、IaC化が妥当。Pythonで統一 |
| AWS Lambda (Python 3.12) | サーバレス、無料枠で月30回実行は十分収まる |
| Lambda 1関数構成 | 月30回・1実行5分以内の規模で責務分離はソースコード内のモジュール分割で十分。Step Functionsは状態管理が必要になってから |
| Amazon DynamoDB (オンデマンド) | スキーマ柔軟、無料枠で初期データ量を吸収 |
| Amazon EventBridge Scheduler | cron式でタイムゾーン指定可能、Lambda起動の標準パターン |
| AWS Systems Manager Parameter Store standard | Slack Webhook URL、興味プロンプトを SecureString で保管。CDK では枠を作らず（CFn制約）、デプロイ後に CLI で投入 |
| Amazon Bedrock 経由 Amazon Nova Pro | IAM 認証で API キー不要。`apac.amazon.nova-pro-v1:0` APAC Cross-Region Inference Profile で東京含む APAC リージョンに自動分散。Bedrock Converse API 経由で boto3 から呼び出す。Claude Haiku 4.5 と比較して入力 $1.00→$0.80/1M、出力 $5.00→$3.20/1M とコスト面で有利（2026-05-16 切替、コスト削減が主目的） |
| HF Daily Papers API | 人手キュレーション×コミュニティUpvoteの一次ソース |
| arXiv API | 公式新着取得、レート制限緩い |

### 4.3 リージョン

`ap-northeast-1`（東京）を採用。既存の他プロジェクトと統一して運用負荷を下げる。Amazon Nova Pro は Bedrock 経由のため、リクエスト発行リージョン = ap-northeast-1。APAC CRIS で APAC 内（東京・大阪・ソウル・ムンバイ・シンガポール・シドニー）に自動分散する。Slack Webhook は AWS 外部サービスのためリージョン依存なし。

## 5. フェーズ計画

### Phase 1（MVP, 本計画のスコープ）
HF Daily Papers + arXiv + HF Trending の収集、Amazon Nova Pro によるスコアリングと要約、Slack配信、DynamoDB蓄積。これだけで毎朝3本配信が動く状態を目指す。

### Phase 2（精度向上）
SPECTER2 embeddingによる類似度計算、X言及数のaltmetricsブースト、フィードバックループ（Slackのリアクションで興味学習）。モデル切替は当面なし（コスト最優先方針、2026-05-16 確定）。

### Phase 3（拡張）
Notion DB連携、過去論文検索UI、週次サマリ機能。

## 6. スコープ外（明示的に作らないもの）

- 配信先の複数化（Slack専用でMVP）
- Web UI、ダッシュボード
- 英語要約（日本語のみ）
- 多分野対応（生成AI/LLM領域に特化）
- ユーザー認証、マルチテナント
- Step Functions による状態管理（必要になったらPhase 2で導入）

## 7. コスト試算（月額）

| 項目 | 試算 |
|------|------|
| Bedrock 経由 Amazon Nova Pro（スコアリング 50本/日 + 要約 3本/日 × 30日） | 約 $0.5-1 |
| AWS Lambda（30回実行、1024MB、平均2分） | 無料枠内 |
| DynamoDB オンデマンド（月数千リクエスト） | 無料枠内 |
| EventBridge Scheduler | 無料枠内 |
| AWS SSM Parameter Store standard（3パラメータ） | 無料 |
| **合計** | **$1-2 / 月** |

予算上限 $10/月 に対し、Secrets Manager 比でさらに $1.20/月節約。

## 8. リスクと対策

| リスク | 対策 |
|------|------|
| Bedrock APIレート制限 | スコアリングを10本/呼び出しのバッチ化、tenacityでリトライ |
| HF API仕様変更 | 取得失敗時はarXivのみで継続、Slack に警告通知 |
| 配信内容の品質ムラ | Phase 2でフィードバック学習を導入。モデル切替はコスト方針上当面なし |
| シークレット漏洩 | LLM 認証は Bedrock 経由の IAM のみで API キー不要、SSM SecureString（KMS暗号化）+ IAM最小権限、`.gitignore` 厳守 |
| AWS料金暴騰 | CloudWatch Billing アラート $10/月 設定 |

## 9. 興味プロンプト（スコアリング基準）

SSM Parameter Store の `/ai-paper-radar/runtime/INTEREST_PROMPT` に格納する初期プロンプト。Phase 2以降で動的更新できる仕組みを検討する。

```
私はクラウドアーキテクト兼開発者です。以下の領域に強い関心があります。

- RAGアーキテクチャと検索品質改善
- エージェント型AI設計（Agentic AI）、ツール呼び出し、マルチエージェント協調
- LLM評価手法、ベンチマーク設計
- ベクトルデータベース、埋め込み技術
- プロンプトエンジニアリング、コンテキスト圧縮
- AWS Bedrock、Google Cloud Vertex AI などのクラウド生成AIサービス
- 日本語LLMアプリケーション開発、日本語特化モデル

これらに関連する論文ほど高いスコアを付けてください。
理論研究単独より、実装・評価・アーキテクチャ提案がある論文を優先します。
```

## 10. 次のアクション

1. ~~本計画書のてつてつ確認~~ → 完了
2. `docs/spec.md` 詳細化（DynamoDBスキーマ、Lambda I/O設計、Bedrock プロンプト、CDK構成）← 着手中
3. spec.md の再確認後、CDK実装着手
