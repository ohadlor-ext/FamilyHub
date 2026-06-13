from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from database import get_db
from routers.auth import get_current_user_dep
from models.user import User, UserRole
from models.task import Task, TaskStatus, TaskPriority

router = APIRouter(prefix="/tasks", tags=["tasks"])


class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    assigned_to: Optional[int] = None
    due_date: Optional[datetime] = None
    priority: TaskPriority = TaskPriority.MEDIUM
    is_recurring: bool = False
    recurrence_rule: Optional[str] = None


class TaskUpdate(BaseModel):
    status: Optional[TaskStatus] = None
    title: Optional[str] = None
    description: Optional[str] = None
    due_date: Optional[datetime] = None
    priority: Optional[TaskPriority] = None


@router.get("/")
def list_tasks(
    assigned_to: Optional[int] = None,
    status: Optional[TaskStatus] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    query = db.query(Task)
    if current_user.role == UserRole.CHILD:
        query = query.filter(Task.assigned_to == current_user.id)
    elif assigned_to:
        query = query.filter(Task.assigned_to == assigned_to)
    if status:
        query = query.filter(Task.status == status)

    tasks = query.order_by(Task.due_date.asc().nullslast()).all()
    return {
        "tasks": [
            {
                "id": t.id,
                "title": t.title,
                "description": t.description,
                "status": t.status,
                "priority": t.priority,
                "assigned_to": t.assigned_to,
                "due_date": t.due_date,
                "is_recurring": t.is_recurring,
            }
            for t in tasks
        ]
    }


@router.post("/")
def create_task(
    task_data: TaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    task = Task(**task_data.model_dump(), created_by=current_user.id)
    db.add(task)
    db.commit()
    db.refresh(task)
    return {"message": "משימה נוצרה", "task_id": task.id}


@router.patch("/{task_id}")
def update_task(
    task_id: int,
    update_data: TaskUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="משימה לא נמצאה")
    if current_user.role == UserRole.CHILD and task.assigned_to != current_user.id:
        raise HTTPException(status_code=403, detail="אין הרשאה")

    for field, value in update_data.model_dump(exclude_none=True).items():
        setattr(task, field, value)
    if update_data.status == TaskStatus.DONE:
        task.completed_at = datetime.utcnow()

    db.commit()
    return {"message": "משימה עודכנה"}


@router.delete("/{task_id}")
def delete_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    if current_user.role != UserRole.PARENT:
        raise HTTPException(status_code=403, detail="הורים בלבד")
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="משימה לא נמצאה")
    db.delete(task)
    db.commit()
    return {"message": "משימה נמחקה"}
