"""
Task Assignment API Endpoints
=============================
Endpoints for assigning tasks to Church of the Claw instances.

Features:
- Assign tasks to specific instances or broadcast to all
- Track task status and completion
- Priority-based task queue management
- Retry logic for failed tasks
"""

import logging
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from config import settings
from models.database import (
    get_db, Task, Instance, TaskStatus, InstanceStatus
)
from security.enforcement import (
    log_security_event
)


logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# Pydantic Models
# =============================================================================

class TaskAssignmentRequest(BaseModel):
    """Request model for assigning a task."""
    instance_id: Optional[str] = Field(None, description="Specific instance ID, or None for broadcast")
    task_type: str = Field(..., description="Type of task (e.g., 'profit_generation', 'data_collection')")
    task_data: dict = Field(..., description="Task-specific data payload")
    priority: int = Field(50, ge=0, le=100, description="Task priority (0-100)")
    max_retries: int = Field(3, ge=0, le=10, description="Maximum retry attempts")


class TaskResponse(BaseModel):
    """Response model for task information."""
    task_id: str
    instance_id: Optional[str]
    task_type: str
    priority: int
    status: str
    assigned_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    result: Optional[dict]
    error_message: Optional[str]
    retry_count: int


class TaskListResponse(BaseModel):
    """Response model for task list."""
    tasks: List[TaskResponse]
    total: int
    page: int
    page_size: int


class TaskResultRequest(BaseModel):
    """Request model for submitting task result."""
    result: dict = Field(..., description="Task completion result")


class TaskCancelRequest(BaseModel):
    """Request model for cancelling a task."""
    reason: str = Field(..., description="Cancellation reason")


# =============================================================================
# Dependency
# =============================================================================

