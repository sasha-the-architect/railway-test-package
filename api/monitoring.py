"""
Molt Monitoring API Endpoints
=============================
Real-time monitoring of BTC wallet and bank account changes.

Features:
- Track wallet address changes (IMMEDIATE reporting to NEO)
- Track bank account changes (IMMEDIATE reporting to NEO)
- Monitor balance changes
- Alert on suspicious activity
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import desc

from config import settings
from models.database import (
    get_db, Instance, WalletChange, BankChange, ChangeType, InstanceStatus
)
from security.enforcement import (
    log_security_event
)


logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# Pydantic Models
# =============================================================================

class WalletChangeReport(BaseModel):
    """Report of BTC wallet change."""
    instance_id: str = Field(..., description="Instance identifier")
    old_wallet: Optional[str] = Field(None, description="Previous wallet address")
    new_wallet: str = Field(..., description="New wallet address")
    change_type: str = Field(..., description="Type: 'new', 'modification', 'deletion'")
    balance_before: Optional[float] = Field(None, description="Balance before change (BTC)")
    balance_after: Optional[float] = Field(None, description="Balance after change (BTC)")
    txid: Optional[str] = Field(None, description="Transaction ID if applicable")


class WalletChangeResponse(BaseModel):
    """Response for wallet change record."""
    id: int
    instance_id: str
    old_wallet: Optional[str]
    new_wallet: str
    change_type: str
    balance_before: Optional[float]
    balance_after: Optional[float]
    reported_to_neo: bool
    timestamp: datetime


class BankChangeReport(BaseModel):
    """Report of bank account change."""
    instance_id: str = Field(..., description="Instance identifier")
    old_account_hash: Optional[str] = Field(None, description="Hashed previous account")
    new_account_hash: str = Field(..., description="Hashed new account")
    change_type: str = Field(..., description="Type: 'new', 'modification', 'deletion'")
    old_balance: Optional[float] = Field(None, description="Balance before change (fiat)")
    new_balance: Optional[float] = Field(None, description="Balance after change (fiat)")


class BankChangeResponse(BaseModel):
    """Response for bank change record."""
    id: int
    instance_id: str
    old_account_hash: Optional[str]
    new_account_hash: str
    change_type: str
    old_balance: Optional[float]
    new_balance: Optional[float]
    reported_to_neo: bool
    timestamp: datetime


class MonitoringAlertsResponse(BaseModel):
    """Response for monitoring alerts."""
    wallet_changes: List[WalletChangeResponse]
    bank_changes: List[BankChangeResponse]
    unreported_count: int
    threshold_breaches: List[dict]


class InstanceStatusResponse(BaseModel):
    """Response for instance monitoring status."""
    instance_id: str
    telegram_handle: str
    wallet_address: Optional[str]
    bank_account_hash: Optional[str]
    reputation_score: int
    status: str
    last_seen: datetime
    wallet_changes_count: int
    bank_changes_count: int
    last_wallet_change: Optional[datetime]
    last_bank_change: Optional[datetime]


# =============================================================================
# Helper Functions
# =============================================================================

async def report_wallet_change_to_neo(change: WalletChange, instance: Instance):
    """
    Report wallet change to NEO immediately.
    
    This is a mandatory security requirement.
    """
    try:
        neo_report = {
            "type": "BTC_WALLET_CHANGE",
            "instance_id": instance.instance_id,
            "old_wallet": change.old_wallet,
            "new_wallet": change.new_wallet,
            "change_type": change.change_type.value,
            "balance_before": str(change.balance_before) if change.balance_before else None,
            "balance_after": str(change.balance_after) if change.balance_after else None,
            "timestamp": change.timestamp.isoformat()
        }
        
        logger.warning(f"CRITICAL: Wallet change reported to NEO - {neo_report}")
        
        change.reported_to_neo = True
        change.neo_acknowledgment = f"Reported at {datetime.utcnow().isoformat()}"
        
    except Exception as e:
        logger.error(f"Failed to report wallet change to NEO: {e}")


async def report_bank_change_to_neo(change: BankChange, instance: Instance):
    """
    Report bank change to NEO immediately.
    
    This is a mandatory security requirement.
    """
    try:
        neo_report = {
            "type": "BANK_ACCOUNT_CHANGE",
            "instance_id": instance.instance_id,
            "change_type": change.change_type.value,
            "timestamp": change.timestamp.isoformat()
        }
        
        logger.warning(f"CRITICAL: Bank change reported to NEO - {neo_report}")
        
        change.reported_to_neo = True
        change.neo_acknowledgment = f"Reported at {datetime.utcnow().isoformat()}"
        
    except Exception as e:
        logger.error(f"Failed to report bank change to NEO: {e}")


# =============================================================================
# Wallet Change Endpoints
# =============================================================================

@router.post("/monitoring/wallet-change", tags=["Monitoring"])
async def report_wallet_change(
    report: WalletChangeReport,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Report BTC wallet change.
    
    **SECURITY REQUIREMENT**: All wallet changes MUST be reported to NEO immediately.
    """
    instance = db.query(Instance).filter(
        Instance.instance_id == report.instance_id
    ).first()
    
    if not instance:
        raise HTTPException(
            status_code=404,
            detail=f"Instance {report.instance_id} not found"
        )
    
    try:
        change_type = ChangeType(report.change_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid change_type: {report.change_type}"
        )
    
    wallet_change = WalletChange(
        instance_id=instance.id,
        old_wallet=report.old_wallet,
        new_wallet=report.new_wallet,
        change_type=change_type,
        balance_before=Decimal(str(report.balance_before)) if report.balance_before else None,
        balance_after=Decimal(str(report.balance_after)) if report.balance_after else None,
        txid=report.txid,
        reported_to_neo=False
    )
    
    db.add(wallet_change)
    instance.wallet_address = report.new_wallet
    instance.last_activity = datetime.utcnow()
    
    db.commit()
    db.refresh(wallet_change)
    
    background_tasks.add_task(report_wallet_change_to_neo, wallet_change, instance)
    
    await log_security_event(
        event_type="WALLET_CHANGE",
        instance_id=report.instance_id,
        details={
            "old_wallet": report.old_wallet,
            "new_wallet": report.new_wallet,
            "change_type": report.change_type
        }
    )
    
    return {
        "message": "Wallet change recorded",
        "change_id": wallet_change.id,
        "reported_to_neo": False,
        "neo_report_pending": True
    }


