from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from utils import from_avro_abris_config, from_avro
import os

#Loading variables
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "broker:29092")
SCHEMA_REGISTRY_URL = os.getenv('SCHEMA_REGISTRY_URL')
TOPIC = 'crypto'


#Spark session
spark = (
    SparkSession.builder\
    .appName("crypto-stream")\
    .getOrCreate()
)


# connect to the kafka crypto topic and fetch binary data
crypto_bin =(
    spark.readStream\
    .format("kafka")\
    .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP_SERVERS)\
    .option("subscribe", TOPIC)\
    .load()
) 

# Use schema registry for deserialization
from_avro_abris_settings = from_avro_abris_config({'schema.registry.url': SCHEMA_REGISTRY_URL}, TOPIC, False)
crypto_parsed = crypto_bin.withColumn("parsed", from_avro("value", from_avro_abris_settings))


# An example aggregation: count events per symbol
query = (
    crypto_parsed
        .writeStream
        .outputMode("append")   
        .format("console")        # console sink for a quick test
        .option("truncate", False)
        .start()
)

query.awaitTermination()
