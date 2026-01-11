# 設計書

## 実装アプローチ

AgentCore Gateway + Lambda Target パターンを採用する。

```
Agent (MCPClient) → AgentCore Gateway → Calendar Lambda → Google Calendar API
```

## 変更・追加するコンポーネント

### 新規作成

| ファイル | 役割 |
|---------|------|
| `mcp/calendar/__init__.py` | パッケージ初期化 |
| `mcp/calendar/handler.py` | Calendar Lambda ハンドラ |
| `cdk/gateway_stack.py` | AgentCore Gateway + Lambda Target |
| `interfaces/slack/oauth_callback.py` | OAuth Callback Lambda ハンドラ |

### 変更

| ファイル | 変更内容 |
|---------|---------|
| `cdk/app.py` | GatewayStack の追加 |
| `cdk/slack_stack.py` | OAuth Callback Lambda + API Gateway エンドポイント追加 |
| `agent.py` | MCPClient で Gateway に接続、`custom_state` で Slack user_id を渡す |
| `cdk/post-deploy.sh` | Callback URL を新しいエンドポイントに更新 |

## アーキテクチャ詳細

### Calendar Lambda (`mcp/calendar/handler.py`)

```python
def handler(event, context):
    """
    AgentCore Gateway からの MCP リクエストを処理

    event 構造（inputSchema のプロパティがそのまま渡される）:
    {
        "start_date": "2026-01-03",
        "access_token": "ya29.xxx..."  # Agent側から渡される
    }

    context.client_context.custom:
    {
        "bedrockAgentCoreToolName": "CalendarTarget___get_events",
        ...
    }
    """
```

**OAuth トークン取得フロー**:
- Agent 側で `@requires_access_token` を使用してトークン取得
- Agent がツール呼び出し時に `access_token` を引数として渡す
- Lambda は受け取ったトークンで Google Calendar API を呼び出す

**ツール実装**:

| ツール名 | 処理内容 |
|---------|---------|
| `get_events` | Calendar API の events.list を呼び出し |
| `create_event` | Calendar API の events.insert を呼び出し |
| `update_event` | Calendar API の events.patch を呼び出し |
| `delete_event` | Calendar API の events.delete を呼び出し |

### Gateway Stack (`cdk/gateway_stack.py`)

```python
class GatewayStack(Stack):
    def __init__(self, ...):
        # 1. Calendar Lambda 関数
        calendar_lambda = Function(...)

        # 2. Cognito User Pool（Gateway 認証用）
        user_pool = cognito.UserPool(...)
        resource_server = cognito.UserPoolResourceServer(
            identifier="gateway-api",
            scopes=[ResourceServerScope(scope_name="invoke")]
        )
        app_client = user_pool.add_client(
            generate_secret=True,
            o_auth=OAuthSettings(
                flows=OAuthFlows(client_credentials=True),
                scopes=[OAuthScope.resource_server(resource_server, ...)]
            )
        )

        # 3. AgentCore Gateway（CUSTOM_JWT 認証）
        gateway = CfnGateway(
            name="mynion-calendar-gateway",
            protocol_type="MCP",
            authorizer_type="CUSTOM_JWT",
            authorizer_configuration=AuthorizerConfigurationProperty(
                custom_jwt_authorizer=CustomJWTAuthorizerConfigurationProperty(
                    discovery_url=f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}/.well-known/openid-configuration",
                    allowed_clients=[app_client.user_pool_client_id]
                )
            )
        )

        # 4. Lambda Target
        target = CfnGatewayTarget(
            gateway_identifier=gateway.ref,
            name="calendar",
            target_configuration=TargetConfigurationProperty(
                mcp=McpTargetConfigurationProperty(
                    lambda_=McpLambdaTargetConfigurationProperty(
                        lambda_arn=calendar_lambda.function_arn,
                        tool_schema=ToolSchemaProperty(
                            inline_payload=[...]  # ツール定義
                        )
                    )
                )
            ),
            credential_provider_configurations=[
                CredentialProviderConfigurationProperty(
                    credential_provider_type="GATEWAY_IAM_ROLE"
                )
            ]
        )

        # 5. Agent 用 OAuth シークレット（Secrets Manager）
        agent_secret = secretsmanager.Secret(
            secret_name="mynion-gateway-cognito",
            secret_object_value={
                "client_id": app_client.user_pool_client_id,
                "client_secret": app_client.user_pool_client_secret,
                "token_endpoint": f"https://{domain}.auth.{region}.amazoncognito.com/oauth2/token",
                "scope": "gateway-api/invoke"
            }
        )
```

**注意**: 当初は IAM 認証を計画していたが、CloudFormation の early validation エラーにより CUSTOM_JWT + Cognito に変更した。

### Agent 変更 (`agent.py`)

```python
from strands import Agent
from strands.tools.mcp import MCPClient

# Cognito からトークン取得
token = get_cognito_token(
    client_id=secret["client_id"],
    client_secret=secret["client_secret"],
    token_endpoint=secret["token_endpoint"],
    scope=secret["scope"]
)

# Gateway への MCPClient 接続（Bearer トークン認証）
mcp_client = MCPClient(
    endpoint=gateway_endpoint,
    headers={"Authorization": f"Bearer {token}"}
)

agent = Agent(
    model="bedrock/claude-sonnet-4",
    tools=[mcp_client]
)
```

## 認証フロー

### Inbound（Agent → Gateway）

