# 詳細設計書（03_detailed_design.md）

## 1. データスキーマ定義

### 1.1 `data/portfolio.json` スキーマ
仮想口座の現在状態と履歴を保持するJSONファイル。

```json
{
  "cash": 330.0,
  "initial_capital": 330.0,
  "total_deposited": 330.0,
  "last_deposit_month": "2026-11",
  "last_market_date": "2026-11-13",
  "updated_at": "2026-11-14T09:00:00+09:00",
  "holdings": {
    "SPYM": {
      "ticker": "SPYM",
      "sector": "Broad Market ETF",
      "shares": 2,
      "avg_cost": 68.5,
      "current_price": 70.0,
      "market_value": 140.0,
      "unrealized_pnl": 3.0,
      "unrealized_pnl_pct": 2.19
    }
  },
  "deposit_history": [
    {
      "date": "2026-11-14",
      "month": "2026-11",
      "amount": 330.0,
      "type": "INITIAL",
      "note": "初回初期資金入金"
    }
  ],
  "asset_history": [
    {
      "date": "2026-11-14",
      "market_date": "2026-11-13",
      "cash": 330.0,
      "holdings_value": 0.0,
      "total_equity": 330.0,
      "total_deposited": 330.0,
      "total_return": 0.0,
      "total_return_pct": 0.0,
      "action": "HOLD",
      "ticker": "NONE"
    }
  ]
}
```

### 1.2 `data/trade_history.csv` カラム定義
UTF-8（ヘッダー付きCSV）形式で全売買および検証結果を記録する。

| カラム名 | 型 | 説明 | 例 |
| :--- | :--- | :--- | :--- |
| `date` | `str` | 実行日（`YYYY-MM-DD`） | `2026-11-14` |
| `market_date` | `str` | 対象市場取引日（`YYYY-MM-DD`） | `2026-11-13` |
| `action` | `str` | 実行アクション（`BUY`, `SELL`, `HOLD`） | `BUY` |
| `ticker` | `str` | ティッカーシンボル（HOLD時は `NONE`） | `SCHD` |
| `sector` | `str` | セクター名（HOLD時は `-`） | `Dividend ETF` |
| `shares` | `int` | 約定株数（整数、HOLD時は `0`） | `1` |
| `price` | `float` | 約定単価（USD、HOLD時は `0.0`） | `28.50` |
| `total_amount` | `float` | 約定合計金額（USD、`shares * price`） | `28.50` |
| `cash_after` | `float` | 取引後の現金残高（USD） | `301.50` |
| `total_equity_after` | `float` | 取引後の総資産額（USD） | `330.00` |
| `note` | `str` | 約定理由・フォールバック理由メモ | `AI決定通り新規1株買付執行` |

---

## 2. 監視対象ユニバース定義（厳選50銘柄）

`screener.py` 内の定数 `UNIVERSE_STOCKS`（辞書：`ticker -> sector`）として以下の計50銘柄をハードコード定義する。

1. **Technology (6銘柄)**: `AAPL`, `MSFT`, `NVDA`, `GOOGL`, `INTC`, `CSCO`
2. **Financials (5銘柄)**: `JPM`, `BAC`, `WFC`, `C`, `SOFI`
3. **Healthcare (5銘柄)**: `JNJ`, `PFE`, `MRK`, `ABBV`, `BMY`
4. **Consumer Discretionary (4銘柄)**: `AMZN`, `TSLA`, `F`, `NKE`
5. **Consumer Staples (5銘柄)**: `PG`, `KO`, `PEP`, `WMT`, `KHC`
6. **Energy (4銘柄)**: `XOM`, `CVX`, `OXY`, `SLB`
7. **Industrials (4銘柄)**: `GE`, `CAT`, `BA`, `CSX`
8. **Materials (3銘柄)**: `FCX`, `NEM`, `DOW`
9. **Utilities (3銘柄)**: `NEE`, `SO`, `AES`
10. **Real Estate (3銘柄)**: `PLD`, `O`, `VICI`
11. **Communication Services (3銘柄)**: `META`, `VZ`, `T`
12. **Low-Cost ETFs (5銘柄)**:
    - `SPYM`: `"Broad Market ETF"`
    - `SCHD`: `"Dividend ETF"`
    - `QQQM`: `"Growth/Tech ETF"`
    - `VXUS`: `"International ETF"`
    - `VTI`: `"Broad Market ETF"`

---

## 3. 各モジュールのクラス・関数詳細設計

### 3.1 `screener.py`

#### (1) `flatten_yfinance_df(df: pd.DataFrame) -> pd.DataFrame`
- **引数**: `yfinance` から取得した `DataFrame`
- **戻り値**: カラムが1階層にフラット化された `DataFrame`
- **ロジック**:
  - `isinstance(df.columns, pd.MultiIndex)` が `True` の場合、`df = df.copy()` の上で `df.columns = df.columns.get_level_values(0)` を適用する。
  - 重複カラムがある場合は先頭カラムを採用する。