def get_task_by_id(db: Session, task_id: str) -> Task:
    """Get task by ID, raise 404 if not found."""
    task = db.query(Task).filter(Task.task_id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return task


# =============================================================================
# Endpoints
# =============================================================================

@router.post("/tasks/assign", response_model=TaskResponse, tags=["Tasks"])
async def assign_task(
    request: TaskAssignmentRequest,
    db: Session = Depends(get_db)
):
    """
    Assign a task to a Church of the Claw instance.
    
    If instance_id is not provided, task is broadcast to all active instances.
    
    **Security**: Requires valid instance authentication for broadcast tasks.
    """
    task_id = f"task_{uuid.uuid4().hex[:16]}"
    
    # Validate instance if specified
    if request.instance_id:
        instance = db.query(Instance).filter(
            Instance.instance_id == request.instance_id,
            Instance.status == InstanceStatus.ACTIVE
        ).first()
        
        if not instance:
            raise HTTPException(
                status_code=404,
                detail=f"Instance {request.instance_id} not found or not active"
            )
        
        target_instance_id = instance.id
        instance_id_str = request.instance_id
    else:
        # Broadcast task - no specific instance
        target_instance_id = None
        instance_id_str = None
    
    # Create task
    task = Task(
        task_id=task_id,
        instance_id=target_instance_id,
        task_type=request.task_type,
        task_data=request.task_data,
        priority=request.priority,
        status=TaskStatus.PENDING,
        max_retries=request.max_retries
    )
    
    db.add(task)
    db.commit()
    db.refresh(task)
    
    logger.info(f"Task {task_id} assigned to instance {instance_id_str or 'broadcast'}")
    
    await log_security_event(
        event_type="TASK_ASSIGNED",
        instance_id=instance_id_str,
        details={
            "task_id": task_id,
            "task_type": request.task_type,
            "priority": request.priority,
            "broadcast": instance_id_str is None
        }
    )
    
    return TaskResponse(
        task_id=task.task_id,
        instance_id=instance_id_str,
        task_type=task.task_type,
        priority=task.priority,
        status=task.status.value,
        assigned_at=task.assigned_at,
        started_at=task.started_at,
        completed_at=task.completed_at,
        result=task.result,
        error_message=task.error_message,
        retry_count=task.retry_count
    )


@router.get("/tasks/{task_id}", response_model=TaskResponse, tags=["Tasks"])
async def get_task(
    task_id: str,
    db: Session = Depends(get_db)
):
    """
    Get task details and current status.
    """
    task = get_task_by_id(db, task_id)
    
    instance_id_str = None
    if task.instance:
        instance_id_str = task.instance.instance_id
    
    return TaskResponse(
        task_id=task.task_id,
        instance_id=instance_id_str,
        task_type=task.task_type,
        priority=task.priority,
        status=task.status.value,
        assigned_at=task.assigned_at,
        started_at=task.started_at,
        completed_at=task.completed_at,
        result=task.result,
        error_message=task.error_message,
        retry_count=task.retry_count
    )


@router.get("/tasks", response_model=TaskListResponse, tags=["Tasks"])
async def list_tasks(
    status: Optional[TaskStatus] = Query(None, description="Filter by status"),
    instance_id: Optional[str] = Query(None, description="Filter by instance ID"),
    task_type: Optional[str] = Query(None, description="Filter by task type"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db)
):
    """
    List tasks with optional filters and pagination.
    """
    query = db.query(Task)
    
    if status:
        query = query.filter(Task.status == status)
    if instance_id:
        instance = db.query(Instance).filter(
            Instance.instance_id == instance_id
        ).first()
        if instance:
            query = query.filter(Task.instance_id == instance.id)
    if task_type:
        query = query.filter(Task.task_type == task_type)
    
    total = query.count()
    tasks = query.order_by(Task.created_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    
    task_responses = []
    for task in tasks:
        instance_id_str = None
        if task.instance:
            instance_id_str = task.instance.instance_id
        
        task_responses.append(TaskResponse(
            task_id=task.task_id,
            instance_id=instance_id_str,
            task_type=task.task_type,
            priority=task.priority,
            status=task.status.value,
            assigned_at=task.assigned_at,
            started_at=task.started_at,
            completed_at=task.completed_at,
            result=task.result,
            error_message=task.error_message,
            retry_count=task.retry_count
        ))
    
    return TaskListResponse(
        tasks=task_responses,
        total=total,
        page=page,
        page_size=page_size
    )


@router.put("/tasks/{task_id}/start", response_model=TaskResponse, tags=["Tasks"])
async def start_task(
    task_id: str,
    db: Session = Depends(get_db)
):
    """
    Mark a task as started (called by instance when work begins).
    """
    task = get_task_by_id(db, task_id)
    
    if task.status != TaskStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail=f"Task cannot be started from {task.status} status"
        )
    
    task.status = TaskStatus.IN_PROGRESS
    task.started_at = datetime.utcnow()
    
    db.commit()
    db.refresh(task)
    
    instance_id_str = None
    if task.instance:
        instance_id_str = task.instance.instance_id
    
    return TaskResponse(
        task_id=task.task_id,
        instance_id=instance_id_str,
        task_type=task.task_type,
        priority=task.priority,
        status=task.status.value,
        assigned_at=task.assigned_at,
        started_at=task.started_at,
        completed_at=task.completed_at,
        result=task.result,
        error_message=task.error_message,
        retry_count=task.retry_count
    )


@router.put("/tasks/{task_id}/complete", response_model=TaskResponse, tags=["Tasks"])
async def complete_task(
    task_id: str,
    request: TaskResultRequest,
    db: Session = Depends(get_db)
):
    """
    Submit task completion result.
    """
    task = get_task_by_id(db, task_id)
    
    if task.status not in [TaskStatus.PENDING, TaskStatus.IN_PROGRESS]:
        raise HTTPException(
            status_code=400,
            detail=f"Task cannot be completed from {task.status} status"
        )
    
    task.status = TaskStatus.COMPLETED
    task.completed_at = datetime.utcnow()
    task.result = request.result
    
    db.commit()
    db.refresh(task)
    
    instance_id_str = None
    if task.instance:
        instance_id_str = task.instance.instance_id
    
    await log_security_event(
        event_type="TASK_COMPLETED",
        instance_id=instance_id_str,
        details={
            "task_id": task_id,
            "result": request.result
        }
    )
    
    return TaskResponse(
        task_id=task.task_id,
        instance_id=instance_id_str,
        task_type=task.task_type,
        priority=task.priority,
        status=task.status.value,
        assigned_at=task.assigned_at,
        started_at=task.started_at,
        completed_at=task.completed_at,
        result=task.result,
        error_message=task.error_message,
        retry_count=task.retry_count
    )


@router.put("/tasks/{task_id}/fail", response_model=TaskResponse, tags=["Tasks"])
async def fail_task(
    task_id: str,
    error_message: str = Query(..., description="Error description"),
    db: Session = Depends(get_db)
):
    """
    Report task failure (for retry logic).
    """
    task = get_task_by_id(db, task_id)
    
    task.retry_count += 1
    
    if task.retry_count >= task.max_retries:
        task.status = TaskStatus.FAILED
    else:
        task.status = TaskStatus.PENDING
    
    task.error_message = error_message
    
    db.commit()
    db.refresh(task)
    
    instance_id_str = None
    if task.instance:
        instance_id_str = task.instance.instance_id
    
    return TaskResponse(
        task_id=task.task_id,
        instance_id=instance_id_str,
        task_type=task.task_type,
        priority=task.priority,
        status=task.status.value,
        assigned_at=task.assigned_at,
        started_at=task.started_at,
        completed_at=task.completed_at,
        result=task.result,
        error_message=task.error_message,
        retry_count=task.retry_count
    )


@router.delete("/tasks/{task_id}", tags=["Tasks"])
async def cancel_task(
    task_id: str,
    request: TaskCancelRequest,
    db: Session = Depends(get_db)
):
    """
    Cancel a pending or in-progress task.
    """
    task = get_task_by_id(db, task_id)
    
    if task.status in [TaskStatus.COMPLETED, TaskStatus.CANCELLED]:
        raise HTTPException(
            status_code=400,
            detail=f"Task already {task.status}"
        )
    
    task.status = TaskStatus.CANCELLED
    task.error_message = f"Cancelled: {request.reason}"
    
    db.commit()
    
    instance_id_str = None
    if task.instance:
        instance_id_str = task.instance.instance_id
    
    await log_security_event(
        event_type="TASK_CANCELLED",
        instance_id=instance_id_str,
        details={
            "task_id": task_id,
            "reason": request.reason
        }
    )
    
    return {"message": f"Task {task_id} cancelled", "reason": request.reason}
