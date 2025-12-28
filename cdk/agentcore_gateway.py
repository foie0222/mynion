"""CDK Stack for AgentCore Gateway with Google Calendar Lambda Target.

This stack creates:
- Lambda function for Google Calendar operations
- AgentCore Gateway for MCP protocol
- Lambda Target for calendar tools

OAuth Authentication Flow:
1. Agent (agent.py) uses AgentCore Identity to obtain Google OAuth token
2. Agent passes access_token as a tool parameter to MCP calls
3. Gateway invokes Lambda using IAM role (GATEWAY_IAM_ROLE)
4. Lambda uses access_token to authenticate with Google Calendar API

Reference: https://dev.classmethod.jp/articles/amazon-bedrock-agentcore-gateway-lambda-tool/

Note: The OAuth Credential Provider (GoogleCalendarProvider) is created separately
via AgentCore Identity CLI, not in this CDK stack. The agent handles the OAuth
flow including user consent and token refresh.
"""

from pathlib import Path

from aws_cdk import BundlingOptions, CfnOutput, Duration, Stack
from aws_cdk import aws_bedrockagentcore as agentcore
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from constructs import Construct


class AgentCoreGatewayStack(Stack):
    """Stack for AgentCore Gateway with Google Calendar tools."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Path to the Lambda code
        lambda_code_path = Path(__file__).parent.parent / "mcp" / "calendar"

        # Create Lambda function for Calendar operations
        calendar_lambda = lambda_.Function(
            self,
            "CalendarToolsLambda",
            function_name="mynion-calendar-tools",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset(
                str(lambda_code_path),
                bundling=BundlingOptions(
                    image=lambda_.Runtime.PYTHON_3_11.bundling_image,
                    command=[
                        "bash",
                        "-c",
                        "pip install -r requirements.txt -t /asset-output && cp -au . /asset-output",
                    ],
                ),
            ),
            timeout=Duration.seconds(30),
            memory_size=256,
            description="Lambda function for Google Calendar MCP tools",
        )

        # IAM role for Gateway execution
        gateway_execution_role = iam.Role(
            self,
            "GatewayExecutionRole",
            assumed_by=iam.ServicePrincipal(
                "bedrock-agentcore.amazonaws.com",
                conditions={
                    "StringEquals": {"aws:SourceAccount": Stack.of(self).account},
                    "ArnLike": {
                        "aws:SourceArn": f"arn:aws:bedrock-agentcore:{Stack.of(self).region}:{Stack.of(self).account}:*"
                    },
                },
            ),
            description="Execution role for AgentCore Gateway",
        )

        # Grant Gateway role permission to invoke Lambda
        # Note: OAuth is handled by the agent, not the Gateway. The Gateway only needs
        # permission to invoke the Lambda function using IAM authentication.
        calendar_lambda.grant_invoke(gateway_execution_role)

        # Create AgentCore Gateway
        # authorizer_type="NONE" means the Gateway itself doesn't require authentication.
        # The agent authenticates with Google via AgentCore Identity and passes the
        # access_token as a tool parameter.
        gateway = agentcore.CfnGateway(
            self,
            "CalendarGateway",
            name="mynion-calendar-gateway",
            protocol_type="MCP",
            authorizer_type="NONE",
            role_arn=gateway_execution_role.role_arn,
            description="Gateway for Google Calendar MCP tools",
            protocol_configuration=agentcore.CfnGateway.GatewayProtocolConfigurationProperty(
                mcp=agentcore.CfnGateway.MCPGatewayConfigurationProperty(
                    instructions="Google Calendar tools for listing, creating, updating, and deleting calendar events.",
                    search_type="SEMANTIC",
                    supported_versions=["2025-06-18"],
                )
            ),
        )

        # Create Lambda Target with tool schemas
        # Reference: https://dev.classmethod.jp/articles/amazon-bedrock-agentcore-gateway-lambda-tool/
        #
        # Tool schema format follows the article pattern:
        # - Each tool has name, description, and inputSchema
        # - inputSchema defines type: object with properties and required fields
        # - access_token is passed by the agent after obtaining OAuth token via AgentCore Identity
        #
        # credential_provider_type="GATEWAY_IAM_ROLE" means the Gateway uses its IAM role
        # to invoke the Lambda (not for Google OAuth, which is handled by the agent).
        calendar_target = agentcore.CfnGatewayTarget(
            self,
            "CalendarLambdaTarget",
            name="calendar-tools",
            gateway_identifier=gateway.attr_gateway_identifier,
            target_configuration=agentcore.CfnGatewayTarget.TargetConfigurationProperty(
                mcp=agentcore.CfnGatewayTarget.McpTargetConfigurationProperty(
                    lambda_=agentcore.CfnGatewayTarget.McpLambdaTargetConfigurationProperty(
                        lambda_arn=calendar_lambda.function_arn,
                        tool_schema=agentcore.CfnGatewayTarget.ToolSchemaProperty(
                            inline_payload=[
                                # list_events: List calendar events within a time range
                                agentcore.CfnGatewayTarget.ToolDefinitionProperty(
                                    name="list_events",
                                    description="List calendar events within a time range. Returns events from the user's primary calendar.",
                                    input_schema=agentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                        type="object",
                                        properties={
                                            "access_token": agentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="Google OAuth access token",
                                            ),
                                            "time_min": agentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="Start time in ISO format (default: now)",
                                            ),
                                            "time_max": agentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="End time in ISO format (default: 7 days from now)",
                                            ),
                                            "max_results": agentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="integer",
                                                description="Maximum number of events (default: 10)",
                                            ),
                                        },
                                        required=["access_token"],
                                    ),
                                ),
                                # create_event: Create a new calendar event
                                agentcore.CfnGatewayTarget.ToolDefinitionProperty(
                                    name="create_event",
                                    description="Create a new calendar event with the specified title, start time, and end time.",
                                    input_schema=agentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                        type="object",
                                        properties={
                                            "access_token": agentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="Google OAuth access token",
                                            ),
                                            "summary": agentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="Title of the event",
                                            ),
                                            "start_time": agentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="Start time in ISO format (e.g., 2024-12-01T10:00:00+09:00)",
                                            ),
                                            "end_time": agentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="End time in ISO format",
                                            ),
                                            "description": agentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="Description of the event (optional)",
                                            ),
                                            "location": agentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="Location of the event (optional)",
                                            ),
                                            "timezone": agentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="Timezone (e.g., Asia/Tokyo). Default: Asia/Tokyo",
                                            ),
                                        },
                                        required=["access_token", "summary", "start_time", "end_time"],
                                    ),
                                ),
                                # update_event: Update an existing calendar event
                                agentcore.CfnGatewayTarget.ToolDefinitionProperty(
                                    name="update_event",
                                    description="Update an existing calendar event. Only provided fields will be updated.",
                                    input_schema=agentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                        type="object",
                                        properties={
                                            "access_token": agentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="Google OAuth access token",
                                            ),
                                            "event_id": agentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="ID of the event to update",
                                            ),
                                            "summary": agentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="New title of the event (optional)",
                                            ),
                                            "start_time": agentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="New start time in ISO format (optional)",
                                            ),
                                            "end_time": agentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="New end time in ISO format (optional)",
                                            ),
                                            "description": agentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="New description (optional)",
                                            ),
                                            "location": agentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="New location (optional)",
                                            ),
                                            "timezone": agentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="Timezone for the event (optional)",
                                            ),
                                        },
                                        required=["access_token", "event_id"],
                                    ),
                                ),
                                # delete_event: Delete a calendar event
                                agentcore.CfnGatewayTarget.ToolDefinitionProperty(
                                    name="delete_event",
                                    description="Delete a calendar event by its ID.",
                                    input_schema=agentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                        type="object",
                                        properties={
                                            "access_token": agentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="Google OAuth access token",
                                            ),
                                            "event_id": agentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="ID of the event to delete",
                                            ),
                                        },
                                        required=["access_token", "event_id"],
                                    ),
                                ),
                            ]
                        ),
                    )
                )
            ),
            credential_provider_configurations=[
                agentcore.CfnGatewayTarget.CredentialProviderConfigurationProperty(
                    credential_provider_type="GATEWAY_IAM_ROLE",
                )
            ],
            description="Lambda target for Google Calendar tools",
        )

        # Ensure target is created after gateway
        calendar_target.add_dependency(gateway)

        # Outputs
        CfnOutput(
            self,
            "GatewayArn",
            value=gateway.attr_gateway_arn,
            description="ARN of the Calendar Gateway",
            export_name=f"{Stack.of(self).stack_name}-GatewayArn",
        )

        CfnOutput(
            self,
            "GatewayUrl",
            value=gateway.attr_gateway_url,
            description="MCP endpoint URL for the Calendar Gateway",
            export_name=f"{Stack.of(self).stack_name}-GatewayUrl",
        )

        CfnOutput(
            self,
            "CalendarLambdaArn",
            value=calendar_lambda.function_arn,
            description="ARN of the Calendar Lambda function",
            export_name=f"{Stack.of(self).stack_name}-CalendarLambdaArn",
        )

        # Expose for other stacks
        self.gateway_url = gateway.attr_gateway_url
        self.gateway_arn = gateway.attr_gateway_arn
