import os
import pandas as pd
from datetime import datetime, timedelta
import pendulum

from airflow.decorators import dag, task
from airflow.providers.postgres.hooks.postgres import PostgresHook

default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "retries": 0,
    "start_date": pendulum.datetime(2023, 1, 1, tz="UTC"),
}


@dag(
    dag_id="local_postgres_pipeline",
    default_args=default_args,
    schedule=None,
    catchup=False,
    tags=["postgres", "csv"],
)
def local_postgres_pipeline():

    @task
    def check_db_connection():
        """Verifica che il database PostgreSQL sia connesso."""
        try:
            hook = PostgresHook(postgres_conn_id="postgres_neon")
            connection = hook.get_conn()
            cursor = connection.cursor()
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            cursor.close()
            connection.close()

            if result and result[0] == 1:
                print("Database connection successful!")
                return True
            else:
                raise Exception("Database connection test failed")
        except Exception as e:
            print(f"Database connection error: {str(e)}")
            raise

    @task
    def update_table_from_csv():
        """Legge un file CSV e aggiorna/crea una tabella Postgres."""
        try:
            # Percorso al file CSV
            csv_path = "/opt/airflow/include/config/data.csv"

            # Se il file non esiste, creiamo dati di esempio
            if not os.path.exists(csv_path):
                # Crea la directory se non esiste
                os.makedirs(os.path.dirname(csv_path), exist_ok=True)

                # Crea dati di esempio
                sample_data = pd.DataFrame(
                    {
                        "name": ["company1", "company2", "company3"],
                        "url": [
                            "http://company1.com",
                            "http://company2.com",
                            "http://company3.com",
                        ],
                    }
                )
                sample_data.to_csv(csv_path, index=False)
                print(f"File CSV di esempio creato in {csv_path}")

            # Leggi il CSV
            df = pd.read_csv(csv_path)
            print(f"Letti {len(df)} record dal file CSV")

            # Pulizia dei dati
            df.drop_duplicates(inplace=True)
            if "name" in df.columns:
                df["name"] = df["name"].str.lower()
            if "url" in df.columns:
                df["url"] = df["url"].str.rstrip("/")

            # Connessione al database
            hook = PostgresHook(postgres_conn_id="postgres_default")

            # Crea tabella se non esiste
            hook.run(
                """
                CREATE TABLE IF NOT EXISTS neo (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) UNIQUE,
                    url VARCHAR(255),
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """
            )

            # Inserisci o aggiorna i dati
            for _, row in df.iterrows():
                hook.run(
                    f"""
                    INSERT INTO neo (name, url) 
                    VALUES ('{row['name']}', '{row['url']}')
                    ON CONFLICT (name) 
                    DO UPDATE SET 
                        url = EXCLUDED.url,
                        updated_at = CURRENT_TIMESTAMP;
                """
                )

            return f"Tabella neo aggiornata con {len(df)} record"
        except Exception as e:
            print(f"Errore nell'aggiornamento della tabella: {e}")
            raise

    @task
    def count_records():
        """Conta i record nella tabella aggiornata."""
        hook = PostgresHook(postgres_conn_id="postgres_default")
        result = hook.get_first("SELECT COUNT(*) FROM neo;")
        count = result[0]
        print(f"Numero di record nella tabella neo: {count}")
        return count

    # Definisci la sequenza di esecuzione
    db_check = check_db_connection()
    update_table = update_table_from_csv()
    count = count_records()

    # Imposta le dipendenze
    db_check >> update_table >> count


# Istanzia il DAG
local_dag = local_postgres_pipeline()
