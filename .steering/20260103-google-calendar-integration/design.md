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

### 変更

| ファイル | 変更内容 |
|---------|---------|
| `cdk/app.py` | GatewayStack の追加 |
| `agent.py` | MCPClient で Gateway に接続 |

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

- AgentCore Identity の OAuth2 Credential Provider を使用（予定）
- 現状は Agent 側で Google OAuth トークンを取得し、ツール引数として渡す

### 初回認証フロー（Google Calendar）

1. ユーザーがカレンダー操作を要求
2. Agent が Google OAuth 認証 URL を生成
3. Slack に認証リンクを表示
4. ユーザーが Google で認証
5. Agent がアクセストークンを取得
6. ツール呼び出し時に `access_token` 引数として渡す

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

## 参照ドキュメント

- `docs/functional-design.md`: シーケンス図、コンポーネント設計
- `docs/architecture.md`: 認証方式、技術スタック
