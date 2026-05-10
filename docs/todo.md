# AI Paper Radar — タスク管理

> 最終更新: 2026-05-10

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

## Phase 3: デプロイ・試験運用

> ユニットテスト 29 件 と CDK スナップショット 8 件は Phase 2 で実装・パス済み。Phase 3 はデプロイ作業に専念する。

- [x] PR #2（Lambda 実装）を main にマージ（2026-05-06）
- [x] `cdk synth` / `cdk diff` による事前確認 → 11 リソース新規、IAM は最小権限で確認（2026-05-06）
- [x] dev 環境（ap-northeast-1）へ `cdk deploy` → 13/13 CREATE_COMPLETE（2026-05-06）
- [x] **Bedrock 経由への切替** PR #3 作成（2026-05-10、`feature/bedrock-migration`）
- [x] PR #3 を main に squash マージ（2026-05-10、sha 79bdbcc）
- [x] Bedrock 化後の `cdk deploy` 再実行（IAM 差分のみ、2026-05-10、37 秒で UPDATE_COMPLETE）
- [ ] AWS Console で Bedrock の Anthropic Claude Haiku 4.5 model access を有効化
- [x] SSM SecureString 2 件投入（`SLACK_WEBHOOK_URL` / `INTEREST_PROMPT`、API キーは Bedrock で不要化、2026-05-10）
- [ ] Lambda の手動 invoke で初回動作確認（Slack に届くか、CloudWatch Logs に異常なし）
- [ ] 1 週間の試験運用、配信品質チェック
- [ ] 本番デプロイ（必要なら別スタック名・別リージョン構成）

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
