# AI Investment Firm（マルチAIエージェントによる米国株仮想投資会社）

米国株（S&P500主要11セクター代表45銘柄＋低価格優良ETF 5銘柄の計50銘柄）を対象に、追加課金ゼロ（無料ライブラリ・Gemini API無料枠・GitHub Actions無料枠・GitHub Pages無料枠）で毎朝9:00（JST）に自動稼働するペーパートレード・シミュレーションシステムです。

---

## 主な特徴・運用ルール

1. **初期資金と月次積立（二重加算防止）**
   - 初回起動時の初期現金残高は **`$330.0`**（約50,000円）でスタートします（初月は `+$100.0` の重複加算を行いません）。
   - 翌月以降、毎月の初回稼働日に **`+$100.0`**（約15,000円）を自動入金し、`last_deposit_month`（`YYYY-MM`）により同月内の二重加算を防止します。
2. **SBI証券（米国株現物）前提の取引ルール**
   - **現物買いのみ**（信用取引・空売りなし）。
   - **1株単位（整数株）のみ**売買可能（端株・小数点株は禁止）。
3. **セクター分散と35%上限ロック（初期デッドロック回避特例付き）**
   - すでに保有している銘柄と同じセクターへの集中を避け、他セクターや低価格優良ETF（`SPYM`, `SCHD`, `QQQM`, `VXUS`, `VTI`）への分散を優先します。
   - 購入後の1銘柄評価額が「総資産の35%」を超える追加購入はプログラム側でブロックします。
   - **初期特例**：総資産が `$1,000.0` 未満の初期フェーズにおいて、未保有銘柄を「新規に1株だけ（`shares=1`）」購入する場合に限り、現金残高の範囲内であれば35%制限を免除して購入を許可します。
4. **2段階省エネ設計（AI APIコール最小化）**
   - **第1段階（`screener.py` / AI使用量ゼロ）**：厳選50銘柄の株価・出来高データから14日RSI、5日/25日移動平均線乖離率、出来高変化率を算出し、現金残高で購入可能な上位6銘柄に絞り込みます。
   - **第2段階（`agents.py` & `portfolio_manager.py`）**：最新SDK `google-genai`（モデル: `gemini-2.5-flash`）の構造化出力を用い、1回のAPIコールで4体のAI社員（①情報収集担当、②テクニカル分析担当、③ファンドマネージャー、④執行・経理担当）による議論と最終意思決定を行います。

---

## フォルダ構成

```text
ai-investment-firm/
├── documents/                           # 設計書・テスト仕様書・操作マニュアル一式（日本語）
│   ├── 01_requirements_definition.md    # 要件定義書
│   ├── 02_basic_design.md               # 基本設計書
│   ├── 03_detailed_design.md            # 詳細設計書
│   ├── 04_unit_test_spec.md             # 単体テスト仕様書
│   ├── 05_integration_test_spec.md      # 結合テスト仕様書
│   ├── 06_scenario_test_spec.md         # シナリオテスト仕様書
│   └── 07_user_manual.md                # ★初心者向け：使い方・画面の見方ガイド（図解付き）
├── tests/                               # pytest 自動テストコード一式
│   ├── test_unit.py
│   ├── test_integration.py
│   └── test_scenario.py
├── .github/workflows/daily_meeting.yml  # 毎朝9:00(JST)自動実行＆結果自動コミット用
├── .env.example
├── .gitignore
├── requirements.txt
├── README.md
├── main.py                              # メイン実行スクリプト（--force オプション対応）
├── screener.py                          # 【第1段階】厳選50銘柄から上位6銘柄に絞る処理
├── agents.py                            # 【第2段階】AIエージェント会議と構造化出力処理
├── portfolio_manager.py                 # 仮想口座の残高計算・1株単位の約定・CSV/JSON保存
├── dashboard_generator.py               # 会議結果と資産状況から docs/index.html を生成する処理
├── data/
│   ├── portfolio.json                   # 現在の現金残高・保有株・業種・積立履歴・総資産推移
│   └── trade_history.csv                # 全売買履歴（Excelで確認可能）
├── reports/
│   └── YYYY-MM-DD.md                    # 毎朝のAIエージェント経営会議レポート
└── docs/
    └── index.html                       # PC・スマホ閲覧用の朝刊ダッシュボード画面（GitHub Pages用）
```

---

## ローカル環境構築・実行手順

### 1. 仮想環境の作成とライブラリインストール

```bash
cd ai-investment-firm
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 環境変数（`.env`）の設定

`.env.example` をコピーして `.env` を作成し、Google AI Studio（https://aistudio.google.com/ ）で取得した無料の `GEMINI_API_KEY` を設定します（未設定の場合は安全なモックHOLDモードで動作します）。

```bash
cp .env.example .env
# .env 内の GEMINI_API_KEY=your_api_key_here を実際のキーに書き換えてください
```

### 3. シミュレーションの実行

```bash
# 通常実行（土日・祝日で取引日が更新されていない場合はスキップ）
.venv/bin/python main.py

# 強制実行（休場日でもテスト実行したい場合）
.venv/bin/python main.py --force
```

### 4. 自動テスト（pytest）の実行

```bash
.venv/bin/pytest -v
```

---

## GitHub Secrets 登録と GitHub Pages 公開手順

### Step 1: GitHub リポジトリへのプッシュ
本プロジェクトを GitHub リポジトリ（Public または Private）へプッシュします。

### Step 2: `GEMINI_API_KEY` を GitHub Secrets に登録
1. GitHub リポジトリ画面上部の **Settings** タブを開きます。
2. 左サイドバーの **Secrets and variables** → **Actions** をクリックします。
3. **New repository secret** ボタンをクリックします。
4. 以下のように入力して **Add secret** で保存します：
   - **Name**: `GEMINI_API_KEY`
   - **Secret**: Google AI Studio で取得した Gemini API キー文字列

### Step 3: GitHub Actions の書き込み権限確認
1. **Settings** → **Actions** → **General** を開きます。
2. **Workflow permissions** セクションで **Read and write permissions** が選択されていることを確認します（`.github/workflows/daily_meeting.yml` 内にも `permissions: contents: write` を設定済みです）。
3. **Actions** タブから `Daily AI Investment Meeting` を選択し、**Run workflow** から手動テスト実行できることを確認します。

### Step 4: GitHub Pages で朝刊ダッシュボード（`docs/index.html`）を公開
1. GitHub リポジトリの **Settings** → 左サイドバーの **Pages** を開きます。
2. **Build and deployment** の **Source** で `Deploy from a branch` を選択します。
3. **Branch** で `main`（またはデフォルトブランチ）を選択し、フォルダを **`/docs`** に指定して **Save** をクリックします。
4. 数分後に発行される URL（`https://<ユーザー名>.github.io/<リポジトリ名>/`）へスマートフォンやPCからアクセスすると、毎朝9:00（JST）に自動更新される朝刊ダッシュボードを閲覧できます。