- **CUSTOM_JWT 認証**（Cognito OAuth トークン）
- Agent が Secrets Manager から Cognito クレデンシャルを取得
- `client_credentials` フローでアクセストークンを取得
- Bearer トークンとして Gateway に送信

```
Agent → Secrets Manager → Cognito Token Endpoint → Gateway
```

### Outbound（Gateway → Google）

AgentCore Identity の OAuth2 Credential Provider + **セッションバインディング**パターンを使用。

```
Agent → GetResourceOauth2Token → 認証URL + sessionUri
    ↓
ユーザー → Google で認証（code, state 付きで callback）
    ↓
Google → AgentCore Callback URL
    ↓
AgentCore → 私たちの Callback URL（session_id 付き）
    ↓
Callback Lambda → CompleteResourceTokenAuth API
    ↓
Agent → トークン取得成功
```

### OAuth Callback Endpoint (`interfaces/slack/oauth_callback.py`)

AgentCore からリダイレクトされた OAuth 認証完了リクエストを処理する。

```python
def handler(event, context):
    """
    AgentCore からの OAuth callback を処理

    クエリパラメータ:
    - session_id: AgentCore が発行したセッション識別子
    - user_id: Slack ユーザーID（custom_state から復元）
    """
    session_id = event['queryStringParameters']['session_id']
    user_id = event['queryStringParameters'].get('user_id')

    # CompleteResourceTokenAuth を呼び出してセッションをバインド
    identity_client = IdentityClient(region)
    identity_client.complete_resource_token_auth(
        session_uri=session_id,
        user_identifier=UserIdIdentifier(user_id=user_id)
    )

    # 成功レスポンス（HTML）
    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'text/html'},
        'body': '<html>認証が完了しました。このタブを閉じてください。</html>'
    }
```

**セッションバインディングが必要な理由**:
- 認証を開始したユーザーと完了したユーザーが同一であることを確認
- Authorization URL が他人に転送されても、セッションがバインドされないため安全
- AWS 公式推奨パターン（[OAuth2 Authorization URL Session Binding](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/oauth2-authorization-url-session-binding.html)）

### 初回認証フロー（Google Calendar）

1. ユーザーがカレンダー操作を要求
2. Agent が `GetResourceOauth2Token` を呼び出し、認証 URL と sessionUri を取得
3. Slack に認証リンクを表示（`custom_state` に Slack user_id を含める）
4. ユーザーが Google で認証
5. Google が AgentCore Callback URL にリダイレクト（code, state 付き）
6. AgentCore がトークンを取得し、私たちの Callback URL にリダイレクト（session_id 付き）
7. Callback Lambda が `CompleteResourceTokenAuth` を呼び出し
8. Agent がトークンをポーリングで取得
9. ツール呼び出し時に `access_token` を自動注入

## 依存パッケージ

Calendar Lambda 用:

```
google-api-python-client>=2.0.0
google-auth>=2.0.0
```

## 影響範囲

- `cdk/app.py`: 新しい Stack の import と依存関係追加
- `agent.py`: MCPClient の追加（既存動作に影響なし）
- CDK デプロイ: 新規リソース作成

## Workload Identity 設定

### 問題

AgentCore Runtime が自動生成する Workload Identity に `allowedResourceOauth2ReturnUrls` を設定する必要がある。
CDK alpha construct (Runtime) には この設定を行う機能がない。

### 調査結果

- AWS SDK for JavaScript (v3) には `@aws-sdk/client-bedrockagentcorecontrol` パッケージが存在しない
- したがって CDK の `AwsCustomResource` は使用不可
- aws-samples リポジトリでは AWS CLI を使った post-deploy スクリプトで対応

### 解決策

`cdk/post-deploy.sh` スクリプトを作成:

```bash
#!/bin/bash
# 1. CloudFormation から Runtime ID を取得
RUNTIME_ID=$(aws cloudformation describe-stacks --stack-name AgentCoreStack ...)

# 2. Runtime 情報から Workload Identity ARN を取得
WORKLOAD_IDENTITY_ARN=$(aws bedrock-agentcore-control get-agent-runtime ...)

# 3. Workload Identity を更新
aws bedrock-agentcore-control update-workload-identity \
    --name "$WORKLOAD_IDENTITY_NAME" \
    --allowed-resource-oauth2-return-urls "[\"$CALLBACK_URL\"]"
```

### デプロイ手順

```bash
# 1. CDK デプロイ
cd cdk
uv run --directory .. npx cdk deploy --all --require-approval never \
  --app "uv run --directory .. python cdk/app.py" \
  --context "mynion:googleCredentialProvider=GoogleCalendarProvider" \
  --context "mynion:googleOauthCallbackUrl=https://..."

# 2. Post-deploy スクリプト実行
./post-deploy.sh
```

## 環境変数管理

`cdk/cdk.context.json` で管理（git ignore 対象）:

```json
{
  "mynion:googleCredentialProvider": "GoogleCalendarProvider",
  "mynion:googleOauthCallbackUrl": "https://bedrock-agentcore.ap-northeast-1.amazonaws.com/identities/oauth2/callback/xxx"
}
```

テンプレートは `cdk/cdk.context.json.example` を参照。

## 参照ドキュメント

- `docs/functional-design.md`: シーケンス図、コンポーネント設計
- `docs/architecture.md`: 認証方式、技術スタック
- `aws-samples/sample-claude-code-web-agent-on-bedrock-agentcore`: post-deploy パターンの参考
