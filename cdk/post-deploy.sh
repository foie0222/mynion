#!/bin/bash
# post-deploy.sh
#
# CDK deploy 後に実行するスクリプト
# Workload Identity の allowedResourceOauth2ReturnUrls を設定する
#
# 使い方:
#   ./post-deploy.sh
#
# 必要な環境変数:
#   AWS_REGION (デフォルト: ap-northeast-1)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AWS_REGION="${AWS_REGION:-ap-northeast-1}"

# 色の定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}Post-deploy: Workload Identity の OAuth callback URL を設定${NC}"
echo "========================================================"
echo ""

# SlackIntegrationStack から OAuth Callback URL を取得
echo -e "${YELLOW}OAuth Callback URL を取得中...${NC}"
CALLBACK_URL=$(aws cloudformation describe-stacks \
    --stack-name SlackIntegrationStack \
    --region "$AWS_REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='OAuthCallbackUrl'].OutputValue" \
    --output text 2>/dev/null)

if [ -z "$CALLBACK_URL" ] || [ "$CALLBACK_URL" = "None" ]; then
    echo -e "${RED}Error: SlackIntegrationStack から OAuthCallbackUrl を取得できませんでした${NC}"
    echo "CDK deploy が完了しているか確認してください"
    exit 1
fi

echo "Callback URL: $CALLBACK_URL"
echo ""

# CloudFormation から Runtime ID を取得
echo -e "${YELLOW}Runtime ID を取得中...${NC}"
RUNTIME_ID=$(aws cloudformation describe-stacks \
    --stack-name AgentCoreStack \
    --region "$AWS_REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='RuntimeId'].OutputValue" \
    --output text 2>/dev/null)

if [ -z "$RUNTIME_ID" ] || [ "$RUNTIME_ID" = "None" ]; then
    echo -e "${RED}Error: AgentCoreStack から RuntimeId を取得できませんでした${NC}"
    echo "CDK deploy が完了しているか確認してください"
    exit 1
fi

echo "Runtime ID: $RUNTIME_ID"
echo ""

# Runtime 情報から Workload Identity ARN を取得
echo -e "${YELLOW}Workload Identity ARN を取得中...${NC}"
RUNTIME_INFO=$(aws bedrock-agentcore-control get-agent-runtime \
    --agent-runtime-id "$RUNTIME_ID" \
    --region "$AWS_REGION" \
    --output json 2>/dev/null)

WORKLOAD_IDENTITY_ARN=$(echo "$RUNTIME_INFO" | jq -r '.workloadIdentityDetails.workloadIdentityArn')
if [ -z "$WORKLOAD_IDENTITY_ARN" ] || [ "$WORKLOAD_IDENTITY_ARN" = "null" ]; then
    echo -e "${RED}Error: Workload Identity ARN を取得できませんでした${NC}"
    exit 1
fi

# ARN から name を抽出
# ARN format: arn:aws:bedrock-agentcore:region:account:workload-identity-directory/default/workload-identity/NAME
WORKLOAD_IDENTITY_NAME=$(echo "$WORKLOAD_IDENTITY_ARN" | awk -F'/' '{print $NF}')

echo "Workload Identity ARN: $WORKLOAD_IDENTITY_ARN"
echo "Workload Identity Name: $WORKLOAD_IDENTITY_NAME"
echo ""

# Workload Identity を更新
echo -e "${YELLOW}Workload Identity の OAuth callback URL を更新中...${NC}"
UPDATE_RESULT=$(aws bedrock-agentcore-control update-workload-identity \
    --name "$WORKLOAD_IDENTITY_NAME" \
    --region "$AWS_REGION" \
    --allowed-resource-oauth2-return-urls "[\"$CALLBACK_URL\"]" \
    2>&1)

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Workload Identity の OAuth callback URL を更新しました${NC}"
    echo ""
    echo "設定内容:"
    echo "  Workload Identity: $WORKLOAD_IDENTITY_NAME"
    echo "  allowedResourceOauth2ReturnUrls: $CALLBACK_URL"
else
    echo -e "${RED}Error: Workload Identity の更新に失敗しました${NC}"
    echo "$UPDATE_RESULT"
    exit 1
fi

echo ""
echo -e "${GREEN}Post-deploy 完了!${NC}"
