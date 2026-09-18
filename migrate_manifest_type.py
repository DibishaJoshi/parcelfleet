import sqlite3
import os

db_paths = ['instance/parcelfleet.db', 'parcelfleet.db']
for p in db_paths:
    if os.path.exists(p):
        conn = sqlite3.connect(p)
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(manifests)")
        cols = [r[1] for r in cur.fetchall()]
        print(f"DB {p} columns:", cols)
        if 'manifest_type' not in cols:
            cur.execute("ALTER TABLE manifests ADD COLUMN manifest_type VARCHAR(50) DEFAULT 'Inter-Hub Transfer'")
            conn.commit()
            print(f"Added manifest_type to {p}")
        else:
            print(f"manifest_type already exists in {p}")
        conn.close()
