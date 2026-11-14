"""
結合テストスイート（tests/test_integration.py）
05_integration_test_spec.md（IT-01 〜 IT-04）に基づき、モジュール間連携と永続化を検証する。
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents import MeetingDecision, build_meeting_prompt, run_ai_meeting
from dashboard_generator import generate_dashboard
from portfolio_manager import (
    append_trade_history,
    generate_daily_report,
    load_or_init_portfolio,
    load_trade_history,
    save_portfolio,
    validate_and_execute,
)
from screener import UNIVERSE_STOCKS, screen_stocks


def _make_mock_ticker_factory(price_map: dict[str, float], market_date: str = "2026-11-13"):
    dates = pd.bdate_range(end=market_date, periods=35)

    def _factory(ticker: str):
        mock_t = MagicMock()
        base_price = price_map.get(ticker, 50.0)
        closes = np.linspace(base_price * 1.08, base_price, len(dates))
        volumes = np.array([1_000_000] * (len(dates) - 1) + [1_400_000])
        mock_t.history.return_value = pd.DataFrame(
            {"Close": closes, "Volume": volumes}, index=dates
        )
        mock_t.news = [{"title": f"{ticker} announces solid quarterly earnings"}]
        return mock_t

    return _factory


def test_it01_screener_to_agents_prompt_and_decision(tmp_path: Path) -> None:
    """IT-01: 一次スクリーニング結果からAI会議プロンプト生成＆意思決定取得"""
    portfolio = load_or_init_portfolio(tmp_path / "portfolio.json", current_date="2026-11-14")
    price_map = {"SCHD": 28.0, "SPYM": 68.0, "INTC": 24.0, "KO": 62.0, "VZ": 40.0, "PFE": 26.0, "MSFT": 450.0}

    with patch("screener.yf.Ticker", side_effect=_make_mock_ticker_factory(price_map)):
        screen_res = screen_stocks(cash=portfolio["cash"], existing_holdings={}, top_n=6)

    candidates = screen_res["candidates"]
    assert len(candidates) == 6
    # 現金残高 $330 を超える MSFT ($450) は候補に含まれないこと
    candidate_tickers = [c["ticker"] for c in candidates]
    assert "MSFT" not in candidate_tickers

    prompt = build_meeting_prompt(portfolio, candidates, screen_res["holdings_info"])
    assert "330.00" in prompt
    assert candidates[0]["ticker"] in prompt

    with patch.dict("os.environ", {"GEMINI_API_KEY": ""}, clear=False):
        decision = run_ai_meeting(prompt)
    assert isinstance(decision, MeetingDecision)


def test_it02_agents_to_portfolio_manager_buy_flow(tmp_path: Path) -> None:
    """IT-02: AIの BUY 決定からポートフォリオ・CSV・日次レポートの一貫更新"""
    portfolio_path = tmp_path / "data" / "portfolio.json"
    csv_path = tmp_path / "data" / "trade_history.csv"
    reports_dir = tmp_path / "reports"

    portfolio = load_or_init_portfolio(portfolio_path, current_date="2026-11-14")
    all_prices = {"SCHD": 28.50, "SPYM": 68.00}
    decision = MeetingDecision(
        action="BUY",
        ticker="SCHD",
        shares=2,
        researcher_comment="SCHDは増配銘柄で構成され安定した資金流入が継続。",
        analyst_comment="14日RSIが32と押し目水準にあり反発が期待できる。",
        manager_reason="現金$330のうち$57でSCHDを2株購入し配当基盤を構築する。",
        sbi_order_guide="SBI証券アプリでSCHDを現物買・成行または指値$28.50で2株注文。",
    )

    portfolio, exec_res = validate_and_execute(
        portfolio=portfolio,
        decision=decision,
        all_prices=all_prices,
        sector_map=UNIVERSE_STOCKS,
        current_date="2026-11-14",
        market_date="2026-11-13",
    )
    save_portfolio(portfolio, portfolio_path)
    append_trade_history(exec_res, csv_path)
    report_path = generate_daily_report(portfolio, decision, exec_res, [], reports_dir)

    assert exec_res["action"] == "BUY"
    assert exec_res["ticker"] == "SCHD"
    assert exec_res["shares"] == 2
    assert portfolio["cash"] == 330.0 - 57.0
    assert portfolio["holdings"]["SCHD"]["shares"] == 2
    assert csv_path.exists()
    assert report_path.exists()
    report_text = report_path.read_text(encoding="utf-8")
    assert "SCHD" in report_text
    assert "SBI証券アプリでSCHD" in report_text


def test_it03_agents_to_portfolio_manager_fallback_on_35pct_violation(tmp_path: Path) -> None:
    """IT-03: 違反注文（35%超過の複数株買い）時の自動フォールバック結合動作"""
    portfolio_path = tmp_path / "data" / "portfolio.json"
    csv_path = tmp_path / "data" / "trade_history.csv"
    reports_dir = tmp_path / "reports"

    portfolio = load_or_init_portfolio(portfolio_path, current_date="2026-11-14")
    all_prices = {"SPYM": 80.0}
    # $80 * 2株 = $160 (総資産$330の48.5% > 35%、かつ2株なので初期1株特例の対象外)
    decision = MeetingDecision(
        action="BUY",
        ticker="SPYM",
        shares=2,
        researcher_comment="S&P500連動ETFで堅調。",
        analyst_comment="トレンド良好。",
        manager_reason="2株まとめて購入したい。",
        sbi_order_guide="SPYMを2株買付。",
    )

    portfolio, exec_res = validate_and_execute(
        portfolio=portfolio,
        decision=decision,
        all_prices=all_prices,
        sector_map=UNIVERSE_STOCKS,
        current_date="2026-11-14",
        market_date="2026-11-13",
    )
    save_portfolio(portfolio, portfolio_path)
    append_trade_history(exec_res, csv_path)
    report_path = generate_daily_report(portfolio, decision, exec_res, [], reports_dir)

    assert exec_res["action"] == "HOLD"
    assert exec_res["shares"] == 0
    assert portfolio["cash"] == 330.0
    assert "35%上限" in exec_res["note"]
    assert "35%上限ロック" in report_path.read_text(encoding="utf-8")


def test_it04_portfolio_to_dashboard_generator(tmp_path: Path) -> None:
    """IT-04: ポートフォリオ状態・会議結果・取引履歴からの docs/index.html 生成"""
    portfolio_path = tmp_path / "data" / "portfolio.json"
    csv_path = tmp_path / "data" / "trade_history.csv"
    html_path = tmp_path / "docs" / "index.html"

    portfolio = load_or_init_portfolio(portfolio_path, current_date="2026-11-14")
    all_prices = {"SCHD": 28.0}
    decision = MeetingDecision(
        action="BUY",
        ticker="SCHD",
        shares=2,
        researcher_comment="情報収集担当テストコメント",
        analyst_comment="テクニカル分析担当テストコメント",
        manager_reason="ファンドマネージャーテストコメント",
        sbi_order_guide="SBI証券テスト注文ガイド",
    )
    portfolio, exec_res = validate_and_execute(
        portfolio, decision, all_prices, UNIVERSE_STOCKS, "2026-11-14", "2026-11-13"
    )
    append_trade_history(exec_res, csv_path)
    trades = load_trade_history(csv_path)

    out_file = generate_dashboard(portfolio, decision, exec_res, trades, html_path)
    assert out_file.exists()
    html_text = out_file.read_text(encoding="utf-8")

    assert "https://cdn.tailwindcss.com" in html_text
    assert "https://cdn.jsdelivr.net/npm/chart.js" in html_text
    assert "BUY（現物買付）" in html_text
    assert "SCHD" in html_text
    assert "情報収集担当テストコメント" in html_text
    assert "テクニカル分析担当テストコメント" in html_text
    assert "ファンドマネージャーテストコメント" in html_text
    assert "SBI証券テスト注文ガイド" in html_text
