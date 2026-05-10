# AI Paper Radar — 知見・決定事項の記録

> 最終更新: 2026-05-05

このファイルは、プロジェクトの設計判断・調査結果・ハマったポイントを蓄積する。セッションをまたいで参照される最重要ドキュメント。

---

## 1. 一次ソース裏どり結果（2026-05-05実施）

### 1.1 Paper Espresso（arXiv:2604.04562）— 実在確認、設計の参考事例

- **タイトル**: "Paper Espresso: From Paper Overload to Research Insight"
- **著者**: Mingzhe Du, Luu Anh Tuan, Dong Huang, See-kiong Ng（NTU）
- **公開日**: 2026年4月6日
- **HF Paper ページ**: https://huggingface.co/papers/2604.04562
- **arXiv**: https://arxiv.org/abs/2604.04562

このプロジェクトは我々の構想とほぼ同一のアーキテクチャ：データ層は HF Daily Papers API + arXiv、AI処理層は Google Gemini で要約・トレンド分析、UI層は Streamlit。35ヶ月運用で13,300論文、6,673トピックを処理した実績がある。

得られた重要な定量的知見：
- トピックnoveltyとcommunity engagementには**正の相関**。最も新しい話題は2倍のupvoteを集める
- 新トピックは**中央値8ヶ月でピーク到達**、その後**1ヶ月で半分の注目を失う**
- 2025年中盤に "RL for LLM reasoning" が急増（arXiv全体の構造変化）

→ **示唆**: 速報性が決定的に重要。週次配信より日次配信が望ましい。novelな話題ほど発見価値が高いので、スコアリングでnovelty重みを軽視してはいけない。

### 1.2 Papers with Code — 実質サービス終了、HF移行済み

`paperswithcode.com` にアクセスすると `huggingface.co/papers/trending` に **302リダイレクト**される。Metaが運営を終了し、Hugging Face に統合された。

→ **対応**: 我々のデータソースから Papers with Code を外し、HF Trending Papers として扱う。コードがついた論文の取得は HF API 経由で代替可能。

### 1.3 HF Daily Papers の Upvote 仕様 — 順位付けは公式ではない

HF公式ブログには「upvoteで論文を **highlight** する」と書かれているが、「順位付けメカニズム」の明示はない。てつてつのレポートにある「Upvoteで順位付け」は若干強めの解釈。

→ **対応**: 実装では upvote数を「補助シグナル」として扱い、公式の順位付け仕様とは断定しない。

---

## 2. てつてつ作成の徹底調査レポート（2026年5月）

> 以下、てつてつが一次ソースを丁寧に確認して作成した本プロジェクトの礎となる調査レポート。本文をそのまま保存する。

### 2.1 エグゼクティブサマリー

「毎朝3本」を一次ソースに基づいて選びたい場合、**「人手キュレーション × コミュニティUpvote」**を組み合わせた **Hugging Face Daily Papers** が最も再現可能性・信頼性のバランスが取れた一次ソースに近い。これはAK氏（Ahsen Khaliq, @_akhaliq）と認可された投稿者によるキュレーションを起点に、コミュニティのUpvoteで順位付けされる仕組みであることがHugging Face公式ブログで明示されている。

一方、「自分の興味」に合わせた個別最適化には、SVM＋TF-IDFベースの **arXiv Sanity Lite**（Karpathy、ソースコード公開済み）と、**Semantic Scholar Recommendations API**（SPECTERベース、論文embedding使用）が一次ソース・アルゴリズムが完全公開されており、自前パイプライン構築の基盤になる。

学術的には、Beel et al. (2016) の "Research-paper recommender systems: a literature survey" が分野の基準サーベイで、200本以上の論文をレビューしている。生成AI分野は「引用が付くまでの遅延」が長いため、**Citation-basedメトリクスは原理的に向かず**、**Altmetrics（特にTwitter/X言及）+ コミュニティUpvote + Content-based embedding** の組み合わせが現実解となる。

### 2.2 既存サービス調査（要点のみ）

#### キュレーション型（人手・コミュニティ）

