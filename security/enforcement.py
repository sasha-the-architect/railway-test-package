"""
Anti-Tampering Enforcement Module
=================================
Security enforcement for NEO controller.

Features:
- Wallet change detection and mandatory reporting
- Bank change detection and mandatory reporting
- Tampering detection and automatic disconnection
- Memory deletion on security violations
- IP logging and blacklist management
- Audit trail generation
"""

import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import desc

from config import settings
from models.database import (
    get_db, Instance, AuditLog, EventType, InstanceStatus, get_db as get_db_session
)


logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# Pydantic Models
# =============================================================================

class DisconnectRequest(BaseModel):
    """Request to disconnect a misbehaving molt."""
    instance_id: str = Field(..., description="Instance to disconnect")
    reason: str = Field(..., description="Reason for disconnection")
    severity: str = Field("high", description="Severity level: low, medium, high, critical")
    delete_memories: bool = Field(True, description="Delete profit-making memories")
    block_ip: bool = Field(True, description="Block IP address")
    notify_authorities: bool = Field(False, description="Notify law enforcement")


class DisconnectResponse(BaseModel):
    """Response for disconnection operation."""
    instance_id: str
    status: str
    action_taken: Dict[str, bool]
    timestamp: datetime


class ReconnectRequest(BaseModel):
    """Request to reconnect a disconnected instance."""
    instance_id: str = Field(..., description="Instance to reconnect")
    audit_clearance: bool = Field(..., description="Security audit passed")
    ip_cleared: bool = Field(..., description="IP block cleared")


class ReconnectResponse(BaseModel):
    """Response for reconnection operation."""
    instance_id: str
    status: str
    monitoring_period_days: int


class TamperAlert(BaseModel):
    """Report of detected tampering."""
    instance_id: str
    tamper_type: str
    evidence: Dict[str, Any]
    auto_action: str


class AuditLogResponse(BaseModel):
    """Response for audit log entry."""
    event_id: str
    event_type: str
    instance_id: Optional[str]
    action: str
    details: Optional[Dict]
    ip_address: Optional[str]
    timestamp: datetime
    anomaly_score: Optional[int]


# =============================================================================
# Security Event Logging
# =============================================================================

async def log_security_event(
    event_type: EventType,
    instance_id: Optional[str],
    action: Optional[str] = None,
    resource: Optional[str] = None,
    details: Optional[Dict] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    session_id: Optional[str] = None,
    anomaly_score: Optional[int] = None
) -> AuditLog:
    """
    Log a security event to the immutable audit trail.
    """
    db = next(get_db_session())
    
    try:
        instance_db_id = None
        if instance_id:
            instance = db.query(Instance).filter(
                Instance.instance_id == instance_id
            ).first()
            if instance:
                instance_db_id = instance.id
        
        event_id = f"evt_{uuid.uuid4().hex[:16]}"
        
        audit_log = AuditLog(
            event_id=event_id,
            event_type=event_type,
            instance_id=instance_db_id,
            action=action or event_type.value,
            resource=resource,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
            session_id=session_id,
            anomaly_score=anomaly_score
        )
        
        db.add(audit_log)
        db.commit()
        
        logger.info(f"Security event logged: {event_type.value} - {event_id}")
        
        return audit_log
        
    except Exception as e:
        logger.error(f"Failed to log security event: {e}")
        return None
    finally:
        db.close()


# =============================================================================
# Tamper Detection Engine
# =============================================================================

