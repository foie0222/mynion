#!/usr/bin/env python3
import os
import aws_cdk as cdk
from agentcore_runtime import MynionStack

app = cdk.App()

# Create the Mynion stack
# Deploy to ap-northeast-1 (Tokyo) region
MynionStack(
    app,
    "MynionStack",
    env=cdk.Environment(
        account=os.getenv("CDK_DEFAULT_ACCOUNT"),
        region="ap-northeast-1",
    ),
    description="Stack for deploying Mynion Strands Agent to AWS Bedrock AgentCore Runtime",
)

app.synth()
