# Mynion Project Rules

## Git & Issue Management
- Git操作は必ずGitHub MCPを使用する（bash gitコマンドは使わない）
- 機能追加やバグ修正を始める前に、GitHub Issueを作成する
- 作業時は `git worktree` を使用してブランチごとに別ディレクトリで作業する
- worktreeのフォルダ名はissue番号に合わせる（例: `issue-3`, `issue-12`）
- コミットメッセージにはIssue番号を含める（例: "Issue #3: カレンダーMCP追加"）
- コミットメッセージにClaudeの署名（Co-Authored-By等）は含めない
- PRを作成する際は変更内容を明確に記載する

## MCP Usage
- 利用可能なMCPサーバー: github, filesystem, aws-documentation, cdk-mcp-server, amazon-bedrock-agentcore-mcp-server
- ファイル操作はfilesystem MCPを優先使用
- GitHub操作（issue, PR, code search等）はgithub MCPを使用
- AWSドキュメント参照はaws-documentation MCPを使用

## Development Workflow
- Python 3.11+ を使用
- パッケージ管理は uv を使用
- コミット前に `ruff check` を実行
- 型チェックは `mypy` で実施

## Project Structure
- `cdk/` - AWS CDKインフラストラクチャコード
- `interfaces/` - 外部システム連携（Slack等）
- `mcp/` - MCPサーバー実装
- `agent.py` - Strands Agentのメイン実装

## Technology Stack
- AWS CDK (Python) for infrastructure
- Strands Agents (Bedrock AgentCore)
- Slack Bolt for Slack integration
- Google Calendar API for calendar features
- FastAPI + Uvicorn for API server
