import asyncio, logging, os, socket
from contextlib import asynccontextmanager
from alpaca.data.live import CryptoDataStream
from confluent_kafka import Producer
from confluent_kafka.serialization import SerializationContext, MessageField, StringSerializer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer
from confluent_kafka.admin import AdminClient, NewTopic
import avro.schema

# List of cryptocurrency pairs to subscribe to for quote data
SUBSCRIPTIONS = [
    "BTC/USD", "ETH/USD", "AAVE/USD", "AVAX/USD", "BAT/USD", "BCH/USD", "CRV/USD", "DOGE/USD",
    "DOT/USD", "GRT/USD", "LINK/USD", "LTC/USD", "MKR/USD", "PEPE/USD", "SHIB/USD", "SOL/USD",
    "SUSHI/USD", "TRUMP/USD", "UNI/USD", "XRP/USD", "XTZ/USD", "YFI/USD"
]


@asynccontextmanager
async def kafka_producer(**conf):
    """
    Asynchronous context manager that yields a Kafka producer.

    Args:
        **conf: Arbitrary keyword arguments for Kafka Producer configuration.

    Yields:
        Producer: An instance of the Confluent Kafka Producer.
    """
    producer = Producer(conf)
    yield producer


async def flush_loop(producer):
    """
    Asynchronous loop that continuously polls the Kafka producer 
    to allow delivery callbacks to be processed.

    Args:
        producer (Producer): Kafka producer instance.
    """
    while True:
        producer.poll(0)
        await asyncio.sleep(0.5)


def build_serializers(schema_path: str, registry_url: str, serializer_conf: dict):
    """
    Build Kafka Avro key and value serializers using schema registry.

    Args:
        schema_path (str): Path to the Avro schema file.
        registry_url (str): URL of the schema registry.
        serializer_conf (dict): Configuration for the Avro serializer.

    Returns:
        tuple: A tuple containing a StringSerializer and an AvroSerializer.
    """
    with open(schema_path) as f:
        schema_str = f.read()
    schema_registry = SchemaRegistryClient({"url": registry_url})
    avro_ser = AvroSerializer(schema_registry, schema_str, lambda o, _: o, serializer_conf)
    return StringSerializer("utf_8"), avro_ser


def delivery_report(err, msg):
    """
    Delivery report callback function for Kafka messages.

    Logs whether the message was successfully delivered or failed.

    Args:
        err (KafkaError or None): Error info if the message failed.
        msg (Message): Kafka message instance.
    """
    if err:
        logging.error(f"delivery failed: {err}")
    else:
        logging.info(f"delivered to %s [%d] @ offset %d",
                      msg.topic(), msg.partition(), msg.offset())


async def main():
    """
    Main asynchronous function that sets up Kafka producer, topic, serializers,
    Alpaca CryptoDataStream, and handles quote ingestion and Kafka publishing.
    """
    # Kafka configuration
    kafka_conf = {
        "bootstrap.servers": os.getenv("KAFKA_BOOTSTRAP_SERVERS", "broker:29092"),
        "client.id": socket.gethostname(),
        "linger.ms": 5, # wait 5 ms for batching then flush
        "batch.size": 4096, # a batch of 4 KB (a message is of approximatly 53-60 bytes)
        "enable.idempotence": True,
        "compression.type": "lz4"
    }

    # Topic setup
    admin = AdminClient({"bootstrap.servers": kafka_conf["bootstrap.servers"]})
    topic = NewTopic("raw_prices", num_partitions=8, replication_factor=1)
    futures = admin.create_topics([topic])

    for topic_name, future in futures.items():
        try:
            future.result()
            logging.info(f"Topic '{topic_name}' created.")
        except Exception as e:
            logging.warning(f"Topic '{topic_name}' may already exist or failed to create: {e}")

    # Serializer config
    serializer_conf = {
        'auto.register.schemas': True
    }

    # Build serializers
    key_ser, avro_ser = build_serializers("./schemas/crypto.avsc", os.getenv("SCHEMA_REGISTRY_URL"), serializer_conf)

    async with kafka_producer(**kafka_conf) as producer:

        async def quote_handler(data):
            """
            Handles incoming quote data and produces it to Kafka.

            Args:
                data (alpaca.data.models.Quote): Incoming quote data from Alpaca stream.
            """
            payload = {
                "symbol": data.symbol,
                "timestamp": int(data.timestamp.timestamp() * 1_000_000),
                "bid_price": data.bid_price,
                "bid_size": data.bid_size,
                "bid_exchange": data.bid_exchange,
                "ask_price": data.ask_price,
                "ask_size": data.ask_size,
                "ask_exchange": data.ask_exchange,
                "conditions": data.conditions,
                "tape": data.tape
            }

            while True:
                try:
                    producer.produce(
                        topic="raw_prices",
                        key=key_ser(payload["symbol"], SerializationContext("raw_prices", MessageField.KEY)),
                        value=avro_ser(payload, SerializationContext("raw_prices", MessageField.VALUE)),
                        on_delivery=delivery_report,
                    )
                    break
                except BufferError:
                    await asyncio.sleep(0.05)  # back off until queue frees

        # Connect to Alpaca WebSocket for crypto quotes
        stream = CryptoDataStream(os.getenv("ALPACA_KEY"), os.getenv("ALPACA_SECRET"))
        stream.subscribe_quotes(quote_handler, *SUBSCRIPTIONS)

        # Background task to flush Kafka producer
        flush_task = asyncio.create_task(flush_loop(producer))
        try:
            await stream._run_forever()  # Blocks until cancelled or error
        finally:
            flush_task.cancel()         # Stop the background polling loop
            await asyncio.gather(flush_task, return_exceptions=True)
            producer.flush()            # Final blocking flush (guarantees delivery)


if __name__ == "__main__":
    """
    Entry point for the script.

    Sets up logging and runs the main async event loop.
    """
    logging.basicConfig(level=logging.INFO)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
