# Mynion - Slack AI Assistant on AWS Bedrock AgentCore

SlackからGoogleカレンダーを操作できるAIアシスタント。AWS Bedrock AgentCoreとStrands Agentを使用。

## 機能

- **Slack連携**: メンションでAIアシスタントと対話
- **Googleカレンダー統合**: 予定の取得・作成（OAuth認証）
- **自然言語処理**: 日本語で予定を確認・登録

## アーキテクチャ

```
┌─────────┐     ┌─────────────┐     ┌──────────────────┐
│  Slack  │────▶│ API Gateway │────▶│ Receiver Lambda  │
└─────────┘     └─────────────┘     └────────┬─────────┘
                                              │ SQS
                                              ▼
┌─────────────────┐     ┌─────────────────────────────────┐
│ Worker Lambda   │────▶│ AgentCore Runtime (Strands)     │
└─────────────────┘     └────────────────┬────────────────┘
                                         │ MCP
                                         ▼
                        ┌─────────────────────────────────┐
                        │ AgentCore Gateway               │
                        │ └── Calendar MCP Lambda         │
                        └────────────────┬────────────────┘
                                         │ OAuth
                                         ▼
                        ┌─────────────────────────────────┐
                        │ Google Calendar API             │
                        └─────────────────────────────────┘
```

## プロジェクト構造

```
mynion/
├── agent.py                          # Strands Agent (AgentCore Runtime)
├── Dockerfile                        # Agent用Dockerイメージ
├── pyproject.toml                    # Python依存関係
├── cdk/                              # AWS CDKインフラ
│   ├── app.py                        # CDKエントリーポイント
│   ├── agentcore_runtime.py          # AgentCore Runtimeスタック
│   ├── gateway_stack.py              # AgentCore Gatewayスタック
│   ├── slack_stack.py                # Slack連携スタック
│   ├── cdk.context.json.example      # コンテキスト設定例
│   └── post-deploy.sh                # デプロイ後スクリプト
├── interfaces/slack/                 # Slackインターフェース
│   ├── receiver.py                   # イベント受信Lambda
│   ├── worker/                       # ワーカーLambda
│   └── oauth_callback/               # OAuthコールバックLambda
├── mcp/calendar/                     # Calendar MCP
│   └── handler.py                    # カレンダー操作ハンドラー
└── docs/                             # ドキュメント
```

## セットアップ

### 前提条件

- Python 3.11+
- [uv](https://astral.sh/uv) (パッケージマネージャー)
- Node.js (CDK CLI用)
- AWS CLI (設定済み)
- Docker

### 1. 依存関係のインストール

```bash
uv sync --dev
uv run pre-commit install
```

### 2. Google OAuth設定

1. [Google Cloud Console](https://console.cloud.google.com/)でOAuthクライアントを作成
2. AWS Bedrock AgentCoreでCredential Providerを設定
3. `cdk/cdk.context.json`を作成:

```json
{
  "mynion:googleCredentialProvider": "YourGoogleCredentialProviderName",
  "mynion:googleOauthCallbackUrl": "https://bedrock-agentcore.ap-northeast-1.amazonaws.com/identities/oauth2/callback/your-callback-id"
}
```

### 3. Slack App設定

1. [Slack API](https://api.slack.com/apps)でAppを作成
2. Bot Token Scopesを設定: `chat:write`, `app_mentions:read`
3. Event SubscriptionsでRequest URLを設定
4. AWS Secrets Managerに認証情報を保存

### 4. デプロイ

```bash
cd cdk

# 初回のみ
cdk bootstrap aws://ACCOUNT-ID/ap-northeast-1

# デプロイ
cdk deploy --all

# OAuth callback URL設定（デプロイ後）
./post-deploy.sh
```

## 使い方

Slackでボットをメンションして話しかけます：

```
@mynion 明日の予定は？
@mynion 来週月曜の10時から11時に会議を入れて
```

初回利用時はGoogle認証が必要です。表示されるリンクから認証を完了してください。

## 開発

### ローカルテスト

```bash
# Agentのテスト
uv run uvicorn agent:app --host 0.0.0.0 --port 8080

curl -X POST http://localhost:8080/invocations \
  -H "Content-Type: application/json" \
  -d '{"input": {"prompt": "こんにちは"}}'
```

### コード品質

```bash
# リント・フォーマット
uv run ruff check --fix .
uv run ruff format .

# 型チェック
uv run mypy .
```

## スタックの削除

```bash
cd cdk
cdk destroy --all
```

## 参考リンク

- [AWS Bedrock AgentCore Documentation](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/)
- [Strands Agents](https://pypi.org/project/strands-agents/)
- [Slack Bolt for Python](https://slack.dev/bolt-python/)
