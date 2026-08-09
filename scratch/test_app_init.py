import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base
from dotenv import load_dotenv

load_dotenv(dotenv_path='backend/.env')
DATABASE_URL = os.getenv("DATABASE_URL")
print(f"DATABASE_URL: {DATABASE_URL}")

try:
    engine = create_engine(DATABASE_URL)
    Base = declarative_base()
    print("Engine created. Attempting to connect...")
    with engine.connect() as conn:
        print("Connected successfully!")
except Exception as e:
    print(f"Connection failed: {e}")

uploads_dir = os.getenv("UPLOADS_DIR")
print(f"UPLOADS_DIR: {uploads_dir}")
try:
    os.makedirs(uploads_dir, exist_ok=True)
    print("UPLOADS_DIR checked/created successfully.")
except Exception as e:
    print(f"UPLOADS_DIR error: {e}")
