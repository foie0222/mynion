"""
AgentCore Runtime client for invoking the Mynion agent.

Uses bedrock-agentcore service to invoke AgentCore Runtime endpoints.
Handles streaming responses and session management.
"""

import json
import logging
from typing import Any

import boto3
from botocore.config import Config

logger = logging.getLogger()


class AgentCoreClient:
    """Client for interacting with AgentCore Runtime via boto3."""

    def __init__(self, endpoint_arn: str, region: str):
        """
        Initialize AgentCore client.

        Args:
            endpoint_arn: AgentCore Runtime endpoint ARN
            region: AWS region
        """
        self.endpoint_arn = endpoint_arn
        self.region = region

        config = Config(
            read_timeout=300,
            connect_timeout=10,
            retries={"max_attempts": 2, "mode": "standard"},
        )

        self.client = boto3.client(
            "bedrock-agentcore",
            region_name=region,
            config=config,
        )

    def invoke_agent(self, user_id: str, session_id: str, input_text: str) -> dict[str, Any] | str:
        """
        Invoke the AgentCore Runtime.

        Args:
            user_id: User identifier (slack-{team_id}-{user_id})
            session_id: Session identifier (slack-{thread_id})
            input_text: User's input message

        Returns:
            Response from AgentCore Runtime
        """
        try:
            logger.info(f"Invoking agent: session={session_id}, user={user_id}")

            payload = json.dumps({"input": {"prompt": input_text}}).encode()

            response = self.client.invoke_agent_runtime(
                agentRuntimeArn=self.endpoint_arn,
                runtimeSessionId=session_id,
                payload=payload,
            )

            logger.info("Agent response received")

            # Parse and return the response directly (no wrapper)
            return self._parse_response(response)

        except Exception as e:
            logger.error(f"Error invoking agent: {str(e)}", exc_info=True)
            raise

    def _parse_response(self, response: dict[str, Any]) -> dict[str, Any] | str:
        """
        Parse response from AgentCore Runtime.

        Args:
            response: Response from invoke_agent_runtime API

        Returns:
            Parsed response (str for streaming, dict for JSON)
        """
        try:
            content_type = response.get("contentType", "")
            logger.info(f"Response content type: {content_type}")

            if "text/event-stream" in content_type:
                content = []
                for line in response["response"].iter_lines(chunk_size=10):
                    if line:
                        line_str = line.decode("utf-8")
                        if line_str.startswith("data: "):
                            data = line_str[6:]
                            content.append(data)
                            logger.debug(f"Received chunk: {data}")

                result = "\n".join(content) if content else "応答がありませんでした。"
                logger.info(f"Complete response received: {len(content)} chunks")
                return result

            elif content_type == "application/json":
                content = []
                for chunk in response.get("response", []):
                    content.append(chunk.decode("utf-8"))
                parsed: dict[str, Any] = json.loads("".join(content))
                return parsed

            else:
                logger.warning(f"Unexpected content type: {content_type}")
                return str(response)

        except Exception as e:
            logger.error(f"Error parsing response: {str(e)}", exc_info=True)
            return f"レスポンスのパースに失敗しました: {str(e)}"
