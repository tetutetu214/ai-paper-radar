# AI Paper Radar — 知見・決定事項の記録

> 最終更新: 2026-05-12

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

### 3.3 なぜ Haiku でスコアリング、Sonnet で要約か（**廃止: §9 参照**）
~~スコアリングは50本/日のバッチ処理で安価さが重要 → Haiku 4.5。要約は3本/日で品質が重要 → Sonnet 4.6。コストは月 $3-6 に収まる試算。~~

→ 2026-05-16 に Amazon Nova Pro へ全面切替（§9 参照）。スコアリング・要約ともに同一モデル（Nova Pro）を使用する単純構成に変更。判断軸はコスト最優先。

### 3.4 リージョン選択
ap-northeast-1（東京）。既存の他プロジェクト（chicken-knowledge-rag 等）と統一して運用負荷を下げる。Anthropic API と Slack Webhook はAWS外部サービスのためリージョン依存しない。Bedrock等の先行リリースは東京リージョンでも数ヶ月遅れで利用可能になるので個人用途では問題ない。

---

## 4. ハマったポイント・要注意事項

### 4.0 Phase 4 申し送り：要約の DynamoDB 保存（2026-05-10）

`notifier.py` は配信時に `title_ja` / `summary_ja` をメモリ上で生成して Slack に POST するが、DynamoDB には書き戻していない。`mark_delivered` は `delivered_at` のみ更新。

**現状の挙動（バグではなく仕様未定義）**:
- spec.md §3.4 では `summary_ja` (S, △) の項目が定義されているが「DB に保存する」とは明記なし
- 実装は「配信対象のみ生成（メモリ）」に振っており保存していない
- Slack 投稿には正しく要約が入っている（2026-05-10 配信実機確認済み）

**Phase 4 で改善する場合のメリ・デメ**:
- 保存する: 配信ログを DB だけで完結確認可能、再表示時に Bedrock 再呼び出し不要
- 保存しない（現状）: DB 書き込み回数を抑えられる

個人用かつ毎日 3 件配信なら月 90 行の追加更新でコストはほぼ無視可能。Phase 4 で「保存する」方向に振ると運用しやすい。

### 4.1 Lambda アーキテクチャと native 拡張のクロスコンパイル問題（2026-05-10）

Phase 3 デプロイ後の Lambda 手動 invoke で `Runtime.ImportModuleError: No module named 'pydantic_core._pydantic_core'` が発生。

**原因の連鎖**:
- Lambda 関数アーキテクチャは arm64 にしていた（コスト 20% 削減狙い）
- bundling Docker は WSL2 ホスト（x86_64）で動くため、`pip install -r requirements.txt -t /asset-output` がホスト用 wheel を取得 → pydantic_core の x86_64 .so が Layer に入る
- arm64 Lambda はその .so を読めず ImportError
- Phase 2 時点では anthropic Direct API 利用で pydantic に間接依存していたが import パスを通らず顕在化せず、Bedrock 移行で boto3 経由 botocore.auth が pydantic を使う import パスに変わって発覚

**試した方法と次の壁**:
- `--platform manylinux2014_aarch64 --only-binary=:all:` を追加 → pydantic_core は OK だが、feedparser の依存 sgmllib3k は pure Python なのに wheel が PyPI に登録されておらず（古いパッケージ）、`--only-binary` 縛りで sdist build を禁じてしまうため fail

**最終的な解決策**:
- Lambda アーキテクチャを **x86_64** に変更（WSL2 ホストと一致、bundling のクロスアーキ問題自体を消す）
- arm64 維持の代替案（2 段階 pip install / arm64 native Docker + QEMU）はあるが、月 $1〜2 のシステムでコスト 20% 差は微々たるためシンプルさ優先

**学んだこと**:
- Lambda の bundling 設計は「関数アーキテクチャ」と「ホスト Docker のアーキテクチャ」が一致しているかを必ずチェックする
- `--only-binary=:all:` は強力だが、wheel 提供のない古い pure Python パッケージで詰まる罠あり
- pydantic_core のような Rust 製 native 拡張は wheel ファイル名に platform tag（`manylinux2014_aarch64` 等）が入っている → 入っていない `.whl` はアーキ非依存（pure Python）

---

