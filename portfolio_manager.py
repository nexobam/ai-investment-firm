"""
仮想口座の残高計算・月次積立・物理バリデーション・1株単位の仮想約定・
CSV/JSON保存・日次Markdownレポート出力を担う執行・経理担当モジュール。
"""

from __future__ import annotations

import csv
import datetime
import json
import logging
from pathlib import Path
from typing import Any

from agents import MeetingDecision

logger = logging.getLogger(__name__)

INITIAL_CAPITAL_USD: float = 330.0
MONTHLY_DEPOSIT_USD: float = 100.0
MAX_SINGLE_STOCK_RATIO: float = 0.35
INITIAL_EXEMPTION_EQUITY_THRESHOLD: float = 1000.0

TRADE_HISTORY_COLUMNS: list[str] = [
    "date",
    "market_date",
    "action",
    "ticker",
    "sector",
    "shares",
    "price",
    "total_amount",
    "cash_after",
    "total_equity_after",
    "note",
]


def load_or_init_portfolio(portfolio_path: Path, current_date: str | None = None) -> dict[str, Any]:
    """
    portfolio.jsonを読み込む。存在しない場合は初期資金$330.0で新規作成する。
    初月は初期資金$330.0のみとし、+$100.0の重複加算を防ぐため last_deposit_month に当月を記録する。
    """
    if current_date is None:
        current_date = datetime.date.today().strftime("%Y-%m-%d")
    current_month = current_date[:7]

    if portfolio_path.exists():
        try:
            with portfolio_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "cash" in data:
                return data
        except Exception as exc:
            logger.warning("portfolio.jsonの読み込みに失敗したため再初期化します: %s", exc)

    now_iso = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat(timespec="seconds")
    portfolio: dict[str, Any] = {
        "cash": INITIAL_CAPITAL_USD,
        "initial_capital": INITIAL_CAPITAL_USD,
        "total_deposited": INITIAL_CAPITAL_USD,
        "last_deposit_month": current_month,
        "last_market_date": "",
        "updated_at": now_iso,
        "holdings": {},
        "deposit_history": [
            {
                "date": current_date,
                "month": current_month,
                "amount": INITIAL_CAPITAL_USD,
                "type": "INITIAL",
                "note": "初回初期資金入金 ($330.0)",
            }
        ],
        "asset_history": [],
    }
    save_portfolio(portfolio, portfolio_path)
    return portfolio


def save_portfolio(portfolio: dict[str, Any], portfolio_path: Path) -> None:
    """
    ポートフォリオ辞書をJSONファイルに整形保存する。
    """
    portfolio_path.parent.mkdir(parents=True, exist_ok=True)
    with portfolio_path.open("w", encoding="utf-8") as f:
        json.dump(portfolio, f, ensure_ascii=False, indent=2)


def apply_monthly_deposit(portfolio: dict[str, Any], current_date: str) -> tuple[dict[str, Any], bool]:
    """
    実行日の年月（YYYY-MM）が last_deposit_month と異なる場合（毎月の初回稼働日）、
    現金残高に +$100.0 を自動加算し、last_deposit_month を当月に更新する。
    """
    current_month = current_date[:7]
    last_month = str(portfolio.get("last_deposit_month", ""))

    if not last_month:
        portfolio["last_deposit_month"] = current_month
        return portfolio, False

    if current_month != last_month:
        portfolio["cash"] = round(float(portfolio.get("cash", 0.0)) + MONTHLY_DEPOSIT_USD, 2)
        portfolio["total_deposited"] = round(
            float(portfolio.get("total_deposited", INITIAL_CAPITAL_USD)) + MONTHLY_DEPOSIT_USD,
            2,
        )
        portfolio["last_deposit_month"] = current_month
        deposit_history = portfolio.setdefault("deposit_history", [])
        deposit_history.append(
            {
                "date": current_date,
                "month": current_month,
                "amount": MONTHLY_DEPOSIT_USD,
                "type": "MONTHLY",
                "note": f"{current_month} 月次自動積立 (+$100.0)",
            }
        )
        logger.info("月次積立を実行しました (%s): +$%.2f", current_month, MONTHLY_DEPOSIT_USD)
        return portfolio, True

    return portfolio, False


