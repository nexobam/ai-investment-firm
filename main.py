"""
AI Investment Firm メイン実行スクリプト
毎朝9:00（JST）の定期実行および `--force` オプションによる強制実行に対応し、
一次スクリーニング → マルチAIエージェント会議 → 物理バリデーション＆約定 →
レポート＆朝刊HTMLダッシュボード生成を一貫して行う。
"""

from __future__ import annotations

import argparse
import datetime
import logging
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from agents import build_meeting_prompt, run_ai_meeting
from dashboard_generator import generate_dashboard
from portfolio_manager import (
     append_trade_history,
    apply_monthly_deposit,
    generate_daily_report,
    load_or_init_portfolio,
    load_trade_history,
    save_portfolio,
    validate_and_execute,
)
from screener import get_latest_market_date, screen_stocks

BASE_DIR = Path(__file__).resolve().parent


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def run_daily_workflow(
    base_dir: Path = BASE_DIR,
    force: bool = False,
    current_date: str | None = None,
    owner_instruction: str = "",
    analysis_only: bool = False,
    proposal_only: bool = False,
) -> dict[str, Any]:
    """
    日次シミュレーションのフルパイプラインを実行する。
    """
    load_dotenv(base_dir / ".env")
    if current_date is None:
        # 日本時間（JST）ベースの日付を取得
        jst = datetime.timezone(datetime.timedelta(hours=9))
        current_date = datetime.datetime.now(jst).strftime("%Y-%m-%d")

    data_dir = base_dir / "data"
    reports_dir = base_dir / "reports"
    docs_dir = base_dir / "docs"

    portfolio_path = data_dir / "portfolio.json"
    trade_csv_path = data_dir / "trade_history.csv"
    dashboard_path = docs_dir / "index.html"

    # 1. ポートフォリオの読み込みまたは初期化（初期資金 $330.0）
    portfolio = load_or_init_portfolio(portfolio_path, current_date=current_date)

    # 2. 米国市場の最新取引日確認＆休場日スキップ判定
    latest_market_date = get_latest_market_date()
    prev_market_date = str(portfolio.get("last_market_date", ""))

    if not force and prev_market_date and latest_market_date == prev_market_date:
        logging.info(
            "米国市場休場日（前回取引日 %s と同一）のため処理をスキップします。(--force で強制実行可能)",
            latest_market_date,
        )
        return {
            "status": "SKIPPED",
            "reason": "MARKET_CLOSED",
            "market_date": latest_market_date,
            "portfolio": portfolio,
        }

    # 3. 月次積立判定（翌月初回稼働日のみ +$100.0、二重加算防止）
    portfolio, deposited = apply_monthly_deposit(portfolio, current_date=current_date)
    if deposited:
        logging.info("月次自動積立 (+$100.0) を反映しました。現在現金残高: $%.2f", portfolio["cash"])

    # 4. 第1段階：Python一次スクリーニング（AI使用量ゼロ）
    logging.info("第1段階：厳選50銘柄の一次スクリーニングを開始します...")
    screen_result = screen_stocks(
        cash=float(portfolio["cash"]),
        existing_holdings=portfolio.get("holdings", {}),
        top_n=6,
    )
    market_date = screen_result["latest_market_date"] or latest_market_date
    candidates = screen_result["candidates"]
    holdings_info = screen_result["holdings_info"]
    all_prices = screen_result["all_prices"]
    sector_map = screen_result["sector_map"]

    logging.info(
        "一次スクリーニング完了: 候補 %d 銘柄選出 (対象取引日: %s)",
        len(candidates),
        market_date,
    )

    # 5. 第2段階：マルチAIエージェント経営会議（1回のAPIコールで構造化JSON取得）
    logging.info("第2段階：マルチAIエージェント経営会議を開始します...")
    effective_instruction = owner_instruction.strip()
    if analysis_only:
        analysis_note = "【分析専用モード】今回は売買注文を実行せず（action='HOLD', ticker='NONE', shares=0）、候補銘柄と保有銘柄の詳細な分析コメントと今後の戦略提案のみを行ってください。"
        effective_instruction = f"{effective_instruction}\n{analysis_note}".strip()

    prompt_text = build_meeting_prompt(
        portfolio,
        candidates,
        holdings_info,
        owner_instruction=effective_instruction,
    )
    decision = run_ai_meeting(prompt_text)
    if analysis_only and decision.action.upper() != "HOLD":
        decision.sbi_order_guide = (
            f"【分析のみモード（AI推奨案: {decision.action} {decision.ticker} {decision.shares}株）】"
            f" {decision.sbi_order_guide}"
        )
        decision.action = "HOLD"
        decision.ticker = "NONE"
        decision.shares = 0

    logging.info(
        "AI会議結論: Action=%s, Ticker=%s, Shares=%d",
        decision.action,
        decision.ticker,
        decision.shares,
    )

    # 6. 執行・経理担当による物理バリデーション＆仮想約定（または提案のみ記録）
    portfolio, execution_result = validate_and_execute(
        portfolio=portfolio,
        decision=decision,
        all_prices=all_prices,
        sector_map=sector_map,
        current_date=current_date,
        market_date=market_date,
        proposal_only=proposal_only,
    )

    # 7. データ永続化（portfolio.json, trade_history.csv, reports/YYYY-MM-DD.md, docs/index.html）
    save_portfolio(portfolio, portfolio_path)
    append_trade_history(execution_result, trade_csv_path)
    report_path = generate_daily_report(
        portfolio=portfolio,
        decision=decision,
        execution_result=execution_result,
        candidates=candidates,
        reports_dir=reports_dir,
    )
    recent_trades = load_trade_history(trade_csv_path, limit=30)
    generate_dashboard(
        portfolio=portfolio,
        decision=decision,
        execution_result=execution_result,
        trade_history=recent_trades,
        output_path=dashboard_path,
    )

    logging.info(
        "日次処理完了: 最終アクション=%s (%s %d株) / 総資産=$%.2f / レポート=%s",
        execution_result["action"],
        execution_result["ticker"],
        execution_result["shares"],
        execution_result["total_equity_after"],
        report_path.name,
    )

    return {
        "status": "COMPLETED",
        "market_date": market_date,
        "deposited": deposited,
        "decision": decision,
        "execution_result": execution_result,
        "portfolio": portfolio,
        "report_path": report_path,
        "dashboard_path": dashboard_path,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AI Investment Firm - マルチAIエージェントによる米国株ペーパートレードシステム"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="休場日（前回取引日と同一）であってもスキップせず強制実行する",
    )
    parser.add_argument(
        "--instruction",
        type=str,
        default="",
        help="オーナー（社長）からAI社員への直接命令・投資方針指示",
    )
    parser.add_argument(
        "--analysis-only",
        action="store_true",
        help="売買は行わず（HOLD固定）、今すぐ最新の市場分析と会議だけを実行する",
    )
    parser.add_argument(
        "--auto-execute",
        action="store_true",
        help="提案のみで止めず、AIの決定通りに自動で仮想約定まで行う場合に指定",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    args = parse_args(argv)
    run_daily_workflow(
        base_dir=BASE_DIR,
        force=args.force or bool(args.instruction) or args.analysis_only,
        owner_instruction=args.instruction,
        analysis_only=args.analysis_only,
        proposal_only=not args.auto_execute,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