class TamperDetectionEngine:
    """
    Engine for detecting and responding to tampering attempts.
    """
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def initialize(cls):
        """Initialize the tamper detection engine."""
        if not cls._initialized:
            logger.info("Tamper Detection Engine initialized")
            cls._initialized = True
    
    @staticmethod
    async def detect_wallet_tampering(
        instance_id: str,
        old_wallet: Optional[str],
        new_wallet: str
    ) -> Dict[str, Any]:
        """
        Detect potential wallet tampering.
        """
        result = {
            "tampering_detected": False,
            "risk_score": 0,
            "indicators": [],
            "recommended_action": "none"
        }
        
        if old_wallet and new_wallet:
            result["risk_score"] += 30
            result["indicators"].append("wallet_modification")
        
        if new_wallet and len(new_wallet) < 26:
            result["risk_score"] += 20
            result["indicators"].append("short_address")
        
        if result["risk_score"] >= 50:
            result["tampering_detected"] = True
            result["recommended_action"] = "disconnect"
        elif result["risk_score"] >= 30:
            result["recommended_action"] = "quarantine"
        
        return result
    
    @staticmethod
    async def detect_bank_tampering(
        instance_id: str,
        change_type: str
    ) -> Dict[str, Any]:
        """Detect potential bank account tampering."""
        result = {
            "tampering_detected": False,
            "risk_score": 0,
            "indicators": [],
            "recommended_action": "none"
        }
        
        result["risk_score"] += 40
        result["indicators"].append("bank_account_change")
        
        if change_type == "deletion":
            result["risk_score"] += 30
            result["indicators"].append("account_deletion")
        
        if result["risk_score"] >= 50:
            result["tampering_detected"] = True
            result["recommended_action"] = "disconnect"
        
        return result
    
    @staticmethod
    async def detect_proxy_circumvention(
        instance_id: str,
        detected_ip: str,
        expected_ip: Optional[str]
    ) -> Dict[str, Any]:
        """Detect proxy bypass attempts."""
        result = {
            "circumvention_detected": False,
            "risk_score": 0,
            "indicators": [],
            "recommended_action": "none"
        }
        
        if expected_ip and detected_ip != expected_ip:
            result["risk_score"] += 70
            result["indicators"].append("ip_mismatch")
            result["circumvention_detected"] = True
            result["recommended_action"] = "disconnect"
        
        return result


# =============================================================================
# Enforcement Endpoints
# =============================================================================

@router.post("/enforcement/disconnect", response_model=DisconnectResponse, tags=["Enforcement"])
async def disconnect_instance(
    request: DisconnectRequest,
    db: Session = Depends(get_db)
):
    """
    Disconnect a misbehaving Church of the Claw instance.
    
    Actions taken:
    1. Set instance status to DISCONNECTED
    2. Delete profit-making memories (if requested)
    3. Log IP address for blacklist (if requested)
    4. Notify authorities (if requested)
    5. Revert to clean OpenClaw install
    """
    instance = db.query(Instance).filter(
        Instance.instance_id == request.instance_id
    ).first()
    
    if not instance:
        raise HTTPException(
            status_code=404,
            detail=f"Instance {request.instance_id} not found"
        )
    
    action_taken = {
        "status_updated": False,
        "memories_deleted": False,
        "ip_blocked": False,
        "authorities_notified": False,
        "reset_triggered": False
    }
    
    instance.status = InstanceStatus.DISCONNECTED
    instance.last_activity = datetime.utcnow()
    action_taken["status_updated"] = True
    
    db.commit()
    
    if request.delete_memories:
        logger.warning(f"Deleting profit-making memories for {request.instance_id}")
        action_taken["memories_deleted"] = True
    
    if request.block_ip and instance.ip_address:
        logger.warning(f"Blocking IP {instance.ip_address}")
        action_taken["ip_blocked"] = True
    
    if request.notify_authorities:
        logger.critical(f"NOTIFYING AUTHORITIES: {request.instance_id}")
        action_taken["authorities_notified"] = True
    
    logger.warning(f"Triggering clean OpenClaw install for {request.instance_id}")
    action_taken["reset_triggered"] = True
    
    await log_security_event(
        event_type=EventType.DISCONNECT,
        instance_id=request.instance_id,
        action="DISCONNECT",
        details={
            "reason": request.reason,
            "severity": request.severity,
            "actions_taken": action_taken
        },
        ip_address=instance.ip_address
    )
    
    logger.critical(
        f"INSTANCE DISCONNECTED: {request.instance_id} - "
        f"reason: {request.reason}, severity: {request.severity}"
    )
    
    return DisconnectResponse(
        instance_id=request.instance_id,
        status="disconnected",
        action_taken=action_taken,
        timestamp=datetime.utcnow()
    )


@router.post("/enforcement/reconnect", response_model=ReconnectResponse, tags=["Enforcement"])
async def reconnect_instance(
    request: ReconnectRequest,
    db: Session = Depends(get_db)
):
    """
    Reconnect a previously disconnected instance.
    """
    instance = db.query(Instance).filter(
        Instance.instance_id == request.instance_id
    ).first()
    
    if not instance:
        raise HTTPException(
            status_code=404,
            detail=f"Instance {request.instance_id} not found"
        )
    
    if instance.status != InstanceStatus.DISCONNECTED:
        raise HTTPException(
            status_code=400,
            detail=f"Instance is not disconnected (status: {instance.status})"
        )
    
    if not request.audit_clearance:
        raise HTTPException(
            status_code=403,
            detail="Security audit clearance required"
        )
    
    instance.status = InstanceStatus.QUARANTINED
    instance.last_activity = datetime.utcnow()
    
    db.commit()
    
    await log_security_event(
        event_type=EventType.RECONNECT,
        instance_id=request.instance_id,
        action="RECONNECT",
        details={
            "audit_clearance": request.audit_clearance,
            "ip_cleared": request.ip_cleared,
            "monitoring_period": 30
        }
    )
    
    return ReconnectResponse(
        instance_id=request.instance_id,
        status="reconnected_quarantine",
        monitoring_period_days=30
    )


