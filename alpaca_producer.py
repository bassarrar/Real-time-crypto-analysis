import asyncio, logging, os, socket
from contextlib import asynccontextmanager
from dotenv import load_dotenv, find_dotenv
from alpaca.data.live import CryptoDataStream
from confluent_kafka import Producer
from confluent_kafka.serialization import SerializationContext, MessageField, StringSerializer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer
import avro.schema


# Loading variables
load_dotenv(find_dotenv("./environment/.env"))


SUBSCRIPTIONS = ["BTC/USD", "ETH/USD","AAVE/USD", "AVAX/USD", "BAT/USD", "BCH/USD", "CRV/USD", "DOGE/USD",
                 "DOT/USD", "GRT/USD", "LINK/USD", "LTC/USD", "MKR/USD", "PEPE/USD", "SHIB/USD", "SOL/USD",
                 "SUSHI/USD", "TRUMP/USD", "UNI/USD", "XRP/USD", "XTZ/USD", "YFI/USD"]

@asynccontextmanager
async def kafka_producer(**conf):
    producer = Producer(conf)
    yield producer


async def flush_loop(producer):
    while True:
        producer.poll(0)
        await asyncio.sleep(0.5)


def build_serializers(schema_path: str, registry_url: str, serializer_conf: dict):
    with open(schema_path) as f:
        schema_str = f.read()
    schema_registry = SchemaRegistryClient({"url": registry_url})
    avro_ser = AvroSerializer(schema_registry, schema_str, lambda o, _: o, serializer_conf)
    return StringSerializer("utf_8"), avro_ser

    
def delivery_report(err, msg):
    if err:
        logging.error(f"  delivery failed: {err}")
    else:
        logging.debug("  delivered to %s [%d] @ offset %d",
                      msg.topic(), msg.partition(), msg.offset())

async def main():
    # kafka config 
    kafka_conf = {"bootstrap.servers": "localhost:9092",
            "client.id": socket.gethostname(),
            "linger.ms": 20,
            "enable.idempotence": True,
            "compression.type": "zstd"}
            
    # serializer config
    serializer_conf = {
    'auto.register.schemas': True
    }

    #building serializers
    key_ser, avro_ser = build_serializers("./schemas/crypto.avsc", os.getenv("SCHEMA_REGISTRY_URL"), serializer_conf)
    async with kafka_producer(**kafka_conf) as producer:
        async def quote_handler(data):
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
                        topic="crypto",
                        key=key_ser(payload["symbol"], SerializationContext("crypto", MessageField.KEY)),
                        value=avro_ser(payload, SerializationContext("crypto", MessageField.VALUE)),
                        on_delivery=delivery_report,
                    )
                    break
                except BufferError:
                    await asyncio.sleep(0.05)  # back‑off until queue frees

        stream = CryptoDataStream(os.getenv("ALPACA_KEY"), os.getenv("ALPACA_SECRET"))
        stream.subscribe_quotes(quote_handler, *SUBSCRIPTIONS)
        flush_task = asyncio.create_task(flush_loop(producer))
        try:
            await stream._run_forever()          # Blocks until cancelled or error
        finally:
            flush_task.cancel()         # Stop the background polling loop
            await asyncio.gather(flush_task, return_exceptions=True)
            producer.flush()            # Final blocking flush (guarantees delivery)
       

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())