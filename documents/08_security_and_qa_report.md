# 脆弱性診断・QA品質保証報告書（08_security_and_qa_report.md）

## 1. 概要
本ドキュメントは、「AI Investment Firm（マルチAIエージェント仮想投資会社）」システムに対して実施した**セキュリティ脆弱性診断（ソースコード監査・対策実装）**および**QA（単体・結合・シナリオ自動テスト再実施）**の結果をまとめた報告書である。

- **診断・検証実施日**: 2026-11-14
- **対象モジュール**: `main.py`, `server.py`, `screener.py`, `agents.py`, `portfolio_manager.py`, `dashboard_generator.py`, `.github/workflows/daily_meeting.yml`
- **総合判定**: **合格（検出された全リスク項目に対する防御実装完了・全19自動テストPASS）**

---

## 2. 脆弱性診断結果と実施した対策一覧

OWASP Top 10 およびローカルWebサーバー／金融データ処理アプリケーション特有の脅威モデルに基づき、以下の7項目について診断およびハードニング（堅牢化）を実施した。

| 診断ID | カテゴリ | 対象箇所 | 診断内容・潜在的リスク | 実施した対策・改修内容 | 状態 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **VULN-01** | **CORS / CSRF（クロスサイト・リクエスト・フォージェリ）** | `server.py`<br/>`DashboardRequestHandler` | ローカルサーバー（`127.0.0.1:8000`）で無制限な `Access-Control-Allow-Origin: *` を許可していると、ブラウザで悪意ある外部サイトを開いた際にバックグラウンドから `POST /api/manual_trade` 等を不正 호출されるリスクがある。 | `_is_origin_allowed()` を実装し、`Origin` ヘッダーがローカル環境（`http://127.0.0.1:*`, `http://localhost:*`, または `file://` 由来の `null` / 空文字）以外の場合は **`403 Forbidden`** で即時遮断するよう修正。 | ✅ **対策済** |
| **VULN-02** | **DoS（巨大ペイロード送信によるメモリ枯渇）** | `server.py`<br/>`_read_json_body` | `Content-Length` に上限がない場合、巨大なPOSTリクエストによりローカルサーバープロセスがメモリ枯渇を起こすリスクがある。 | `MAX_REQUEST_BODY_BYTES = 65_536`（64KB上限）を設定し、超過時は読み込む前に **`413 Payload Too Large`**、不正ヘッダー時は **`400 Bad Request`** を返すよう実装。 | ✅ **対策済** |
| **VULN-03** | **入力値汚染・インジェクション・大量バッチ送信** | `server.py`<br/>`do_POST` (`/api/manual_trade`, `/api/meeting`) | ティッカー名へのHTMLタグや特殊文字混入、または数千件の配列送信による処理遅延リスク。 | ティッカー正規表現 `TICKER_REGEX = re.compile(r"^[A-Z0-9.\-]{1,10}$")` による厳格な形式検証、1回あたりの一括取引上限 `MAX_BATCH_TRADES = 20` 件、指示文字数上限 `500文字`、メモ上限 `200文字` を実装。 | ✅ **対策済** |
| **VULN-04** | **CSV数式インジェクション（CSV Formula Injection）** | `portfolio_manager.py`<br/>`append_trade_history` | `trade_history.csv` をExcelやNumbersで開いた際、メモ欄等に `=`, `+`, `-`, `@` で始まる文字列が含まれていると数式・外部コマンドとして解釈されるリスク。 | `_sanitize_csv_field()` を実装し、先頭が `=`, `+`, `-`, `@`, `\t` の場合はシングルクォート `'` を先頭に付与して無害化し、改行コード（`\r\n`, `\r`, `\n`）をスペースへ正規化する処理を実装。 | ✅ **対策済** |
| **VULN-05** | **XSS（クロスサイト・スクリプティング：サーバー＆DOM）** | `dashboard_generator.py` | AI出力コメントやユーザー入力メモ・ティッカー名がHTML生成時やJavaScriptの `innerHTML` 更新時にエスケープされない場合、スクリプトが実行されるリスク。 | Python側では全動的テキストに `html.escape()` を適用し、フロントエンドJavaScript側でも `escapeHtmlJs()` 関数を実装して `updateLiveTradeCalc()`, `renderTradeCart()`, `showOwnerAlert()` 内の動的文字列を完全エスケープ。 | ✅ **対策済** |
| **VULN-06** | **クリックジャッキング / MIMEスニッフィング** | `server.py`<br/>`_send_cors_headers` | 外部ページの `<iframe>` への埋め込みやブラウザのMIMEタイプ誤認によるスクリプト実行リスク。 | 全HTTPレスポンスに `X-Frame-Options: DENY` および `X-Content-Type-Options: nosniff` ヘッダーを付与。 | ✅ **対策済** |
| **VULN-07** | **秘密情報（APIキー）の漏洩防止** | `.gitignore`, `agents.py`, `.github/workflows/daily_meeting.yml` | `GEMINI_API_KEY` がGitリポジトリやログに出力されるリスク。 | `.env` は `.gitignore` で追跡対象外とし、GitHub Actionsでは `${{ secrets.GEMINI_API_KEY }}` から環境変数 주입。コード内にもハードコードされたシークレットが存在しないことを確認。 | ✅ **確認済** |