### 4.2 既存論文の毎日再採点バグと put_item の全項目置換（2026-05-11）

Phase 3 自動配信開始日（2026-05-11）に、Bedrock のトークン使用量を確認したところ、手動 invoke 日（5/10）と自動配信日（5/11）の Input/Output トークン数がほぼ同一（約 22k/6.4k）で、毎日フル 50 件採点が走っていることが判明。

**原因**:
- `collector.upsert_dynamodb()` が `table.put_item()` で項目を**完全置換**していた
- 既存レコードに付いている `score` / `score_padded` / `score_reason` / `summary_ja` / `delivered_at` が、翌日の再収集時に新しい item dict（これらの属性を含まない）で上書きされて消える
- `scorer.fetch_unscored_papers()` は `collected_date = 今日 AND attribute_not_exists(score)` でフィルタしている → 上書き直後は全件「未採点」扱いになり、HF Trending 等で複数日にまたがって露出する論文も毎日採点し直されていた

**修正方針（PR #5、案A: update_item 切替）**:
- 既存レコードがあれば `table.update_item()` で可変メタデータ（title, authors, abstract, published_at, collected_at, collected_date, upvotes, ttl）のみ更新
- `source` は `ADD #src :s` で集合マージ（put_item 全置換ではなく値を増やすだけ）
- `score` 系の属性は **UpdateExpression に含めない** → DynamoDB は既存値を保持する
- 新規レコードは従来通り `put_item` で作成（score 系は最初から存在しない）

**コスト影響（想定）**:
- 仮に日次の真の新規論文が 30%（50件中15件）と仮定すると、Bedrock 採点対象が 50 → 15 件に削減
- 月コスト見込み: 約 250 円 → 約 75 円（年 3,050 円 → 約 900 円）
- 絶対額は小さいが、Phase 4 で abstract 拡大・配信本数増加した場合に効く

**学んだこと**:
- `put_item` は**項目を完全置換**する操作。「一部の属性だけ更新したい」ときは `update_item` を使う
- DynamoDB の StringSet 型は `update_item` の `ADD` 演算子で要素を追加できる（set union）。`put_item` で書き直す必要はない
- ステップ間で属性が増えていくスキーマ（収集 → 採点 → 配信 でフィールドが追加されるパターン）は、後段で追加された属性が前段の再実行で消えないかを必ず検証する
- 「DynamoDB Read コストを節約しよう」と get_item を省略して put_item 一発で済ませる設計は危険。本件では既に get_item で existing を読んでいたのに、なぜか put_item で全上書きしていたのが盲点だった

**検証**:
- `tests/test_collector.py::test_upsert_dynamodb_preserves_score_fields` で score/summary/delivered 系の保持を検証
- `tests/test_collector.py::test_upsert_dynamodb_updates_mutable_fields` で可変属性が新値で更新されることを検証

---

### 4.3 連日同一配信問題と未配信フィルタの追加（2026-05-11）

§4.2 の修正（既存論文 score 保持）だけだと別の問題が浮上することがレビュー中に判明。

**問題**:
- collector が既存レコードの `collected_date` を毎日「今日」に上書きしている
- `notifier.fetch_top_n` は GSI を `collected_date = 今日` で引き、score 降順で Top N を取る
- しかも `delivered_at` での除外をしていなかった
- 結果: 昨日 score=92 で配信された論文が、翌日もそのまま Top 3 に登場 → **連日まったく同じ Slack 投稿になる**
- §4.2 修正前は毎日全件再採点していたので、Claude Haiku の非決定性で偶然順位が入れ替わっていたが、§4.2 で score を保持するようになると「偶然の救済」が消えてこの問題が顕在化する

**修正方針（PR #5 内に追加コミット、案 E: 未配信フィルタ）**:
- `notifier.fetch_top_n` の GSI Query に `FilterExpression=Attr("delivered_at").not_exists()` を追加
- `Limit=n` を GSI Query 段階では指定しない（FilterExpression と組み合わせると Limit 適用後にフィルタされて N 未満になりがちなため）
- 全件 Query → Python 側で `[:n]` にスライス（1 日の収集上限が 50 件程度なので全件読みでも問題なし）

