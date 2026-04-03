"""Seed the database with initial child profiles."""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from database import SessionLocal
from models import Child

def seed():
    db = SessionLocal()
    # Only seed if no children exist
    if db.query(Child).count() > 0:
        print("Children already exist, skipping seed.")
        db.close()
        return

    children = [
        Child(name="Lucas", nickname="Lucas", color="#4A90D9", grade_year="3rd"),
        Child(name="Mila", nickname="Mila", color="#E88AB5", grade_year="1st"),
        Child(name="Olivia", nickname="Olivia", color="#7BC67E", grade_year="Pre-K"),
        Child(name="Joshua", nickname="Joshua", color="#F5A623", grade_year="N/A"),
    ]
    db.add_all(children)
    db.commit()
    print(f"Seeded {len(children)} children.")
    db.close()

if __name__ == "__main__":
    seed()
