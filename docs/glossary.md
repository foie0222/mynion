# ユビキタス言語定義

## ドメイン用語

### AI エージェント関連

| 用語 | 英語 | 定義 | コード上の命名 |
|------|------|------|----------------|
| エージェント | Agent | ユーザーの要求を理解し、ツールを使用してタスクを実行する AI システム | `Agent`, `agent` |
| ランタイム | Runtime | エージェントをホスティング・実行する環境 | `AgentCoreRuntime`, `runtime` |
| ゲートウェイ | Gateway | エージェントにツールを提供する MCP サーバー | `AgentCoreGateway`, `gateway` |
| ツール | Tool | エージェントが実行できる機能（カレンダー操作等） | `Tool`, `tools` |
| セッション | Session | ユーザーとエージェント間の対話のコンテキスト | `session_id` |
| 推論 | Inference | LLM による応答生成 | `inference` |

### 認証・認可関連

| 用語 | 英語 | 定義 | コード上の命名 |
|------|------|------|----------------|
| トークン | Token | 認証情報を表すアクセストークン | `access_token` |
| トークン保管庫 | Token Vault | AgentCore Identity のトークン保存場所 | `TokenVault` |
| 資格情報プロバイダ | Credential Provider | OAuth2 クライアント設定を管理 | `CredentialProvider` |
| ユーザー連携 | User Federation | ユーザー同意による OAuth2 フロー | `USER_FEDERATION` |
| 署名検証 | Signature Verification | Slack リクエストの正当性確認 | `verify_signature` |

### MCP 関連

| 用語 | 英語 | 定義 | コード上の命名 |
|------|------|------|----------------|
| MCP | Model Context Protocol | エージェントとツール間の標準プロトコル | - |
| MCP クライアント | MCP Client | MCP サーバーに接続するクライアント | `MCPClient` |
| MCP ターゲット | MCP Target | Gateway に登録されたツール（Lambda 等） | `target` |

## ビジネス用語

### スケジュール管理

| 用語 | 英語 | 定義 | コード上の命名 |
|------|------|------|----------------|
| 予定 | Event | カレンダーに登録されたスケジュール項目 | `event`, `Event` |
| リマインダー | Reminder | 予定の事前通知 | `reminder` |
| 空き時間 | Free Time | 予定が入っていない時間帯 | `free_slots` |
| 調整 | Coordination | 複数人の予定を合わせること | `coordinate` |

### Slack 連携

| 用語 | 英語 | 定義 | コード上の命名 |
|------|------|------|----------------|
| メンション | Mention | `@bot` でボットを呼び出すこと | `app_mention` |
| スレッド | Thread | メッセージへの返信連鎖 | `thread_ts` |
| チャンネル | Channel | Slack のメッセージ送受信場所 | `channel_id` |

## UI/UX 用語

### Slack Bot インタラクション

| 用語 | 英語 | 定義 |
|------|------|------|
| 応答 | Response | ボットからユーザーへの返答 |
| フィードバック | Feedback | 処理中を示す「考え中...」等のメッセージ |
| エラーメッセージ | Error Message | 処理失敗時の通知 |
| 認証リンク | Auth Link | Google 認証のための URL |

### 対話パターン

| パターン | 説明 |
|---------|------|
| 即時応答 | メンションに対して即座に反応を返す |
| 段階的フィードバック | 「考え中...」→ 結果に更新 |
| スレッド返信 | 元のメッセージのスレッドに返信 |
| エラーリカバリー | エラー時も適切なメッセージを返す |

## 英語・日本語対応表

### システムコンポーネント

| 日本語 | 英語 | 略称 |
|--------|------|------|
| 受信者 | Receiver | - |
| 作業者 | Worker | - |
| エージェント | Agent | - |
| ゲートウェイ | Gateway | GW |
| ランタイム | Runtime | - |

### AWS サービス

| 日本語 | 英語 | 略称 |
|--------|------|------|
| シークレット管理 | Secrets Manager | SM |
| API ゲートウェイ | API Gateway | APIGW |
| ラムダ | Lambda | - |
| ベッドロック | Bedrock | - |

### 操作・アクション

| 日本語 | 英語 | コード |
|--------|------|--------|
| 取得 | Get | `get_events` |
| 作成 | Create | `create_event` |
| 更新 | Update | `update_event` |
| 削除 | Delete | `delete_event` |
| 呼び出し | Invoke | `invoke_agent` |

## コード上の命名規則

### Lambda ハンドラ

```python
def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda エントリポイント"""
```

### 環境変数

```python
SLACK_SECRET_ARN = "..."      # ARN は大文字スネークケース
AGENTCORE_RUNTIME_ID = "..."
AWS_REGION = "..."
```

### クラス名

```python
class SlackClient:            # PascalCase
class AgentCoreClient:
class CalendarHandler:
```

### メソッド名

```python
def get_events():            # snake_case、動詞 + 名詞
def create_event():
def post_message():
def verify_signature():
```

### 変数名

```python
user_message = "..."         # snake_case
slack_event = {}
agent_response = ""
thread_ts = "..."            # Slack 由来は原語維持
```

### 定数

```python
SLACK_SESSION_NAMESPACE = uuid.UUID("...")  # UPPER_SNAKE_CASE
MAX_RETRY_COUNT = 3
DEFAULT_TIMEOUT = 30
```
