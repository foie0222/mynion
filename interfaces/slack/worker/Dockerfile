# Lambda Worker Container Image
# This container handles Slack event processing and AgentCore Runtime invocation

FROM public.ecr.aws/lambda/python:3.11

# Copy requirements and install dependencies
COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

# Copy worker code as a package to maintain import structure
COPY __init__.py ${LAMBDA_TASK_ROOT}/worker/
COPY handler.py ${LAMBDA_TASK_ROOT}/worker/
COPY agent_client.py ${LAMBDA_TASK_ROOT}/worker/

# Set the CMD to your handler (module path: worker.handler.handler)
CMD [ "worker.handler.handler" ]
