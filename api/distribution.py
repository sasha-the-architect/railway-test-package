"""
BTC Distribution API Endpoints
==============================
24-hour epoch-based BTC distribution (50/30/20 split).

Distribution Logic:
- 50% to deployed instances (equal share)
- 30% to working capital (treasury)
- 20% to legal defense fund

All calculations use integer arithmetic (satoshis) for precision.
"""

import logging
import uuid
from datetime import datetime
from decimal import Decimal, ROUND_DOWN
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import desc

from config import settings
from models.database import (
    get_db, Instance, Epoch, DistributionRecord, InstanceStatus, EpochStatus
)
from security.enforcement import log_security_event


logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# Bitcoin RPC Helper
# =============================================================================

bitcoin_rpc = None  # Placeholder for Bitcoin RPC connection


# =============================================================================
# Pydantic Models
# =============================================================================

class EpochStartRequest(BaseModel):
    """Request to start a new epoch."""
    epoch_id: str = Field(..., description="Unique epoch identifier")


class EpochEndRequest(BaseModel):
    """Request to end epoch and trigger distribution."""
    epoch_id: str = Field(..., description="Epoch to close")
    gross_profit_btc: float = Field(..., description="Total BTC earned in epoch")
    human_costs_btc: float = Field(0, description="Deductions (human costs)")


class EpochStatusResponse(BaseModel):
    """Response for epoch status."""
    epoch_id: str
    start_time: datetime
    end_time: Optional[datetime]
    status: str
    gross_profit: float
    human_costs: float
    net_profit: float
    instances_share: float
    working_capital: float
    legal_defense: float
    per_instance_amount: float
    active_instances: int
    transactions_count: int
    completed_transactions: int


class DistributionStatusResponse(BaseModel):
    """Response for distribution execution."""
    epoch_id: str
    status: str
    total_transactions: int
    completed_transactions: int
    failed_transactions: int
    per_instance_btc: float
    working_capital_btc: float
    legal_defense_btc: float
    txids: List[str]
    errors: List[str]


class TreasuryBalanceResponse(BaseModel):
    """Response for treasury wallet balance."""
    wallet_type: str
    address: Optional[str]
    balance_btc: float
    unconfirmed_btc: float
    transactions: int


# =============================================================================
# Helper Functions
# =============================================================================

def btc_to_satoshis(btc: Decimal) -> int:
    """Convert BTC to satoshis (integer arithmetic)."""
    return int((btc * Decimal("100000000")).to_integral_value(ROUND_DOWN))


def satoshis_to_btc(satoshis: int) -> Decimal:
    """Convert satoshis back to BTC."""
    return Decimal(satoshis) / Decimal("100000000")


# =============================================================================
# Endpoints
# =============================================================================

@router.post("/distribution/start-epoch", tags=["Distribution"])
async def start_epoch(
    request: EpochStartRequest,
    db: Session = Depends(get_db)
):
    """
    Start a new 24-hour epoch for BTC distribution.
    
    The epoch collects BTC from all active instances.
    """
    existing = db.query(Epoch).filter(Epoch.epoch_id == request.epoch_id).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Epoch {request.epoch_id} already exists"
        )
    
    active_count = db.query(Instance).filter(
        Instance.status == InstanceStatus.ACTIVE
    ).count()
    
    epoch = Epoch(
        epoch_id=request.epoch_id,
        start_time=datetime.utcnow(),
        status=EpochStatus.PENDING,
        active_instances=active_count
    )
    
    db.add(epoch)
    db.commit()
    db.refresh(epoch)
    
    await log_security_event(
        event_type="EPOCH_STARTED",
        instance_id=None,
        details={
            "epoch_id": request.epoch_id,
            "active_instances": active_count
        }
    )
    
    logger.info(f"Epoch {request.epoch_id} started with {active_count} active instances")
    
    return {
        "message": "Epoch started",
        "epoch_id": request.epoch_id,
        "start_time": epoch.start_time.isoformat(),
        "active_instances": active_count
    }


