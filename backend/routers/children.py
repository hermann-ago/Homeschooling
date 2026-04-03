from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from database import get_db
from models import Child
from schemas import ChildCreate, ChildUpdate, ChildResponse

router = APIRouter()


@router.get("/", response_model=List[ChildResponse])
def list_children(db: Session = Depends(get_db)):
    return db.query(Child).order_by(Child.id).all()


@router.post("/", response_model=ChildResponse, status_code=201)
def create_child(child: ChildCreate, db: Session = Depends(get_db)):
    db_child = Child(**child.model_dump())
    db.add(db_child)
    db.commit()
    db.refresh(db_child)
    return db_child


@router.get("/{child_id}", response_model=ChildResponse)
def get_child(child_id: int, db: Session = Depends(get_db)):
    child = db.query(Child).filter(Child.id == child_id).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    return child


@router.put("/{child_id}", response_model=ChildResponse)
def update_child(child_id: int, updates: ChildUpdate, db: Session = Depends(get_db)):
    child = db.query(Child).filter(Child.id == child_id).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    for key, value in updates.model_dump(exclude_unset=True).items():
        setattr(child, key, value)
    db.commit()
    db.refresh(child)
    return child


@router.delete("/{child_id}", status_code=204)
def delete_child(child_id: int, db: Session = Depends(get_db)):
    child = db.query(Child).filter(Child.id == child_id).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    db.delete(child)
    db.commit()
    return None
