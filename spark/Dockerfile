FROM bitnami/spark:3.5.1

USER root

# Create missing directory for apt if needed
RUN mkdir -p /var/lib/apt/lists

# Copy app and requirements

COPY requirements.txt /opt/requirements.txt

# Install Python and dependencies
RUN apt-get update && \
    apt-get install -y python3-pip && \
    pip3 install --no-cache-dir -r /opt/requirements.txt && \
    apt-get clean

USER 1001