def update_holdings_valuation(
    portfolio: dict[str, Any],
    all_prices: dict[str, float],
    sector_map: dict[str, str] | None = None,
) -> float:
    """
    保有銘柄の現在株価・時価評価額・含み損益を最新化し、保有株評価額合計を返す。
    """
    sector_map = sector_map or {}
    holdings = portfolio.get("holdings", {})
    total_holdings_value = 0.0

    for ticker, item in list(holdings.items()):
        shares = int(item.get("shares", 0))
        if shares <= 0:
            del holdings[ticker]
            continue
        avg_cost = float(item.get("avg_cost", 0.0))
        current_price = round(float(all_prices.get(ticker, item.get("current_price", avg_cost))), 2)
        market_value = round(shares * current_price, 2)
        cost_basis = round(shares * avg_cost, 2)
        unrealized_pnl = round(market_value - cost_basis, 2)
        unrealized_pnl_pct = (
            round((unrealized_pnl / cost_basis) * 100.0, 2) if cost_basis > 0 else 0.0
        )

        item["ticker"] = ticker
        item["sector"] = item.get("sector") or sector_map.get(ticker, "Other")
        item["shares"] = shares
        item["avg_cost"] = round(avg_cost, 2)
        item["current_price"] = current_price
        item["market_value"] = market_value
        item["unrealized_pnl"] = unrealized_pnl
        item["unrealized_pnl_pct"] = unrealized_pnl_pct
        total_holdings_value += market_value

    return round(total_holdings_value, 2)


