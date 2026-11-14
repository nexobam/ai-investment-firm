# 結合テスト仕様書（05_integration_test_spec.md）

## 1. 概要
本仕様書は、複数のモジュール間（`screener.py` → `agents.py` → `portfolio_manager.py` → `dashboard_generator.py`）のデータ受け渡しとファイル永続化連携を検証する結合テスト（`tests/test_integration.py`）のテストケースを定義する。

---

## 2. 結合テストケース一覧

| テストID | 連携対象モジュール | テスト項目 | 入力条件・モック設定 | 期待される結果（合否判定基準） |
| :--- | :--- | :--- | :--- | :--- |
| IT-01 | `screener.py` → `agents.py` | 一次スクリーニング結果からAI会議プロンプト生成＆意思決定取得 | `yf.Ticker` をモックして現金 `$330.0` で買える複数銘柄の株価・ニュースを返し、`screen_stocks()` の出力を `build_meeting_prompt()` → `run_ai_meeting()`（モック）へ渡す | 現金残高以下の銘柄から上位6銘柄が抽出され、生成されたプロンプトに候補銘柄のティッカー・RSI・セクター・ニュースが含まれ、`MeetingDecision` オブジェクトが正常に返却されること。 |
| IT-02 | `agents.py` → `portfolio_manager.py` | AIの `BUY` 決定からポートフォリオ・CSV・日次レポートの一貫更新 | `MeetingDecision(action="BUY", ticker="SCHD", shares=2, ...)` を `validate_and_execute()` → `save_portfolio()` → `append_trade_history()` → `generate_daily_report()` に連携する | `portfolio.json` の現金減算・`holdings["SCHD"]` の株数2株登録が行われ、`trade_history.csv` に `BUY` 行が追記され、`reports/YYYY-MM-DD.md` に3名のエージェント発言と執行結果が出力されること。 |
| IT-03 | `agents.py` → `portfolio_manager.py` | 違反注文（35%超過の複数株買い）時の自動フォールバック結合動作 | AIが総資産 `$330.0` に対して `$80.0` の銘柄を `shares=2`（`$160.0` = 48.5% > 35%、かつ複数株のため初期免除対象外）で `BUY` 決定したデータを連携する | `portfolio_manager` が35%上限違反を検知して `HOLD` に変更し、`portfolio.json` の現金が `$330.0` のまま維持され、`trade_history.csv` とレポートにフォールバック理由が記録されること。 |
| IT-04 | `portfolio_manager.py` → `dashboard_generator.py` | ポートフォリオ状態・会議結果・取引履歴からの `docs/index.html` 生成 | 保有株（`SCHD`, `SPYM`）・資産推移・取引履歴を持つデータと `MeetingDecision` を `generate_dashboard()` に渡す | `docs/index.html` が生成され、Tailwind CSS / Chart.js CDNタグ、総資産額、アクションバッジ（`🟢 株を購入 (BUY)` 等）、4体のAI社員コメント、SBI証券注文ガイド、保有銘柄・履歴が含まれていること。 |
| IT-05 | `agents.py` → `portfolio_manager.py` → `dashboard_generator.py` | 提案のみモード時の履歴非汚染・RPGドット絵アイコン・調子バッジ・複数銘柄提案の統合検証 | `proposal_only=True` で `additional_proposals` 付きの `MeetingDecision` を処理後、オーナーによる実売買（`record_owner_trade_report`）を1件記録して `generate_dashboard()` を実行する | 提案のみモードでは現金が減らず、ダッシュボードにはドラクエ風ドット絵SVG（`shape-rendering="crispEdges"`）、調子バッジ（`🌞 好調！`）、ローディングモーダル（`aiLoadingOverlay`）、複数提案チェックボックス（`multi-prop-check`）が出力され、履歴テーブルには提案のみ（`HOLD`）の行が表示されず実行済み取引と口座状況のみが表示されること。 |
