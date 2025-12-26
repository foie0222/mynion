# GitHub Copilot Instructions for Mynion Project

## 言語設定
**すべてのレビューとコメントは日本語で返信してください。**

## プロジェクト概要
このプロジェクトは、Strands AgentをAWS Bedrock AgentCore Runtimeにデプロイするためのプロジェクトです。

## 技術スタック
- **言語**: Python 3.11+
- **パッケージ管理**: uv
- **インフラ**: AWS CDK (Python)
- **フレームワーク**: Strands Agents (Bedrock AgentCore), FastAPI, Slack Bolt
- **API連携**: Google Calendar API

## プロジェクト構造
- `cdk/` - AWS CDKインフラストラクチャコード
- `interfaces/` - 外部システム連携（Slack等）
- `mcp/` - MCPサーバー実装
- `agent.py` - Strands Agentのメイン実装

## コーディング規約

### Git & Issue Management
- 機能追加やバグ修正を始める前に、GitHub Issueを作成する
- コミットメッセージには必ずIssue番号を含める
  - 例: `Issue #3: カレンダーMCP追加`
- コミットメッセージにClaudeの署名（Co-Authored-By等）は**含めない**
- PRを作成する際は変更内容を明確に記載する

### コード品質
- コミット前に `ruff check` を実行すること
- 型チェックは `mypy` で実施すること
- Python型ヒントを必ず使用すること

### MCP使用時の注意
利用可能なMCPサーバー:
- github
- filesystem
- aws-documentation
- cdk-mcp-server
- amazon-bedrock-agentcore-mcp-server

## レビュー時の重点項目
1. **セキュリティ**: 機密情報の漏洩、脆弱性の有無
2. **型安全性**: Python型ヒントの適切な使用
3. **エラーハンドリング**: 適切な例外処理
4. **AWS リソース**: IAMロールやリソースポリシーの最小権限原則
5. **コミットメッセージ**: Issue番号が含まれているか、署名が含まれていないか
6. **依存関係**: 不要な依存の追加を避ける

## コードスタイル
- Ruffの設定に従う
- 既存のコードスタイルと一貫性を保つ
- 必要に応じてコメントは日本語で記述可能
