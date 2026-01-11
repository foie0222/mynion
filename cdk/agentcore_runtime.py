from pathlib import Path

from aws_cdk import CfnOutput, Stack
from aws_cdk import aws_bedrock_agentcore_alpha as agentcore
from aws_cdk import aws_iam as iam
from constructs import Construct


class AgentCoreStack(Stack):
    """Stack for deploying Mynion agent to AWS Bedrock AgentCore Runtime"""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Get the path to the agent directory (parent of cdk directory)
        agent_dir = Path(__file__).parent.parent

        # Create IAM role for the agent runtime
        # This role will be assumed by the AgentCore Runtime to execute the agent
        execution_role = iam.Role(
            self,
            "MynionAgentExecutionRole",
            assumed_by=iam.ServicePrincipal(
                "bedrock-agentcore.amazonaws.com",
                conditions={
                    "StringEquals": {"aws:SourceAccount": Stack.of(self).account},
                    "ArnLike": {
                        "aws:SourceArn": f"arn:aws:bedrock-agentcore:{Stack.of(self).region}:{Stack.of(self).account}:*"
                    },
                },
            ),
            description="Execution role for Mynion agent runtime",
        )

        # ECR permissions for pulling Docker images
        execution_role.add_to_policy(
            iam.PolicyStatement(
                sid="ECRImageAccess",
                actions=[
                    "ecr:BatchGetImage",
                    "ecr:GetDownloadUrlForLayer",
                    "ecr:GetAuthorizationToken",
                ],
                resources=["*"],
            )
        )

        # CloudWatch Logs permissions
        execution_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                    "logs:DescribeLogStreams",
                    "logs:DescribeLogGroups",
                ],
                resources=[
                    f"arn:aws:logs:{Stack.of(self).region}:{Stack.of(self).account}:log-group:/aws/bedrock-agentcore/runtimes/*",
                    f"arn:aws:logs:{Stack.of(self).region}:{Stack.of(self).account}:log-group:*",
                ],
            )
        )

        # X-Ray permissions for tracing
        execution_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "xray:PutTraceSegments",
                    "xray:PutTelemetryRecords",
                    "xray:GetSamplingRules",
                    "xray:GetSamplingTargets",
                ],
                resources=["*"],
            )
        )

        # CloudWatch metrics
        execution_role.add_to_policy(
            iam.PolicyStatement(
                actions=["cloudwatch:PutMetricData"],
                resources=["*"],
                conditions={"StringEquals": {"cloudwatch:namespace": "bedrock-agentcore"}},
            )
        )

        # Grant permissions to invoke Bedrock models
        # The Strands agent needs to call Bedrock foundation models
        execution_role.add_to_policy(
            iam.PolicyStatement(
                sid="BedrockModelInvocation",
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                ],
                resources=[
                    "arn:aws:bedrock:*::foundation-model/*",
                    f"arn:aws:bedrock:{Stack.of(self).region}:{Stack.of(self).account}:*",
                ],
            )
        )

        # Grant permissions for AgentCore Identity (Token Vault access)
        # Required for OAuth2 token retrieval from credential providers
        execution_role.add_to_policy(
            iam.PolicyStatement(
                sid="AgentCoreIdentityAccess",
                actions=[
                    "bedrock-agentcore:GetResourceOauth2Token",
                ],
                resources=[
                    f"arn:aws:bedrock-agentcore:{Stack.of(self).region}:{Stack.of(self).account}:workload-identity-directory/default/workload-identity/*",
                    f"arn:aws:bedrock-agentcore:{Stack.of(self).region}:{Stack.of(self).account}:token-vault/default/oauth2credentialprovider/*",
                    f"arn:aws:bedrock-agentcore:{Stack.of(self).region}:{Stack.of(self).account}:workload-identity-directory/default",
                    f"arn:aws:bedrock-agentcore:{Stack.of(self).region}:{Stack.of(self).account}:token-vault/default",
                ],
            )
        )

        # Grant permissions to read OAuth2 credential provider secrets
        execution_role.add_to_policy(
            iam.PolicyStatement(
                sid="SecretsManagerAccess",
                actions=["secretsmanager:GetSecretValue"],
                resources=[
                    f"arn:aws:secretsmanager:{Stack.of(self).region}:{Stack.of(self).account}:secret:bedrock-agentcore-identity!default/oauth2/*",
                    f"arn:aws:secretsmanager:{Stack.of(self).region}:{Stack.of(self).account}:secret:mynion-gateway-cognito-*",
                ],
            )
        )

        # Grant permissions to invoke AgentCore Gateway
        execution_role.add_to_policy(
            iam.PolicyStatement(
                sid="AgentCoreGatewayAccess",
                actions=[
                    "bedrock-agentcore:InvokeGateway",
                ],
                resources=[
                    f"arn:aws:bedrock-agentcore:{Stack.of(self).region}:{Stack.of(self).account}:gateway/*",
                ],
            )
        )

        # Create the agent runtime artifact from local Docker context
        # This will build the Docker image from the Dockerfile and push it to ECR
        agent_runtime_artifact: agentcore.AgentRuntimeArtifact = (
            agentcore.AgentRuntimeArtifact.from_asset(str(agent_dir))
        )

        # Create the AgentCore Runtime
        self.runtime = agentcore.Runtime(
            self,
            "MynionRuntime",
            runtime_name="mynion_agent",
            agent_runtime_artifact=agent_runtime_artifact,
            execution_role=execution_role,
            description="Mynion Strands Agent Runtime",
            # Use public network configuration (default)
            # For VPC deployment, use RuntimeNetworkConfiguration.usingVpc()
            network_configuration=agentcore.RuntimeNetworkConfiguration.using_public_network(),
        )

        # Expose runtime properties for other stacks
        self.agent_runtime_id = self.runtime.agent_runtime_id
        self.agent_runtime_arn = self.runtime.agent_runtime_arn

        # Output important information
        CfnOutput(
            self,
            "RuntimeArn",
            value=self.runtime.agent_runtime_arn,
            description="ARN of the Mynion AgentCore Runtime",
            export_name=f"{Stack.of(self).stack_name}-RuntimeArn",
        )

        CfnOutput(
            self,
            "RuntimeId",
            value=self.agent_runtime_id,
            description="ID of the Mynion AgentCore Runtime",
            export_name=f"{Stack.of(self).stack_name}-RuntimeId",
        )
