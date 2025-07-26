CREATE USER IF NOT EXISTS crypto_user IDENTIFIED WITH plaintext_password BY 'password';

GRANT SELECT, INSERT, UPDATE, DELETE ON crypto.* TO crypto_user;

CREATE DATABASE IF NOT EXISTS crypto;

CREATE TABLE IF NOT EXISTS crypto.raw_prices (
    symbol LowCardinality(String) CODEC(ZSTD(3)),
    bid_price Float32 CODEC(ZSTD(3)),
    bid_size Float32 CODEC(ZSTD(3)),
    timestamp DateTime64 CODEC(Delta, ZSTD(3)),
    ask_price Float32 CODEC(ZSTD(3)),
    ask_size Float32 CODEC(ZSTD(3))
) ENGINE = MergeTree
ORDER BY (symbol, timestamp);

