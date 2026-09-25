from typing import List

from fastapi import APIRouter, Depends

from app_context import request_operation as write
from dependencies import require_member, require_parent, store
from schemas import ChildCreate, ChildResponse, ChildUpdate
from utils import get_or_404

router = APIRouter()


@router.get("", response_model=List[ChildResponse], dependencies=[Depends(require_member)])
def list_children():
    return sorted(store().all("children"), key=lambda c: c["id"])


@router.post("", response_model=ChildResponse, status_code=201, dependencies=[Depends(require_parent)])
def create_child(child: ChildCreate):
    with write("children.create", f"Added {child.name}") as tx:
        return tx.insert("children", child.model_dump())


@router.get("/{child_id}", response_model=ChildResponse, dependencies=[Depends(require_member)])
def get_child(child_id: int):
    return get_or_404(store(), "children", child_id, "Child")


@router.put("/{child_id}", response_model=ChildResponse, dependencies=[Depends(require_parent)])
def update_child(child_id: int, updates: ChildUpdate):
    get_or_404(store(), "children", child_id, "Child")
    with write("children.update") as tx:
        return tx.update("children", child_id, updates.model_dump(exclude_unset=True))


@router.delete("/{child_id}", status_code=204, dependencies=[Depends(require_parent)])
def delete_child(child_id: int):
    get_or_404(store(), "children", child_id, "Child")
    with write("children.delete") as tx:
        tx.delete("children", child_id)
    return None
