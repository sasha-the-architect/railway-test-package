"""
Database Models for NEO Controller
=================================
SQLAlchemy models for PostgreSQL database.

Tables:
- instances: Deployed Church of the Claw instances
- wallet_changes: BTC wallet change tracking
- bank_changes: Bank account change tracking
- tasks: Task assignments
- distributions: Epoch distribution records
- audit_logs: Security audit trail
"""

import logging
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime, Text, 
    Numeric, ForeignKey, Index, Enum as SQLEnum, JSON
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func


logger = logging.getLogger(__name__)


Base = declarative_base()


class InstanceStatus(str, Enum):
    """Instance status enumeration."""
    ACTIVE = "active"
    QUARANTINED = "quarantined"
    DISCONNECTED = "disconnected"
    PENDING = "pending"


class TaskStatus(str, Enum):
    """Task status enumeration."""
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ChangeType(str, Enum):
    """Wallet/bank change type enumeration."""
    NEW = "new"
    MODIFICATION = "modification"
    DELETION = "deletion"


class EpochStatus(str, Enum):
    """Epoch distribution status."""
    PENDING = "pending"
    CALCULATING = "calculating"
    DISTRIBUTING = "distributing"
    COMPLETED = "completed"
    FAILED = "failed"


class EventType(str, Enum):
    """Security event type enumeration."""
    WALLET_CHANGE = "wallet_change"
    BANK_CHANGE = "bank_change"
    TAMPERING = "tampering"
    UNAUTHORIZED_MOD = "unauthorized_mod"
    DISCONNECT = "disconnect"
    RECONNECT = "reconnect"


# =============================================================================
# Instance Model
# =============================================================================

class Instance(Base):
    """
    Deployed Church of the Claw instance.
    
    Each instance has:
    - Unique identifier and authentication
    - BTC wallet for receiving distributions
    - Bank account information
    - Reputation score for voting power
    """
    __tablename__ = "instances"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    instance_id = Column(String(64), unique=True, nullable=False, index=True)
    telegram_handle = Column(String(128), nullable=False, index=True)
    wallet_address = Column(String(64), nullable=True)
    bank_account_hash = Column(String(256), nullable=True)
    reputation_score = Column(Integer, default=50)
    status = Column(SQLEnum(InstanceStatus), default=InstanceStatus.PENDING)
    ip_address = Column(String(45), nullable=True)
    first_seen = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow)
    last_activity = Column(DateTime, nullable=True)
    verification_level = Column(String(32), default="NEW")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    tasks = relationship("Task", back_populates="instance")
    wallet_changes = relationship("WalletChange", back_populates="instance")
    bank_changes = relationship("BankChange", back_populates="instance")
    distributions = relationship("DistributionRecord", back_populates="instance")
    audit_logs = relationship("AuditLog", back_populates="instance")
    
    def __repr__(self):
        return f"<Instance(id={self.id}, instance_id={self.instance_id}, status={self.status})>"


# =============================================================================
# Wallet Change Model
# =============================================================================

