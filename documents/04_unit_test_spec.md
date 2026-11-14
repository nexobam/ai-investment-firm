# 単体テスト仕様書（04_unit_test_spec.md）

## 1. 概要
本仕様書は、`screener.py`, `agents.py`, `portfolio_manager.py`, `dashboard_generator.py` の各関数単体のロジックを検証する単体テスト（`tests/test_unit.py`）のテストケースを定義する。外部通信（Yahoo Finance、Gemini API）はすべてモックまたはインメモリデータを用いて高速・決定論的に検証する。

---

## 2. 単体テストケース一覧

| テストID | 対象モジュール / 関数 | テスト項目 | 入力条件・前提条件 | 期待される結果（合否判定基準） |
| :--- | :--- | :--- | :--- | :--- |
| UT-01 | `screener.py`<br/>`UNIVERSE_STOCKS` | 厳選50銘柄ユニバース定義の検証 | `UNIVERSE_STOCKS` 辞書を参照する | 登録銘柄数がちょうど `50` であり、5つの低価格ETF（`SPYM`, `SCHD`, `QQQM`, `VXUS`, `VTI`）すべてが含まれ、全銘柄に非空のセクター名が定義されていること。 |
| UT-02 | `screener.py`<br/>`flatten_yfinance_df` | MultiIndexカラムのフラット化処理 | `pd.MultiIndex.from_product([["Close", "Volume"], ["AAPL"]])` を持つDataFrameを渡す | 返却されたDataFrameの `columns` が単一階層となり、`"Close"` および `"Volume"` カラムとして直接参照できること。 |
| UT-03 | `screener.py`<br/>`calculate_rsi` / `calculate_technical_metrics` | 14日RSI・移動平均乖離率・出来高変化率・スコアの計算 | 30営業日分の株価・出来高DataFrame（下落基調の押し目データおよび上昇データ）を渡す | `rsi_14` が `0.0 <= rsi_14 <= 100.0` の範囲内で算出され、`ma5_dev_pct`, `ma25_dev_pct`, `vol_ratio`, `score` が数値として正しく返ること。25行未満のデータでは `None` を返すこと。 |
| UT-04 | `screener.py`<br/>`extract_news_titles` | 異なる辞書構造からのニュースタイトル安全抽出 | 旧形式 `{"title": "News A"}` と新形式 `{"content": {"title": "News B"}}` および空要素が混在したリストを渡す | 例外を発生させず `["News A", "News B"]` が抽出されること。 |
| UT-05 | `portfolio_manager.py`<br/>`load_or_init_portfolio` | 初回起動時の初期資金 `$330.0` と初月二重入金防止 | 未作成の `portfolio.json` パスと実行日 `"2026-11-14"` を渡して初期化後、同月 `"2026-11-20"` で `apply_monthly_deposit` を呼ぶ | 初期 `cash` が `330.0`、`last_deposit_month` が `"2026-11"` となり、同月内の `apply_monthly_deposit` では入金が行われず（`deposited=False`）、`cash` が `330.0` のままであること。 |
| UT-06 | `portfolio_manager.py`<br/>`apply_monthly_deposit` | 翌月初回実行時の `+$100.0` 自動積立と二重加算防止 | `last_deposit_month="2026-11"`, `cash=330.0` の状態で `"2026-12-01"` を渡して実行し、続けて `"2026-12-02"` でもう一度実行する | 1回目の実行で `cash` が `430.0`, `total_deposited` が `430.0`, `last_deposit_month` が `"2026-12"` に更新され、2回目の同月実行では加算されないこと。 |
| UT-07 | `portfolio_manager.py`<br/>`validate_and_execute` | 1株単位（整数株）チェックと残高不足チェック | ① `shares=0` または負数の `BUY` 決定<br/>② `cash=50.0` で株価 `$60.0` の銘柄を1株 `BUY` する決定 | いずれも物理バリデーションにより拒否され、安全に `action="HOLD"`, `shares=0` にフォールバックし、現金残高が減らないこと。 |
| UT-08 | `portfolio_manager.py`<br/>`validate_and_execute` | 35%上限ロックと「総資産$1,000未満・未保有銘柄の新規1株購入」免除特例 | ① 総資産 `$330.0`（`$1,000`未満）で未保有の `$200.0`（構成比60.6%）の銘柄を **新規に1株（`shares=1`）** 買う決定<br/>② 同条件で **2株（`shares=2`）** 買う、または既保有銘柄を35%超まで追加購入する決定<br/>③ 総資産 `$1,200.0`（`$1,000`以上）で未保有の `$500.0`（構成比41.6%）の銘柄を1株買う決定 | ① は初期免除特例により **BUYが許可** され約定すること。<br/>② および ③ は35%上限ロックによりブロックされ、`HOLD` にフォールバックすること。 |
| UT-09 | `portfolio_manager.py`<br/>`validate_and_execute` | 空売り防止・保有株数超過売却のブロック | 未保有銘柄の `SELL` 決定、および保有1株に対して `shares=2` の `SELL` 決定を渡す | いずれもブロックされて `HOLD` にフォールバックし、保有株数がマイナスにならないこと。 |
| UT-10 | `agents.py`<br/>`run_ai_meeting` | APIキー未設定時のモック応答と `google-genai` 呼び出し | ① `GEMINI_API_KEY=""` の状態で呼び出す<br/>② `genai.Client` をモックしてJSON応答を返させる | ① API通信を行わず `action="HOLD"` の `MeetingDecision` が返ること。<br/>② `gemini-2.5-flash` と `response_schema=MeetingDecision` で呼び出され、パース済みの `MeetingDecision` インスタンスが返ること。 |
