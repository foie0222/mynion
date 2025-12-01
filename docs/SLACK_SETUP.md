# Slack App設定ガイド - Mynion

このガイドでは、MynionエージェントをSlack Appとして設定する手順を説明します。

## 前提条件

- AWSアカウントとCDKのセットアップ完了
- Slackワークスペースの管理者権限
- AgentCoreStack（AgentCore Runtime）のデプロイ完了

## 📐 アーキテクチャ

```
Slack Event → API Gateway → Lambda Receiver (200 OK即返却)
  ↓ (非同期invoke)
Lambda Worker (Container)
  ↓ (boto3 + User-Id Header)
AgentCore Runtime
```

- **Lambda Receiver**: Slackの3秒ルールを守るため、即座に200 OKを返却
- **Lambda Worker**: 非同期でAgentCore Runtimeを呼び出し、結果をSlackに送信
- **セッションID**: `slack-{thread_id}` （1スレッド = 1セッション）
- **ユーザーID**: `slack-{team_id}-{user_id}` （AgentCore Identity用）

## 📋 設定手順

### 1. インフラのデプロイ

まず、Slack統合スタックをデプロイします。

```bash
# 依存関係のインストール
uv sync

# CDKスタックのデプロイ
cd cdk
cdk deploy AgentCoreStack        # AgentCore Runtime（既にデプロイ済みの場合はスキップ）
cdk deploy SlackIntegrationStack # Slack統合インフラ
```

デプロイ完了後、以下の出力を控えておきます：
- `SlackWebhookUrl`: Slackイベントを受け取るURL
- `SlackSecretArn`: Slackクレデンシャルを保存するSecrets ManagerのARN

### 2. Slack Appの作成

#### 2.1. Slack APIサイトでアプリを作成

