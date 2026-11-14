"""
シナリオテストスイート（tests/test_scenario.py）
06_scenario_test_spec.md（ST-01: Step 1 〜 Step 5）に基づき、
初回起動($330) → 初期特例1株購入 → 休場日スキップ＆強制実行 → 翌月+$100積立 →
同月二重入金防止 → 値上がり売却・利益確定＆HTMLダッシュボード出力のE2Eフローを検証する。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents import MeetingDecision
from main import run_daily_workflow


def _create_mock_yf_ticker(price_map: dict[str, float], market_date: str):
    dates = pd.bdate_range(end=market_date, periods=35)

    def _side_effect(ticker: str):
        m = MagicMock()
        p = price_map.get(ticker, 40.0)
        closes = np.linspace(p * 1.05, p, len(dates))
        volumes = np.array([1_000_000] * (len(dates) - 1) + [1_300_000])
        m.history.return_value = pd.DataFrame(
            {"Close": closes, "Volume": volumes}, index=dates
        )
        m.news = [{"content": {"title": f"{ticker} market update on {market_date}"}}]
        return m

    return _side_effect


def test_st01_full_lifecycle_scenario(tmp_path: Path) -> None:
    """
    ST-01: 仮想投資会社 ライフサイクル一貫運用シナリオ（Step 1 〜 Step 5）
    """
    base_dir = tmp_path / "sim_workspace"
    base_dir.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------------------
    # Step 1: 初回起動 (2026-11-14 / 取引日 2026-11-13)
    # 初期資金 $330.0。総資産 $1,000 未満の初期特例により AAPL ($150.0 = 45.5% > 35%) を新規1株購入
    # -------------------------------------------------------------------------
    prices_step1 = {"AAPL": 150.0, "SCHD": 28.0, "SPYM": 70.0}
    decision_step1 = MeetingDecision(
        action="BUY",
        ticker="AAPL",
        shares=1,
        researcher_comment="Appleの新製品需要が底堅い。",
        analyst_comment="押し目からの反発初動。",
        manager_reason="総資産$1,000未満の新規1株特例を活用してAAPLを1株購入。",
        sbi_order_guide="AAPLを現物1株成行買付。",
    )

    with patch("screener.yf.Ticker", side_effect=_create_mock_yf_ticker(prices_step1, "2026-11-13")):
        with patch("main.run_ai_meeting", return_value=decision_step1):
            res1 = run_daily_workflow(base_dir=base_dir, force=False, current_date="2026-11-14")

    assert res1["status"] == "COMPLETED"
    assert res1["deposited"] is False  # 初月は+$100重複加算なし
    assert res1["execution_result"]["action"] == "BUY"
    assert res1["execution_result"]["ticker"] == "AAPL"
    assert res1["execution_result"]["shares"] == 1
    assert res1["portfolio"]["cash"] == 180.0
    assert res1["portfolio"]["total_deposited"] == 330.0
    assert res1["portfolio"]["holdings"]["AAPL"]["shares"] == 1

    # -------------------------------------------------------------------------
    # Step 2: 休場日スキップ (2026-11-15 / 取引日 2026-11-13 で同一) & --force 強制実行
    # -------------------------------------------------------------------------
    with patch("screener.yf.Ticker", side_effect=_create_mock_yf_ticker(prices_step1, "2026-11-13")):
        with patch("main.run_ai_meeting") as mock_ai_skip:
            res2_skip = run_daily_workflow(base_dir=base_dir, force=False, current_date="2026-11-15")
            assert res2_skip["status"] == "SKIPPED"
            assert res2_skip["reason"] == "MARKET_CLOSED"
            mock_ai_skip.assert_not_called()

    # --force 指定時は同取引日でも実行され、SCHD 2株 (@$28.0 = $56.0 <= 35%) を購入
    decision_step2_force = MeetingDecision(
        action="BUY",
        ticker="SCHD",
        shares=2,
        researcher_comment="高配当ETFへの資金流入。",
        analyst_comment="RSI落ち着き、セクター分散に有効。",
        manager_reason="SCHDを2株追加購入。",
        sbi_order_guide="SCHDを現物2株買付。",
    )
    with patch("screener.yf.Ticker", side_effect=_create_mock_yf_ticker(prices_step1, "2026-11-13")):
        with patch("main.run_ai_meeting", return_value=decision_step2_force):
            res2_force = run_daily_workflow(base_dir=base_dir, force=True, current_date="2026-11-15")

    assert res2_force["status"] == "COMPLETED"
    assert res2_force["execution_result"]["action"] == "BUY"
    assert res2_force["portfolio"]["cash"] == 124.0  # 180.0 - 56.0
    assert res2_force["portfolio"]["holdings"]["SCHD"]["shares"] == 2

    # -------------------------------------------------------------------------
    # Step 3: 翌月1日の月次積立 (+$100.0) と SPYM 1株 (@$70.0) 購入
    # -------------------------------------------------------------------------
    decision_step3 = MeetingDecision(
        action="BUY",
        ticker="SPYM",
        shares=1,
        researcher_comment="米国市場全体が堅調推移。",
        analyst_comment="25日線サポート確認。",
        manager_reason="月次積立+$100を活用しSPYMを1株購入。",
        sbi_order_guide="SPYMを1株現物買付。",
    )
    with patch("screener.yf.Ticker", side_effect=_create_mock_yf_ticker(prices_step1, "2026-12-01")):
        with patch("main.run_ai_meeting", return_value=decision_step3):
            res3 = run_daily_workflow(base_dir=base_dir, force=False, current_date="2026-12-01")

    assert res3["status"] == "COMPLETED"
    assert res3["deposited"] is True
    assert res3["portfolio"]["total_deposited"] == 430.0
    assert res3["portfolio"]["last_deposit_month"] == "2026-12"
    assert res3["portfolio"]["cash"] == 154.0  # 124.0 + 100.0 - 70.0
    assert res3["portfolio"]["holdings"]["SPYM"]["shares"] == 1

    # -------------------------------------------------------------------------
    # Step 4: 同月2日目の積立二重加算防止と HOLD
    # -------------------------------------------------------------------------
    decision_step4 = MeetingDecision(
        action="HOLD",
        ticker="NONE",
        shares=0,
        researcher_comment="イベント前で様子見。",
        analyst_comment="中立水準。",
        manager_reason="本日は現金温存とする。",
        sbi_order_guide="本日の注文はありません。",
    )
    with patch("screener.yf.Ticker", side_effect=_create_mock_yf_ticker(prices_step1, "2026-12-02")):
        with patch("main.run_ai_meeting", return_value=decision_step4):
            res4 = run_daily_workflow(base_dir=base_dir, force=False, current_date="2026-12-02")

    assert res4["status"] == "COMPLETED"
    assert res4["deposited"] is False
    assert res4["portfolio"]["total_deposited"] == 430.0
    assert res4["portfolio"]["cash"] == 154.0

    # -------------------------------------------------------------------------
    # Step 5: AAPL が $150.0 -> $175.0 (+$25.0) に値上がりし、1株売却（利益確定）
    # -------------------------------------------------------------------------
    prices_step5 = {"AAPL": 175.0, "SCHD": 28.0, "SPYM": 70.0}
    decision_step5 = MeetingDecision(
        action="SELL",
        ticker="AAPL",
        shares=1,
        researcher_comment="目標株価到達に伴う利益確定局面。",
        analyst_comment="RSI上昇につき一旦利確推奨。",
        manager_reason="AAPL 1株を$175で売却し+$25の利益を確定する。",
        sbi_order_guide="SBI証券で保有中のAAPL 1株を現物成行売却。",
    )
    with patch("screener.yf.Ticker", side_effect=_create_mock_yf_ticker(prices_step5, "2026-12-03")):
        with patch("main.run_ai_meeting", return_value=decision_step5):
            res5 = run_daily_workflow(base_dir=base_dir, force=False, current_date="2026-12-03")

    assert res5["status"] == "COMPLETED"
    assert res5["execution_result"]["action"] == "SELL"
    assert res5["execution_result"]["ticker"] == "AAPL"
    assert "AAPL" not in res5["portfolio"]["holdings"]
    assert res5["portfolio"]["cash"] == 329.0  # 154.0 + 175.0
    assert res5["execution_result"]["total_equity_after"] == 455.0  # 329 + 56 + 70
    assert res5["execution_result"]["total_return"] == 25.0  # 455.0 - 430.0
    assert res5["execution_result"]["total_return_pct"] == 5.81

    # 永続化ファイルの最終確認
    saved_portfolio = json.loads((base_dir / "data" / "portfolio.json").read_text(encoding="utf-8"))
    assert saved_portfolio["cash"] == 329.0
    assert (base_dir / "data" / "trade_history.csv").exists()
    assert (base_dir / "reports" / "2026-12-03.md").exists()
    assert (base_dir / "docs" / "index.html").exists()
