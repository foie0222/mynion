#!/usr/bin/env python3
import os

import aws_cdk as cdk

from cdk.agentcore_runtime import AgentCoreStack
from cdk.slack_stack import SlackIntegrationStack

app = cdk.App()

# Common environment
env = cdk.Environment(
    account=os.getenv("CDK_DEFAULT_ACCOUNT"),
    region="ap-northeast-1",
)

# Create the AgentCore Runtime stack
agentcore_stack = AgentCoreStack(
    app,
    "AgentCoreStack",
    env=env,
    description="Stack for deploying Mynion Strands Agent to AWS Bedrock AgentCore Runtime",
)

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

# Add explicit dependency
slack_integration_stack.add_dependency(agentcore_stack)

app.synth()
