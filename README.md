# Mynion - Strands Agent on AWS Bedrock AgentCore

このプロジェクトは、Strands AgentをAWS Bedrock AgentCore Runtimeにデプロイするためのものです。

## プロジェクト構造

```
mynion/
├── agent.py                 # FastAPIベースのStrands Agentアプリケーション
├── Dockerfile               # ARM64対応のDockerイメージ定義
├── pyproject.toml           # Pythonプロジェクトの依存関係
├── uv.lock                  # uvロックファイル
└── cdk/                     # AWS CDKインフラストラクチャコード
    ├── app.py               # CDKアプリケーションのエントリーポイント
    ├── agentcore_runtime.py # AgentCore Runtimeスタック定義
    ├── cdk.json             # CDK設定
    └── requirements.txt     # CDK依存関係
```

## 前提条件

1. **Python 3.11以上**
2. **uv** (Pythonパッケージマネージャー)
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

3. **Node.js** (CDK CLIに必要)
4. **AWS CLI** (設定済み)
   ```bash
   aws configure
   ```

5. **AWS CDK CLI**
   ```bash
   npm install -g aws-cdk
   ```

6. **Docker** (ローカルテスト用)

## ローカルでのテスト

デプロイ前にローカルでエージェントをテストできます：

```bash
# 依存関係のインストール
uv sync

# アプリケーションの起動
uv run uvicorn agent:app --host 0.0.0.0 --port 8080

# 別のターミナルでテスト
# /pingエンドポイント
curl http://localhost:8080/ping

# /invocationsエンドポイント
curl -X POST http://localhost:8080/invocations \
  -H "Content-Type: application/json" \
  -d '{
    "input": {"prompt": "人工知能とは何ですか？"}
  }'
```

## AWSへのデプロイ

### 1. AWS認証情報の設定

```bash
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
export AWS_REGION="ap-northeast-1"
```

### 2. CDK Bootstrap（初回のみ）

CDKを初めて使用するAWSアカウント/リージョンの場合、bootstrapが必要です：

```bash
cd cdk
cdk bootstrap aws://ACCOUNT-ID/ap-northeast-1
```

### 3. CDK依存関係のインストール

```bash
cd cdk
uv pip install --prerelease=allow -r requirements.txt
```

注：`aws-cdk-aws-bedrock-agentcore-alpha`はalphaパッケージなので、`--prerelease=allow`フラグが必要です。

### 4. CDKスタックのシンセサイズ

CloudFormationテンプレートを生成して確認：

```bash
cdk synth
```

### 5. デプロイ

```bash
cdk deploy
```

デプロイには数分かかります。以下の処理が行われます：
- Dockerイメージのビルド（ARM64対応）
- ECRリポジトリの作成とイメージのプッシュ
- IAM実行ロールの作成（Bedrockモデルへのアクセス権限付き）
- AgentCore Runtimeの作成
- Productionエンドポイントの作成

### 6. デプロイ完了後の情報確認

デプロイが完了すると、以下の情報が出力されます：
- Runtime ARN
- Endpoint ARN

これらの情報を使ってエージェントを呼び出すことができます。

## エージェントの呼び出し

デプロイ後、以下のようにエージェントを呼び出すことができます：

```python
import boto3
import json

# クライアントの作成
client = boto3.client('bedrock-agentcore', region_name='ap-northeast-1')

# エージェントの呼び出し
payload = json.dumps({
    "input": {"prompt": "機械学習を簡単に説明してください"}
})

response = client.invoke_agent_runtime(
    agentRuntimeArn='<YOUR_RUNTIME_ARN>',  # cdk deployの出力から取得
    runtimeSessionId='unique-session-id-at-least-33-characters-long',
    payload=payload,
    qualifier="production"  # または "DEFAULT"
)

# レスポンスの読み取り
response_body = response['response'].read()
response_data = json.loads(response_body)
print("Agent Response:", response_data)
```

## スタックの削除

リソースを削除する場合：

```bash
cd cdk
cdk destroy
```

## アーキテクチャ

このプロジェクトは以下のAWSリソースを使用します：

1. **Amazon ECR**: Dockerイメージのストレージ
2. **AWS Bedrock AgentCore Runtime**: エージェントの実行環境
3. **IAM Role**: AgentCore Runtimeの実行ロール（Bedrockモデルへのアクセス権限付き）
4. **Runtime Endpoints**: エージェントへのアクセスポイント

## セキュリティのベストプラクティス

- IAMロールは最小権限の原則に従っています
- Bedrockモデルへのアクセスは必要な操作のみに制限できます（`cdk/agentcore_runtime.py`の`resources`を編集）
- VPCデプロイも可能です（`RuntimeNetworkConfiguration.using_vpc()`を使用）

## トラブルシューティング

### Docker BuildXが利用できない

```bash
docker buildx create --use
```

### CDK Bootstrapエラー

AWS CLIの認証情報が正しく設定されているか確認してください：

```bash
aws sts get-caller-identity
```

### デプロイ中のタイムアウト

Dockerイメージのビルドとプッシュには時間がかかる場合があります。初回デプロイは特に時間がかかることがあります。

## 参考リンク

- [AWS Bedrock AgentCore Documentation](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/)
- [AWS CDK Python Documentation](https://docs.aws.amazon.com/cdk/api/v2/python/)
- [Strands Agents Documentation](https://pypi.org/project/strands-agents/)