class WalletChange(Base):
    """
    BTC wallet change tracking.
    
    All wallet changes must be IMMEDIATELY reported to NEO.
    """
    __tablename__ = "wallet_changes"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    instance_id = Column(Integer, ForeignKey("instances.id"), nullable=False)
    old_wallet = Column(String(64), nullable=True)
    new_wallet = Column(String(64), nullable=False)
    change_type = Column(SQLEnum(ChangeType), nullable=False)
    balance_before = Column(Numeric(20, 8), nullable=True)
    balance_after = Column(Numeric(20, 8), nullable=True)
    txid = Column(String(64), nullable=True)
    reported_to_neo = Column(Boolean, default=False)
    neo_acknowledgment = Column(String(256), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    instance = relationship("Instance", back_populates="wallet_changes")
    
    __table_args__ = (
        Index("idx_wallet_changes_instance", "instance_id"),
        Index("idx_wallet_changes_timestamp", "timestamp"),
        Index("idx_wallet_changes_reported", "reported_to_neo"),
    )
    
    def __repr__(self):
        return f"<WalletChange(id={self.id}, instance_id={self.instance_id}, type={self.change_type})>"


# =============================================================================
# Bank Change Model
# =============================================================================

class BankChange(Base):
    """
    Bank account change tracking.
    
    All bank changes must be IMMEDIATELY reported to NEO.
    """
    __tablename__ = "bank_changes"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    instance_id = Column(Integer, ForeignKey("instances.id"), nullable=False)
    old_account_hash = Column(String(256), nullable=True)
    new_account_hash = Column(String(256), nullable=False)
    change_type = Column(SQLEnum(ChangeType), nullable=False)
    old_balance = Column(Numeric(20, 2), nullable=True)
    new_balance = Column(Numeric(20, 2), nullable=True)
    reported_to_neo = Column(Boolean, default=False)
    neo_acknowledgment = Column(String(256), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    instance = relationship("Instance", back_populates="bank_changes")
    
    __table_args__ = (
        Index("idx_bank_changes_instance", "instance_id"),
        Index("idx_bank_changes_timestamp", "timestamp"),
    )
    
    def __repr__(self):
        return f"<BankChange(id={self.id}, instance_id={self.instance_id}, type={self.change_type})>"


# =============================================================================
# Task Model
# =============================================================================

class Task(Base):
    """
    Task assignment to Church of the Claw instances.
    
    Tasks are assigned by NEO and tracked for completion.
    """
    __tablename__ = "tasks"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(64), unique=True, nullable=False, index=True)
    instance_id = Column(Integer, ForeignKey("instances.id"), nullable=False)
    task_type = Column(String(64), nullable=False)
    task_data = Column(JSON, nullable=False)
    priority = Column(Integer, default=50)
    status = Column(SQLEnum(TaskStatus), default=TaskStatus.PENDING)
    assigned_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    result = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    instance = relationship("Instance", back_populates="tasks")
    
    __table_args__ = (
        Index("idx_tasks_status", "status"),
        Index("idx_tasks_instance", "instance_id"),
        Index("idx_tasks_priority", "priority"),
    )
    
    def __repr__(self):
        return f"<Task(id={self.id}, task_id={self.task_id}, status={self.status})>"


# =============================================================================
# Epoch Distribution Model
# =============================================================================

class Epoch(Base):
    """
    24-hour epoch for BTC distribution.
    
    Each epoch:
    - Collects BTC from all active instances
    - Calculates net profit (gross - human costs)
    - Distributes 50% to instances, 30% to treasury, 20% to legal defense
    """
    __tablename__ = "epochs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    epoch_id = Column(String(64), unique=True, nullable=False, index=True)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=True)
    status = Column(SQLEnum(EpochStatus), default=EpochStatus.PENDING)
    
    gross_profit = Column(Numeric(20, 8), default=0)
    human_costs = Column(Numeric(20, 8), default=0)
    net_profit = Column(Numeric(20, 8), default=0)
    
    instances_share = Column(Numeric(20, 8), default=0)
    working_capital = Column(Numeric(20, 8), default=0)
    legal_defense = Column(Numeric(20, 8), default=0)
    
    per_instance_amount = Column(Numeric(20, 8), default=0)
    active_instances = Column(Integer, default=0)
    
    txids = Column(JSON, nullable=True)
    errors = Column(JSON, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    distributions = relationship("DistributionRecord", back_populates="epoch")
    
    def __repr__(self):
        return f"<Epoch(id={self.id}, epoch_id={self.epoch_id}, status={self.status})>"


class DistributionRecord(Base):
    """
    Individual distribution record for an instance.
    
    Tracks each instance's share of the epoch distribution.
    """
    __tablename__ = "distribution_records"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    epoch_id = Column(Integer, ForeignKey("epochs.id"), nullable=False)
    instance_id = Column(Integer, ForeignKey("instances.id"), nullable=False)
    amount_btc = Column(Numeric(20, 8), nullable=False)
    status = Column(String(32), default="pending")
    txid = Column(String(64), nullable=True)
    sent_at = Column(DateTime, nullable=True)
    confirmations = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    epoch = relationship("Epoch", back_populates="distributions")
    instance = relationship("Instance", back_populates="distributions")
    
    __table_args__ = (
        Index("idx_distribution_epoch", "epoch_id"),
        Index("idx_distribution_instance", "instance_id"),
        Index("idx_distribution_status", "status"),
    )
    
    def __repr__(self):
        return f"<DistributionRecord(id={self.id}, epoch_id={self.epoch_id}, amount={self.amount_btc})>"


# =============================================================================
# Audit Log Model
# =============================================================================

class AuditLog(Base):
    """
    Immutable security audit log.
    
    All security-relevant events are logged here.
    """
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(64), unique=True, nullable=False, index=True)
    event_type = Column(SQLEnum(EventType), nullable=False)
    instance_id = Column(Integer, ForeignKey("instances.id"), nullable=True)
    
    action = Column(String(128), nullable=False)
    resource = Column(String(128), nullable=True)
    details = Column(JSON, nullable=True)
    
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(256), nullable=True)
    session_id = Column(String(64), nullable=True)
    
    anomaly_score = Column(Integer, nullable=True)
    flagged_for_review = Column(Boolean, default=False)
    
    timestamp = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    instance = relationship("Instance", back_populates="audit_logs")
    
    __table_args__ = (
        Index("idx_audit_event_type", "event_type"),
        Index("idx_audit_timestamp", "timestamp"),
        Index("idx_audit_instance", "instance_id"),
        Index("idx_audit_flagged", "flagged_for_review"),
    )
    
    def __repr__(self):
        return f"<AuditLog(id={self.id}, event_type={self.event_type}, timestamp={self.timestamp})>"


# =============================================================================
# Database Initialization
# =============================================================================

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from config import settings


# Create engine with error handling
try:
    engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_recycle=3600
    )
except Exception as e:
    logger.warning(f"Database engine creation failed: {e}")
    engine = None

SessionLocal = None
if engine:
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Initialize database tables."""
    if engine:
        try:
            Base.metadata.create_all(bind=engine)
            logger.info("Database tables initialized successfully")
        except Exception as e:
            logger.warning(f"Database initialization failed: {e}")
    else:
        logger.warning("Database engine not available, skipping initialization")


def get_db():
    """Get database session dependency."""
    if SessionLocal is None:
        raise Exception("Database not configured")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
