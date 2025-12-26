# Lambda Worker Container Image
# This container handles Slack event processing and AgentCore Runtime invocation

FROM public.ecr.aws/lambda/python:3.11

# Copy requirements and install dependencies
COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

# Copy worker code
COPY handler.py ${LAMBDA_TASK_ROOT}/
COPY agent_client.py ${LAMBDA_TASK_ROOT}/

# Set the CMD to your handler
CMD [ "handler.handler" ]