#### (2) `calculate_rsi(series: pd.Series, period: int = 14) -> float`
- **引数**: 終値の `pd.Series`, 期間 `period=14`
- **戻り値**: 直近のRSI値（`0.0` 〜 `100.0` の `float`）
- **ロジック**:
  - `delta = series.diff()`
  - `gain = delta.clip(lower=0.0).rolling(window=period, min_periods=period).mean()`
  - `loss = (-delta.clip(upper=0.0)).rolling(window=period, min_periods=period).mean()`
  - `loss == 0` の場合は `100.0`（上昇もない場合は `50.0`）を返す。
  - `rs = gain / loss`, `rsi = 100.0 - (100.0 / (1.0 + rs))` の最新値を小数点第2位丸めで返す。

#### (3) `calculate_technical_metrics(df: pd.DataFrame) -> dict | None`
- **引数**: 単一銘柄の株価履歴 `DataFrame`（`Close`, `Volume` を含む）
- **戻り値**: テクニカル指標辞書（データ行数が25行未満の場合は `None`）
- **算出項目とスコア計算式**:
  - `price`: 最新終値 `float(close.iloc[-1])`
  - `rsi_14`: 14日RSI
  - `ma5`: 5日移動平均、乖離率 `ma5_dev_pct = ((price - ma5) / ma5) * 100`
  - `ma25`: 25日移動平均、乖離率 `ma25_dev_pct = ((price - ma25) / ma25) * 100`
  - `vol_ratio`: 直近出来高 / 過去20日平均出来高
  - **テクニカルスコア (`score`) 計算式（100点満点基準）**:
    - ベーススコア: `50.0`
    - **押し目買い評価**:
      - `rsi_14 <= 30`: `+25.0`（強い売られすぎ反発期待）
      - `30 < rsi_14 <= 40`: `+18.0`（押し目圏）
      - `40 < rsi_14 <= 55`: `+10.0`（健全な水準）
      - `rsi_14 >= 75`: `-15.0`（過熱警戒）
    - **トレンド初動・移動平均評価**:
      - `ma5 > ma25` かつ `-2.0 <= ma25_dev_pct <= 5.0`: `+15.0`（上昇トレンド初動）
      - `-8.0 <= ma25_dev_pct < -2.0`: `+10.0`（25日線からの押し目）
      - `ma25_dev_pct > 10.0`: `-10.0`（上方乖離しすぎ）
    - **出来高評価**:
      - `vol_ratio >= 1.2`: `+10.0`（出来高を伴う注目度上昇）
      - `1.0 <= vol_ratio < 1.2`: `+5.0`

#### (4) `extract_news_titles(raw_news: list, max_items: int = 3) -> list[str]`
- **引数**: `yf.Ticker(t).news` のリスト、最大件数
- **戻り値**: タイトル文字列のリスト
- **ロジック**:
  - 各要素 `item`（辞書）から `item.get("title") or item.get("content", {}).get("title", "")` を取得し、空文字でないものを最大 `max_items` 件返す。

#### (5) `screen_stocks(cash: float, existing_holdings: dict, top_n: int = 6) -> dict`
- **引数**: 現在の現金残高 `cash`、保有銘柄辞書 `existing_holdings`、抽出件数 `top_n=6`
- **戻り値**:
  - `latest_market_date`: 最新取引日文字列（`YYYY-MM-DD`）
  - `candidates`: 上位6銘柄のリスト（各要素に `ticker`, `sector`, `price`, `rsi_14`, `ma5_dev_pct`, `ma25_dev_pct`, `vol_ratio`, `score`, `news` を含む）
  - `holdings_info`: 保有銘柄の最新指標＋ニュース辞書
  - `all_prices`: 取得できた全銘柄の最新終値辞書 `dict[str, float]`
- **ロジック**:
  - 50銘柄（＋保有銘柄）について `yf.Ticker(t).history(period="3mo")` を取得。
  - 購入候補フィルター：`metrics["price"] <= cash` を満たす銘柄に限定。
  - セクター分散ボーナス：未保有セクターの銘柄にはスコア `+5.0`、ETFには安定性ボーナス `+3.0` を加算。
  - スコア降順でソートし、上位 `top_n`（6銘柄）を選出。
  - 選出された上位6銘柄と現在保有銘柄のみ `yf.Ticker(t).news` からニュースを取得。

---

### 3.2 `agents.py`

#### (1) `MeetingDecision(BaseModel)`
厳守仕様通りのPydanticモデル：
- `action: str` (`"BUY"`, `"SELL"`, or `"HOLD"`)
- `ticker: str` (対象ティッカー、HOLD時は `"NONE"`)
- `shares: int` (売買株数、1株単位の整数、HOLD時は `0`)
- `researcher_comment: str`
- `analyst_comment: str`
- `manager_reason: str`
- `sbi_order_guide: str`