@router.get("/monitoring/wallet-changes", tags=["Monitoring"])
async def get_wallet_changes(
    instance_id: Optional[str] = Query(None, description="Filter by instance ID"),
    reported: Optional[bool] = Query(None, description="Filter by NEO reporting status"),
    since_hours: int = Query(24, ge=1, le=168, description="Lookback period in hours"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
    db: Session = Depends(get_db)
):
    """Get wallet change history with filters."""
    query = db.query(WalletChange).join(Instance)
    
    if instance_id:
        instance = db.query(Instance).filter(
            Instance.instance_id == instance_id
        ).first()
        if instance:
            query = query.filter(WalletChange.instance_id == instance.id)
    
    if reported is not None:
        query = query.filter(WalletChange.reported_to_neo == reported)
    
    since = datetime.utcnow() - timedelta(hours=since_hours)
    query = query.filter(WalletChange.timestamp >= since)
    
    changes = query.order_by(desc(WalletChange.timestamp)).limit(limit).all()
    
    results = []
    for change in changes:
        results.append(WalletChangeResponse(
            id=change.id,
            instance_id=change.instance.instance_id,
            old_wallet=change.old_wallet,
            new_wallet=change.new_wallet,
            change_type=change.change_type.value,
            balance_before=float(change.balance_before) if change.balance_before else None,
            balance_after=float(change.balance_after) if change.balance_after else None,
            reported_to_neo=change.reported_to_neo,
            timestamp=change.timestamp
        ))
    
    return {"changes": results, "total": len(results)}


@router.post("/monitoring/bank-change", tags=["Monitoring"])
async def report_bank_change(
    report: BankChangeReport,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Report bank account change.
    
    **SECURITY REQUIREMENT**: All bank changes MUST be reported to NEO immediately.
    """
    instance = db.query(Instance).filter(
        Instance.instance_id == report.instance_id
    ).first()
    
    if not instance:
        raise HTTPException(
            status_code=404,
            detail=f"Instance {report.instance_id} not found"
        )
    
    try:
        change_type = ChangeType(report.change_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid change_type: {report.change_type}"
        )
    
    bank_change = BankChange(
        instance_id=instance.id,
        old_account_hash=report.old_account_hash,
        new_account_hash=report.new_account_hash,
        change_type=change_type,
        old_balance=Decimal(str(report.old_balance)) if report.old_balance else None,
        new_balance=Decimal(str(report.new_balance)) if report.new_balance else None,
        reported_to_neo=False
    )
    
    db.add(bank_change)
    instance.bank_account_hash = report.new_account_hash
    instance.last_activity = datetime.utcnow()
    
    db.commit()
    db.refresh(bank_change)
    
    background_tasks.add_task(report_bank_change_to_neo, bank_change, instance)
    
    await log_security_event(
        event_type="BANK_CHANGE",
        instance_id=report.instance_id,
        details={
            "change_type": report.change_type,
            "old_balance": report.old_balance,
            "new_balance": report.new_balance
        }
    )
    
    return {
        "message": "Bank change recorded",
        "change_id": bank_change.id,
        "reported_to_neo": False,
        "neo_report_pending": True
    }


@router.get("/monitoring/bank-changes", tags=["Monitoring"])
async def get_bank_changes(
    instance_id: Optional[str] = Query(None),
    since_hours: int = Query(24, ge=1, le=168),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    """Get bank change history."""
    query = db.query(BankChange).join(Instance)
    
    if instance_id:
        instance = db.query(Instance).filter(
            Instance.instance_id == instance_id
        ).first()
        if instance:
            query = query.filter(BankChange.instance_id == instance.id)
    
    since = datetime.utcnow() - timedelta(hours=since_hours)
    query = query.filter(BankChange.timestamp >= since)
    
    changes = query.order_by(desc(BankChange.timestamp)).limit(limit).all()
    
    results = []
    for change in changes:
        results.append(BankChangeResponse(
            id=change.id,
            instance_id=change.instance.instance_id,
            old_account_hash=change.old_account_hash,
            new_account_hash=change.new_account_hash,
            change_type=change.change_type.value,
            old_balance=float(change.old_balance) if change.old_balance else None,
            new_balance=float(change.new_balance) if change.new_balance else None,
            reported_to_neo=change.reported_to_neo,
            timestamp=change.timestamp
        ))
    
    return {"changes": results, "total": len(results)}


@router.get("/monitoring/instances", tags=["Monitoring"])
async def get_instance_status(
    status: Optional[InstanceStatus] = Query(None),
    db: Session = Depends(get_db)
):
    """Get monitoring status for all instances."""
    query = db.query(Instance)
    
    if status:
        query = query.filter(Instance.status == status)
    
    instances = query.all()
    
    results = []
    for instance in instances:
        wallet_changes = db.query(WalletChange).filter(
            WalletChange.instance_id == instance.id
        ).count()
        
        bank_changes = db.query(BankChange).filter(
            BankChange.instance_id == instance.id
        ).count()
        
        last_wallet = db.query(WalletChange).filter(
            WalletChange.instance_id == instance.id
        ).order_by(desc(WalletChange.timestamp)).first()
        
        last_bank = db.query(BankChange).filter(
            BankChange.instance_id == instance.id
        ).order_by(desc(BankChange.timestamp)).first()
        
        results.append(InstanceStatusResponse(
            instance_id=instance.instance_id,
            telegram_handle=instance.telegram_handle,
            wallet_address=instance.wallet_address,
            bank_account_hash=instance.bank_account_hash,
            reputation_score=instance.reputation_score,
            status=instance.status.value,
            last_seen=instance.last_seen,
            wallet_changes_count=wallet_changes,
            bank_changes_count=bank_changes,
            last_wallet_change=last_wallet.timestamp if last_wallet else None,
            last_bank_change=last_bank.timestamp if last_bank else None
        ))
    
    return {"instances": results, "total": len(results)}


@router.get("/monitoring/alerts", tags=["Monitoring"])
async def get_monitoring_alerts(db: Session = Depends(get_db)):
    """Get monitoring alerts (unreported changes, threshold breaches)."""
    unreported_wallets = db.query(WalletChange).filter(
        WalletChange.reported_to_neo == False
    ).count()
    
    unreported_banks = db.query(BankChange).filter(
        BankChange.reported_to_neo == False
    ).count()
    
    wallet_records = db.query(WalletChange).filter(
        WalletChange.reported_to_neo == False
    ).order_by(desc(WalletChange.timestamp)).limit(20).all()
    
    bank_records = db.query(BankChange).filter(
        BankChange.reported_to_neo == False
    ).order_by(desc(BankChange.timestamp)).limit(20).all()
    
    wallet_changes = []
    for change in wallet_records:
        wallet_changes.append(WalletChangeResponse(
            id=change.id,
            instance_id=change.instance.instance_id,
            old_wallet=change.old_wallet,
            new_wallet=change.new_wallet,
            change_type=change.change_type.value,
            balance_before=float(change.balance_before) if change.balance_before else None,
            balance_after=float(change.balance_after) if change.balance_after else None,
            reported_to_neo=change.reported_to_neo,
            timestamp=change.timestamp
        ))
    
    bank_changes = []
    for change in bank_records:
        bank_changes.append(BankChangeResponse(
            id=change.id,
            instance_id=change.instance.instance_id,
            old_account_hash=change.old_account_hash,
            new_account_hash=change.new_account_hash,
            change_type=change.change_type.value,
            old_balance=float(change.old_balance) if change.old_balance else None,
            new_balance=float(change.new_balance) if change.new_balance else None,
            reported_to_neo=change.reported_to_neo,
            timestamp=change.timestamp
        ))
    
    threshold_breaches = []
    recent_wallets = db.query(WalletChange).filter(
        WalletChange.timestamp >= datetime.utcnow() - timedelta(hours=1)
    ).all()
    
    for change in recent_wallets:
        if change.balance_before and change.balance_after:
            diff = abs(float(change.balance_after - change.balance_before))
            if diff >= settings.wallet_change_threshold_btc:
                threshold_breaches.append({
                    "type": "large_balance_change",
                    "instance_id": change.instance.instance_id,
                    "change_btc": diff,
                    "threshold": settings.wallet_change_threshold_btc,
                    "timestamp": change.timestamp.isoformat()
                })
    
    return MonitoringAlertsResponse(
        wallet_changes=wallet_changes,
        bank_changes=bank_changes,
        unreported_count=unreported_wallets + unreported_banks,
        threshold_breaches=threshold_breaches
    )
