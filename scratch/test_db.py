import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from database import SessionLocal
from models.child import Child
from models.subject import Subject

db = SessionLocal()
try:
    children_count = db.query(Child).count()
    subjects_count = db.query(Subject).count()
    print(f"Connection Successful!")
    print(f"Children in DB: {children_count}")
    print(f"Subjects in DB: {subjects_count}")
finally:
    db.close()