- **Hugging Face Daily Papers** ★最重要: AK氏 + コミュニティsubmit + Upvote。約3,700本featured（2024年9月時点）。HF API経由取得可。https://huggingface.co/papers
- **AK (@_akhaliq) on X**: HF Daily Papersの実質的な人格化アカウント、約468.7K followers
- **Aran Komatsuzaki (@arankomatsuzaki)**: GPT-J共同開発者、学術視点キュレーション
- **The Batch (Andrew Ng)**: 人手編集、週刊メール、業界文脈含む
- **AlphaSignal**: 自称ハイブリッドだがアルゴリズム非公開
- **TLDR AI**: 専門家フリーランス雇用、平日メール
- **AIDB（日本語）**: 株式会社Parks運営、人手キュレーション、毎週日曜「今週の注目AI論文リスト」更新
- **Papers with Code**: 2026年現在、HF Trendingに統合済み

#### アルゴリズム型

- **arXiv Sanity Lite** ★アルゴリズム公開: TF-IDF + SVM、Karpathy、MIT License、自前運用可。https://github.com/karpathy/arxiv-sanity-lite
- **Semantic Scholar Recommendations API** ★API公開: SPECTERベース、cold-start対応、無料。https://api.semanticscholar.org/api-docs/recommendations
- **SPECTER (Cohan et al., ACL 2020)**: 学習済み論文embedding、新規論文にも適用可能、cold-start問題の事実上の業界標準
- **Connected Papers**: Co-citation + Bibliographic coupling による論文マップ可視化
- **ArxivDigest (AutoLLM)**: GPT-3.5/4でユーザー興味記述に対しスコアリング、GitHub Action + メール配信。https://github.com/AutoLLM/ArxivDigest

### 2.3 学術的「注目論文判定手法」の研究

#### サーベイ論文
- **Beel et al. (2016)**: 分野の基準サーベイ。Content-based filtering 55%、CF 18%、Graph-based 16%
- **Kreutz & Schenkel (2022)**: 直近のサーベイ（arXiv:2201.00682）

#### 主要手法と生成AI分野での適性

| 手法 | 速報性 | Cold-start耐性 | 推奨度 |
|---|---|---|---|
| Citation count | ×（遅い） | × | △ |
| Altmetrics (Twitter等) | ◎ | ○ | ◎ |
| Mendeley readership | ○ | △ | ◎ |
| Content-based (TF-IDF+SVM) | ◎ | ◎ | ◎ |
| SPECTER/SciBERT embedding | ◎ | ◎ | ◎ |
| Collaborative filtering | △ | × | × |
| LLMによるscoring (ArxivDigest型) | ◎ | ◎ | ◎ |

#### 生成AI分野での重要な実証研究
- **He et al. (2024). "Tweets to Citations"** arXiv:2401.13782 — AK氏とAran Komatsuzaki氏のXツイートが被引用数に与える因果的影響を定量分析
- **Wang et al. (2025). "Who Gets Recommended?"** arXiv:2501.00367 — LLM推薦は引用数の多い・新しめ・著者人数の多い論文を優先する傾向
- **Petiska, E. (2023)** arXiv:2409.19868 — LLMは引用数が多い・古い・有名ジャーナル掲載論文を優先推薦（Matthew効果の増幅）

### 2.4 結論（生成AIアーキテクト視点の推奨スタック）

- **第1階層**: HF Daily Papers + AK on X
- **第2階層**: arXiv Sanity Lite（自前運用） + ArxivDigest（自然言語興味記述でLLMスコアリング）
- **第3階層**: AIDB（日本語、週次） + The Batch（業界文脈、週次）

**重要な認識**:
- Citation数は3〜12ヶ月遅れる → 生成AI論文の意思決定材料として原理的に不向き
- 単一サービス依存はsystematic biasを招く
- 「コミュニティUpvote × 専門家Xシグナル × 自分のContent-based filter」の三点合議が最ロバスト

---

## 3. 設計判断の記録

### 3.1 なぜCDK Pythonか
リソース数6-8個、IaC管理が妥当な規模。CLAUDE.md規約でPython優先。CDKは型補完が効き、再現性も高い。`cdk watch` でホットリロードも可。

