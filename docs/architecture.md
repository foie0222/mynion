# 技術仕様書

## テクノロジースタック

### 言語・ランタイム

| 技術 | バージョン | 用途 |
|------|-----------|------|
| Python | 3.11+ | アプリケーション全体 |
| Node.js | 22.x | CDK CLI 実行環境 |

### AI エージェント

| 技術 | 説明 |
|------|------|
| Strands Agents | AI エージェントフレームワーク |
| Amazon Bedrock | LLM プロバイダー（Claude 3.5 Sonnet） |
| AgentCore Runtime | エージェントホスティング環境 |
| AgentCore Gateway | MCP サーバー（ツール公開） |
| AgentCore Identity | OAuth2 トークン管理 |

### インフラストラクチャ

| 技術 | 説明 |
|------|------|
| AWS CDK (Python) | Infrastructure as Code |
| AWS Lambda | サーバーレス関数 |
| Amazon API Gateway | REST API エンドポイント |
| AWS Secrets Manager | 認証情報管理 |

### 外部連携

| 技術 | 説明 |
|------|------|
| Slack Bolt | Slack アプリ統合 |
| Google Calendar API | カレンダー操作 |

### 依存パッケージ

```toml
# pyproject.toml より
dependencies = [
    "fastapi>=0.121.1",
    "httpx>=0.28.1",
    "pydantic>=2.12.4",
    "strands-agents>=1.15.0",
    "uvicorn[standard]>=0.38.0",
    "slack-bolt>=1.21.4",
    "boto3>=1.37.8",
    "aws-cdk-lib>=2.224.0",
    "constructs>=10.4.3",
    "aws-cdk-aws-bedrock-agentcore-alpha==2.224.0a0",
]
```

## 開発ツールと手法

### コード品質ツール

| ツール | 用途 | 実行方法 |
|--------|------|----------|
| Ruff | Linter + Formatter | 保存時自動実行 / `ruff check .` |
| Mypy | 静的型チェック | `mypy .` |
| Pylance | リアルタイム型チェック | VSCode 拡張 |

### パッケージ管理

| ツール | 用途 |
|--------|------|
| uv | Python パッケージ管理 |
| npm | Node.js パッケージ管理（CDK CLI） |

### IDE 設定

推奨 VSCode 拡張機能:
- Python
- Pylance
- Ruff
- GitHub Copilot

### Git ワークフロー

- `git worktree` を使用してブランチごとに別ディレクトリで作業
- GitHub MCP を使用して Issue/PR を管理
- コミットメッセージに Issue 番号を含める

## 技術的制約と要件

### AWS リージョン

| 用途 | リージョン |
|------|-----------|
| メインデプロイ | ap-northeast-1（東京） |
| AgentCore | ap-northeast-1（東京） |

### Slack 制約

| 制約 | 対応 |
|------|------|
| 3秒タイムアウト | Receiver Lambda で即座に 200 OK 返却 |
| リトライ | イベント ID による重複排除 |
| 署名検証 | HMAC-SHA256 で検証必須 |

### AgentCore 制約

| 制約 | 値 |
|------|-----|
| セッション ID 最小長 | 33 文字 |
| ユーザー ID 形式 | 任意文字列 |
| ストリーミング | 対応 |

### 認証・認可

#### Gateway Inbound 認証
- IAM 認証（SigV4 署名）
- Agent の IAM ロールに Gateway 呼び出し権限を付与

#### Google Calendar 認証
- AgentCore Identity による OAuth2
- USER_FEDERATION フローでユーザー同意を取得
- Token Vault でトークンを管理

### セキュリティ要件

| 要件 | 実装 |
|------|------|
| 認証情報管理 | AWS Secrets Manager |
| IAM 最小権限 | 必要最小限のポリシーのみ付与 |
| 入力バリデーション | Pydantic によるスキーマ検証 |
| ログ出力 | 機密情報をマスク |

## パフォーマンス要件

### レスポンス時間

| 処理 | 目標 |
|------|------|
| Slack イベント応答 | 3 秒以内（200 OK） |
| エージェント応答 | 30 秒以内 |
| カレンダー操作 | 10 秒以内 |

### 可用性

| 項目 | 目標 |
|------|------|
| 稼働率 | 99.5% |
| エラー率 | 1% 未満 |

### スケーラビリティ

| 項目 | 対応 |
|------|------|
| 同時接続 | Lambda 自動スケール |
| リクエスト増加 | AgentCore Runtime 自動スケール |

## デプロイメント

### 環境

| 環境 | 用途 |
|------|------|
| dev | 開発・テスト |
| prod | 本番 |

### デプロイコマンド

```bash
# 依存関係同期
uv sync

# CDK デプロイ
cd cdk
cdk deploy --all

# AgentCore デプロイ
agentcore deploy
```

### CI/CD チェック

```bash
# 型チェック
mypy .

# Lint チェック
ruff check .

# フォーマットチェック
ruff format --check .
```
