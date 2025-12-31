# 開発ガイドライン

## コーディング規約

### Python スタイル

- Python 3.11+ の機能を使用
- 型ヒントを積極的に使用
- Ruff による自動フォーマットに従う

### インポート順序

Ruff (isort) により自動整理:

```python
# 1. 標準ライブラリ
import json
import logging
from typing import Any

# 2. サードパーティ
import boto3
import httpx
from pydantic import BaseModel

# 3. ローカル
from .agent_client import AgentCoreClient
```

### ドキュメント文字列

Google スタイルを使用:

```python
def process_event(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    Slack イベントを処理する。

    Args:
        event: Slack からのイベントペイロード
        context: Lambda コンテキスト

    Returns:
        処理結果を含むレスポンス

    Raises:
        ValueError: 必須フィールドが欠落している場合
    """
```

### エラーハンドリング

```python
try:
    result = api_call()
except SpecificException as e:
    logger.error(f"API call failed: {e}", exc_info=True)
    raise
except Exception as e:
    logger.error(f"Unexpected error: {e}", exc_info=True)
    return {"statusCode": 500, "body": "Internal error"}
```

## 命名規則

### ファイル・ディレクトリ

| 対象 | 規則 | 例 |
|------|------|-----|
| Python ファイル | snake_case | `agent_client.py` |
| Python パッケージ | snake_case | `slack/worker/` |
| ドキュメント | kebab-case | `development-guidelines.md` |
| 設定ファイル | UPPERCASE | `CLAUDE.md`, `README.md` |

### Python コード

| 対象 | 規則 | 例 |
|------|------|-----|
| クラス | PascalCase | `SlackClient` |
| 関数・メソッド | snake_case | `get_events()` |
| 変数 | snake_case | `user_message` |
| 定数 | UPPER_SNAKE_CASE | `AWS_REGION` |
| プライベート | 先頭 `_` | `_slack_credentials` |

### 環境変数

```python
# 定数として定義
SLACK_SECRET_ARN = os.environ.get("SLACK_SECRET_ARN", "")
AGENTCORE_RUNTIME_ID = os.environ.get("AGENTCORE_RUNTIME_ID", "")
```

## フォーマット規約

### Ruff 設定（pyproject.toml）

```toml
[tool.ruff]
target-version = "py311"
line-length = 100

[tool.ruff.lint]
select = ["E", "W", "F", "I", "N", "UP", "B", "C4", "SIM"]
```

### 自動フォーマット

```bash
# フォーマット実行
ruff format .

# フォーマット確認（CI 用）
ruff format --check .
```

## テスト規約

### テストファイル配置

```
tests/
├── unit/
│   ├── interfaces/
│   │   └── slack/
│   │       └── test_receiver.py
│   └── mcp/
│       └── calendar/
│           └── test_handler.py
├── integration/
│   └── test_slack_integration.py
└── conftest.py
```

### テスト命名

```python
def test_receiver_returns_200_for_valid_event():
    """正常なイベントで 200 を返す"""

def test_receiver_rejects_invalid_signature():
    """無効な署名を拒否する"""
```

### テスト実行

```bash
# 全テスト
pytest

# 特定ディレクトリ
pytest tests/unit/

# カバレッジ
pytest --cov=interfaces --cov=mcp
```

## Git 規約

### ブランチ戦略

- `main` - 本番環境
- `feature/[issue-number]-[description]` - 機能追加
- `fix/[issue-number]-[description]` - バグ修正

### コミットメッセージ

```
fix #3: カレンダー MCP 追加

- Calendar Lambda を実装
- Gateway Target を設定
- AgentCore Identity を統合
```

- Issue 番号を含める: `fix #N:` または `refs #N:`
- 動詞で始める: add, fix, update, remove, refactor
- 本文は変更の「なぜ」を説明

### git worktree の使用

```bash
# 新しいブランチで作業開始
git worktree add ../mynion-issue-3 feature/3-calendar-mcp

# 作業完了後
git worktree remove ../mynion-issue-3
```

## 開発環境セットアップ

### 1. 依存関係インストール

```bash
# Python 依存関係
uv sync

# Node.js（CDK 用）
npm install -g aws-cdk
```

### 2. VSCode 拡張機能

推奨拡張機能をインストール:
1. `Cmd+Shift+P` → `Extensions: Show Recommended Extensions`
2. 表示された拡張機能をすべてインストール

手動インストール:
- Python
- Pylance
- Ruff
- GitHub Copilot（推奨）

### 3. pre-commit 設定

```bash
pre-commit install
```

## ローカル開発

### Agent のローカル実行

```bash
# 仮想環境有効化
source .venv/bin/activate

# Agent 起動（開発モード）
uvicorn main:app --reload --port 8000
```

### 環境変数設定

ローカル実行時に必要な環境変数:

```bash
# AWS 認証情報
export AWS_PROFILE=your-profile
export AWS_REGION=ap-northeast-1

# AgentCore 設定（デプロイ後に取得）
export AGENTCORE_RUNTIME_ENDPOINT=arn:aws:bedrock-agentcore:...
```

### Agent 呼び出しテスト

```bash
# invoke_agent.py を使用
python invoke_agent.py "今日の予定を教えて"
```

### ローカルでの Slack イベントテスト

Slack からのイベントをローカルでテストする場合:

1. ngrok などで一時的な公開 URL を作成
2. Slack App の Event Subscriptions URL を更新
3. ローカルで Receiver Lambda 相当の処理を実行

```bash
# ngrok でトンネル作成
ngrok http 8000
```

## 品質チェック

### コミット前チェック

```bash
# 型チェック
mypy .

# Lint
ruff check .

# フォーマット確認
ruff format --check .
```

### 自動修正

```bash
# Lint 自動修正
ruff check --fix .

# フォーマット
ruff format .
```

### CI/CD チェック

```bash
# すべてのチェックを実行
mypy . && ruff check . && ruff format --check .
```

## コード品質ツール

### Pylance（リアルタイム型チェック）

VSCode でファイルを開くと自動的に動作:
- 型エラーを赤線で表示
- 自動補完を強化
- 関数の戻り値型をインレイヒント表示

### Mypy（厳密な型チェック）

```bash
# プロジェクト全体
mypy .

# 特定ディレクトリ
mypy cdk/
mypy interfaces/

# 厳密モード
mypy --strict cdk/
```

### Ruff（Linter + Formatter）

```bash
# Lint
ruff check .

# 自動修正
ruff check --fix .

# フォーマット
ruff format .
```

## トラブルシューティング

### Pylance が型を認識しない

```bash
# 型スタブを再インストール
uv add --dev types-boto3

# VSCode 再起動
```

### Mypy エラーが多すぎる

`pyproject.toml` で厳密度を調整:

```toml
[tool.mypy]
disallow_untyped_defs = false
```

### Ruff との既存コードの衝突

一時的に特定ルールを無効化:

```python
# ruff: noqa: E501
def very_long_function_name():
    pass
```

## よく使うコマンド

```bash
# すべてのチェック
mypy . && ruff check . && ruff format --check .

# すべて自動修正
ruff check --fix . && ruff format .

# CDK デプロイ
cd cdk && cdk deploy --all

# AgentCore デプロイ
agentcore deploy
```
