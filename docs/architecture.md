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
    "aws-cdk-lib>=2.233.0",
    "constructs>=10.4.3",
    "aws-cdk-aws-bedrock-agentcore-alpha>=2.233.0a0",
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
- CUSTOM_JWT 認証（Cognito OAuth トークン）
- Cognito User Pool で `client_credentials` フローを使用
- Agent が Secrets Manager から認証情報を取得し、Cognito からトークンを取得

#### Google Calendar 認証（OAuth2 Session Binding）

AgentCore Identity の OAuth2 Credential Provider + **Session Binding** パターンを使用。

| コンポーネント | 役割 |
|---------------|------|
| OAuth2 Credential Provider | Google OAuth2 クライアント設定を管理 |
| Workload Identity | `allowedResourceOauth2ReturnUrls` で Callback URL を登録 |
| Callback Lambda | Session Binding を完了（`CompleteResourceTokenAuth` 呼び出し） |
| Token Vault | トークンを安全に保存・自動リフレッシュ |

**Session Binding フロー:**
1. Agent が `GetResourceOauth2Token` を呼び出し（`custom_state` に Slack user_id を含める）
2. ユーザーが Google で認証
3. Google → AgentCore Callback → 私たちの Callback Lambda にリダイレクト
4. Callback Lambda が `CompleteResourceTokenAuth` を呼び出し
5. Agent がポーリングでトークン取得

**Session Binding の意義:**
- 認証を開始したユーザーと完了したユーザーが同一であることを確認
- Authorization URL が他人に転送されても、セッションがバインドされないため安全
- AWS 公式推奨パターン（[OAuth2 Authorization URL Session Binding](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/oauth2-authorization-url-session-binding.html)）

### セキュリティ要件

| 要件 | 実装 |
|------|------|
| 認証情報管理 | AWS Secrets Manager |
| IAM 最小権限 | 必要最小限のポリシーのみ付与 |
| 入力バリデーション | Pydantic によるスキーマ検証 |
| ログ出力 | 機密情報をマスク |
| OAuth Callback | Session Binding で認証セッションを検証 |
| Callback URL | HTTPS のみ、Workload Identity に事前登録 |
| セッション有効期限 | Authorization URL は 10 分で失効 |

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
