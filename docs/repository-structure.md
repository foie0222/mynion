# リポジトリ構造定義書

## フォルダ・ファイル構成

```
mynion/
├── .github/                    # GitHub 設定
│   └── copilot-instructions.md # Copilot 設定
├── .steering/                  # 作業単位のドキュメント
│   └── [YYYYMMDD]-[title]/     # 各作業のステアリングファイル
│       ├── requirements.md     # 作業要求
│       ├── design.md           # 設計
│       └── tasklist.md         # タスクリスト
├── cdk/                        # AWS CDK インフラストラクチャ
│   ├── app.py                  # CDK アプリケーションエントリポイント
│   ├── slack_stack.py          # Slack 連携スタック
│   ├── agentcore_runtime.py    # AgentCore ランタイム設定
│   └── cdk.json                # CDK 設定
├── docs/                       # 永続的ドキュメント
│   ├── product-requirements.md # プロダクト要求定義書
│   ├── functional-design.md    # 機能設計書
│   ├── architecture.md         # 技術仕様書
│   ├── repository-structure.md # リポジトリ構造定義書（本ファイル）
│   ├── development-guidelines.md # 開発ガイドライン
│   └── glossary.md             # ユビキタス言語定義
├── interfaces/                 # 外部システム連携
│   └── slack/                  # Slack 連携
│       ├── __init__.py
│       ├── receiver.py         # Receiver Lambda
│       └── worker/             # Worker Lambda
│           ├── __init__.py
│           ├── handler.py      # Worker Lambda ハンドラ
│           └── agent_client.py # AgentCore クライアント
├── mcp/                        # MCP サーバー実装（予定）
│   └── calendar/               # カレンダー MCP
│       ├── __init__.py
│       └── handler.py          # Calendar Lambda
├── agent.py                    # Strands Agent メイン実装
├── main.py                     # ローカル開発用エントリポイント
├── invoke_agent.py             # Agent 呼び出しスクリプト
├── pyproject.toml              # Python プロジェクト設定
├── uv.lock                     # 依存関係ロックファイル
├── Dockerfile                  # Agent コンテナビルド
├── CLAUDE.md                   # Claude Code 設定
└── README.md                   # プロジェクト説明
```

## ディレクトリの役割

### `cdk/` - インフラストラクチャコード

AWS CDK を使用したインフラストラクチャ定義。

| ファイル | 役割 |
|---------|------|
| `app.py` | CDK アプリケーションのエントリポイント |
| `slack_stack.py` | Slack 連携用 Lambda・API Gateway |
| `agentcore_runtime.py` | AgentCore Runtime 設定 |

### `interfaces/` - 外部システム連携

外部システム（Slack等）との連携を担当。

| パス | 役割 |
|------|------|
| `slack/receiver.py` | Slack イベント受信（署名検証、Worker 呼び出し） |
| `slack/worker/handler.py` | メッセージ処理（Agent 呼び出し、Slack 応答） |
| `slack/worker/agent_client.py` | AgentCore Runtime クライアント |

### `mcp/` - MCP サーバー実装（予定）

AgentCore Gateway のターゲットとなる Lambda 関数。

| パス | 役割 |
|------|------|
| `calendar/handler.py` | Google Calendar API 操作 |

### `docs/` - 永続的ドキュメント

プロジェクト全体の設計・方針を定義。

| ファイル | 役割 |
|---------|------|
| `product-requirements.md` | プロダクト要求定義 |
| `functional-design.md` | 機能設計・アーキテクチャ |
| `architecture.md` | 技術仕様・スタック |
| `repository-structure.md` | リポジトリ構造 |
| `development-guidelines.md` | 開発規約・ワークフロー |
| `glossary.md` | 用語定義 |

### `.steering/` - 作業単位のドキュメント

特定の開発作業に関するステアリングファイル。

命名規則: `.steering/[YYYYMMDD]-[開発タイトル]/`

## ファイル配置ルール

### Lambda ハンドラ

Lambda 関数のハンドラは以下の命名規則に従う:

```
interfaces/[システム名]/[機能名]/handler.py
mcp/[サービス名]/handler.py
```

ハンドラ関数名: `handler(event, context)`

### CDK スタック

スタックファイルは `cdk/` 直下に配置:

```
cdk/[スタック名]_stack.py
```

クラス名: `[StackName]Stack`

### テストファイル（予定）

```
tests/
├── unit/
│   ├── interfaces/
│   └── mcp/
├── integration/
└── conftest.py
```

### 設定ファイル

| ファイル | 配置場所 | 用途 |
|---------|---------|------|
| `pyproject.toml` | ルート | Python プロジェクト設定 |
| `cdk.json` | `cdk/` | CDK 設定 |
| `.pre-commit-config.yaml` | ルート | pre-commit フック |

## モジュール間の依存関係

```mermaid
graph TD
    subgraph "Lambda Functions"
        Receiver[interfaces/slack/receiver.py]
        Worker[interfaces/slack/worker/handler.py]
        Calendar[mcp/calendar/handler.py]
    end

    subgraph "Agent"
        Agent[agent.py]
    end

    subgraph "CDK"
        SlackStack[cdk/slack_stack.py]
        AgentCoreConfig[cdk/agentcore_runtime.py]
    end

    Receiver --> Worker
    Worker --> Agent
    Agent --> Calendar
    SlackStack --> Receiver
    SlackStack --> Worker
    AgentCoreConfig --> Agent
```

## 命名規則

### ファイル名

- Python: `snake_case.py`
- Markdown: `kebab-case.md`（ドキュメント）または `UPPERCASE.md`（設定）

### ディレクトリ名

- `snake_case`（Python パッケージ）
- `kebab-case`（ステアリングディレクトリ）

### クラス・関数名

- クラス: `PascalCase`
- 関数・変数: `snake_case`
- 定数: `UPPER_SNAKE_CASE`