**採用しなかった選択肢**:
- 案 D（`collected_date` を初収集日のまま保持）: 「昨日トレンド入りしたが配信されなかった論文を今日再評価する」経路を失う
- 案 F（N 日の冷却期間付き再配信）: ロジックが複雑、てつてつの「一度配信したら次は外す」というシンプル方針と合わない

**学んだこと**:
- DynamoDB の Query で `FilterExpression` と `Limit` を併用する場合、`Limit` は **「フィルタ前の件数」** に適用される（フィルタ後ではない）。N 件確実に欲しいなら、Limit を広めに取るか Limit を外して Python 側で絞る
- 「日次配信」コンセプトのアプリでは、配信済みフラグでの除外は **GSI Query の段階で**やるべき。後段で気付くと修正コストが上がる
- バグ修正の副作用：1 つのバグを直すと、それまで偶然マスクされていた別のバグが顕在化することがある（put_item 全置換 → 全件再採点 → 非決定性で順位入れ替わり、という偶然の連鎖が壊れる）

**検証**:
- `tests/test_notifier.py::test_fetch_top_n_excludes_already_delivered` で配信済みが除外されることを検証
- `tests/test_notifier.py::test_fetch_top_n_returns_less_than_n_when_few_unscored_remaining` で n 未満でもエラーにならないことを検証

---

### 4.4 PR #5 デプロイ後の手動 invoke で 11 倍コスト事故（2026-05-12）

PR #5 のデプロイ後、修正効果を確認するため `aws lambda invoke` を実行したところ、**3 重実行**が発生して Bedrock コストが普段の 11 倍（$0.054 → $0.613 ≒ 約 95 円）になった。

**事故の連鎖**:
1. `aws lambda invoke` を `--cli-read-timeout 0` を付けずに実行
2. Lambda 実行時間が 4-5 分（240 件 collected が判明、後述）で AWS CLI のデフォルト read timeout 60 秒を超過
3. AWS CLI が自動リトライ（デフォルト 3 回まで）→ 1 分間隔で 3 つの Lambda 実行が並走
4. Lambda に `ReservedConcurrentExecutions` 制限がなかったので、3 つとも実行された
5. Bedrock 呼び出し: 通常 8 回 → **72 回**（3 実行 × 24 回）

**「Collected 240 papers」の真因**:
- spec.md §4.2 に「MAX_PAPERS_PER_DAY=50」と書かれていたが、`settings.py` で読み込むだけで **collector で実際に使われていなかった**
- HF Daily Papers + arXiv + HF Trending の合計 240 件がそのまま全件採点対象になっていた
- 通常日の「Collected 50 papers」は偶然そのくらいの件数だったか、HF/arXiv の返却数が日によって変動していた

**修正方針（PR #6）**:
1. **同時実行ガード**: CDK Stack の Lambda Function に `reserved_concurrent_executions=1` を追加
2. **MAX_PAPERS_PER_DAY の実装**: collector に `_select_top_papers(limit)` を追加し、upvotes 降順でソート → 先頭 `limit` 件に絞る。lambda_function.py で `collector.fetch_all(limit=settings.max_papers_per_day)` として呼ぶ
3. upvotes 降順を選んだ理由: HF Daily/Trending は upvotes が付き、arXiv 新着は 0。これで「コミュニティが注目している論文」が自動的に優先される

**運用ルール（手動 invoke のコマンド）**:
- `aws lambda invoke --cli-read-timeout 0 --cli-connect-timeout 0 --invocation-type RequestResponse ...` で同期実行
- もしくは `--invocation-type Event` で非同期（fire-and-forget）にして、CloudWatch Logs で結果確認

**学んだこと**:
- AWS CLI のデフォルト read timeout は 60 秒。長時間 Lambda を sync invoke するときは `--cli-read-timeout 0` 必須
- AWS CLI は失敗時に自動リトライする（デフォルト 3 回）。冪等性のない処理を sync invoke する場合、これが二重起動の温床になる
- Lambda の `ReservedConcurrentExecutions=1` は「最大 1 つだけ動く」物理保証。Scheduler の重複起動・CLI のリトライ・手動 invoke の重なりを **物理的に止められる**ので、冪等性が完全でない処理では設定するのが安全寄り
- spec に書いた設定値が**実装で使われているか**は別途検証が必要。「環境変数を読む」と「実際に処理に効かせる」は別

