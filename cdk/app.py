#!/usr/bin/env python3
import os

import aws_cdk as cdk
from agentcore_gateway import AgentCoreGatewayStack
from agentcore_runtime import AgentCoreStack
from slack_stack import SlackIntegrationStack

app = cdk.App()

# Common environment
env = cdk.Environment(
    account=os.getenv("CDK_DEFAULT_ACCOUNT"),
    region="ap-northeast-1",
)

# Create the AgentCore Gateway stack first (Calendar tools)
# The Gateway URL will be passed to the Runtime as an environment variable
gateway_stack = AgentCoreGatewayStack(
    app,
    "AgentCoreGatewayStack",
    env=env,
    description="Stack for AgentCore Gateway with Google Calendar tools",
)

# Create the AgentCore Runtime stack
# Receives Gateway URL to enable calendar tools
agentcore_stack = AgentCoreStack(
    app,
    "AgentCoreStack",
    calendar_gateway_url=gateway_stack.gateway_url,
    env=env,
    description="Stack for deploying Mynion Strands Agent to AWS Bedrock AgentCore Runtime",
)

# Runtime depends on Gateway (needs the Gateway URL)
agentcore_stack.add_dependency(gateway_stack)

# Create the Slack integration stack
# This stack depends on the AgentCore stack for runtime ID and ARN
slack_integration_stack = SlackIntegrationStack(
    app,
    "SlackIntegrationStack",
    agentcore_runtime_id=agentcore_stack.agent_runtime_id,
    agentcore_endpoint_arn=agentcore_stack.agent_runtime_arn,
    env=env,
    description="Stack for Slack integration with Mynion AgentCore Runtime",
)

# Slack depends on Runtime
slack_integration_stack.add_dependency(agentcore_stack)

app.synth()
