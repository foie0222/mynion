# タスクリスト

## Phase 3: Calendar Lambda 実装 ✅

- [x] `mcp/calendar/__init__.py` 作成
- [x] `mcp/calendar/handler.py` 作成
  - [x] `get_events` ツール実装
  - [x] `create_event` ツール実装
  - [x] `update_event` ツール実装
  - [x] `delete_event` ツール実装
- [x] Google Calendar API クライアント実装
- [x] Agent側からトークンを受け取る方式に変更（Lambda Targetでは直接OAuth不可のため）

## Phase 4: CDK Stack 実装 ✅

- [x] `cdk/gateway_stack.py` 作成
  - [x] Calendar Lambda 関数定義
  - [x] Gateway Service Role 作成
  - [x] ツールスキーマ定義（CALENDAR_TOOL_SCHEMA）
- [x] `cdk/app.py` に GatewayStack 追加
- [x] Lambda 用 IAM ロール設定
- 注意: CfnGateway/CfnGatewayTarget は L1 コンストラクトがまだ利用不可のため、AWS CLI で別途作成が必要

## Phase 5: Agent 統合 ✅

- [x] `agent.py` を BedrockAgentCoreApp ベースに書き換え
- [x] MCPClient による Gateway 接続
- [x] `@requires_access_token` デコレーターによる OAuth 認証
- [x] StreamingQueue による認証 URL の非同期配信
- [x] AgentCore Identity/Gateway 用 IAM 権限追加

## Phase 6: デプロイ & テスト

### CDK デプロイ ✅

- [x] `cdk deploy GatewayStack` 実行
  - Gateway Endpoint: `https://mynion-calendar-gateway-zqgb38xjtt.gateway.bedrock-agentcore.ap-northeast-1.amazonaws.com/mcp`
  - Cognito OAuth シークレット: `mynion-gateway-cognito`
- [x] `cdk deploy AgentCoreStack` 実行
  - Runtime ID: `mynion_agent-9E5srk7Da4`
- [x] `cdk deploy SlackIntegrationStack` 実行
  - Slack Webhook: `https://3d1x2wj2wk.execute-api.ap-northeast-1.amazonaws.com/prod/slack/events`

### Gateway 動作確認 ✅

- [x] Cognito から OAuth トークン取得成功
- [x] MCP tools/list リクエスト成功
  - `calendar___get_events`
  - `calendar___create_event`
  - `calendar___update_event`
  - `calendar___delete_event`

### 事前設定 ✅

- [x] Google Cloud Console で OAuth 2.0 クライアント作成済み
  - Authorized redirect URI に AgentCore のコールバック URL を追加済み

- [x] AgentCore Identity の OAuth2 Credential Provider 作成済み
  - Provider 名: `GoogleCalendarProvider`

### Agent 更新 ✅

- [x] Agent に Gateway 接続設定を追加
  - Gateway Endpoint: `https://mynion-calendar-gateway-zqgb38xjtt.gateway.bedrock-agentcore.ap-northeast-1.amazonaws.com/mcp`
  - Cognito シークレット: `mynion-gateway-cognito`
  - Google OAuth Provider: `GoogleCalendarProvider`
  - Cognito JWT 認証に対応（`cognito_auth_streamablehttp_client`）
- [x] AuthInjectingMCPClient 実装
  - MCPClient を継承し、calendar ツール呼び出し時に Google OAuth トークンを自動注入
  - トークン未取得時は認証 URL をエラーとして返却

### Workload Identity 設定 ✅

- [x] Workload Identity の `allowedResourceOauth2ReturnUrls` 設定
  - AWS SDK for JS が BedrockAgentCoreControl 未対応のため、AwsCustomResource は使用不可
  - 代わりに `cdk/post-deploy.sh` スクリプトを作成（AWS CLI 使用）
  - CDK デプロイ後に `./cdk/post-deploy.sh` を実行して設定
- [x] cdk.context.json による環境変数管理
  - `mynion:googleCredentialProvider`: OAuth2 Credential Provider 名
  - `mynion:googleOauthCallbackUrl`: AgentCore Identity コールバック URL

## Phase 7: OAuth Callback Endpoint 実装

### 問題の原因

- AgentCore Identity は**セッションバインディング**パターンを要求
- `CompleteResourceTokenAuth` API を呼び出さないとトークン取得が完了しない
- 現状: Google 認証後に `authorizationCode` と `state` が null エラー

### 実装タスク

- [ ] `interfaces/slack/oauth_callback.py` 作成
  - [ ] `session_id` クエリパラメータ取得
  - [ ] `user_id` 取得（`custom_state` から復元）
  - [ ] `CompleteResourceTokenAuth` API 呼び出し
  - [ ] 成功/エラーレスポンス（HTML）

- [ ] `cdk/slack_stack.py` 更新
  - [ ] OAuth Callback Lambda 追加
  - [ ] API Gateway に `/oauth/callback` エンドポイント追加
  - [ ] IAM 権限追加（`CompleteResourceTokenAuth` 用）
  - [ ] CloudFormation Output に Callback URL 追加

- [ ] `cdk/post-deploy.sh` 更新
  - [ ] `allowedResourceOauth2ReturnUrls` を新しい Callback URL に変更

- [ ] `agent.py` 更新
  - [ ] `callback_url` を新しいエンドポイントに変更
  - [ ] `custom_state` パラメータで Slack user_id を渡す

### CDK 再デプロイ

- [ ] `cdk deploy SlackIntegrationStack` 実行
- [ ] `./cdk/post-deploy.sh` 実行
- [ ] Workload Identity の `allowedResourceOauth2ReturnUrls` 確認

### E2E テスト

- [ ] OAuth 認証フローテスト
  - [ ] Slack でカレンダー操作をリクエスト
  - [ ] 認証 URL が表示される
  - [ ] Google で認証
  - [ ] 「認証完了」ページが表示される
  - [ ] 再度カレンダー操作 → 成功
- [ ] E2E テスト（Slack → カレンダー操作）

## 品質チェック ✅

- [x] `ruff check .` パス
- [x] `ruff format --check .` パス
- [x] `mypy .` パス
