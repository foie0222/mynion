"""
Example script to invoke the deployed Mynion agent on AWS Bedrock AgentCore Runtime

Usage:
    python invoke_agent.py <runtime_arn> <prompt>

Example:
    python invoke_agent.py arn:aws:bedrock-agentcore:ap-northeast-1:123456789012:runtime/mynion-agent-xxx "機械学習を簡単に説明してください"
"""

import json
import sys
import uuid

import boto3


def invoke_agent(runtime_arn: str, prompt: str, qualifier: str = "production"):
    """
    Invoke the deployed agent on AWS Bedrock AgentCore Runtime

    Args:
        runtime_arn: The ARN of the agent runtime (from cdk deploy output)
        prompt: The user prompt to send to the agent
        qualifier: The endpoint qualifier to use (default: "production", can also use "DEFAULT")
    """
    # Create the AgentCore client
    client = boto3.client("bedrock-agentcore", region_name="ap-northeast-1")

    # Prepare the payload
    payload = json.dumps({"input": {"prompt": prompt}})

    # Generate a unique session ID (must be at least 33 characters)
    session_id = str(uuid.uuid4()) + "-" + str(uuid.uuid4())

    print(f"Invoking agent with session ID: {session_id}")
    print(f"Runtime ARN: {runtime_arn}")
    print(f"Qualifier: {qualifier}")
    print(f"Prompt: {prompt}\n")

    try:
        # Invoke the agent
        response = client.invoke_agent_runtime(
            agentRuntimeArn=runtime_arn,
            runtimeSessionId=session_id,
            payload=payload,
            qualifier=qualifier,
        )

        # Read and parse the response
        response_body = response["response"].read()
        response_data = json.loads(response_body)

        print("Agent Response:")
        print(json.dumps(response_data, indent=2, ensure_ascii=False))

        return response_data

    except Exception as e:
        print(f"Error invoking agent: {e}")
        raise


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    runtime_arn = sys.argv[1]
    prompt = sys.argv[2]
    qualifier = sys.argv[3] if len(sys.argv) > 3 else "production"

    invoke_agent(runtime_arn, prompt, qualifier)