---

## 3. QAテスト再実施結果（全19テストケース）

改修およびセキュリティ強化後の全コードに対して `pytest` による自動テストスイート（単体テスト13件、結合テスト5件、E2Eシナリオテスト1件の計19件）を実行し、すべてパスすることを確認した。

### 3.1 テスト実行サマリー
- **実行コマンド**: `.venv/bin/pytest -v tests`
- **実行環境**: macOS / Python 3.14.6 / pytest 9.2.0
- **結果**: **19 passed, 0 failed (所要時間: 1.40s)**

### 3.2 テストケース別合否一覧

| 区分 | テストID | テスト関数名 | 検証内容 | 結果 |
| :--- | :--- | :--- | :--- | :--- |
| **単体** | UT-01 | `test_ut01_universe_stocks_definition` | 厳選50銘柄ユニバース＋優良5ETF定義検証 | ✅ PASS |
| **単体** | UT-02 | `test_ut02_flatten_yfinance_df_multiindex` | `yfinance` MultiIndexカラムのフラット化検証 | ✅ PASS |
| **単体** | UT-03 | `test_ut03_calculate_rsi_and_technical_metrics` | 14日RSI・移動平均乖離率・出来高変化率・スコア計算検証 | ✅ PASS |
| **単体** | UT-04 | `test_ut04_extract_news_titles_various_formats` | 新旧フォーマット混在ニュースからの安全なタイトル抽出検証 | ✅ PASS |
| **単体** | UT-05 | `test_ut05_initial_portfolio_no_double_deposit` | 初回起動時の初期資金 `$330.0` と初月二重入金防止検証 | ✅ PASS |
| **単体** | UT-06 | `test_ut06_monthly_deposit_next_month` | 翌月初回実行時の `+$100.0` 自動積立と二重加算防止検証 | ✅ PASS |
| **単体** | UT-07 | `test_ut07_validation_integer_shares_and_insufficient_cash` | 整数株チェックと現金残高不足時の安全フォールバック検証 | ✅ PASS |
| **単体** | UT-08 | `test_ut08_35pct_cap_and_initial_single_share_exemption` | 35%上限ロックと総資産`$1,000`未満時の新規1株購入免除特例検証 | ✅ PASS |
| **単体** | UT-09 | `test_ut09_prevent_short_selling_and_excess_sell` | 空売り防止・保有株数超過売却のブロック検証 | ✅ PASS |
| **単体** | UT-10 | `test_ut10_run_ai_meeting_mock_and_genai_sdk` | APIキー未設定時のモック応答と `google-genai` 呼び出し検証 | ✅ PASS |
| **単体** | UT-11 | `test_ut11_owner_instruction_and_manual_trade_report` | オーナー指示プロンプト反映と手動売買・入金報告の記帳検証 | ✅ PASS |
| **単体** | UT-12 | `test_ut12_csv_injection_sanitization_and_multi_proposals` | CSV数式インジェクション無害化と複数銘柄提案（`SubOrderProposal`）検証 | ✅ PASS |
| **単体** | UT-13 | `test_ut13_server_security_origin_and_validation` | `server.py` のOrigin検証・ティッカー正規表現・上限設定検証 | ✅ PASS |
| **結合** | IT-01 | `test_it01_screener_to_agents_prompt_and_decision` | スクリーニング結果からAI会議プロンプト生成＆意思決定取得 | ✅ PASS |
| **結合** | IT-02 | `test_it02_agents_to_portfolio_manager_buy_flow` | `BUY` 決定からポートフォリオ・CSV・日次レポートの一貫更新 | ✅ PASS |
| **結合** | IT-03 | `test_it03_agents_to_portfolio_manager_fallback_on_35pct_violation` | 35%超過違反時の `HOLD` 自動フォールバック結合動作 | ✅ PASS |
| **結合** | IT-04 | `test_it04_portfolio_to_dashboard_generator` | ポートフォリオ・会議結果・履歴からの `docs/index.html` 生成 | ✅ PASS |
| **結合** | IT-05 | `test_it05_rpg_icons_mood_and_executed_only_history` | 提案モード時の履歴非汚染・RPGドット絵アイコン・調子バッジ・複数銘柄提案の統合検証 | ✅ PASS |
| **E2E** | ST-01 | `test_st01_full_lifecycle_scenario` | 初回起動→初期特例購入→休場日スキップ→翌月積立→売却益確定の一貫シナリオ | ✅ PASS |
