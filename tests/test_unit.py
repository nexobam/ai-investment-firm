"""
単体テストスイート（tests/test_unit.py）
04_unit_test_spec.md（UT-01 〜 UT-10）に基づき、各関数の単体ロジックを検証する。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

# プロジェクトルートをパスに追加
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents import MeetingDecision, SubOrderProposal, build_meeting_prompt, run_ai_meeting
from portfolio_manager import (
    _sanitize_csv_field,
    append_trade_history,
    apply_monthly_deposit,
    load_or_init_portfolio,
    record_owner_trade_report,
    validate_and_execute,
)
from server import MAX_BATCH_TRADES, MAX_REQUEST_BODY_BYTES, TICKER_REGEX, _is_origin_allowed
from screener import (
    LOW_COST_ETFS,
    UNIVERSE_STOCKS,
    calculate_rsi,
    calculate_technical_metrics,
    extract_news_titles,
    flatten_yfinance_df,
)


def test_ut01_universe_stocks_definition() -> None:
    """UT-01: 厳選50銘柄ユニバース定義の検証"""
    assert len(UNIVERSE_STOCKS) == 50
    for etf in ("SPYM", "SCHD", "QQQM", "VXUS", "VTI"):
        assert etf in UNIVERSE_STOCKS
        assert etf in LOW_COST_ETFS
    for ticker, sector in UNIVERSE_STOCKS.items():
        assert isinstance(ticker, str) and len(ticker) > 0
        assert isinstance(sector, str) and len(sector) > 0


def test_ut02_flatten_yfinance_df_multiindex() -> None:
    """UT-02: MultiIndexカラムのフラット化処理"""
    dates = pd.date_range("2026-10-01", periods=5, freq="B")
    arrays = [["Close", "Volume"], ["AAPL", "AAPL"]]
    multi_cols = pd.MultiIndex.from_arrays(arrays, names=["Price", "Ticker"])
    data = np.array([[150.0, 1000000], [151.0, 1100000], [152.0, 1200000], [153.0, 1300000], [154.0, 1400000]])
    df = pd.DataFrame(data, index=dates, columns=multi_cols)

    assert isinstance(df.columns, pd.MultiIndex)
    flat_df = flatten_yfinance_df(df)
    assert not isinstance(flat_df.columns, pd.MultiIndex)
    assert "Close" in flat_df.columns
    assert "Volume" in flat_df.columns
    assert float(flat_df["Close"].iloc[-1]) == 154.0


def test_ut03_calculate_rsi_and_technical_metrics() -> None:
    """UT-03: 14日RSI・移動平均乖離率・出来高変化率・スコアの計算"""
    dates = pd.date_range("2026-09-01", periods=30, freq="B")
    # 緩やかな下落（押し目）データを作成
    closes = pd.Series(np.linspace(100.0, 85.0, 30), index=dates)
    volumes = pd.Series([1_000_000] * 29 + [1_500_000], index=dates)
    df = pd.DataFrame({"Close": closes, "Volume": volumes}, index=dates)

    rsi = calculate_rsi(closes, period=14)
    assert 0.0 <= rsi <= 30.0

    metrics = calculate_technical_metrics(df)
    assert metrics is not None
    assert metrics["price"] == 85.0
    assert 0.0 <= metrics["rsi_14"] <= 100.0
    assert metrics["vol_ratio"] > 1.2
    assert metrics["score"] >= 70.0  # 売られすぎ＋出来高増加で高スコア

    # 25行未満のデータは None を返すこと
    short_df = df.iloc[:20]
    assert calculate_technical_metrics(short_df) is None


def test_ut04_extract_news_titles_various_formats() -> None:
    """UT-04: 異なる辞書構造からのニュースタイトル安全抽出"""
    raw_news = [
        {"title": "News Title Old Format"},
        {"content": {"title": "News Title Nested Format"}},
        {"content": {}},
        {},
        "invalid_entry",
        {"title": "News Title Old Format"},  # 重複タイトルは除外されること
        {"title": "Third Unique News"},
        {"title": "Fourth News Exceeding Max"},
    ]
    titles = extract_news_titles(raw_news, max_items=3)
    assert titles == [
        "News Title Old Format",
        "News Title Nested Format",
        "Third Unique News",
    ]


def test_ut05_initial_portfolio_no_double_deposit(tmp_path: Path) -> None:
    """UT-05: 初回起動時の初期資金 $330.0 と初月二重入金防止"""
    portfolio_path = tmp_path / "portfolio.json"
    portfolio = load_or_init_portfolio(portfolio_path, current_date="2026-11-14")

    assert portfolio["cash"] == 330.0
    assert portfolio["total_deposited"] == 330.0
    assert portfolio["last_deposit_month"] == "2026-11"
    assert len(portfolio["deposit_history"]) == 1

    # 同月内の再実行で +$100 が二重加算されないことを確認
    portfolio, deposited = apply_monthly_deposit(portfolio, current_date="2026-11-20")
    assert deposited is False
    assert portfolio["cash"] == 330.0
    assert portfolio["total_deposited"] == 330.0


def test_ut06_monthly_deposit_next_month(tmp_path: Path) -> None:
    """UT-06: 翌月初回実行時の +$100.0 自動積立と二重加算防止"""
    portfolio_path = tmp_path / "portfolio.json"
    portfolio = load_or_init_portfolio(portfolio_path, current_date="2026-11-14")

    # 翌月（2026-12-01）の初回実行
    portfolio, deposited1 = apply_monthly_deposit(portfolio, current_date="2026-12-01")
    assert deposited1 is True
    assert portfolio["cash"] == 430.0
    assert portfolio["total_deposited"] == 430.0
    assert portfolio["last_deposit_month"] == "2026-12"

    # 同月翌日（2026-12-02）の2回目実行では加算されないこと
    portfolio, deposited2 = apply_monthly_deposit(portfolio, current_date="2026-12-02")
    assert deposited2 is False
    assert portfolio["cash"] == 430.0
    assert portfolio["total_deposited"] == 430.0


def test_ut07_validation_integer_shares_and_insufficient_cash(tmp_path: Path) -> None:
    """UT-07: 1株単位（整数株）チェックと残高不足チェック"""
    portfolio = load_or_init_portfolio(tmp_path / "portfolio.json", current_date="2026-11-14")
    portfolio["cash"] = 50.0
    all_prices = {"SPYM": 60.0}

    # ① 株数0のBUY決定 -> HOLDへフォールバック
    dec_zero = MeetingDecision(
        action="BUY",
        ticker="SPYM",
        shares=0,
        researcher_comment="r",
        analyst_comment="a",
        manager_reason="m",
        sbi_order_guide="g",
    )
    portfolio, res1 = validate_and_execute(
        portfolio, dec_zero, all_prices, UNIVERSE_STOCKS, "2026-11-14", "2026-11-13"
    )
    assert res1["action"] == "HOLD"
    assert portfolio["cash"] == 50.0

    # ② 残高不足 ($50 < $60) のBUY決定 -> HOLDへフォールバック
    dec_over_cash = MeetingDecision(
        action="BUY",
        ticker="SPYM",
        shares=1,
        researcher_comment="r",
        analyst_comment="a",
        manager_reason="m",
        sbi_order_guide="g",
    )
    portfolio, res2 = validate_and_execute(
        portfolio, dec_over_cash, all_prices, UNIVERSE_STOCKS, "2026-11-14", "2026-11-13"
    )
    assert res2["action"] == "HOLD"
    assert portfolio["cash"] == 50.0


def test_ut08_35pct_cap_and_initial_single_share_exemption(tmp_path: Path) -> None:
    """UT-08: 35%上限ロックと「総資産$1,000未満・未保有銘柄の新規1株購入」免除特例"""
    # ケース①: 総資産$330 (<$1,000) で未保有銘柄 ($200 = 60.6% > 35%) を「新規1株」購入 -> 特例で許可
    portfolio1 = load_or_init_portfolio(tmp_path / "p1.json", current_date="2026-11-14")
    all_prices = {"QQQM": 200.0, "SPYM": 80.0}
    dec_exempt = MeetingDecision(
        action="BUY",
        ticker="QQQM",
        shares=1,
        researcher_comment="r",
        analyst_comment="a",
        manager_reason="m",
        sbi_order_guide="g",
    )
    portfolio1, res1 = validate_and_execute(
        portfolio1, dec_exempt, all_prices, UNIVERSE_STOCKS, "2026-11-14", "2026-11-13"
    )
    assert res1["action"] == "BUY"
    assert res1["shares"] == 1
    assert portfolio1["cash"] == 130.0
    assert portfolio1["holdings"]["QQQM"]["shares"] == 1

    # ケース②: 総資産$330 (<$1,000) だが 2株 ($80 * 2 = $160 = 48.5% > 35%) 購入 -> 免除対象外でブロック
    portfolio2 = load_or_init_portfolio(tmp_path / "p2.json", current_date="2026-11-14")
    dec_two_shares = MeetingDecision(
        action="BUY",
        ticker="SPYM",
        shares=2,
        researcher_comment="r",
        analyst_comment="a",
        manager_reason="m",
        sbi_order_guide="g",
    )
    portfolio2, res2 = validate_and_execute(
        portfolio2, dec_two_shares, all_prices, UNIVERSE_STOCKS, "2026-11-14", "2026-11-13"
    )
    assert res2["action"] == "HOLD"
    assert portfolio2["cash"] == 330.0

    # ケース③: 総資産$1,200 (>=$1,000) で未保有銘柄 ($500 = 41.7% > 35%) を1株購入 -> 35%ロックでブロック
    portfolio3 = load_or_init_portfolio(tmp_path / "p3.json", current_date="2026-11-14")
    portfolio3["cash"] = 1200.0
    portfolio3["total_deposited"] = 1200.0
    all_prices_high = {"MSFT": 500.0}
    dec_high_equity = MeetingDecision(
        action="BUY",
        ticker="MSFT",
        shares=1,
        researcher_comment="r",
        analyst_comment="a",
        manager_reason="m",
        sbi_order_guide="g",
    )
    portfolio3, res3 = validate_and_execute(
        portfolio3, dec_high_equity, all_prices_high, UNIVERSE_STOCKS, "2026-11-14", "2026-11-13"
    )
    assert res3["action"] == "HOLD"
    assert portfolio3["cash"] == 1200.0


def test_ut09_prevent_short_selling_and_excess_sell(tmp_path: Path) -> None:
    """UT-09: 空売り防止・保有株数超過売却のブロック"""
    portfolio = load_or_init_portfolio(tmp_path / "portfolio.json", current_date="2026-11-14")
    portfolio["holdings"]["SCHD"] = {
        "ticker": "SCHD",
        "sector": "Dividend ETF",
        "shares": 1,
        "avg_cost": 28.0,
        "current_price": 29.0,
    }
    all_prices = {"SCHD": 29.0, "AAPL": 220.0}

    # 未保有銘柄 AAPL の売却 -> HOLD
    dec_unheld = MeetingDecision(
        action="SELL",
        ticker="AAPL",
        shares=1,
        researcher_comment="r",
        analyst_comment="a",
        manager_reason="m",
        sbi_order_guide="g",
    )
    portfolio, res1 = validate_and_execute(
        portfolio, dec_unheld, all_prices, UNIVERSE_STOCKS, "2026-11-14", "2026-11-13"
    )
    assert res1["action"] == "HOLD"

    # 保有1株に対して2株の売却 -> HOLD
    dec_excess = MeetingDecision(
        action="SELL",
        ticker="SCHD",
        shares=2,
        researcher_comment="r",
        analyst_comment="a",
        manager_reason="m",
        sbi_order_guide="g",
    )
    portfolio, res2 = validate_and_execute(
        portfolio, dec_excess, all_prices, UNIVERSE_STOCKS, "2026-11-14", "2026-11-13"
    )
    assert res2["action"] == "HOLD"
    assert portfolio["holdings"]["SCHD"]["shares"] == 1


def test_ut10_run_ai_meeting_mock_and_genai_sdk() -> None:
    """UT-10: APIキー未設定時のモック応答と google-genai 呼び出し検証"""
    with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
        decision_mock = run_ai_meeting("test prompt")
        assert decision_mock.action == "HOLD"
        assert decision_mock.ticker == "NONE"
        assert decision_mock.shares == 0

    fake_json = MeetingDecision(
        action="BUY",
        ticker="SCHD",
        shares=2,
        researcher_comment="好調な配当ETFニュース",
        analyst_comment="RSIが35で押し目水準",
        manager_reason="現金残高内で2株買付を決定",
        sbi_order_guide="SBI証券でSCHDを成行2株買付",
    ).model_dump_json()

    mock_response = MagicMock()
    mock_response.text = fake_json

    with patch.dict(os.environ, {"GEMINI_API_KEY": "test_valid_key"}, clear=False):
        with patch("agents.genai.Client") as mock_client_cls:
            mock_client_instance = MagicMock()
            mock_client_instance.models.generate_content.return_value = mock_response
            mock_client_cls.return_value = mock_client_instance

            decision_real = run_ai_meeting("test prompt")
            assert decision_real.action == "BUY"
            assert decision_real.ticker == "SCHD"
            assert decision_real.shares == 2
            mock_client_instance.models.generate_content.assert_called_once()


def test_ut11_owner_instruction_and_manual_trade_report(tmp_path: Path) -> None:
    """UT-11: オーナー直接命令のプロンプト反映と手動売買・入金報告の記帳検証"""
    portfolio = load_or_init_portfolio(tmp_path / "portfolio.json", current_date="2026-11-14")
    prompt = build_meeting_prompt(
        portfolio,
        candidates=[],
        holdings_info={},
        owner_instruction="高配当ETFのSCHDを最優先で分析してください",
    )
    assert "高配当ETFのSCHDを最優先で分析してください" in prompt

    # ① オーナー買付報告 (SCHD 2株 @ $28.50 = $57.00)
    portfolio, dec_buy, res_buy = record_owner_trade_report(
        portfolio=portfolio,
        action="BUY",
        ticker="SCHD",
        shares=2,
        price=28.50,
        sector_map=UNIVERSE_STOCKS,
        current_date="2026-11-14",
        note="SBI証券NISA枠で買付",
    )
    assert res_buy["action"] == "BUY"
    assert portfolio["cash"] == 330.0 - 57.0
    assert portfolio["holdings"]["SCHD"]["shares"] == 2

    # ② オーナー売却報告 (SCHD 1株 @ $30.00)
    portfolio, dec_sell, res_sell = record_owner_trade_report(
        portfolio=portfolio,
        action="SELL",
        ticker="SCHD",
        shares=1,
        price=30.00,
        sector_map=UNIVERSE_STOCKS,
        current_date="2026-11-14",
    )
    assert res_sell["action"] == "SELL"
    assert portfolio["holdings"]["SCHD"]["shares"] == 1
    assert portfolio["cash"] == 273.0 + 30.0

    # ③ オーナー追加入金報告 (+$50.00)
    portfolio, dec_dep, res_dep = record_owner_trade_report(
        portfolio=portfolio,
        action="DEPOSIT",
        ticker="CASH",
        shares=0,
        price=50.00,
        sector_map=UNIVERSE_STOCKS,
        current_date="2026-11-14",
    )
    assert portfolio["cash"] == 353.0
    assert portfolio["total_deposited"] == 380.0


def test_ut12_csv_injection_sanitization_and_multi_proposals(tmp_path: Path) -> None:
    """UT-12: CSV数式インジェクション無害化と複数銘柄提案スキーマ（SubOrderProposal）検証"""
    # CSV Formula Injection Sanitization
    assert _sanitize_csv_field("=cmd|' /C calc'!A0") == "'=cmd|' /C calc'!A0"
    assert _sanitize_csv_field("+SUM(A1:A2)") == "'+SUM(A1:A2)"
    assert _sanitize_csv_field("-1+1") == "'-1+1"
    assert _sanitize_csv_field("@IMPORTXML()") == "'@IMPORTXML()"
    assert _sanitize_csv_field("通常のメモ\r\n改行あり") == "通常のメモ 改行あり"

    history_csv = tmp_path / "trade_history.csv"
    append_trade_history(
        execution_result={
            "date": "2026-11-14",
            "market_date": "2026-11-13",
            "action": "BUY",
            "ticker": "NVDA",
            "sector": "Technology",
            "shares": 2,
            "price": 150.0,
            "total_amount": 300.0,
            "cash_after": 30.0,
            "total_equity_after": 330.0,
            "note": "=1+1 悪意ある数式メモ",
        },
        csv_path=history_csv,
    )
    csv_text = history_csv.read_text(encoding="utf-8")
    assert "'=1+1 悪意ある数式メモ" in csv_text

    # SubOrderProposal を含む MeetingDecision の検証
    multi_dec = MeetingDecision(
        action="BUY",
        ticker="SCHD",
        shares=2,
        researcher_comment="情報屋コメント",
        analyst_comment="大賢者コメント",
        manager_reason="リーダーコメント",
        sbi_order_guide="注文ガイド",
        additional_proposals=[
            SubOrderProposal(action="BUY", ticker="SPYM", shares=1, reason="コアETFも同時買い増し"),
            SubOrderProposal(action="BUY", ticker="KHC", shares=2, reason="高配当バリュー株も分散"),
        ],
    )
    assert len(multi_dec.additional_proposals) == 2
    assert multi_dec.additional_proposals[0].ticker == "SPYM"
    assert multi_dec.additional_proposals[1].shares == 2


def test_ut13_server_security_origin_and_validation() -> None:
    """UT-13: ローカルサーバーのOrigin検証（CSRF/CORS防御）・ティッカー正規表現・上限設定の検証"""
    # 許可されるローカルOrigin
    assert _is_origin_allowed("") is True
    assert _is_origin_allowed("null") is True
    assert _is_origin_allowed("http://127.0.0.1:8000") is True
    assert _is_origin_allowed("http://localhost:8000") is True

    # 拒否される外部悪意サイトOrigin
    assert _is_origin_allowed("https://evil.example.com") is False
    assert _is_origin_allowed("http://127.0.0.1.evil.com") is False
    assert _is_origin_allowed("http://malicious.local") is False

    # ティッカー正規表現検証
    assert TICKER_REGEX.match("NVDA") is not None
    assert TICKER_REGEX.match("BRK.B") is not None
    assert TICKER_REGEX.match("<script>") is None
    assert TICKER_REGEX.match("NVDA;DROP") is None
    assert TICKER_REGEX.match("TOO_LONG_TICKER_NAME") is None

    # リクエスト上限値定数
    assert MAX_REQUEST_BODY_BYTES == 65_536
    assert MAX_BATCH_TRADES == 20


