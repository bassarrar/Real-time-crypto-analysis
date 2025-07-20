FROM bitnami/spark:3.5.1

USER root

RUN mkdir -p /var/lib/apt/lists

COPY requirements.txt /opt/requirements.txt

# Set workdir for installations and pip cache
WORKDIR /tmp

ENV PIP_CACHE_DIR=/tmp/.cache/pip

RUN apt-get update && apt-get install -y python3-pip wget && \
    pip3 install --no-cache-dir -r /opt/requirements.txt && \
    apt-get clean

WORKDIR /opt/bitnami/spark/jars

RUN wget https://repo1.maven.org/maven2/org/apache/spark/spark-sql-kafka-0-10_2.12/3.5.1/spark-sql-kafka-0-10_2.12-3.5.1.jar && \
    wget https://repo1.maven.org/maven2/org/apache/spark/spark-avro_2.12/3.5.1/spark-avro_2.12-3.5.1.jar && \
    wget https://repo1.maven.org/maven2/za/co/absa/abris_2.12/6.4.0/abris_2.12-6.4.0.jar && \
    wget https://repo1.maven.org/maven2/org/apache/avro/avro/1.10.2/avro-1.10.2.jar && \
    wget https://packages.confluent.io/maven/io/confluent/kafka-avro-serializer/6.2.1/kafka-avro-serializer-6.2.1.jar && \
    wget https://packages.confluent.io/maven/io/confluent/kafka-schema-registry-client/6.2.1/kafka-schema-registry-client-6.2.1.jar

    

USER 1001
