"""
AgentCore Gateway Stack for Calendar MCP tools.

This stack creates:
- Calendar Lambda function
- Cognito User Pool for OAuth2 authentication
- AgentCore Gateway with CUSTOM_JWT authorizer
- Lambda Target with calendar tools
"""

from pathlib import Path

from aws_cdk import CfnOutput, Duration, RemovalPolicy, SecretValue, Stack
from aws_cdk import aws_bedrockagentcore as agentcore
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from aws_cdk import aws_secretsmanager as secretsmanager
from constructs import Construct


def _create_tool_definitions() -> list[agentcore.CfnGatewayTarget.ToolDefinitionProperty]:
    """Create tool definitions for the calendar Lambda target."""
    return [
        agentcore.CfnGatewayTarget.ToolDefinitionProperty(
            name="get_events",
            description="Get calendar events for a specified date range",
            input_schema=agentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                type="object",
                properties={
                    "access_token": agentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                        type="string",
                        description="Google OAuth2 access token",
                    ),
                    "start_date": agentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                        type="string",
                        description="Start date in YYYY-MM-DD format",
                    ),
                    "end_date": agentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                        type="string",
                        description="End date in YYYY-MM-DD format (optional)",
                    ),
                },
                required=["access_token", "start_date"],
            ),
        ),
        agentcore.CfnGatewayTarget.ToolDefinitionProperty(
            name="create_event",
            description="Create a new calendar event",
            input_schema=agentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                type="object",
                properties={
                    "access_token": agentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                        type="string",
                        description="Google OAuth2 access token",
                    ),
                    "title": agentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                        type="string",
                        description="Event title",
                    ),
                    "start_time": agentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                        type="string",
                        description="Start time in ISO 8601 format",
                    ),
                    "end_time": agentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                        type="string",
                        description="End time in ISO 8601 format (optional)",
                    ),
                    "description": agentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                        type="string",
                        description="Event description (optional)",
                    ),
                    "location": agentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                        type="string",
                        description="Event location (optional)",
                    ),
                },
                required=["access_token", "title", "start_time"],
            ),
        ),
        agentcore.CfnGatewayTarget.ToolDefinitionProperty(
            name="update_event",
            description="Update an existing calendar event",
            input_schema=agentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                type="object",
                properties={
                    "access_token": agentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                        type="string",
                        description="Google OAuth2 access token",
                    ),
                    "event_id": agentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                        type="string",
                        description="ID of the event to update",
                    ),
                    "title": agentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                        type="string",
                        description="New event title (optional)",
                    ),
                    "start_time": agentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                        type="string",
                        description="New start time in ISO 8601 format (optional)",
                    ),
                    "end_time": agentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                        type="string",
                        description="New end time in ISO 8601 format (optional)",
                    ),
                    "description": agentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                        type="string",
                        description="New event description (optional)",
                    ),
                    "location": agentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                        type="string",
                        description="New event location (optional)",
                    ),
                },
                required=["access_token", "event_id"],
            ),
        ),
        agentcore.CfnGatewayTarget.ToolDefinitionProperty(
            name="delete_event",
            description="Delete a calendar event",
            input_schema=agentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                type="object",
                properties={
                    "access_token": agentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                        type="string",
                        description="Google OAuth2 access token",
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


class GatewayStack(Stack):
    """Stack for AgentCore Gateway with Calendar Lambda Target."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Path to calendar Lambda code
        calendar_lambda_path = Path(__file__).parent.parent / "mcp" / "calendar"

        # Create Calendar Lambda function
        calendar_lambda = lambda_.Function(
            self,
            "CalendarLambda",
            function_name="mynion-calendar-mcp",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=lambda_.Code.from_asset(
                str(calendar_lambda_path),
                bundling={
                    "image": lambda_.Runtime.PYTHON_3_12.bundling_image,
                    "command": [
                        "bash",
                        "-c",
                        "pip install -r requirements.txt -t /asset-output && cp -r . /asset-output",
                    ],
                },
            ),
            timeout=Duration.seconds(30),
            memory_size=256,
            description="Calendar MCP Lambda for Google Calendar operations",
            log_retention=logs.RetentionDays.ONE_WEEK,
        )

        # Grant Lambda permission to be invoked by AgentCore Gateway
        calendar_lambda.add_permission(
            "AgentCoreGatewayInvoke",
            principal=iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
            action="lambda:InvokeFunction",
            source_account=Stack.of(self).account,
        )

        # Create Gateway service role
        gateway_service_role = iam.Role(
            self,
            "GatewayServiceRole",
            assumed_by=iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
            description="Service role for AgentCore Gateway",
        )

        # Grant Gateway permission to invoke Lambda
        gateway_service_role.add_to_policy(
            iam.PolicyStatement(
                actions=["lambda:InvokeFunction"],
                resources=[calendar_lambda.function_arn],
            )
        )

        # Create Cognito User Pool for Gateway OAuth authentication
        user_pool = cognito.UserPool(
            self,
            "GatewayUserPool",
            user_pool_name="mynion-gateway-pool",
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Create resource server for OAuth scopes
        resource_server = cognito.UserPoolResourceServer(
            self,
            "GatewayResourceServer",
            user_pool=user_pool,
            identifier="gateway-api",
            scopes=[
                cognito.ResourceServerScope(scope_name="invoke", scope_description="Invoke gateway")
            ],
        )

        # Create OAuth app client with client_credentials flow
        app_client = user_pool.add_client(
            "GatewayOAuthClient",
            generate_secret=True,
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(client_credentials=True),
                scopes=[
                    cognito.OAuthScope.resource_server(
                        resource_server,
                        cognito.ResourceServerScope(
                            scope_name="invoke", scope_description="Invoke gateway"
                        ),
                    )
                ],
            ),
        )

        # Create Cognito domain for token endpoint
        domain = user_pool.add_domain(
            "GatewayDomain",
            cognito_domain=cognito.CognitoDomainOptions(
                domain_prefix=f"mynion-gateway-{Stack.of(self).account}"
            ),
        )

        # Create secret with OAuth credentials for agent to use
        agent_secret = secretsmanager.Secret(
            self,
            "AgentOAuthSecret",
            secret_name="mynion-gateway-cognito",
            secret_object_value={
                "client_id": SecretValue.unsafe_plain_text(app_client.user_pool_client_id),
                "client_secret": app_client.user_pool_client_secret,
                "token_endpoint": SecretValue.unsafe_plain_text(
                    f"https://{domain.domain_name}.auth.{Stack.of(self).region}.amazoncognito.com/oauth2/token"
                ),
                "scope": SecretValue.unsafe_plain_text("gateway-api/invoke"),
            },
        )

        # Create AgentCore Gateway with CUSTOM_JWT authorizer
        gateway = agentcore.CfnGateway(
            self,
            "CalendarGateway",
            name="mynion-calendar-gateway",
            protocol_type="MCP",
            authorizer_type="CUSTOM_JWT",
            role_arn=gateway_service_role.role_arn,
            authorizer_configuration=agentcore.CfnGateway.AuthorizerConfigurationProperty(
                custom_jwt_authorizer=agentcore.CfnGateway.CustomJWTAuthorizerConfigurationProperty(
                    discovery_url=f"https://cognito-idp.{Stack.of(self).region}.amazonaws.com/{user_pool.user_pool_id}/.well-known/openid-configuration",
                    allowed_clients=[app_client.user_pool_client_id],
                ),
            ),
            description="AgentCore Gateway for Calendar MCP tools",
        )
        gateway.node.add_dependency(resource_server)
        gateway.node.add_dependency(app_client)

        # Create Lambda Target with calendar tools
        gateway_target = agentcore.CfnGatewayTarget(
            self,
            "CalendarTarget",
            gateway_identifier=gateway.ref,
            name="calendar",
            credential_provider_configurations=[
                agentcore.CfnGatewayTarget.CredentialProviderConfigurationProperty(
                    credential_provider_type="GATEWAY_IAM_ROLE"
                )
            ],
            target_configuration=agentcore.CfnGatewayTarget.TargetConfigurationProperty(
                mcp=agentcore.CfnGatewayTarget.McpTargetConfigurationProperty(
                    lambda_=agentcore.CfnGatewayTarget.McpLambdaTargetConfigurationProperty(
                        lambda_arn=calendar_lambda.function_arn,
                        tool_schema=agentcore.CfnGatewayTarget.ToolSchemaProperty(
                            inline_payload=_create_tool_definitions(),
                        ),
                    ),
                ),
            ),
            description="Calendar Lambda Target for Google Calendar operations",
        )
        gateway_target.node.add_dependency(gateway)

        # Store references
        self.calendar_lambda_arn = calendar_lambda.function_arn
        self.gateway_service_role_arn = gateway_service_role.role_arn
        self.gateway_id = gateway.ref
        self.gateway_endpoint = gateway.attr_gateway_url
        self.cognito_secret_arn = agent_secret.secret_arn

        # Outputs
        CfnOutput(
            self,
            "CalendarLambdaArn",
            value=calendar_lambda.function_arn,
            description="ARN of the Calendar Lambda function",
            export_name=f"{Stack.of(self).stack_name}-CalendarLambdaArn",
        )

        CfnOutput(
            self,
            "GatewayServiceRoleArn",
            value=gateway_service_role.role_arn,
            description="ARN of the Gateway service role",
            export_name=f"{Stack.of(self).stack_name}-GatewayServiceRoleArn",
        )

        CfnOutput(
            self,
            "GatewayId",
            value=gateway.ref,
            description="ID of the AgentCore Gateway",
            export_name=f"{Stack.of(self).stack_name}-GatewayId",
        )

        CfnOutput(
            self,
            "GatewayEndpoint",
            value=gateway.attr_gateway_url,
            description="Endpoint URL of the AgentCore Gateway",
            export_name=f"{Stack.of(self).stack_name}-GatewayEndpoint",
        )

        CfnOutput(
            self,
            "CognitoSecretArn",
            value=agent_secret.secret_arn,
            description="ARN of the Cognito OAuth secret",
            export_name=f"{Stack.of(self).stack_name}-CognitoSecretArn",
        )
