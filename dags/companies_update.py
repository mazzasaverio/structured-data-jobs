import os
import pandas as pd
from datetime import datetime, timedelta
import pendulum
from typing import List, Dict, Any

from airflow.decorators import dag, task
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator

# Constants to avoid hardcoding
POSTGRES_CONN_ID = "postgres_neon"
CSV_PATH = "/usr/local/airflow/include/config/companies.csv"
TABLE_NAME = "companies"

default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "start_date": pendulum.datetime(2023, 1, 1, tz="UTC"),
}


@dag(
    dag_id="neo_data_pipeline",
    default_args=default_args,
    schedule=None,
    catchup=False,
    tags=["postgres", "csv", "neo"],
    doc_md="""
    # Neo Data Pipeline
    
    This DAG runs an ETL pipeline that:
    1. Verifies database connection
    2. Reads data from a CSV file and loads it into a PostgreSQL table
    3. Counts the records in the updated table
    
    The DAG uses a table with a predefined schema and supports upsert of existing data.
    """,
)
def neo_data_pipeline():

    # Using SQLExecuteQueryOperator for database operations
    check_db_connection = SQLExecuteQueryOperator(
        task_id="check_db_connection",
        conn_id=POSTGRES_CONN_ID,
        sql="SELECT 1 AS connection_test;",
    )

    # Using SQLExecuteQueryOperator for table creation
    create_table = SQLExecuteQueryOperator(
        task_id="create_table",
        conn_id=POSTGRES_CONN_ID,
        sql=f"""
            CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) UNIQUE,
                url VARCHAR(255),
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """,
    )

    @task(multiple_outputs=True)
    def extract_data_from_csv() -> Dict[str, Any]:
        """
        Extract data from CSV file and return as DataFrame.

        Returns:
            Dict with dataframe and record count.
        """
        if not os.path.exists(CSV_PATH):
            raise FileNotFoundError(f"CSV file {CSV_PATH} does not exist.")

        df = pd.read_csv(CSV_PATH)
        record_count = len(df)

        return {"dataframe": df.to_dict(orient="records"), "record_count": record_count}

    @task
    def transform_data(data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Transform data by applying business rules.

        Args:
            data: Dictionary containing extracted data.

        Returns:
            List of transformed records.
        """
        records = data["dataframe"]

        # Data transformation
        transformed_records = []
        for record in records:
            if "name" in record and record["name"]:
                record["name"] = record["name"].lower()

            if "url" in record and record["url"]:
                record["url"] = record["url"].rstrip("/")

            transformed_records.append(record)

        # Remove duplicates (using name as key)
        seen = set()
        unique_records = []
        for record in transformed_records:
            if record["name"] not in seen:
                seen.add(record["name"])
                unique_records.append(record)

        return unique_records

    @task
    def load_data_to_postgres(transformed_data: List[Dict[str, Any]]) -> int:
        """
        Load transformed data into PostgreSQL database.

        Args:
            transformed_data: List of records to load.

        Returns:
            Number of records loaded.
        """
        hook = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
        conn = hook.get_conn()
        cursor = conn.cursor()

        # Use prepared statements for safety against SQL injection
        insert_query = f"""
            INSERT INTO {TABLE_NAME} (name, url) 
            VALUES (%s, %s)
            ON CONFLICT (name) 
            DO UPDATE SET 
                url = EXCLUDED.url,
                updated_at = CURRENT_TIMESTAMP;
        """

        # Batch insert for better performance
        records_to_insert = [
            (record["name"], record["url"]) for record in transformed_data
        ]
        cursor.executemany(insert_query, records_to_insert)

        conn.commit()
        cursor.close()
        conn.close()

        return len(transformed_data)

    # Using SQLExecuteQueryOperator for counting records
    count_records = SQLExecuteQueryOperator(
        task_id="count_records",
        conn_id=POSTGRES_CONN_ID,
        sql=f"SELECT COUNT(*) AS record_count FROM {TABLE_NAME};",
    )

    # Clear task flow definition
    extracted_data = extract_data_from_csv()
    transformed_data = transform_data(extracted_data)
    records_loaded = load_data_to_postgres(transformed_data)

    # Clear and readable pipeline
    (
        check_db_connection
        >> create_table
        >> extracted_data
        >> transformed_data
        >> records_loaded
        >> count_records
    )


# DAG instance (PEP8 convention for variable names)
neo_data_pipeline_dag = neo_data_pipeline()
