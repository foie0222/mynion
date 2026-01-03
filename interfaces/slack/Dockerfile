FROM public.ecr.aws/lambda/python:3.11

# Install dependencies
COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r requirements.txt

# Copy function code
COPY receiver.py ${LAMBDA_TASK_ROOT}/
COPY __init__.py ${LAMBDA_TASK_ROOT}/

# Set the CMD to your handler
CMD [ "receiver.handler" ]