**コスト影響**:
- 今回の事故損: 約 87 円（11 倍ブレ、絶対額は小さい）
- PR #6 後の通常日コスト: 50 件採点に戻る → 月 75 円見込み（PR #5 修正後の試算と一致）

**検証**:
- `tests/test_collector.py::test_select_top_papers_sorts_by_upvotes_desc` で upvotes 降順ソートを検証
- `tests/test_collector.py::test_select_top_papers_respects_limit` で件数上限カットを検証
- `tests/test_collector.py::test_select_top_papers_with_limit_larger_than_papers_returns_all` で境界条件を検証
- `tests/test_lambda_function.py::test_handler_runs_full_pipeline` で `fetch_all(limit=50)` が渡されることを検証
- `tests/test_cdk_snapshot.py::test_lambda_function_created` で `ReservedConcurrentExecutions=1` を検証

---

---

## 9. Amazon Nova Pro へ全面切替（2026-05-16、コスト削減）

**デプロイ結果サマリ（2026-05-16）**:
- cdk deploy: 38.25 秒で UPDATE_COMPLETE。IAM::Policy と Lambda::Function のみ更新、他リソース不変
- Lambda 初回 invoke: collected=50 / scored=30 / delivered=3 / errors=[]、所要 20.8 秒
- 実行時間が Haiku 時代の 50.9 秒から 20.8 秒に半減（Nova Pro の応答が速い + scored=30 件で少なめだった効果）
- Slack に「Powered by Amazon Nova Pro」フッターで配信成功
- Bedrock 呼び出しコスト試算: 約 $0.033（scorer 3 batch + notifier 3 件）



Claude Haiku 4.5 から Amazon Nova Pro へモデル切替。スコアリング・要約とも `apac.amazon.nova-pro-v1:0`。

**判断根拠（コスト最優先）**:
- Claude Haiku 4.5: input $1.00/1M, output $5.00/1M
- Amazon Nova Pro: input $0.80/1M, output $3.20/1M（Haiku の約 1/1.5）
- てつてつ判断: 「コスト理由なので、いかなる品質議論も関係ない」
- chicken-knowledge-rag・trip-road が既に Nova Pro 採用済みで、運用知見を流用できる

**実装上の影響（重要）**:
- Anthropic SDK（`AnthropicBedrock`）は **Nova モデルを呼べない**。Nova は Anthropic 製ではないため
- 全面的に **boto3 の `bedrock-runtime.converse()` API** に書き換え
- Tool use の構造が違う:
  - Anthropic: `tools=[{name, description, input_schema}]`, `tool_choice={type, name}`
  - Converse: `toolConfig={tools: [{toolSpec: {name, description, inputSchema: {json: ...}}}], toolChoice: {tool: {name}}}`
- レスポンスパースも違う:
  - Anthropic: `response.content[i].type == "tool_use"` → `.input`
  - Converse: `response["output"]["message"]["content"][i]["toolUse"]["input"]`
- メッセージ構造も違う:
  - Anthropic: `messages=[{role, content: str}]`, `system="..."`（文字列）
  - Converse: `messages=[{role, content: [{text: "..."}]}]`, `system=[{text: "..."}]`（リスト）
- max_tokens は `inferenceConfig.maxTokens` に移動

**Inference Profile 選定**:
- `apac.amazon.nova-pro-v1:0` を採用（東京・大阪・ソウル・ムンバイ・シンガポール・シドニーへ分散）
- Anthropic 時代の `global.` 接頭辞は Nova では使えない。Nova は地域別 CRIS（`apac.` / `us.` / `eu.`）が標準

**IAM 権限（APAC CRIS の最小権限 3-Statement）**:
- ① `arn:aws:bedrock:ap-northeast-1:{account}:inference-profile/apac.amazon.nova-pro-v1:0` への InvokeModel（`aws:RequestedRegion=ap-northeast-1`）
- ② 自リージョンの FM ARN `arn:aws:bedrock:ap-northeast-1::foundation-model/amazon.nova-pro-v1:0` への InvokeModel（同条件 + `bedrock:InferenceProfileArn` 一致）
- ③ APAC 他リージョン FM ARN `arn:aws:bedrock:ap-*::foundation-model/amazon.nova-pro-v1:0` への InvokeModel（`bedrock:InferenceProfileArn` 一致のみ。クロスリージョン分散経路）