def validate_and_execute(
    portfolio: dict[str, Any],
    decision: MeetingDecision,
    all_prices: dict[str, float],
    sector_map: dict[str, str],
    current_date: str,
    market_date: str,
    proposal_only: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    ファンドマネージャーの決定に対して物理バリデーションを実行し、
    違反時は安全に HOLD へフォールバックさせる。
    proposal_only=True の場合は口座残高を勝手に動かさず「社長の決定待ち（提案状態）」として記録する。
    """
    holdings_value_before = update_holdings_valuation(portfolio, all_prices, sector_map)
    cash_before = round(float(portfolio.get("cash", 0.0)), 2)
    total_equity_before = round(cash_before + holdings_value_before, 2)

    raw_action = (decision.action or "HOLD").upper().strip()
    raw_ticker = (decision.ticker or "NONE").upper().strip()
    raw_shares = decision.shares

    final_action = "HOLD"
    final_ticker = "NONE"
    final_shares = 0
    executed_price = 0.0
    total_amount = 0.0
    sector = "-"
    proposal_price = 0.0
    proposal_sector = "-"
    is_proposal_pending = False
    validation_note = "AI決定通り現金温存（HOLD）"
    accountant_comment = ""

    holdings: dict[str, dict[str, Any]] = portfolio.setdefault("holdings", {})

    # 1株単位の整数チェック
    if not isinstance(raw_shares, int) or isinstance(raw_shares, bool):
        validation_note = "株数が整数でないためHOLDへフォールバック"
        accountant_comment = f"【物理検証NG】指定株数（{raw_shares}）が1株単位の整数ではないため注文をブロックし、HOLD（現金温存）としました。"
    elif raw_action == "BUY":
        if raw_shares < 1 or raw_ticker in ("", "NONE"):
            validation_note = "BUY指定のティッカーまたは株数が無効なためHOLDへフォールバック"
            accountant_comment = "【物理検証NG】買い注文のティッカーまたは株数（1株以上必須）が不正なため、HOLDに変更しました。"
        else:
            price = round(float(all_prices.get(raw_ticker, 0.0)), 2)
            if price <= 0.0:
                validation_note = f"{raw_ticker}の有効な株価が取得できないためHOLDへフォールバック"
                accountant_comment = f"【物理検証NG】{raw_ticker} の確定終値が取得できないため、安全のためHOLDに変更しました。"
            else:
                cost = round(price * raw_shares, 2)
                existing_holding = holdings.get(raw_ticker, {})
                existing_shares = int(existing_holding.get("shares", 0))
                post_buy_value = round((existing_shares + raw_shares) * price, 2)
                max_allowed_value = round(total_equity_before * MAX_SINGLE_STOCK_RATIO, 2)

                # 初期デッドロック回避特例：総資産$1,000未満 かつ 未保有銘柄 かつ 新規1株のみ購入
                is_initial_single_share_exempt = (
                    total_equity_before < INITIAL_EXEMPTION_EQUITY_THRESHOLD
                    and existing_shares == 0
                    and raw_shares == 1
                )

                if cost > cash_before:
                    validation_note = (
                        f"現金残高不足のためHOLDへフォールバック (必要額 ${cost:.2f} > 残高 ${cash_before:.2f})"
                    )
                    accountant_comment = (
                        f"【物理検証NG：残高不足】{raw_ticker} {raw_shares}株の購入には ${cost:.2f} 必要ですが、"
                        f"現金残高（${cash_before:.2f}）を超えるためブロックし、HOLDとしました。"
                    )
                elif post_buy_value > max_allowed_value and not is_initial_single_share_exempt:
                    validation_note = (
                        f"1銘柄35%上限超過のためHOLDへフォールバック "
                        f"(購入後評価額 ${post_buy_value:.2f} > 上限 ${max_allowed_value:.2f})"
                    )
                    accountant_comment = (
                        f"【物理検証NG：35%上限ロック】{raw_ticker} 購入後の評価額（${post_buy_value:.2f}）が"
                        f"総資産（${total_equity_before:.2f}）の35%上限（${max_allowed_value:.2f}）を超過するため"
                        "追加購入をブロックし、HOLDとしました。"
                    )
                elif proposal_only:
                    # 提案のみモード：社長が決定ボタンを押すまで口座残高は動かさない
                    is_proposal_pending = True
                    proposal_price = price
                    proposal_sector = sector_map.get(raw_ticker, existing_holding.get("sector", "Other"))
                    sector = proposal_sector
                    executed_price = price
                    validation_note = (
                        f"【社長の決定待ち】AI提案: {raw_ticker} {raw_shares}株 @ ${price:.2f}（合計 ${cost:.2f}）の買付方針を提案"
                    )
                    accountant_comment = (
                        f"【資金・ルール検証OK（社長の最終決定待ち）】{raw_ticker} {raw_shares}株 @ ${price:.2f}"
                        f"（合計 ${cost:.2f}）は現金残高（${cash_before:.2f}）およびリスク管理ルールをクリアしています。\n"
                        "AI会議では「方針の提案」までを行い、まだ口座の現金は動かしていません。"
                        "実際に購入される場合は、上の「✅ このAI提案通りに決定する」ボタンを押してください。"
                    )
                else:
                    # BUY 約定成立
                    final_action = "BUY"
                    final_ticker = raw_ticker
                    final_shares = raw_shares
                    executed_price = price
                    total_amount = cost
                    sector = sector_map.get(final_ticker, existing_holding.get("sector", "Other"))

                    portfolio["cash"] = round(cash_before - cost, 2)
                    prev_cost_total = float(existing_holding.get("avg_cost", 0.0)) * existing_shares
                    new_total_shares = existing_shares + final_shares
                    new_avg_cost = round((prev_cost_total + cost) / new_total_shares, 2)

                    holdings[final_ticker] = {
                        "ticker": final_ticker,
                        "sector": sector,
                        "shares": new_total_shares,
                        "avg_cost": new_avg_cost,
                        "current_price": executed_price,
                        "market_value": round(new_total_shares * executed_price, 2),
                        "unrealized_pnl": round((executed_price - new_avg_cost) * new_total_shares, 2),
                        "unrealized_pnl_pct": round(
                            ((executed_price - new_avg_cost) / new_avg_cost) * 100.0, 2
                        )
                        if new_avg_cost > 0
                        else 0.0,
                    }
                    all_prices[final_ticker] = executed_price

                    if is_initial_single_share_exempt and post_buy_value > max_allowed_value:
                        validation_note = (
                            f"初期特例（総資産$1,000未満・未保有新規1株）適用により {final_ticker} 1株を買付約定"
                        )
                        accountant_comment = (
                            f"【約定完了（初期特例適用）】総資産 ${total_equity_before:.2f}（$1,000未満）における"
                            f"未保有銘柄の新規1株購入特例を適用し、{final_ticker} を 1株 @ ${executed_price:.2f}"
                            f"（合計 ${total_amount:.2f}）で買付執行しました。"
                        )
                    else:
                        validation_note = f"{final_ticker} {final_shares}株 @ ${executed_price:.2f} 買付約定"
                        accountant_comment = (
                            f"【約定完了】現金残高・1株整数条件・35%上限ルール（上限 ${max_allowed_value:.2f}）の"
                            f"すべてをクリアしたため、{final_ticker} {final_shares}株 @ ${executed_price:.2f}"
                            f"（合計 ${total_amount:.2f}）を買付執行しました。"
                        )

    elif raw_action == "SELL":
        existing_holding = holdings.get(raw_ticker)
        existing_shares = int(existing_holding.get("shares", 0)) if existing_holding else 0
        if raw_shares < 1 or raw_ticker in ("", "NONE") or existing_shares <= 0:
            validation_note = f"未保有銘柄({raw_ticker})の売却指示のためHOLDへフォールバック"
            accountant_comment = (
                f"【物理検証NG：空売り防止】{raw_ticker} は現在保有していないため売却注文をブロックし、HOLDとしました。"
            )
        elif raw_shares > existing_shares:
            validation_note = (
                f"保有株数超過の売却指示のためHOLDへフォールバック (指示 {raw_shares}株 > 保有 {existing_shares}株)"
            )
            accountant_comment = (
                f"【物理検証NG：売却数量超過】{raw_ticker} の売却指示（{raw_shares}株）が現在保有株数（{existing_shares}株）"
                "を超えているためブロックし、HOLDとしました。"
            )
        else:
            price = round(
                float(all_prices.get(raw_ticker, existing_holding.get("current_price", existing_holding.get("avg_cost", 0.0)))),
                2,
            )
            if price <= 0.0:
                validation_note = f"{raw_ticker}の有効な売却株価が取得できないためHOLDへフォールバック"
                accountant_comment = f"【物理検証NG】{raw_ticker} の現在株価が取得できないため売却を見送り、HOLDとしました。"
            elif proposal_only:
                is_proposal_pending = True
                proposal_price = price
                proposal_sector = existing_holding.get("sector", sector_map.get(raw_ticker, "Other"))
                sector = proposal_sector
                executed_price = price
                proceeds = round(price * raw_shares, 2)
                validation_note = (
                    f"【社長の決定待ち】AI提案: {raw_ticker} {raw_shares}株 @ ${price:.2f}（受取目安 ${proceeds:.2f}）の売却方針を提案"
                )
                accountant_comment = (
                    f"【保有株チェックOK（社長の最終決定待ち）】保有中の {raw_ticker} {raw_shares}株 @ ${price:.2f}"
                    f"（受取額目安 ${proceeds:.2f}）の売却提案です。\n"
                    "AI会議では「方針の提案」までを行い、まだ保有株は売却していません。"
                    "実際に売却される場合は、上の「✅ このAI提案通りに決定する」ボタンを押してください。"
                )
            else:
                # SELL 約定成立
                final_action = "SELL"
                final_ticker = raw_ticker
                final_shares = raw_shares
                executed_price = price
                total_amount = round(price * final_shares, 2)
                sector = existing_holding.get("sector", sector_map.get(final_ticker, "Other"))
                avg_cost = float(existing_holding.get("avg_cost", price))
                realized_pnl = round((executed_price - avg_cost) * final_shares, 2)

                portfolio["cash"] = round(cash_before + total_amount, 2)
                remaining_shares = existing_shares - final_shares
                if remaining_shares <= 0:
                    del holdings[final_ticker]
                else:
                    existing_holding["shares"] = remaining_shares
                    existing_holding["current_price"] = executed_price
                    existing_holding["market_value"] = round(remaining_shares * executed_price, 2)
                    existing_holding["unrealized_pnl"] = round(
                        (executed_price - avg_cost) * remaining_shares, 2
                    )

                validation_note = (
                    f"{final_ticker} {final_shares}株 @ ${executed_price:.2f} 売却約定 (実現損益 ${realized_pnl:+.2f})"
                )
                accountant_comment = (
                    f"【売却約定完了】保有株数チェックをクリアし、{final_ticker} {final_shares}株 @ ${executed_price:.2f}"
                    f"（受取額 ${total_amount:.2f} / 実現損益 ${realized_pnl:+.2f}）を売却執行しました。"
                )
    else:
        validation_note = "AI決定通り現金温存（HOLD）"
        accountant_comment = (
            f"【現金温存（HOLD）】ファンドマネージャーの決定通り本日の売買は見送り、"
            f"現金残高 ${cash_before:.2f} を温存しました。"
        )

    # 約定後の時価評価・資産推移更新
    holdings_value_after = update_holdings_valuation(portfolio, all_prices, sector_map)
    cash_after = round(float(portfolio.get("cash", 0.0)), 2)
    total_equity_after = round(cash_after + holdings_value_after, 2)
    total_deposited = round(float(portfolio.get("total_deposited", INITIAL_CAPITAL_USD)), 2)
    total_return = round(total_equity_after - total_deposited, 2)
    total_return_pct = (
        round((total_return / total_deposited) * 100.0, 2) if total_deposited > 0 else 0.0
    )

    now_iso = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat(timespec="seconds")
    portfolio["last_market_date"] = market_date
    portfolio["updated_at"] = now_iso

    snapshot = {
        "date": current_date,
        "market_date": market_date,
        "cash": cash_after,
        "holdings_value": holdings_value_after,
        "total_equity": total_equity_after,
        "total_deposited": total_deposited,
        "total_return": total_return,
        "total_return_pct": total_return_pct,
        "action": final_action,
        "ticker": final_ticker,
    }
    asset_history: list[dict[str, Any]] = portfolio.setdefault("asset_history", [])
    if asset_history and asset_history[-1].get("date") == current_date:
        asset_history[-1] = snapshot
    else:
        asset_history.append(snapshot)

    # もし物理バリデーションでNGとなった場合は提案フラグを下げてdecisionもHOLDに揃える
    if proposal_only and not is_proposal_pending and raw_action in ("BUY", "SELL"):
        decision.action = "HOLD"
        decision.ticker = "NONE"
        decision.shares = 0

    execution_result = {
        "date": current_date,
        "market_date": market_date,
        "requested_action": raw_action,
        "requested_ticker": raw_ticker,
        "requested_shares": raw_shares,
        "is_proposal_only": is_proposal_pending,
        "proposal_price": proposal_price,
        "proposal_sector": proposal_sector,
        "action": final_action,
        "ticker": final_ticker,
        "sector": sector,
        "shares": final_shares,
        "price": executed_price,
        "total_amount": total_amount,
        "cash_after": cash_after,
        "holdings_value_after": holdings_value_after,
        "total_equity_after": total_equity_after,
        "total_deposited": total_deposited,
        "total_return": total_return,
        "total_return_pct": total_return_pct,
        "note": validation_note,
        "accountant_comment": accountant_comment,
    }
    return portfolio, execution_result


def _sanitize_csv_field(value: Any) -> str:
    """
    CSV数式インジェクション（= / + / - / @ 始まり）および改行混入を防止するサニタイズ関数。
    """
    text = (
        str(value if value is not None else "")
        .replace("\r\n", " ")
        .replace("\r", " ")
        .replace("\n", " ")
        .strip()
    )
    if text and text[0] in ("=", "+", "-", "@", "\t"):
        return f"'{text}"
    return text


def append_trade_history(execution_result: dict[str, Any], csv_path: Path) -> None:
    """
    trade_history.csv に当日の約定・判定結果を1行追記する。
    """
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = csv_path.exists() and csv_path.stat().st_size > 0

    row = {
        "date": _sanitize_csv_field(execution_result["date"]),
        "market_date": _sanitize_csv_field(execution_result["market_date"]),
        "action": _sanitize_csv_field(execution_result["action"]),
        "ticker": _sanitize_csv_field(execution_result["ticker"]),
        "sector": _sanitize_csv_field(execution_result["sector"]),
        "shares": execution_result["shares"],
        "price": f"{execution_result['price']:.2f}",
        "total_amount": f"{execution_result['total_amount']:.2f}",
        "cash_after": f"{execution_result['cash_after']:.2f}",
        "total_equity_after": f"{execution_result['total_equity_after']:.2f}",
        "note": _sanitize_csv_field(execution_result["note"]),
    }

    with csv_path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TRADE_HISTORY_COLUMNS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def load_trade_history(csv_path: Path, limit: int = 30) -> list[dict[str, str]]:
    """
    trade_history.csv から直近の取引履歴を読み込む（新しい順）。
    """
    if not csv_path.exists():
        return []
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    return list(reversed(rows[-limit:]))


def generate_daily_report(
    portfolio: dict[str, Any],
    decision: MeetingDecision,
    execution_result: dict[str, Any],
    candidates: list[dict[str, Any]],
    reports_dir: Path,
) -> Path:
    """
    毎朝のAIエージェント経営会議レポートを reports/YYYY-MM-DD.md に出力する。
    """
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_date = execution_result["date"]
    report_path = reports_dir / f"{report_date}.md"

    holdings = portfolio.get("holdings", {})
    holdings_lines = []
    if holdings:
        holdings_lines.append("| ティッカー | セクター | 保有株数 | 平均取得単価 | 現在株価 | 評価額 | 評価損益 |")
        holdings_lines.append("| :--- | :--- | :---: | :---: | :---: | :---: | :---: |")
        for t, h in holdings.items():
            holdings_lines.append(
                f"| **{t}** | {h['sector']} | {h['shares']}株 | ${h['avg_cost']:.2f} | "
                f"${h['current_price']:.2f} | ${h['market_value']:.2f} | "
                f"${h['unrealized_pnl']:+.2f} ({h['unrealized_pnl_pct']:+.2f}%) |"
            )
    else:
        holdings_lines.append("現在保有している銘柄はありません（キャッシュ100%）。")

    candidate_lines = []
    if candidates:
        candidate_lines.append("| 順位 | ティッカー | セクター | 株価 | 14日RSI | 25日線乖離率 | 出来高倍率 | スコア |")
        candidate_lines.append("| :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: |")
        for idx, c in enumerate(candidates, start=1):
            candidate_lines.append(
                f"| {idx} | **{c['ticker']}** | {c['sector']} | ${c['price']:.2f} | "
                f"{c['rsi_14']:.1f} | {c['ma25_dev_pct']:+.2f}% | {c['vol_ratio']:.2f}x | {c['score']:.1f} |"
            )
    else:
        candidate_lines.append("現在の現金残高で購入可能な候補銘柄はありません。")

    content = f"""# AI Investment Firm 朝刊経営会議レポート ({report_date})

- **対象米国市場取引日**: `{execution_result['market_date']}`
- **最終更新日時**: `{portfolio.get('updated_at', '')}`

---

## 1. 本日の最終投資決定・執行サマリー

- **最終執行アクション**: **{execution_result['action']}** （AI提案: `{execution_result['requested_action']}`）
- **対象銘柄（ティッカー）**: `{execution_result['ticker']}` （セクター: `{execution_result['sector']}`）
- **約定株数**: `{execution_result['shares']} 株`
- **約定単価**: `${execution_result['price']:.2f}`
- **約定合計金額**: `${execution_result['total_amount']:.2f}`
- **執行備考**: {execution_result['note']}

### SBI証券 手動注文ガイド
> {decision.sbi_order_guide}

---

## 2. 4体のAIエージェント経営会議議事録

### ① 情報収集担当（News Researcher）
{decision.researcher_comment}

### ② テクニカル分析担当（Technical Analyst）
{decision.analyst_comment}

### ③ ファンドマネージャー（Fund Manager）
{decision.manager_reason}

### ④ 執行・経理担当（Execution & Accounting）
{execution_result['accountant_comment']}

---

## 3. ポートフォリオ資産状況

| 項目 | 金額 / 数値 |
| :--- | :--- |
| **総資産額 (Total Equity)** | **${execution_result['total_equity_after']:.2f}** （約 ¥{int(round(execution_result['total_equity_after'] * 150)):,}） |
| **累計入金額 (Invested Capital)** | ${execution_result['total_deposited']:.2f} |
| **トータル損益 (Total Return)** | **${execution_result['total_return']:+.2f} ({execution_result['total_return_pct']:+.2f}%)** |
| **現金残高 (Cash)** | ${execution_result['cash_after']:.2f} |
| **保有株評価額 (Holdings Value)** | ${execution_result['holdings_value_after']:.2f} |

### 保有銘柄一覧
{chr(10).join(holdings_lines)}

---

## 4. 本日の一次スクリーニング上位候補（最大6銘柄）
{chr(10).join(candidate_lines)}
"""
    with report_path.open("w", encoding="utf-8") as f:
        f.write(content)

    return report_path


def record_owner_trade_report(
    portfolio: dict[str, Any],
    action: str,
    ticker: str,
    shares: int,
    price: float,
    sector_map: dict[str, str],
    current_date: str | None = None,
    note: str = "",
) -> tuple[dict[str, Any], MeetingDecision, dict[str, Any]]:
    """
    オーナー（社長）からの手動売買報告（BUY / SELL / DEPOSIT）をポートフォリオへ反映する。
    """
    jst = datetime.timezone(datetime.timedelta(hours=9))
    now_dt = datetime.datetime.now(jst)
    if current_date is None:
        current_date = now_dt.strftime("%Y-%m-%d")
    market_date = str(portfolio.get("last_market_date") or current_date)

    act = action.upper().strip()
    tkr = ticker.upper().strip() if ticker else "NONE"
    holdings: dict[str, dict[str, Any]] = portfolio.setdefault("holdings", {})
    cash_before = round(float(portfolio.get("cash", 0.0)), 2)

    if act == "DEPOSIT":
        deposit_amount = round(float(price), 2)
        if deposit_amount <= 0:
            raise ValueError("入金額は 0 より大きい金額（USD）を指定してください。")
        portfolio["cash"] = round(cash_before + deposit_amount, 2)
        portfolio["total_deposited"] = round(
            float(portfolio.get("total_deposited", INITIAL_CAPITAL_USD)) + deposit_amount, 2
        )
        portfolio.setdefault("deposit_history", []).append(
            {
                "date": current_date,
                "month": current_date[:7],
                "amount": deposit_amount,
                "type": "OWNER_REPORT",
                "note": note or f"オーナー手動入金報告 (+${deposit_amount:.2f})",
            }
        )
        exec_action = "HOLD"
        exec_ticker = "CASH"
        exec_sector = "Cash Deposit"
        exec_shares = 0
        exec_price = deposit_amount
        exec_total = deposit_amount
        exec_note = note or f"【オーナー報告】現金追加入金 +${deposit_amount:.2f} を反映"
        accountant_msg = f"【オーナー入金反映完了】ご報告いただいた追加入金 +${deposit_amount:.2f} を現金残高および累計元本へ反映しました（現在現金: ${portfolio['cash']:.2f}）。"

    elif act == "BUY":
        if not tkr or tkr == "NONE":
            raise ValueError("購入した銘柄のティッカー（例: NVDA, SCHD）を入力してください。")
        if int(shares) < 1:
            raise ValueError("購入株数は1株以上の整数を指定してください。")
        if float(price) <= 0:
            raise ValueError("約定単価（USD）は 0 より大きい数値を指定してください。")

        exec_shares = int(shares)
        exec_price = round(float(price), 2)
        exec_total = round(exec_shares * exec_price, 2)
        exec_sector = sector_map.get(tkr, holdings.get(tkr, {}).get("sector", "Other"))

        # もし実購入額が現在の仮想現金残高を超えている場合は、差額をオーナー追加入金として自動補填
        auto_topup = 0.0
        if exec_total > cash_before:
            auto_topup = round(exec_total - cash_before, 2)
            portfolio["cash"] = round(cash_before + auto_topup, 2)
            portfolio["total_deposited"] = round(
                float(portfolio.get("total_deposited", INITIAL_CAPITAL_USD)) + auto_topup, 2
            )
            portfolio.setdefault("deposit_history", []).append(
                {
                    "date": current_date,
                    "month": current_date[:7],
                    "amount": auto_topup,
                    "type": "AUTO_TOPUP",
                    "note": f"{tkr} 購入報告に伴う不足現金の自動入金補填 (+${auto_topup:.2f})",
                }
            )

        portfolio["cash"] = round(float(portfolio["cash"]) - exec_total, 2)
        existing = holdings.get(tkr, {})
        old_shares = int(existing.get("shares", 0))
        old_avg = float(existing.get("avg_cost", 0.0))
        new_shares = old_shares + exec_shares
        new_avg = round(((old_shares * old_avg) + exec_total) / new_shares, 2)

        holdings[tkr] = {
            "ticker": tkr,
            "sector": exec_sector,
            "shares": new_shares,
            "avg_cost": new_avg,
            "current_price": exec_price,
            "market_value": round(new_shares * exec_price, 2),
            "unrealized_pnl": round((exec_price - new_avg) * new_shares, 2),
            "unrealized_pnl_pct": round(((exec_price - new_avg) / new_avg) * 100.0, 2)
            if new_avg > 0
            else 0.0,
        }
        exec_action = "BUY"
        exec_ticker = tkr
        topup_msg = f"（不足分 ${auto_topup:.2f} を元本へ自動補填）" if auto_topup > 0 else ""
        exec_note = note or f"【オーナー買付報告】{tkr} {exec_shares}株 @ ${exec_price:.2f} 買付反映{topup_msg}"
        accountant_msg = (
            f"【オーナー買付報告を記帳完了】SBI証券等での実買付報告（{tkr} {exec_shares}株 @ ${exec_price:.2f} / "
            f"合計 ${exec_total:.2f}{topup_msg}）をポートフォリオへ反映しました。現在の {tkr} 保有数は {new_shares}株 です。"
        )

    elif act == "SELL":
        if not tkr or tkr not in holdings:
            raise ValueError(f"銘柄 {tkr} は現在保有リストに存在しないため売却報告できません。")
        existing = holdings[tkr]
        old_shares = int(existing.get("shares", 0))
        if int(shares) < 1 or int(shares) > old_shares:
            raise ValueError(f"売却株数は 1 〜 現在保有株数（{old_shares}株）の範囲で指定してください。")
        if float(price) <= 0:
            raise ValueError("売却単価（USD）は 0 より大きい数値を指定してください。")

        exec_shares = int(shares)
        exec_price = round(float(price), 2)
        exec_total = round(exec_shares * exec_price, 2)
        exec_sector = existing.get("sector", sector_map.get(tkr, "Other"))
        avg_cost = float(existing.get("avg_cost", exec_price))
        realized_pnl = round((exec_price - avg_cost) * exec_shares, 2)

        portfolio["cash"] = round(cash_before + exec_total, 2)
        rem_shares = old_shares - exec_shares
        if rem_shares <= 0:
            del holdings[tkr]
        else:
            existing["shares"] = rem_shares
            existing["current_price"] = exec_price
            existing["market_value"] = round(rem_shares * exec_price, 2)
            existing["unrealized_pnl"] = round((exec_price - avg_cost) * rem_shares, 2)

        exec_action = "SELL"
        exec_ticker = tkr
        exec_note = (
            note
            or f"【オーナー売却報告】{tkr} {exec_shares}株 @ ${exec_price:.2f} 売却反映 (実現損益 ${realized_pnl:+.2f})"
        )
        accountant_msg = (
            f"【オーナー売却報告を記帳完了】{tkr} {exec_shares}株 @ ${exec_price:.2f}（受取額 ${exec_total:.2f} / "
            f"実現損益 ${realized_pnl:+.2f}）の売却をポートフォリオへ反映しました。"
        )
    else:
        raise ValueError(f"未対応の報告区分です: {action}")

    holdings_value_after = update_holdings_valuation(portfolio, {tkr: exec_price} if tkr != "NONE" else {}, sector_map)
    cash_after = round(float(portfolio.get("cash", 0.0)), 2)
    total_equity_after = round(cash_after + holdings_value_after, 2)
    total_deposited = round(float(portfolio.get("total_deposited", INITIAL_CAPITAL_USD)), 2)
    total_return = round(total_equity_after - total_deposited, 2)
    total_return_pct = round((total_return / total_deposited) * 100.0, 2) if total_deposited > 0 else 0.0

    portfolio["updated_at"] = now_dt.isoformat(timespec="seconds")
    snapshot = {
        "date": current_date,
        "market_date": market_date,
        "cash": cash_after,
        "holdings_value": holdings_value_after,
        "total_equity": total_equity_after,
        "total_deposited": total_deposited,
        "total_return": total_return,
        "total_return_pct": total_return_pct,
        "action": exec_action,
        "ticker": exec_ticker,
    }
    asset_history: list[dict[str, Any]] = portfolio.setdefault("asset_history", [])
    if asset_history and asset_history[-1].get("date") == current_date:
        asset_history[-1] = snapshot
    else:
        asset_history.append(snapshot)

    decision = MeetingDecision(
        action=exec_action,
        ticker=exec_ticker,
        shares=exec_shares,
        researcher_comment=f"オーナー（社長）からの手動報告（{act}: {exec_ticker}）を受領しました。次回以降のニュース監視対象へ即座に反映します。",
        analyst_comment=f"ポートフォリオの最新保有状況（現金 ${cash_after:.2f} / 保有評価額 ${holdings_value_after:.2f}）に基づき、テクニカル監視ラインを再計算しました。",
        manager_reason=f"オーナーからの直接報告（{exec_note}）を最優先で承認・反映しました。次回会議ではこの最新ポートフォリオを前提に戦略を立案します。",
        sbi_order_guide=f"オーナーによる実取引報告（{exec_note}）の記帳が完了しています。",
    )

    execution_result = {
        "date": current_date,
        "market_date": market_date,
        "requested_action": exec_action,
        "requested_ticker": exec_ticker,
        "requested_shares": exec_shares,
        "action": exec_action,
        "ticker": exec_ticker,
        "sector": exec_sector,
        "shares": exec_shares,
        "price": exec_price,
        "total_amount": exec_total,
        "cash_after": cash_after,
        "holdings_value_after": holdings_value_after,
        "total_equity_after": total_equity_after,
        "total_deposited": total_deposited,
        "total_return": total_return,
        "total_return_pct": total_return_pct,
        "note": exec_note,
        "accountant_comment": accountant_msg,
    }
    return portfolio, decision, execution_result

