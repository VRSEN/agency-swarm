import pandas as pd
import sqlite3
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
API_DATABASE_FILE = os.path.join(current_dir, "api.sqlite")

def search_from_sqlite(database_path: str, table_name: str, condition: str) -> pd.DataFrame:
    conn = sqlite3.connect(database=database_path)
    query = f"SELECT * FROM {table_name} WHERE {condition}"
    df = pd.read_sql_query(query, conn)
    return df