#### (2) `build_meeting_prompt(portfolio: dict, candidates: list[dict], holdings_info: dict) -> str`
- 現在の現金残高、総資産額、保有銘柄一覧（セクター・株数・取得単価・現在値・含み損益・構成比）、スクリーニング上位6銘柄のテクニカル指標と直近ニュース、および投資ルール（現物整数株のみ、セクター分散、35%上限ルールと総資産$1,000未満時の新規1株免除ルール）を整理したプロンプト文字列を生成する。

#### (3) `run_ai_meeting(prompt_text: str) -> MeetingDecision`
- 厳守1の実装パターンに従い、`os.getenv("GEMINI_API_KEY")` を確認。未設定またはプレースホルダーの場合はモックの `MeetingDecision` を返す。
- 設定されている場合は `genai.Client(api_key=api_key)` から `gemini-2.5-flash` を呼び出し、`MeetingDecision.model_validate_json(response.text)` を返す。万一API例外が発生した場合もフォールバックの `MeetingDecision(action="HOLD", ...)` を返しバッチ停止を防ぐ。

---

### 3.3 `portfolio_manager.py`

#### (1) `load_or_init_portfolio(portfolio_path: Path, current_date: str) -> dict`
- `portfolio.json` が存在すれば読み込んで返す。
- 存在しない場合は初期現金 `cash = 330.0`, `initial_capital = 330.0`, `total_deposited = 330.0`, `last_deposit_month = current_date[:7]` (`YYYY-MM`) として初期化し、`deposit_history` に初回入金 `$330.0` を記録して保存・返却する（**初月は `+$100.0` の重複加算を行わない**）。

#### (2) `apply_monthly_deposit(portfolio: dict, current_date: str) -> tuple[dict, bool]`
- `current_month = current_date[:7]` と `portfolio["last_deposit_month"]` を比較する。
- 異なる場合のみ：`portfolio["cash"] += 100.0`, `portfolio["total_deposited"] += 100.0`, `portfolio["last_deposit_month"] = current_month` とし、`deposit_history` に `amount: 100.0, type: "MONTHLY"` を追記して `(portfolio, True)` を返す。
- 同じ月の場合は何も加算せず `(portfolio, False)` を返す。

#### (3) `validate_and_execute(portfolio: dict, decision: MeetingDecision, all_prices: dict[str, float], sector_map: dict[str, str], current_date: str, market_date: str) -> tuple[dict, dict]`
- **ステップ1：保有株の最新時価評価更新**
  - 保有銘柄の `current_price` を `all_prices` で更新し、`holdings_value` と `total_equity = cash + holdings_value` を算出する。
- **ステップ2：AI決定の物理バリデーション**
  - `action = decision.action.upper().strip()`
  - `shares` が整数でない、または `action in ("BUY", "SELL")` で `shares < 1` の場合 → `HOLD` に強制変更。
  - **`BUY` の場合**:
    1. 対象 `ticker` の現在株価 `price` が取得できない、または `price <= 0` → `HOLD` に変更。
    2. 必要資金 `cost = price * shares` が `portfolio["cash"]` を超える（残高不足） → `HOLD` に変更。
    3. **35%上限ロック判定（初期デッドロック回避特例付き）**:
       - 既存保有株数 `existing_shares = holdings.get(ticker, {}).get("shares", 0)`
       - 購入後評価額 `post_buy_value = (existing_shares + shares) * price`
       - 上限閾値 `limit_value = total_equity * 0.35`
       - **初期免除条件**: `total_equity < 1000.0` かつ `existing_shares == 0`（未保有銘柄）かつ `shares == 1`（新規1株のみ）かつ `cost <= portfolio["cash"]`
       - `post_buy_value > limit_value` であり、かつ初期免除条件を満たさない場合 → 35%上限ロック違反としてブロックし、`HOLD` に変更。
  - **`SELL` の場合**:
    1. 対象 `ticker` を保有していない、または `shares > existing_shares`（空売り・過大売却防止） → `HOLD` に変更。
- **ステップ3：約定計算とポートフォリオ更新**
  - `BUY` 約定時：現金から `cost` を減算し、`holdings[ticker]` の株数・平均取得単価（加重平均）を更新。
  - `SELL` 約定時：現金に売却代金 `proceeds = price * shares` を加算し、保有株数を減算（0株になった場合は `holdings` から削除）。
  - `asset_history` に当日のスナップショットを追加（同日の記録がすでにあれば上書き更新）。
  - 執行担当コメント `accountant_comment` を含む `execution_result` 辞書を返す。

---

### 3.4 `dashboard_generator.py`
- `generate_dashboard(portfolio: dict, decision: MeetingDecision, execution_result: dict, trade_history: list[dict], output_path: Path) -> Path`
- Tailwind CSS（CDN: `https://cdn.tailwindcss.com`）および Chart.js（CDN: `https://cdn.jsdelivr.net/npm/chart.js`）を読み込むHTML5ドキュメントを生成。
- XSS対策および表示崩れ防止のため、文字列は `html.escape()` でエスケープし、Chart.js用のデータは `json.dumps()` で安全に埋め込む。
