# AI Paper Radar — タスク管理

> 最終更新: 2026-05-05

---

## Phase 0: 計画フェーズ ✅ 完了

- [x] 既存サービス・学術手法の調査（てつてつ実施）
- [x] 一次ソース裏どり（Paper Espresso、Papers with Code、HF Daily Papers）
- [x] アーキテクチャ案の合意（CDK Python + Lambda 1関数 + DynamoDB + Slack配信）
- [x] `docs/` 4ファイル + プロジェクト CLAUDE.md 作成
- [x] plan.md のてつてつ確認
- [x] 興味プロンプトの最終確定（日本語版）
- [x] オーケストレーション方式の決定（Lambda 1本化）
- [x] LLMモデルの決定（Claude Haiku 4.5 全工程）

## Phase 1: 仕様策定 ✅ 完了

- [x] spec.md 詳細化（DynamoDBスキーマ、Lambda I/O、Claudeプロンプト、CDK構成）
- [x] spec.md のてつてつ確認
- [x] CDK プロジェクト初期化（uv + npm ローカル方式）
- [x] `pyproject.toml`、`.gitignore`、`.env.example` 作成
- [x] `~/.secrets/ai-paper-radar.env` テンプレート作成（実値はてつてつが投入）
- [x] GitHub リポジトリ作成（パブリック + Secret Scanning + Push Protection 有効化）

## Phase 2: 実装（MVP）

- [x] CDK スタック実装（DynamoDB, Lambda, EventBridge, IAM、SSM 権限付与）
- [x] AWS Budgets $10/月（Context `notification_email` 指定時のみ作成）
- [x] CDK スナップショットテスト（8 件、全パス）
- [x] Lambda 関数 `pipeline` 実装
  - [x] `core/settings.py`（SSM Parameter Store からの一括取得、lru_cache）
  - [x] `core/collector.py`（HF Daily Papers + arXiv + HF Trending 取得、重複排除、DynamoDB upsert）
  - [x] `core/scorer.py`（Claude Haiku Tool Use で 10本バッチスコアリング）
  - [x] `core/notifier.py`（Claude Haiku で日本語要約 + Slack Block Kit 投稿）
  - [x] `lambda_function.py`（ハンドラ統合、ステップ別エラー集約）
- [x] ユニットテスト（29 件全パス、moto + requests-mock + Anthropic SDK モック）

## Phase 3: テスト・デプロイ

- [ ] ユニットテスト（pytest + moto）
  - [ ] collector のテスト（API モック）
  - [ ] scorer のテスト（Anthropic SDK モック）
  - [ ] notifier のテスト（Slack Webhook モック）
- [ ] CDK スナップショットテスト
- [ ] SAM Local による Lambda 統合テスト
- [ ] dev環境への CDK deploy
- [ ] 1週間の試験運用、配信品質チェック
- [ ] 本番デプロイ（同一AWSアカウント・別スタック名）

## Phase 4: 振り返り・拡張検討

- [ ] 1週間の配信ログレビュー
- [ ] 興味プロンプトの調整
- [ ] スコアリング精度の評価、Sonnet 4.6 切替の要否判断
- [ ] Phase 2機能（SPECTER2、altmetrics）の必要性判断
- [ ] Phase 3機能（Notion連携、検索UI）の必要性判断

---

## 完了済みの判断

- 配信先: Slack のみ（蓄積は DynamoDB が担う）
- インフラ: AWS CDK Python + Lambda 1関数 + DynamoDB + EventBridge
- リージョン: ap-northeast-1
- 予算上限: $10/月（試算では $2-4/月）
- 言語: Python 3.12
- Papers with Code は実質終了 → HF Trending に置換
- LLMモデル: Claude Haiku 4.5（スコアリング・要約とも）
- 配信時刻: JST 6:00（UTC 21:00）
- 興味プロンプト: 日本語版で確定（plan.md §9）
