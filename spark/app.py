from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.avro.functions import from_avro
import os, requests

#Spark session
spark = (
    SparkSession.builder\
    .appName("crypto-stream")\
    .getOrCreate()
)

#schema configuration
schema_conf = {
    "subject": "crypto-value"
}
#requests.get(os.getenv("SCHEMA_REGISTRY_URL"))

avro_schema_str = """{
  "type": "record",
  "namespace": "com.alpaca.data",
  "name": "CryptoQuote",

  "doc": "Real‑time bid/ask quote for a crypto pair from Alpaca’s streaming API",
  "fields": [
    {
      "name": "symbol",
      "type": "string",
      "doc": "Trading pair symbol (e.g. BTC/USD)"
    },
    {
      "name": "timestamp",
      "type": {
        "type": "long",
        "logicalType": "timestamp-micros"
      },
      "doc": "Event time in UTC, microsecond precision"
    },
    {
      "name": "bid_price",
      "type": "double",
      "doc": "Best bid price"
    },
    {
      "name": "bid_size",
      "type": "double",
      "doc": "Size (quantity) available at the bid"
    },
    {
      "name": "bid_exchange",
      "type": ["null", "string"],
      "default": null,
      "doc": "Exchange code posting the bid (may be absent)"
    },
    {
      "name": "ask_price",
      "type": "double",
      "doc": "Best ask price"
    },
    {
      "name": "ask_size",
      "type": "double",
      "doc": "Size available at the ask"
    },
    {
      "name": "ask_exchange",
      "type": ["null", "string"],
      "default": null,
      "doc": "Exchange code posting the ask (may be absent)"
    },
    {   
      "name": "conditions",
      "type": ["null", { "type": "array", "items": "string" }],
      "default": null,
      "doc": "Condition flags (array of strings) or null if none"
    },
    {
      "name": "tape",
      "type": ["null", "string"],
      "default": null,
      "doc": "SIP tape identifier (A, B, or C) if provided"
    }
  ]
}
"""

# connect to the kafka crypto topic and fetch binary data
crypto_bin =(
    spark.readStream\
    .format("kafka")\
    .option("kafka.bootstrap.servers", os.getenv("KAFKA_BOOTSTRAP_SERVERS", "broker:29092"))\
    .option("subscribe", "crypto")\
    .load()
) 

# parse data using schema registry
crypto_parsed = crypto_bin.select(
    from_avro(F.col("value"), avro_schema_str).alias("event")
)

# flatten the parsed dataframe
crypto_stream_df = crypto_parsed.select("event.*")


# An example aggregation: count events per symbol
counts_per_symbol = (
    crypto_stream_df
        .groupBy("symbol")
        .count()
)
query = (
    counts_per_symbol
        .writeStream
        .outputMode("complete")   
        .format("console")        # console sink for a quick test
        .option("truncate", False)
        .start()
)

query.awaitTermination()
