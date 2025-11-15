#!/usr/bin/env python3
import os

import aws_cdk as cdk
from agentcore_runtime import MynionStack
from slack_stack import SlackStack

app = cdk.App()

# Common environment
env = cdk.Environment(
    account=os.getenv("CDK_DEFAULT_ACCOUNT"),
    region="ap-northeast-1",
)

# Create the Mynion AgentCore Runtime stack
mynion_stack = MynionStack(
    app,
    "MynionStack",
    env=env,
    description="Stack for deploying Mynion Strands Agent to AWS Bedrock AgentCore Runtime",
)

# Create the Slack integration stack
# This stack depends on the Mynion stack for runtime ID and endpoint ARN
slack_stack = SlackStack(
    app,
    "MynionSlackStack",
    agentcore_runtime_id=mynion_stack.agent_runtime_id,
    agentcore_endpoint_arn=mynion_stack.prod_endpoint.agent_runtime_endpoint_arn,
    env=env,
    description="Stack for Slack integration with Mynion AgentCore Runtime",
)

# Add explicit dependency
slack_stack.add_dependency(mynion_stack)

app.synth()