### 3.2 なぜ Slack のみで MVP（Notionなしで開始）
Notionは「論文を貯めて再読する」用途で価値があるが、DynamoDBに全メタデータを蓄積する設計のため、後から Notion連携や検索UI を追加可能。MVPはシンプル優先。

### 3.3 なぜ Haiku でスコアリング、Sonnet で要約か
スコアリングは50本/日のバッチ処理で安価さが重要 → Haiku 4.5。要約は3本/日で品質が重要 → Sonnet 4.6。コストは月 $3-6 に収まる試算。

### 3.4 リージョン選択
ap-northeast-1（東京）。既存の他プロジェクト（chicken-knowledge-rag 等）と統一して運用負荷を下げる。Anthropic API と Slack Webhook はAWS外部サービスのためリージョン依存しない。Bedrock等の先行リリースは東京リージョンでも数ヶ月遅れで利用可能になるので個人用途では問題ない。

---

## 4. ハマったポイント・要注意事項

（プロジェクト進行中に追記していく）

- 現時点なし

---

## 8. Anthropic Claude を Bedrock 経由へ移行（2026-05-06）

Phase 3 デプロイ後、Anthropic Direct API 利用から **Amazon Bedrock 経由** へ切り替え。

**判断根拠**:
- API キー管理が不要になる（IAM 認証で完結、漏洩リスク削減）
- 課金が AWS にまとまり、Budget で一括監視できる
- Lambda 実行ロールのみで認証されるため、SSM パラメータが 1 件減る（3 → 2）
- `anthropic` SDK の `AnthropicBedrock` クラスは Direct 版と messages API シグネチャが同じで、ロジックの書き換え不要

**Inference Profile 選定**:
- `global.anthropic.claude-haiku-4-5-20251001-v1:0` を採用（てつてつの選択、2026-05-06）
- `jp.` は日本国内ルーティング限定で data residency 上は安全だが、global の方が可用性とスループットが高い
- 論文タイトル・アブストラクト・興味プロンプトはいずれも公開可能な内容で、国外経由のリスクは無視できる

**重要な制約（実装上のハマりポイント）**:
- Bedrock model access の **AWS Console 手動有効化が必須**。IAM 権限を付与しても、Console で Anthropic モデルを Enable していないと InvokeModel は AccessDeniedException で失敗する
- Global Cross-Region Inference Profile は宛先リージョンが全 commercial Region に分散し得るため、IAM Resource ARN に `arn:aws:bedrock:*::foundation-model/...` のワイルドカード指定が必要（公式手順）
- `bedrock:InvokeModel` の Resource は **2 つ必要**: ① ソース側の inference profile ARN ② 宛先側の foundation model ARN

参考: https://docs.aws.amazon.com/bedrock/latest/userguide/inference-profiles-support.html

---

## 7. AWS Budgets を採用（Billing アラート方式の選択、2026-05-05）

CloudWatch Alarm + Billing メトリクスから AWS Budgets に変更。

**判断根拠**:
- CloudWatch Billing メトリクスは **us-east-1 リージョン限定**で取得可能。本プロジェクトの主リージョン ap-northeast-1 とずれる
- Cross-region Stack を作るのは複雑（CDK の `crossRegionReferences=True` 等が必要）
- AWS Budgets はグローバルサービス、リージョン非依存
- メール通知が標準で、SNS Topic 経由より簡単

**実装上の注意**:
- メール通知先はコードにハードコードせず、CDK Context（`-c notification_email=...`）で渡す
- Context 未指定時は Budget リソースを作成しない（オプショナル化、CI/CD 柔軟性のため）
- 80% 閾値で通知（$8 で警告）、ACTUAL（実コスト）モード

---

## 6. SSM Parameter Store 採用の判断（2026-05-05）

シークレット保管先を Secrets Manager から SSM Parameter Store standard に変更。

**判断根拠**:
- 個人用 3 シークレットで自動ローテーション不要（Anthropic/Slack のキーは AWS 外部発行のため、AWS 側で回しても無意味）
- 各値が 4KB 上限内に余裕で収まる（最大の INTEREST_PROMPT で約 600 バイト）
- KMS 暗号化（SecureString）で機密性は Secrets Manager と同等
- 月額コスト $1.20 → $0、年 $14 削減

