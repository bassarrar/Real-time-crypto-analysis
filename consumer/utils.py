from collections import deque
import time, traceback
from datetime import datetime



class InsertBuffer:
    """
        InsertBuffer class is responsible for managing the buffer used for
        inserting a batch of rows into clickhouse database.

        Attributes:
            client (clickhouse_connect.Client): the clickhouse client used to comunicate with clickhouse database.
            table (str): table name in the database.
            batch_size (int): batch size to insert in the table.
            flush_interval (float): interval of time waited before flushing rows to the table.
    """
    def __init__(self, client, table, batch_size=5000, flush_interval=0.5):
        self.client = client
        self.table = table
        self.buffer = deque()
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.last_flush = time.time()
        self.column_names = ['symbol', 'bid_price', 'bid_size','timestamp', 'ask_price', 'ask_size']

    def append(self, row):
        """
            Add a single row to the buffer and attempt to flush it based on buffer size or time interval.

            Args:
                row (dict): A dictionary representing a row to be inserted, 
                    expected to contain the keys in self.column_names.
        """
        self.buffer.append(row)
        self.maybe_flush()

    def maybe_flush(self):
        """
            Flush the buffer if the batch size exceeds the threshold or the flush interval has passed.
            This helps in maintaining efficient inserts without waiting too long or accumulating too many rows.
        """
        now = time.time()
        if len(self.buffer) >= self.batch_size or (now - self.last_flush) >= self.flush_interval:
            self.flush()

    def flush(self):
        """
            Flush the contents of the buffer to the ClickHouse database.
    
            Converts the buffer into a batch format suitable for insertion.
            Handles exceptions and ensures the buffer is cleared only after a successful insert.
            Updates the last_flush timestamp after the operation.
        """
        if not self.buffer:
            return

        try:
            # create a batch using the buffer (a batch is a list of lists(rows))
            batch = [[record[col] for col in self.column_names] for record in self.buffer]
            self.client.insert(
                table=self.table,
                data=batch,
                column_names=self.column_names,
                settings={
                    'async_insert': 1,
                    'wait_for_async_insert': 1,
                    'max_memory_usage': 8 * 1024 * 1024 * 1024 # 8 GB
                }
            )

            # Clear only if insert succeeds
            self.buffer.clear()
            print(f"Successfully {len(batch)} were inserted in clickhouse database")
        except Exception as e:
            print(f"[Insert Error] Failed to insert batch: {e}")
            traceback.print_exc()
        finally:
            self.last_flush = time.time()


    def flush_if_any(self):
        """
            Flush the buffer if it contains any data.

            This is useful for final flush operations when shutting down or finishing a data ingestion cycle.
        """
        if self.buffer:
            self.flush()
