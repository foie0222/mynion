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

    def invoke_agent(self, user_id: str, session_id: str, input_text: str) -> dict[str, Any]:
        """
        Invoke the AgentCore Runtime.

        Args:
            user_id: User identifier (slack-{team_id}-{user_id})
            session_id: Session identifier (slack-{thread_id})
            input_text: User's input message

        Returns:
            Agent response with output text and metadata
        """
        try:
            logger.info(f"Invoking agent: session={session_id}, user={user_id}")

            payload = json.dumps({"prompt": input_text}).encode()

            response = self.client.invoke_agent_runtime(
                agentRuntimeArn=self.endpoint_arn,
                runtimeSessionId=session_id,
                payload=payload,
            )

            logger.info("Agent response received")

            agent_output = self._parse_streaming_response(response)

            return {
                "output": agent_output,
                "requires_auth": False,
                "session_id": session_id,
            }

        except self.client.exceptions.AccessDeniedException as e:
            logger.error(f"Access denied - may need OAuth: {str(e)}")
            return {
                "requires_auth": True,
                "error": str(e),
            }

        except Exception as e:
            logger.error(f"Error invoking agent: {str(e)}", exc_info=True)
            raise

    def _parse_streaming_response(self, response: dict[str, Any]) -> str:
        """
        Parse streaming response from AgentCore Runtime.

        Args:
            response: Response from invoke_agent_runtime API

        Returns:
            Complete response text
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
                return json.loads("".join(content))

            else:
                logger.warning(f"Unexpected content type: {content_type}")
                return str(response)

        except Exception as e:
            logger.error(f"Error parsing response: {str(e)}", exc_info=True)
            return f"レスポンスのパースに失敗しました: {str(e)}"
