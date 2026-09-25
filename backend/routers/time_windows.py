from typing import List

from fastapi import APIRouter, Depends

from app_context import request_operation as write
from dependencies import require_member, require_parent, store
from schemas import TimeWindowCreate, TimeWindowResponse
from utils import get_or_404

router = APIRouter()


# Time windows are nested under children in the API but managed in Settings
@router.get("/by-child/{child_id}", response_model=List[TimeWindowResponse], dependencies=[Depends(require_member)])
def list_time_windows(child_id: int):
    get_or_404(store(), "children", child_id, "Child")
    return sorted(store().find("time_windows", child_id=child_id), key=lambda w: (w["weekday"], w["start_time"]))


@router.post("", response_model=TimeWindowResponse, status_code=201, dependencies=[Depends(require_parent)])
def create_time_window(tw: TimeWindowCreate):
    get_or_404(store(), "children", tw.child_id, "Child")
    with write("time_windows.create") as tx:
        return tx.insert("time_windows", tw.model_dump())


@router.delete("/{tw_id}", status_code=204, dependencies=[Depends(require_parent)])
def delete_time_window(tw_id: int):
    get_or_404(store(), "time_windows", tw_id, "Time window")
    with write("time_windows.delete") as tx:
        tx.delete("time_windows", tw_id)
    return None