**重要な制約（実装上のハマりポイント）**:
SecureString パラメータは CloudFormation/CDK で**作成できない**（AWS 公式制約）。
そのため CDK では Lambda 実行ロールへの権限付与（`ssm:GetParameter*` + `kms:Decrypt` for `alias/aws/ssm`）のみを行い、
パラメータ実体は `aws ssm put-parameter --type SecureString` で**デプロイ後に手動投入**する。

参考: https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-ssm-parameter.html

---

## 5. 学習済み概念

理解度テストハーネス（`~/.claude/CLAUDE.md` 「理解度テストハーネス」ルール）で正答した概念。次回以降のテスト判定に利用する。

| 概念 | 確認日 | 要点 |
|------|--------|------|
| AWS CDK の Construct（L1/L2/L3）| 2026-05-05 | AWSリソースを抽象化したクラス。L1=CFn直結、L2=プロパティ簡略化・デフォルト値あり、L3=複数リソースをまとめたパターン。本プロジェクトは主に L2 を使う |
| Lambda 1関数構成 vs Step Functions のトレードオフ | 2026-05-05 | 規模が小さく状態管理が不要なら Lambda 単体。15分超え・並列化・途中再開が必要なら Step Functions を導入。月30回バッチでは Lambda が最適 |
| Lambda 実行ロール（IAM Role）| 2026-05-05 | Lambda が他AWSサービスを呼ぶには実行ロールに必要権限を Allow するポリシーをアタッチ。アクセスキー埋め込みは禁止。CDKでは `table.grant_read_write_data(fn)` 等のメソッドで一行記述可能 |
| Anthropic Tool Use の本質 | 2026-05-06 | JSON 強制出力に Anthropic 公式が推奨する方法。`response_format` パラメータは Anthropic に存在しない（OpenAI の機能）。tools に input_schema 込みで定義し tool_choice で強制実行、レスポンスは `response.content` の `type=='tool_use'` ブロックの `.input`（dict、json.loads 不要）|
| Anthropic vs OpenAI のレスポンス構造 | 2026-05-06 | OpenAI: `response.choices[0].message.{content,tool_calls}` / Anthropic: `response.content`（ブロックリスト、各 .type で分岐）。混同すると AttributeError |
| DynamoDB Query vs Scan の使い分け | 2026-05-06 | Scan はテーブル全体を走査するため遅くて高い。GSI を Query で利用し PK で絞ってから FilterExpression で属性を絞るのが効率的。本プロジェクトは `gsi_collected_date_score` を利用 |
| 外部 API リトライ戦略（tenacity）| 2026-05-06 | デコレータでリトライ回数・指数バックオフ・jitter・対象例外を宣言的に書ける。`@retry(wait=wait_exponential_jitter(initial=1, max=60), stop=stop_after_attempt(3), retry=retry_if_exception_type(...))` のような定型 |
| CDK Stack のライフサイクルと CDK 管理外リソース | 2026-05-06 | `cdk destroy` で消えるのは Stack 内のリソース（CFn テンプレに含まれるもの）だけ。SecureString は CFn 非対応のため CDK では権限付与だけ行い、パラメータ実体は別管理。完全リセットには `cdk destroy` の後に `aws ssm delete-parameter` が必要 |
| Bedrock Cross-Region Inference Profile の本質 | 2026-05-06 | `global.` / `jp.` などのプロファイル ID は単独のモデル参照ではなく、複数の宛先リージョンに分散ルーティングするロードバランサ。IAM では「ソース inference profile ARN」と「宛先 foundation-model ARN（リージョン *）」の両方を `bedrock:InvokeModel` で許可する必要がある（片方だけでは失敗）|
| Bedrock model access 有効化と IAM の二段階制御 | 2026-05-06 | Bedrock は IAM の `bedrock:InvokeModel` だけでは呼べない。AWS Console の「Model access」で各 Anthropic モデルを Enable する手動操作が別途必要。IAM = 誰が呼べるか、model access = そもそも呼べるか、の二段構え |
