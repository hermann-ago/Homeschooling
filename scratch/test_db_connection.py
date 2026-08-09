import sqlite3
import os
from dotenv import load_dotenv

load_dotenv(dotenv_path='backend/.env')
db_url = os.getenv("DATABASE_URL")
print(f"Testing URL: {db_url}")

if db_url.startswith("sqlite:///"):
    path = db_url[10:]
    print(f"Path: {path}")
    try:
        conn = sqlite3.connect(path)
        print("Successfully connected to SQLite")
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        print(f"Tables: {tables}")
        conn.close()
    except Exception as e:
        print(f"Error: {e}")
else:
    print("Not a sqlite URL")
