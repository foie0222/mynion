"""
AgentCore Runtime client for invoking the Mynion agent.

This client handles:
1. boto3 requests to AgentCore Runtime
2. AWS SigV4 signing for authentication (automatic via boto3)
3. User identity headers for AgentCore Identity
4. Session management
"""

import json
import logging
from typing import Dict, Any
import boto3
from botocore.config import Config

logger = logging.getLogger()


class AgentCoreClient:
    """Client for interacting with AgentCore Runtime via boto3."""

    def __init__(self, runtime_id: str, endpoint_arn: str, region: str):
        """
        Initialize AgentCore client.

        Args:
            runtime_id: AgentCore Runtime ID
            endpoint_arn: AgentCore Runtime endpoint ARN
            region: AWS region
        """
        self.runtime_id = runtime_id
        self.endpoint_arn = endpoint_arn
        self.region = region

        # Configure boto3 client with extended timeout
        config = Config(
            read_timeout=300,  # 5 minutes for long agent responses
            connect_timeout=10,
            retries={"max_attempts": 2, "mode": "standard"},
        )

        # Initialize bedrock-agent-runtime client
        # Note: AgentCore Runtime may use a different service name
        # Adjust if necessary based on actual boto3 API
        self.client = boto3.client(
            "bedrock-agent-runtime",
            region_name=region,
            config=config,
        )

    def invoke_agent(
        self, user_id: str, session_id: str, input_text: str
    ) -> Dict[str, Any]:
        """
        Invoke the AgentCore Runtime with user context.

        Args:
            user_id: User identifier (slack-{team_id}-{user_id})
            session_id: Session identifier (slack-{thread_id})
            input_text: User's input message

        Returns:
            Agent response with output text and metadata
        """
        try:
            logger.info(f"Invoking agent: user={user_id}, session={session_id}")

            # For AgentCore Runtime, we need to pass the user_id header
            # This is typically done via the invoke_agent_runtime API
            # Note: The exact API depends on AgentCore Runtime implementation

            # Extract agent ID and alias from endpoint ARN
            # ARN format: arn:aws:bedrock-agentcore:region:account:runtime/runtime-id/endpoint/endpoint-id
            agent_id = self._extract_agent_id(self.endpoint_arn)
            alias_id = self._extract_alias_id(self.endpoint_arn)

            # Invoke agent with boto3
            # Note: May need to use invoke_agent_for_user or similar API
            # that accepts user_id parameter
            response = self.client.invoke_agent(
                agentId=agent_id,
                agentAliasId=alias_id,
                sessionId=session_id,
                inputText=input_text,
                # Add user context if supported by API
                # Some options:
                # - sessionState with user metadata
                # - custom header configuration
            )

            logger.info(f"Agent response received")

            # Parse the EventStream response
            agent_output = self._parse_agent_response(response)

            return {
                "output": agent_output,
                "requires_auth": False,  # TODO: Detect OAuth requirement from response
                "session_id": session_id,
            }

        except self.client.exceptions.AccessDeniedException as e:
            logger.error(f"Access denied - may need OAuth: {str(e)}")
            # This might indicate OAuth is required
            return {
                "requires_auth": True,
                "auth_url": self._get_auth_url(user_id),  # TODO: Implement
                "provider_name": "Google Calendar",
                "error": str(e),
            }

        except Exception as e:
            logger.error(f"Error invoking agent: {str(e)}", exc_info=True)
            raise

    def _extract_agent_id(self, arn: str) -> str:
        """
        Extract agent ID from ARN.

        Args:
            arn: Agent endpoint ARN

        Returns:
            Agent ID
        """
        # ARN format: arn:aws:bedrock-agentcore:region:account:runtime/runtime-id/...
        # For now, use the runtime_id
        return self.runtime_id

    def _extract_alias_id(self, arn: str) -> str:
        """
        Extract alias ID from ARN.

        Args:
            arn: Agent endpoint ARN

        Returns:
            Alias ID (e.g., "production", "TSTALIASID")
        """
        # This should be extracted from the endpoint ARN or configured separately
        # For now, return a placeholder
        return "production"

    def _parse_agent_response(self, response: Dict[str, Any]) -> str:
        """
        Parse the agent response from Bedrock EventStream.

        Args:
            response: Response from invoke_agent API

        Returns:
            Formatted response text
        """
        try:
            result_text = []

            # Parse EventStream response
            if "completion" in response:
                event_stream = response["completion"]

                for event in event_stream:
                    if "chunk" in event:
                        chunk = event["chunk"]
                        if "bytes" in chunk:
                            result_text.append(chunk["bytes"].decode("utf-8"))

            output = "".join(result_text) if result_text else "応答がありませんでした。"
            return output

        except Exception as e:
            logger.error(f"Error parsing response: {str(e)}", exc_info=True)
            return f"レスポンスのパースに失敗しました: {str(e)}"

    def _get_auth_url(self, user_id: str) -> str:
        """
        Get OAuth authentication URL for user.

        This would typically come from AgentCore Identity response.

        Args:
            user_id: User identifier

        Returns:
            OAuth URL
        """
        # TODO: Implement actual OAuth URL retrieval
        # This should come from AgentCore Identity provider
        return "https://bedrock-agentcore.ap-northeast-1.amazonaws.com/identities/oauth2/authorize?..."
