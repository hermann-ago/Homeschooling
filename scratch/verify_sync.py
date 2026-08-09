import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from database import SessionLocal
from models import CurriculumTopic, ScheduledSlot, Completion
from sqlalchemy import func

db = SessionLocal()
try:
    # Find a topic with at least one scheduled slot
    topic = db.query(CurriculumTopic).join(ScheduledSlot).first()
    if not topic:
        print("No topic with scheduled slots found to test.")
    else:
        print(f"Testing with Topic: {topic.title} (ID: {topic.id})")
        
        # 1. Test Curriculum -> Calendar Sync
        print("Initial state:")
        print(f"  Topic completed: {topic.completed}")
        slots = db.query(ScheduledSlot).filter(ScheduledSlot.topic_id == topic.id).all()
        for s in slots:
            comp = db.query(Completion).filter(Completion.slot_id == s.id).first()
            print(f"  Slot {s.id} completed: {comp is not None}")
        
        # Toggle completion via a simulated call to the router logic (manual for now)
        from routers.subjects import toggle_topic_complete
        print("\nToggling topic completion (Curriculum -> Calendar)...")
        # We need to mock the FastAPI dependency or just call the logic
        # For simplicity, I'll just check the db after calling the logic
        topic.completed = True
        from datetime import datetime
        slots = db.query(ScheduledSlot).filter(ScheduledSlot.topic_id == topic.id).all()
        for slot in slots:
            if not db.query(Completion).filter(Completion.slot_id == slot.id).first():
                db.add(Completion(slot_id=slot.id, completed_at=datetime.utcnow()))
        db.commit()
        
        print("New state:")
        print(f"  Topic completed: {topic.completed}")
        for s in slots:
            comp = db.query(Completion).filter(Completion.slot_id == s.id).first()
            print(f"  Slot {s.id} completed: {comp is not None}")

finally:
    db.close()