**Bedrock model access**:
- Amazon Nova Pro は **Amazon 自社モデル** のため AWS Console での利用申請は **不要**（Anthropic Claude と異なる）
- IAM 権限を付与するだけで即時利用可能

**廃止された依存**:
- `anthropic` SDK は pyproject.toml と Lambda layer の requirements.txt から削除
- これに伴い `uv.lock` も再生成

**Slack フッター文言**:
- 「Powered by Claude Haiku 4.5」→「Powered by Amazon Nova Pro」

参考: https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html

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
| cdk deploy の差分理解（Lambda Code + IAM Policy のみ更新） | 2026-05-16 | cdk diff で `[~]` がついたリソースだけが更新対象。本件では Lambda Function の Code S3Key と IAM Policy の Bedrock 3-Statement だけ。DynamoDB/Scheduler/Role 本体は無関係なので、論文データや配信スケジュールに影響なし。差分の `[+]/[-]/[~]` を読み解けるかが「本番反映前のリスク評価」の核 |
| Bedrock 課金の単位（トークン従量） | 2026-05-16 | Inference Profile はロードバランサであって課金資源ではない。請求は Foundation Model の input/output トークン量のみ。Nova Pro は $0.80/1M input、$3.20/1M output。プロファイル維持費なし、リージョン跨ぎの転送費もなし |
| cdk deploy のロールバック手順 | 2026-05-16 | CDK スタックは「コードからスタックを宣言する」モデルなので、戻したいバージョンの code を `git checkout` してから `cdk deploy` を再実行すれば前状態に巻き戻る。CloudFormation の `RollbackStack` ではなく、git の前バージョン + cdk deploy が王道。DynamoDB データは保持される |
| Bedrock model access 有効化と IAM の二段階制御 | 2026-05-06 | Bedrock は IAM の `bedrock:InvokeModel` だけでは呼べない。AWS Console の「Model access」で各 Anthropic モデルを Enable する手動操作が別途必要。IAM = 誰が呼べるか、model access = そもそも呼べるか、の二段構え |
| Bedrock 移行による認証モデルの本質変化 | 2026-05-10 | Direct API は API キーをコードと SSM の両方で守護していたが、Bedrock 経由は Lambda 実行ロールの IAM 権限のみで完結する。長期存在する機密シークレット自体をシステムから消せるのが価値（PR #3 作成直前テストで確認）|
| Global CRIS の 3-Statement IAM 設計 | 2026-05-10 | Statement ① ソース inference profile（自リージョン限定）、② 自リージョンの foundation-model（ローカル処理経路）、③ ARN リージョン部空 + `aws:RequestedRegion=unspecified` の foundation-model（他リージョンへルーティングされた経路）。③ がないと CRIS が他リージョンにルーティングしたとき AccessDeniedException で失敗する（PR #3 作成直前テストで確認）|
| DynamoDB put_item vs update_item の本質的違い | 2026-05-11 | put_item は項目を完全置換（含めない属性は消える）、update_item は UpdateExpression に書いた属性だけ触る。スキーマが増育する設計（収集→採点→配信でフィールド追加）では put_item で全上書きすると後段で追加された属性が消えるので update_item を使うべき（PR #5 作成直前テストで確認）|
| バグ修正の選択軸：最小修正範囲と伝播リスク | 2026-05-11 | 修正案を複数比較するとき、Bedrock 呼び出し数や read コストではなく「他モジュールへの伝播リスク」と「修正の局所性」を優先する。collector の修正だけで scorer/notifier の I/F を変えない案を採用することで、テスト・レビュー・回帰リスクを最小化（PR #5 作成直前テストで確認）|
| ステップ拡張スキーマの再実行安全性 | 2026-05-11 | 1レコードに対して複数のパイプラインステップが属性を追加していくスキーマ（収集→採点→配信）では、前段の再実行で後段属性が消えないかを必ずテストする。本件は「翌日の collector が score を上書き」が長期間気付かれなかった典型例（PR #5 作成直前テストで確認）|