1. [Slack API](https://api.slack.com/apps)にアクセス
2. **「Create New App」**をクリック
3. **「From scratch」**を選択
4. App Name: `Mynion`（任意の名前）
5. Workspace: 使用するワークスペースを選択
6. **「Create App」**をクリック

#### 2.2. Bot User OAuth Tokenの取得

1. 左サイドバーの **「OAuth & Permissions」** を選択
2. **「Scopes」** セクションまでスクロール
3. **「Bot Token Scopes」** に以下を追加：
   - `app_mentions:read` - メンションを読み取る
   - `chat:write` - メッセージを送信
   - `chat:write.public` - パブリックチャネルに送信
   - `channels:history` - パブリックチャネルのメッセージを読み取る

4. ページ上部の **「Install to Workspace」** をクリック
5. 権限を確認して **「Allow」** をクリック
6. **「Bot User OAuth Token」** (`xoxb-...`で始まる) をコピー

#### 2.3. Signing Secretの取得

1. 左サイドバーの **「Basic Information」** を選択
2. **「App Credentials」** セクションを探す
3. **「Signing Secret」** の **「Show」** をクリック
4. Signing Secretをコピー

### 3. AWS Secrets Managerにクレデンシャルを設定

```bash
# Secrets Managerにトークンを保存
aws secretsmanager put-secret-value \
  --secret-id mynion/slack/credentials \
  --secret-string '{
    "SLACK_BOT_TOKEN": "xoxb-your-bot-token-here",
    "SLACK_SIGNING_SECRET": "your-signing-secret-here"
  }' \
  --region ap-northeast-1
```

または、AWSコンソールから：

1. [Secrets Manager Console](https://console.aws.amazon.com/secretsmanager/)を開く
2. `mynion/slack/credentials`を検索
3. **「Retrieve secret value」** → **「Edit」** をクリック
4. 以下のJSON形式で値を設定：

```json
{
  "SLACK_BOT_TOKEN": "xoxb-your-bot-token-here",
  "SLACK_SIGNING_SECRET": "your-signing-secret-here"
}
```

5. **「Save」** をクリック

### 4. Slack AppにWebhook URLを設定

#### 4.1. Event Subscriptionsの有効化

1. Slack App設定ページの左サイドバーから **「Event Subscriptions」** を選択
2. **「Enable Events」** をONに切り替え
3. **「Request URL」** に、CDKデプロイで出力された`SlackWebhookUrl`を入力
   - 例: `https://xxxxxxxxxx.execute-api.ap-northeast-1.amazonaws.com/prod/slack/events`
4. URLが検証されると **「Verified」** と表示されます ✅

#### 4.2. Bot Eventsの購読

**「Subscribe to bot events」** セクションで以下を追加：

- `app_mention` - ボットがメンションされた時

#### 4.3. 変更を保存

**「Save Changes」** をクリック

### 5. アプリをワークスペースに再インストール

イベント設定を追加した後、アプリを再インストールする必要があります：

1. **「OAuth & Permissions」** ページに移動
2. ページ上部に表示される **「Reinstall to Workspace」** をクリック
3. 権限を確認して **「Allow」** をクリック

## ✅ 動作確認

### テスト1: App Mention

1. Slackの任意のチャネルにMynionを招待：`/invite @Mynion`
2. ボットにメンション：`@Mynion こんにちは`
3. ボットが応答することを確認

### テスト2: DM

1. SlackでMynionにDMを送信
2. ボットが応答することを確認

### テスト3: Slash Command

1. チャネルで `/mynion 今日の予定を教えて` を実行
2. ボットが応答することを確認

## 🔍 トラブルシューティング

### Webhook URLが検証されない

**症状**: Event Subscriptions設定で「Request URL」の検証に失敗する

**解決方法**:
1. Lambda Receiver関数のCloudWatch Logsを確認
2. `SLACK_SIGNING_SECRET`が正しく設定されているか確認
3. API Gatewayのログを確認（`/aws/apigateway/...`）

```bash
# Receiver Lambdaのログを確認
aws logs tail /aws/lambda/SlackIntegrationStack-ReceiverLambda... --follow
```

### ボットが応答しない

**症状**: メンションしても応答がない

**解決方法**:
1. Worker Lambda関数のCloudWatch Logsを確認
2. `SLACK_BOT_TOKEN`が正しく設定されているか確認
3. Receiver LambdaがWorker Lambdaを呼び出しているか確認

```bash
# Worker Lambdaのログを確認
aws logs tail /aws/lambda/SlackIntegrationStack-WorkerLambda... --follow
```

### AgentCore Runtime呼び出しエラー

**症状**: ボットは応答するが、エージェントが動作しない

**解決方法**:
1. Worker LambdaのIAM権限を確認
2. AgentCore Runtime Endpointが正しく設定されているか確認
3. セッションIDとユーザーIDのフォーマットを確認

```bash
# Worker Lambdaの環境変数を確認
aws lambda get-function-configuration \
  --function-name SlackIntegrationStack-WorkerLambda... \
  --query 'Environment.Variables'
```

## 🔐 セキュリティ

### Secrets Rotation

定期的にSlackトークンをローテーションすることを推奨します：

1. Slack APIで新しいTokenを生成
2. Secrets Managerを更新
3. Lambda関数が自動的に新しいトークンを使用（キャッシュクリアのため再起動が必要な場合あり）

### アクセス制御

- ワークスペース内で誰がボットを使用できるかを管理
- 機密情報へのアクセスが必要な場合は、AgentCore Identityで個別のOAuth認証を実施

## 📚 次のステップ

1. **AgentCore Identity設定**: Google Calendar/GmailへのOAuth認証を設定
2. **カスタムツールの追加**: エージェントに追加機能を実装
3. **モニタリング**: CloudWatch DashboardやAlarmsを設定

## 🆘 サポート

問題が発生した場合は、以下を確認してください：

- [Slack API Documentation](https://api.slack.com/docs)
- [AWS Bedrock AgentCore Documentation](https://docs.aws.amazon.com/bedrock-agentcore/)
- プロジェクトのissues: [GitHub Issues](https://github.com/your-repo/issues)
