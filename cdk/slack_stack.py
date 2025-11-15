"""
CDK Stack for Slack integration with Mynion AgentCore Runtime.

This stack creates:
1. Lambda Receiver (Python) - handles Slack events, returns 200 OK immediately
2. Lambda Worker (Container) - processes events, invokes AgentCore Runtime
3. API Gateway - receives Slack webhooks
4. Secrets Manager - stores Slack credentials
5. IAM Roles - appropriate permissions for all components
"""

from pathlib import Path
from aws_cdk import (
    Stack,
    Duration,
    CfnOutput,
    aws_lambda as lambda_,
    aws_apigateway as apigw,
    aws_secretsmanager as secretsmanager,
    aws_iam as iam,
    aws_logs as logs,
)
from constructs import Construct


class SlackStack(Stack):
    """Stack for Slack integration infrastructure."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        agentcore_runtime_id: str,
        agentcore_endpoint_arn: str,
        **kwargs,
    ) -> None:
        """
        Initialize Slack Stack.

        Args:
            scope: CDK scope
            construct_id: Stack ID
            agentcore_runtime_id: AgentCore Runtime ID from MynionStack
            agentcore_endpoint_arn: AgentCore endpoint ARN from MynionStack
            **kwargs: Additional stack parameters
        """
        super().__init__(scope, construct_id, **kwargs)

        self.agentcore_runtime_id = agentcore_runtime_id
        self.agentcore_endpoint_arn = agentcore_endpoint_arn

        # Get app directory path
        app_dir = Path(__file__).parent.parent / "app" / "slack"

        # Create Secrets Manager secret for Slack credentials
        slack_secret = self._create_slack_secret()

        # Create Lambda Worker (Container Image)
        worker_lambda = self._create_worker_lambda(slack_secret)

        # Create Lambda Receiver (Python)
        receiver_lambda = self._create_receiver_lambda(slack_secret, worker_lambda)

        # Create API Gateway for Slack webhooks
        api = self._create_api_gateway(receiver_lambda)

        # Output important values
        self._create_outputs(api, slack_secret)

    def _create_slack_secret(self) -> secretsmanager.Secret:
        """
        Create Secrets Manager secret for Slack credentials.

        Returns:
            Secret resource
        """
        secret = secretsmanager.Secret(
            self,
            "SlackCredentials",
            description="Slack Bot Token and Signing Secret for Mynion",
            secret_name="mynion/slack/credentials",
            # User must manually set these values after deployment
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"SLACK_BOT_TOKEN": "", "SLACK_SIGNING_SECRET": ""}',
                generate_string_key="placeholder",
            ),
        )

        return secret

    def _create_worker_lambda(
        self, slack_secret: secretsmanager.Secret
    ) -> lambda_.DockerImageFunction:
        """
        Create Lambda Worker from Container Image.

        Args:
            slack_secret: Secrets Manager secret for Slack credentials

        Returns:
            Lambda function
        """
        # Get worker directory
        worker_dir = Path(__file__).parent.parent / "app" / "slack" / "worker"

        # Create execution role for Worker Lambda
        worker_role = iam.Role(
            self,
            "WorkerLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Execution role for Mynion Slack Worker Lambda",
        )

        # CloudWatch Logs permissions
        worker_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "service-role/AWSLambdaBasicExecutionRole"
            )
        )

        # Bedrock AgentCore Runtime invocation permissions
        worker_role.add_to_policy(
            iam.PolicyStatement(
                sid="InvokeAgentCoreRuntime",
                actions=[
                    "bedrock-agent-runtime:InvokeAgent",
                    "bedrock-agentcore:InvokeAgentRuntime",
                    "bedrock-agentcore:InvokeAgentRuntimeForUser",
                ],
                resources=[
                    self.agentcore_endpoint_arn,
                    f"arn:aws:bedrock-agentcore:{Stack.of(self).region}:{Stack.of(self).account}:runtime/{self.agentcore_runtime_id}/*",
                ],
            )
        )

        # Secrets Manager read permissions
        slack_secret.grant_read(worker_role)

        # Create Lambda function from Docker image
        worker_lambda = lambda_.DockerImageFunction(
            self,
            "WorkerLambda",
            code=lambda_.DockerImageCode.from_image_asset(str(worker_dir)),
            timeout=Duration.minutes(5),  # Long timeout for agent processing
            memory_size=1024,
            role=worker_role,
            environment={
                "AGENTCORE_RUNTIME_ID": self.agentcore_runtime_id,
                "AGENTCORE_RUNTIME_ENDPOINT": self.agentcore_endpoint_arn,
                "AWS_REGION": Stack.of(self).region,
                "SLACK_SECRET_ARN": slack_secret.secret_arn,
            },
            log_retention=logs.RetentionDays.ONE_WEEK,
        )

        # Grant permission to read Slack credentials
        slack_secret.grant_read(worker_lambda)

        return worker_lambda

    def _create_receiver_lambda(
        self,
        slack_secret: secretsmanager.Secret,
        worker_lambda: lambda_.DockerImageFunction,
    ) -> lambda_.Function:
        """
        Create Lambda Receiver (Python).

        Args:
            slack_secret: Secrets Manager secret for Slack credentials
            worker_lambda: Worker Lambda to invoke asynchronously

        Returns:
            Lambda function
        """
        # Get receiver code path
        receiver_dir = Path(__file__).parent.parent / "app" / "slack"

        # Create execution role for Receiver Lambda
        receiver_role = iam.Role(
            self,
            "ReceiverLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Execution role for Mynion Slack Receiver Lambda",
        )

        # CloudWatch Logs permissions
        receiver_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "service-role/AWSLambdaBasicExecutionRole"
            )
        )

        # Permission to invoke Worker Lambda
        worker_lambda.grant_invoke(receiver_role)

        # Secrets Manager read permissions
        slack_secret.grant_read(receiver_role)

        # Create Lambda function
        receiver_lambda = lambda_.Function(
            self,
            "ReceiverLambda",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="receiver.handler",
            code=lambda_.Code.from_asset(str(receiver_dir)),
            timeout=Duration.seconds(5),  # Must respond within 3 seconds to Slack
            memory_size=256,
            role=receiver_role,
            environment={
                "WORKER_LAMBDA_ARN": worker_lambda.function_arn,
                "SLACK_SECRET_ARN": slack_secret.secret_arn,
            },
            log_retention=logs.RetentionDays.ONE_WEEK,
        )

        return receiver_lambda

    def _create_api_gateway(
        self, receiver_lambda: lambda_.Function
    ) -> apigw.RestApi:
        """
        Create API Gateway for Slack webhooks.

        Args:
            receiver_lambda: Receiver Lambda to integrate with

        Returns:
            API Gateway REST API
        """
        # Create REST API
        api = apigw.RestApi(
            self,
            "SlackWebhookApi",
            rest_api_name="Mynion Slack Webhook API",
            description="API Gateway for receiving Slack events and commands",
            deploy_options=apigw.StageOptions(
                stage_name="prod",
                throttling_rate_limit=100,  # Slack rate limit consideration
                throttling_burst_limit=200,
                logging_level=apigw.MethodLoggingLevel.INFO,
                data_trace_enabled=True,
            ),
        )

        # Create /slack/events endpoint
        events_resource = api.root.add_resource("slack").add_resource("events")

        # Integrate with Receiver Lambda
        lambda_integration = apigw.LambdaIntegration(
            receiver_lambda,
            proxy=True,
            integration_responses=[
                apigw.IntegrationResponse(
                    status_code="200",
                )
            ],
        )

        # Add POST method
        events_resource.add_method(
            "POST",
            lambda_integration,
            method_responses=[
                apigw.MethodResponse(
                    status_code="200",
                )
            ],
        )

        return api

    def _create_outputs(
        self, api: apigw.RestApi, slack_secret: secretsmanager.Secret
    ):
        """
        Create CloudFormation outputs.

        Args:
            api: API Gateway REST API
            slack_secret: Secrets Manager secret
        """
        CfnOutput(
            self,
            "SlackWebhookUrl",
            value=f"{api.url}slack/events",
            description="Slack Event Subscription URL (use this in Slack App config)",
            export_name=f"{Stack.of(self).stack_name}-SlackWebhookUrl",
        )

        CfnOutput(
            self,
            "SlackSecretArn",
            value=slack_secret.secret_arn,
            description="ARN of Slack credentials secret (set SLACK_BOT_TOKEN and SLACK_SIGNING_SECRET)",
            export_name=f"{Stack.of(self).stack_name}-SlackSecretArn",
        )
