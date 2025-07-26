from confluent_kafka import Consumer, KafkaError, KafkaException
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer
from confluent_kafka.serialization import SerializationContext, MessageField
import clickhouse_connect
import os, time, sys, logging
from utils import InsertBuffer
from multiprocessing import Process

sys.stdout.reconfigure(line_buffering=True)


def consume_loop(instance_id):
    """
    Starts a Kafka consumer loop for a single process instance.

    This function:
    - Initializes Kafka and Schema Registry clients.
    - Deserializes Avro messages.
    - Buffers messages using the InsertBuffer class.
    - Periodically commits Kafka offsets.
    - Inserts data in batches into ClickHouse.

    Args:
        instance_id (int): Unique identifier for the consumer process (used for logging).
    
    Raises:
        ValueError: If the required KAFKA_TOPIC environment variable is not set.
        KafkaException: If a Kafka error other than partition EOF occurs.
    """
    print(f"[Process-{instance_id}] Starting consumer process")

    # Kafka Config
    kafka_conf = {
        'bootstrap.servers': os.getenv('KAFKA_BOOTSTRAP_SERVERS'),
        'group.id': 'raw-consumer10', # consumer group id
        'enable.auto.commit': False, #commits are handled manually
        'auto.offset.reset': 'earliest' #try reading kafka messages from the beginning
    }

    schema_reg_config = {
        'url': os.getenv('SCHEMA_REGISTRY_URL')
    }

    # ClickHouse Config
    clickhouse_client = clickhouse_connect.get_client(
        host=os.getenv("CLICKHOUSE_HOST"),
        port=os.getenv("CLICKHOUSE_PORT"),
        username=os.getenv("CLICKHOUSE_USERNAME"),
        password=os.getenv("CLICKHOUSE_PASSWORD"),
        database=os.getenv("CLICKHOUSE_DB"),
    )

    table_name = os.getenv("CLICKHOUSE_TABLE", "raw_prices")
    batch_size = int(os.getenv("BATCH_SIZE", 2000))
    flush_interval = float(os.getenv("FLUSH_INTERVAL", 0.5))
    topic = os.getenv("KAFKA_TOPIC")

    if not topic:
        raise ValueError("Missing KAFKA_TOPIC environment variable")

    #creating a schema-registry client to fetch schemas
    sr_client = SchemaRegistryClient(schema_reg_config)
    avro_deserializer = AvroDeserializer(sr_client)
    consumer = Consumer(kafka_conf)

    # create an instance of InsertBuffer class to handle buffering messages
    insert_buffer = InsertBuffer(
        client=clickhouse_client,
        table=table_name,
        batch_size=batch_size,
        flush_interval=flush_interval
    )

    # commit conumed messages each MIN_COMMIT_COUNT
    MIN_COMMIT_COUNT = 5
    msg_count = 0

    try:
        consumer.subscribe([topic])
        while True:
            msg = consumer.poll(timeout=1.0)
            if msg is None:
                continue

            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    print(f"[Process-{instance_id}] End of partition {msg.partition()} at offset {msg.offset()}")
                else:
                    raise KafkaException(msg.error())
                continue

            try:
                record = avro_deserializer(
                    msg.value(),
                    SerializationContext(msg.topic(), MessageField.VALUE)
                )

                if record:
                    insert_buffer.append(record)

                msg_count += 1
                if msg_count % MIN_COMMIT_COUNT == 0:
                    consumer.commit(asynchronous=False)

            except Exception as e:
                print(f"[Process-{instance_id}] Record error: {e}")

    except KeyboardInterrupt:
        print(f"[Process-{instance_id}] Shutdown requested")
    finally:
        insert_buffer.flush_if_any()
        consumer.close()
        print(f"[Process-{instance_id}] Shutdown complete")


def start_multiple_consumers(process_count: int):
    """
    Starts multiple Kafka consumer processes to handle parallel consumption.

    This function uses Python’s multiprocessing to spawn separate processes, 
    each running `consume_loop()` with a different instance ID.

    Args:
        process_count (int): Number of consumer processes to start.
    """
    processes = []
    for i in range(process_count):
        p = Process(target=consume_loop, args=(i,))
        p.start()
        processes.append(p)

    for p in processes:
        p.join()


if __name__ == '__main__':
    """
    Entry point of the script.

    Sets up logging and reads the number of consumer processes from the environment.
    Starts multiple consumer processes using `start_multiple_consumers`.
    """

    logging.basicConfig(level=logging.INFO)
    process_count = int(os.getenv("CONSUMER_PROCESS_COUNT", 2))
    start_multiple_consumers(process_count)

