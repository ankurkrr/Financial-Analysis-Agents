import mysql.connector
import os
import json
from dotenv import load_dotenv

load_dotenv()

MYSQL_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "localhost"),
    "port": int(os.getenv("MYSQL_PORT", 3306)),
    "user": os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD", ""),
    "database": os.getenv("MYSQL_DB", "tcs_forecast"),
}

class MySQLClient:
    def __init__(self):
        db_name = MYSQL_CONFIG["database"]

        # Step 1: Connect to MySQL *without* database to ensure it exists
        temp_conn = mysql.connector.connect(
            host=MYSQL_CONFIG["host"],
            port=MYSQL_CONFIG["port"],
            user=MYSQL_CONFIG["user"],
            password=MYSQL_CONFIG["password"]
        )
        temp_cursor = temp_conn.cursor()
        temp_cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db_name}")
        temp_conn.commit()
        temp_cursor.close()
        temp_conn.close()

        # Step 2: Connect to the actual database
        self.conn = mysql.connector.connect(**MYSQL_CONFIG)
        self._ensure_tables()

    def _ensure_tables(self):
        cur = self.conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS requests (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            request_uuid VARCHAR(64) UNIQUE,
            payload JSON,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS results (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            request_uuid VARCHAR(64),
            result_json JSON,
            tools_raw JSON,
            llm_mode VARCHAR(32) DEFAULT NULL,
            llm_fake BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX (request_uuid)
        )
        """)
        self.conn.commit()
        cur.close()

        # Ensure llm_events table exists for monitoring/fallback events
        cur = self.conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS llm_events (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            request_uuid VARCHAR(64),
            event_type VARCHAR(64),
            details JSON,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX (request_uuid)
        )
        """)
        self.conn.commit()
        cur.close()

        # Apply any needed ALTER TABLE migrations for existing deployments
        self._apply_migrations()

    def _apply_migrations(self):
        """Apply non-destructive schema migrations (e.g., add new columns).

        This method checks information_schema for missing columns and alters
        tables as needed. Safe to run on every startup.
        """
        cur = self.conn.cursor()
        db_name = MYSQL_CONFIG["database"]

        # Check for llm_mode column
        cur.execute(
            "SELECT COUNT(1) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME='results' AND COLUMN_NAME='llm_mode'",
            (db_name,)
        )
        has_llm_mode = cur.fetchone()[0] > 0

        if not has_llm_mode:
            try:
                cur.execute("ALTER TABLE results ADD COLUMN llm_mode VARCHAR(32) DEFAULT NULL")
            except Exception:
                # best-effort: ignore failures (e.g., permissions) and continue
                pass

        # Check for llm_fake column
        cur.execute(
            "SELECT COUNT(1) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME='results' AND COLUMN_NAME='llm_fake'",
            (db_name,)
        )
        has_llm_fake = cur.fetchone()[0] > 0

        if not has_llm_fake:
            try:
                cur.execute("ALTER TABLE results ADD COLUMN llm_fake BOOLEAN DEFAULT FALSE")
            except Exception:
                pass

        self.conn.commit()
        cur.close()

    def log_request(self, request_uuid: str, payload: dict):
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO requests (request_uuid, payload) VALUES (%s, %s)",
            (request_uuid, json.dumps(payload)),
        )
        self.conn.commit()
        cur.close()

    def log_result(self, request_uuid: str, result: dict, tools_raw: dict = None):
        # Attempt to extract llm metadata for monitoring
        llm_mode = None
        llm_fake = False
        try:
            if isinstance(result, dict):
                meta = result.get("metadata", {})
                llm_mode = meta.get("llm_mode")
                llm_fake = bool(meta.get("llm_fake", False))
        except Exception:
            pass

        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO results (request_uuid, result_json, tools_raw, llm_mode, llm_fake) VALUES (%s, %s, %s, %s, %s)",
            (request_uuid, json.dumps(result), json.dumps(tools_raw or {}), llm_mode, llm_fake),
        )
        self.conn.commit()
        cur.close()

    def log_event(self, request_uuid: str, event_type: str, details: dict = None):
        """Log an LLM-related event for monitoring/audit (e.g., fallback, retry)."""
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO llm_events (request_uuid, event_type, details) VALUES (%s, %s, %s)",
            (request_uuid, event_type, json.dumps(details or {})),
        )
        self.conn.commit()
        cur.close()

    def get_result(self, request_uuid: str):
        cur = self.conn.cursor(dictionary=True)
        cur.execute(
            "SELECT * FROM results WHERE request_uuid=%s ORDER BY created_at DESC LIMIT 1",
            (request_uuid,),
        )
        r = cur.fetchone()
        cur.close()
        return r