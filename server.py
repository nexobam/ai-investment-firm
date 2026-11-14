"""
オーナー（社長）指令室 ＆ 双方向ダッシュボード用ローカルWebサーバー（server.py）
起動すると http://127.0.0.1:8000 でダッシュボード画面を配信し、
画面上のボタンから以下の2つの操作をリアルタイムに実行できる：
1. AI社員への直接命令＆「今すぐ分析・会議」の即時招集（POST /api/meeting）
2. SBI証券等での実際の「買った／売った／追加入金した」報告の即時反映（POST /api/manual_trade）
"""

from __future__ import annotations

import argparse
import json
import logging
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import yfinance as yf
from dotenv import load_dotenv

from dashboard_generator import generate_dashboard
from main import BASE_DIR, run_daily_workflow, setup_logging
from portfolio_manager import (
    append_trade_history,
    generate_daily_report,
    load_or_init_portfolio,
    load_trade_history,
    record_owner_trade_report,
    save_portfolio,
)
from screener import FALLBACK_PRICES, UNIVERSE_STOCKS, flatten_yfinance_df

logger = logging.getLogger(__name__)


def _fetch_latest_price_for_ticker(ticker: str, portfolio: dict[str, Any]) -> float:
    """
    手動売買報告で単価が空欄の場合に、yfinanceまたは保有データから最新株価を取得する。
    """
    tkr = ticker.upper().strip()
    try:
        hist = yf.Ticker(tkr).history(period="5d")
        flat = flatten_yfinance_df(hist)
        if not flat.empty and "Close" in flat.columns:
            val = float(flat["Close"].dropna().iloc[-1])
            if val > 0:
                return round(val, 2)
    except Exception as exc:
        logger.warning("最新株価の自動取得失敗 (%s): %s", tkr, exc)

    held = portfolio.get("holdings", {}).get(tkr, {})
    if held and float(held.get("current_price", 0.0)) > 0:
        return round(float(held["current_price"]), 2)
    if tkr in FALLBACK_PRICES:
        return FALLBACK_PRICES[tkr]
    return 0.0


class DashboardRequestHandler(BaseHTTPRequestHandler):
    """
    ダッシュボードHTML配信およびオーナー指令・売買報告APIを処理するハンドラ。
    file:// で直接 docs/index.html を開いている場合でも通信できるようCORSヘッダーを付与する。
    """

    def _send_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_cors_headers()
        self.end_headers()

    def _send_json(self, status_code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path.startswith("/api/ping"):
            self._send_json(HTTPStatus.OK, {"status": "ok"})
            return

        if self.path in ("/", "/index.html") or self.path.startswith("/?"):
            dashboard_path = BASE_DIR / "docs" / "index.html"
            if not dashboard_path.exists():
                run_daily_workflow(base_dir=BASE_DIR, force=True)
            html_bytes = dashboard_path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html_bytes)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(html_bytes)
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def do_POST(self) -> None:
        content_len = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"
        try:
            data = json.loads(raw_body) if raw_body else {}
        except Exception:
            self._send_json(HTTPStatus.BAD_REQUEST, {"status": "error", "message": "不正なJSONリクエストです。"})
            return

        # 1. AI社員への直接命令＆即時会議招集 API
        if self.path == "/api/meeting":
            instruction = str(data.get("instruction", "")).strip()
            analysis_only = bool(data.get("analysis_only", False))
            try:
                result = run_daily_workflow(
                    base_dir=BASE_DIR,
                    force=True,
                    owner_instruction=instruction,
                    analysis_only=analysis_only,
                    proposal_only=True,
                )
                exec_res = result.get("execution_result", {})
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "status": "ok",
                        "action": exec_res.get("action", "HOLD"),
                        "ticker": exec_res.get("ticker", "NONE"),
                        "shares": exec_res.get("shares", 0),
                        "message": "AI経営会議が完了し、ダッシュボードを更新しました。",
                    },
                )
            except Exception as exc:
                logger.exception("即時AI会議の実行中にエラーが発生しました")
                self._send_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"status": "error", "message": str(exc)},
                )
            return

        # 2. オーナーによる実売買・入金報告 API
        if self.path == "/api/manual_trade":
            action = str(data.get("action", "BUY")).upper().strip()
            ticker = str(data.get("ticker", "")).upper().strip()
            shares = int(data.get("shares", 1) or 1)
            price = float(data.get("price", 0.0) or 0.0)
            note = str(data.get("note", "")).strip()

            portfolio_path = BASE_DIR / "data" / "portfolio.json"
            csv_path = BASE_DIR / "data" / "trade_history.csv"
            reports_dir = BASE_DIR / "reports"
            dashboard_path = BASE_DIR / "docs" / "index.html"

            try:
                portfolio = load_or_init_portfolio(portfolio_path)
                if action in ("BUY", "SELL") and price <= 0.0:
                    price = _fetch_latest_price_for_ticker(ticker, portfolio)
                    if price <= 0.0:
                        raise ValueError(
                            f"{ticker} の現在株価を自動取得できませんでした。約定単価（USD）を直接入力してください。"
                        )

                portfolio, decision, exec_res = record_owner_trade_report(
                    portfolio=portfolio,
                    action=action,
                    ticker=ticker,
                    shares=shares,
                    price=price,
                    sector_map=UNIVERSE_STOCKS,
                    note=note,
                )
                save_portfolio(portfolio, portfolio_path)
                append_trade_history(exec_res, csv_path)
                generate_daily_report(
                    portfolio=portfolio,
                    decision=decision,
                    execution_result=exec_res,
                    candidates=[],
                    reports_dir=reports_dir,
                )
                recent_trades = load_trade_history(csv_path, limit=30)
                import importlib
                import dashboard_generator as _dg
                importlib.reload(_dg)
                _dg.generate_dashboard(
                    portfolio=portfolio,
                    decision=decision,
                    execution_result=exec_res,
                    trade_history=recent_trades,
                    output_path=dashboard_path,
                )
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "status": "ok",
                        "message": exec_res["note"],
                    },
                )
            except Exception as exc:
                logger.warning("手動売買報告エラー: %s", exc)
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"status": "error", "message": str(exc)},
                )
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not Found")


def run_server(host: str = "127.0.0.1", port: int = 8000, open_browser: bool = True) -> None:
    setup_logging()
    load_dotenv(BASE_DIR / ".env")
    server = ThreadingHTTPServer((host, port), DashboardRequestHandler)
    url = f"http://{host}:{port}"
    logging.info("============================================================")
    logging.info("👑 AI Investment Firm 社長室サーバーを起動しました: %s", url)
    logging.info("終了するにはターミナルで Ctrl + C を押してください。")
    logging.info("============================================================")

    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logging.info("サーバーを停止しました。")
    finally:
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Investment Firm 双方向ダッシュボードサーバー")
    parser.add_argument("--host", default="127.0.0.1", help="バインドするホスト名")
    parser.add_argument("--port", type=int, default=8000, help="ポート番号 (デフォルト: 8000)")
    parser.add_argument("--no-browser", action="store_true", help="起動時にブラウザを自動で開かない")
    args = parser.parse_args()
    run_server(host=args.host, port=args.port, open_browser=not args.no_browser)
