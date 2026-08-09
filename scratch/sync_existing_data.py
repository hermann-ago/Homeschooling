import sys
import os
from datetime import datetime

# Add backend to sys.path to import models and database
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from database import SessionLocal
from models import CurriculumTopic, ScheduledSlot, Completion

def sync_existing_data():
    db = SessionLocal()
    try:
        print("Starting one-time synchronization...")
        
        # 1. Sync Curriculum -> Calendar
        # Mark slots as completed if the topic is marked completed
        completed_topics = db.query(CurriculumTopic).filter(CurriculumTopic.completed == True).all()
        print(f"Found {len(completed_topics)} completed topics in curriculum.")
        
        slots_completed_count = 0
        for topic in completed_topics:
            slots = db.query(ScheduledSlot).filter(ScheduledSlot.topic_id == topic.id).all()
            for slot in slots:
                # Check if completion already exists
                existing_comp = db.query(Completion).filter(Completion.slot_id == slot.id).first()
                if not existing_comp:
                    db.add(Completion(slot_id=slot.id, completed_at=datetime.utcnow()))
                    slots_completed_count += 1
        
        print(f"Created {slots_completed_count} missing completion records on the calendar.")

        # 2. Sync Calendar -> Curriculum
        # Mark topics as completed if they have at least one completed slot
        all_completions = db.query(Completion).all()
        print(f"Found {len(all_completions)} completion records on the calendar.")
        
        topics_marked_count = 0
        for comp in all_completions:
            slot = comp.slot
            if slot and slot.topic_id:
                topic = db.query(CurriculumTopic).filter(CurriculumTopic.id == slot.topic_id).first()
                if topic and not topic.completed:
                    topic.completed = True
                    topics_marked_count += 1
        
        print(f"Marked {topics_marked_count} topics as completed in curriculum based on calendar history.")
        
        db.commit()
        print("\nSynchronization complete! All data is now aligned.")
        
    except Exception as e:
        db.rollback()
        print(f"Error during synchronization: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    sync_existing_data()