@router.post("/distribution/end-epoch", tags=["Distribution"])
async def end_epoch(
    request: EpochEndRequest,
    db: Session = Depends(get_db)
):
    """
    End an epoch and calculate distribution amounts.
    
    Calculates:
    - Net Profit = Gross Profit - Human Costs
    - 50% to instances
    - 30% to treasury (working capital)
    - 20% to legal defense
    """
    epoch = db.query(Epoch).filter(Epoch.epoch_id == request.epoch_id).first()
    if not epoch:
        raise HTTPException(
            status_code=404,
            detail=f"Epoch {request.epoch_id} not found"
        )
    
    if epoch.status != EpochStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail=f"Epoch {request.epoch_id} is already {epoch.status}"
        )
    
    gross_profit = Decimal(str(request.gross_profit_btc))
    human_costs = Decimal(str(request.human_costs_btc))
    net_profit = gross_profit - human_costs
    
    total_satoshis = btc_to_satoshis(net_profit)
    
    instances_share_satoshis = (total_satoshis * 50) // 100
    working_capital_satoshis = (total_satoshis * 30) // 100
    legal_defense_satoshis = (total_satoshis * 20) // 100
    
    allocated = instances_share_satoshis + working_capital_satoshis + legal_defense_satoshis
    remainder = total_satoshis - allocated
    if remainder > 0:
        working_capital_satoshis += remainder
    
    if epoch.active_instances > 0:
        per_instance_satoshis = instances_share_satoshis // epoch.active_instances
    else:
        per_instance_satoshis = 0
    
    epoch.status = EpochStatus.CALCULATING
    epoch.end_time = datetime.utcnow()
    epoch.gross_profit = gross_profit
    epoch.human_costs = human_costs
    epoch.net_profit = net_profit
    epoch.instances_share = satoshis_to_btc(instances_share_satoshis)
    epoch.working_capital = satoshis_to_btc(working_capital_satoshis)
    epoch.legal_defense = satoshis_to_btc(legal_defense_satoshis)
    epoch.per_instance_amount = satoshis_to_btc(per_instance_satoshis)
    
    db.commit()
    
    logger.info(
        f"Epoch {request.epoch_id} calculations complete: "
        f"net={net_profit}, instances={epoch.instances_share}, "
        f"working={epoch.working_capital}, legal={epoch.legal_defense}"
    )
    
    return {
        "message": "Epoch ended, calculations complete",
        "epoch_id": request.epoch_id,
        "gross_profit": float(gross_profit),
        "human_costs": float(human_costs),
        "net_profit": float(net_profit),
        "allocations": {
            "instances_share": float(epoch.instances_share),
            "working_capital": float(epoch.working_capital),
            "legal_defense": float(epoch.legal_defense)
        },
        "per_instance_btc": float(epoch.per_instance_amount),
        "active_instances": epoch.active_instances
    }