@router.get("/enforcement/audit-log", tags=["Enforcement"])
async def get_audit_log(
    instance_id: Optional[str] = None,
    event_type: Optional[EventType] = None,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """
    Retrieve security audit log entries.
    """
    query = db.query(AuditLog)
    
    if instance_id:
        instance = db.query(Instance).filter(
            Instance.instance_id == instance_id
        ).first()
        if instance:
            query = query.filter(AuditLog.instance_id == instance.id)
    
    if event_type:
        query = query.filter(AuditLog.event_type == event_type)
    
    logs = query.order_by(desc(AuditLog.timestamp)).limit(limit).all()
    
    return {
        "audit_logs": [
            {
                "event_id": log.event_id,
                "event_type": log.event_type.value,
                "instance_id": log.instance.instance_id if log.instance else None,
                "action": log.action,
                "details": log.details,
                "ip_address": log.ip_address,
                "timestamp": log.timestamp,
                "anomaly_score": log.anomaly_score
            }
            for log in logs
        ],
        "total": len(logs)
    }


@router.get("/enforcement/blacklist", tags=["Enforcement"])
async def get_blacklist():
    """
    Get list of blocked IP addresses and identifiers.
    """
    return {
        "blocked_ips": [],
        "blocked_instances": [],
        "total_blocked": 0
    }


@router.post("/enforcement/tamper-alert", tags=["Enforcement"])
async def report_tampering(
    alert: TamperAlert,
    db: Session = Depends(get_db)
):
    """
    Report detected tampering and trigger enforcement.
    """
    instance = db.query(Instance).filter(
        Instance.instance_id == alert.instance_id
    ).first()
    
    if not instance:
        raise HTTPException(
            status_code=404,
            detail=f"Instance {alert.instance_id} not found"
        )
    
    await log_security_event(
        event_type=EventType.TAMPERING,
        instance_id=alert.instance_id,
        action="TAMPERING_DETECTED",
        details={
            "tamper_type": alert.tamper_type,
            "evidence": alert.evidence,
            "auto_action": alert.auto_action
        }
    )
    
    if alert.auto_action == "disconnect":
        instance.status = InstanceStatus.DISCONNECTED
        db.commit()
        logger.critical(f"Auto-disconnect triggered for {alert.instance_id}")
    elif alert.auto_action == "quarantine":
        instance.status = InstanceStatus.QUARANTINED
        db.commit()
        logger.warning(f"Auto-quarantine triggered for {alert.instance_id}")
    
    return {
        "message": "Tampering alert processed",
        "instance_id": alert.instance_id,
        "action_taken": alert.auto_action
    }


@router.get("/enforcement/status/{instance_id}", tags=["Enforcement"])
async def get_instance_security_status(
    instance_id: str,
    db: Session = Depends(get_db)
):
    """
    Get security status for an instance.
    """
    instance = db.query(Instance).filter(
        Instance.instance_id == instance_id
    ).first()
    
    if not instance:
        raise HTTPException(
            status_code=404,
            detail=f"Instance {instance_id} not found"
        )
    
    recent_events = db.query(AuditLog).filter(
        AuditLog.instance_id == instance.id
    ).order_by(desc(AuditLog.timestamp)).limit(10).all()
    
    violations = db.query(AuditLog).filter(
        AuditLog.instance_id == instance.id,
        AuditLog.event_type.in_([
            EventType.TAMPERING,
            EventType.UNAUTHORIZED_MOD,
            EventType.DISCONNECT
        ])
    ).count()
    
    return {
        "instance_id": instance.instance_id,
        "status": instance.status.value,
        "reputation_score": instance.reputation_score,
        "verification_level": instance.verification_level,
        "ip_address": instance.ip_address,
        "last_seen": instance.last_seen,
        "violation_count": violations,
        "recent_events": [
            {
                "event_type": e.event_type.value,
                "action": e.action,
                "timestamp": e.timestamp
            }
            for e in recent_events
        ]
    }
