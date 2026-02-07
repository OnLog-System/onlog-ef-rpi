import sqlite3
import requests
import time
import json

DB_PATH = "/mnt/nvme/infra/sqlite/sensor_logs.db"
API_URL = "http://43.201.233.103/api/ingest/raw"
API_KEY = "changeme"

BATCH_SIZE = 20
SLEEP_SEC = 5


def main():
    while True:
        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()

            rows = cur.execute(
                """
                SELECT id, payload
                FROM raw_logs
                WHERE uploaded = 0
                  AND received_at >= datetime('now', '-2 minutes')
                ORDER BY received_at
                LIMIT ?
                """,
                (BATCH_SIZE,)
            ).fetchall()

            for row_id, payload in rows:
                r = requests.post(
                    API_URL,
                    headers={
                        "Content-Type": "application/json",
                        "X-API-Key": API_KEY,
                    },
                    data=payload,
                    timeout=5,
                )

                if r.status_code == 200:
                    cur.execute(
                        "UPDATE raw_logs SET uploaded = 1 WHERE id = ?",
                        (row_id,),
                    )
                    conn.commit()
                else:
                    print("upload failed", r.status_code, r.text)
                    break

            conn.close()
        except Exception as e:
            print("sender error:", e)

        time.sleep(SLEEP_SEC)


if __name__ == "__main__":
    main()