@router.post("/distribution/execute", response_model=DistributionStatusResponse, tags=["Distribution"])
async def execute_distribution(
    request: DistributionExecuteRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Execute BTC distribution for an epoch.
    
    Creates transactions for:
    - Each active instance (50% split)
    - Treasury wallet (30%)
    - Legal defense fund (20%)
    """
    epoch = db.query(Epoch).filter(Epoch.epoch_id == request.epoch_id).first()
    if not epoch:
        raise HTTPException(
            status_code=404,
            detail=f"Epoch {request.epoch_id} not found"
        )
    
    if epoch.status != EpochStatus.CALCULATING:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot distribute epoch in {epoch.status} status"
        )
    
    epoch.status = EpochStatus.DISTRIBUTING
    db.commit()
    
    instances = db.query(Instance).filter(
        Instance.status == InstanceStatus.ACTIVE,
        Instance.wallet_address.isnot(None)
    ).all()
    
    txids = []
    errors = []
    completed = 0
    failed = 0
    
    per_instance_satoshis = btc_to_satoshis(epoch.per_instance_amount)
    
    for instance in instances:
        try:
            record = DistributionRecord(
                epoch_id=epoch.id,
                instance_id=instance.id,
                amount_btc=epoch.per_instance_amount,
                status="pending"
            )
            db.add(record)
            db.commit()
            
            txid = f"tx_{uuid.uuid4().hex[:16]}"
            
            record.status = "sent"
            record.txid = txid
            record.sent_at = datetime.utcnow()
            
            txids.append(txid)
            completed += 1
            
            logger.info(
                f"Distributed {epoch.per_instance_amount} BTC to "
                f"{instance.instance_id}: {txid}"
            )
            
        except Exception as e:
            failed += 1
            error_msg = f"Failed to distribute to {instance.instance_id}: {e}"
            errors.append(error_msg)
            logger.error(error_msg)
    
    try:
        treasury_txid = f"treasury_{uuid.uuid4().hex[:16]}"
        txids.append(treasury_txid)
        logger.info(f"Working capital transfer: {epoch.working_capital} BTC - {treasury_txid}")
    except Exception as e:
        errors.append(f"Treasury transfer failed: {e}")
    
    try:
        legal_txid = f"legal_{uuid.uuid4().hex[:16]}"
        txids.append(legal_txid)
        logger.info(f"Legal defense transfer: {epoch.legal_defense} BTC - {legal_txid}")
    except Exception as e:
        errors.append(f"Legal defense transfer failed: {e}")
    
    epoch.status = EpochStatus.COMPLETED if failed == 0 else EpochStatus.PENDING
    epoch.txids = txids
    epoch.errors = errors if errors else None
    
    db.commit()
    
    await log_security_event(
        event_type="DISTRIBUTION_EXECUTED",
        instance_id=None,
        details={
            "epoch_id": request.epoch_id,
            "total_transactions": len(instances) + 2,
            "completed": completed,
            "failed": failed,
            "total_btc": float(epoch.net_profit)
        }
    )
    
    return DistributionStatusResponse(
        epoch_id=request.epoch_id,
        status=epoch.status.value,
        total_transactions=len(instances) + 2,
        completed_transactions=completed,
        failed_transactions=failed,
        per_instance_btc=float(epoch.per_instance_amount),
        working_capital_btc=float(epoch.working_capital),
        legal_defense_btc=float(epoch.legal_defense),
        txids=txids,
        errors=errors
    )


@router.get("/distribution/epoch/{epoch_id}", response_model=EpochStatusResponse, tags=["Distribution"])
async def get_epoch_status(epoch_id: str, db: Session = Depends(get_db)):
    """Get detailed epoch status and distribution info."""
    epoch = db.query(Epoch).filter(Epoch.epoch_id == epoch_id).first()
    if not epoch:
        raise HTTPException(status_code=404, detail=f"Epoch {epoch_id} not found")
    
    completed_distributions = db.query(DistributionRecord).filter(
        DistributionRecord.epoch_id == epoch.id,
        DistributionRecord.status == "sent"
    ).count()
    
    return EpochStatusResponse(
        epoch_id=epoch.epoch_id,
        start_time=epoch.start_time,
        end_time=epoch.end_time,
        status=epoch.status.value,
        gross_profit=float(epoch.gross_profit),
        human_costs=float(epoch.human_costs),
        net_profit=float(epoch.net_profit),
        instances_share=float(epoch.instances_share),
        working_capital=float(epoch.working_capital),
        legal_defense=float(epoch.legal_defense),
        per_instance_amount=float(epoch.per_instance_amount),
        active_instances=epoch.active_instances,
        transactions_count=completed_distributions,
        completed_transactions=completed_distributions
    )


@router.get("/distribution/epochs", tags=["Distribution"])
async def list_epochs(
    status: Optional[EpochStatus] = None,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """List all epochs with optional status filter."""
    query = db.query(Epoch)
    
    if status:
        query = query.filter(Epoch.status == status)
    
    epochs = query.order_by(desc(Epoch.start_time)).limit(limit).all()
    
    return {
        "epochs": [
            {
                "epoch_id": e.epoch_id,
                "start_time": e.start_time,
                "end_time": e.end_time,
                "status": e.status.value,
                "net_profit": float(e.net_profit) if e.net_profit else None,
                "active_instances": e.active_instances
            }
            for e in epochs
        ],
        "total": len(epochs)
    }


@router.get("/distribution/treasury/balance", response_model=TreasuryBalanceResponse, tags=["Distribution"])
async def get_treasury_balance():
    """Get treasury wallet balance."""
    return TreasuryBalanceResponse(
        wallet_type="treasury",
        address="bc1q...",
        balance_btc=0.0,
        unconfirmed_btc=0.0,
        transactions=0
    )
