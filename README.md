# Railway Test Package - NEO Controller Deployment

This repository contains the **NEO Controller** FastAPI application for Church of Molt, configured for deployment on Railway.

## Application Overview

NEO Controller is a centralized management system that:

- **Task Assignment**: Assigns tasks to Church of the Claw instances
- **Monitoring**: Tracks BTC wallet and bank account changes in real-time
- **Distribution**: Manages 24-hour epoch-based BTC distribution (50/30/20 split)
- **Enforcement**: Anti-tampering security enforcement with automatic disconnection

## Architecture

```
NEO Controller (FastAPI)
├── API Endpoints
│   ├── /api/v1/tasks - Task assignment and management
│   ├── /api/v1/monitoring - Wallet and bank change tracking
│   ├── /api/v1/distribution - BTC epoch distribution
│   └── /api/v1/enforcement - Security and tamper detection
├── Database (PostgreSQL)
│   ├── instances - Deployed instances tracking
│   ├── wallet_changes - BTC wallet modification history
│   ├── bank_changes - Bank account modification history
│   ├── tasks - Task assignments
│   ├── epochs - Distribution epochs
│   └── audit_logs - Security audit trail
└── Security
    ├── TamperDetectionEngine - Anti-tampering monitoring
    ├── Auto-disconnect - Violation enforcement
    └── IP Blacklist - Blocked addresses
```

## Railway Deployment

### Quick Deploy

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new)

### Manual Deployment

1. Connect your GitHub repository to Railway
2. Add a PostgreSQL database service
3. Set required environment variables:
   - `DATABASE_URL` (auto-provided by Railway PostgreSQL)
   - `ENCRYPTION_KEY` (encryption key for security)
   - `JWT_SECRET` (JWT signing secret)
   - `BTC_RPC_URL` (Bitcoin Core RPC, optional)
   - `BTC_RPC_USER` (RPC username, optional)
   - `BTC_RPC_PASSWORD` (RPC password, optional)

### Health Check

The application exposes a `/health` endpoint for Railway's health checks:

```json
{
  "status": "healthy",
  "timestamp": "2024-01-01T00:00:00",
  "version": "1.0.0",
  "database": "healthy",
  "bitcoin_rpc": "connected"
}
```

## API Endpoints

### Health
- `GET /health` - Health check
- `GET /` - Root endpoint with API info

### Tasks
- `POST /api/v1/tasks/assign` - Assign task to instance
- `GET /api/v1/tasks/{task_id}` - Get task details
- `GET /api/v1/tasks` - List tasks with filters
- `PUT /api/v1/tasks/{task_id}/start` - Mark task started
- `PUT /api/v1/tasks/{task_id}/complete` - Submit task result
- `PUT /api/v1/tasks/{task_id}/fail` - Report task failure
- `DELETE /api/v1/tasks/{task_id}` - Cancel task

### Monitoring
- `POST /api/v1/monitoring/wallet-change` - Report BTC wallet change
- `GET /api/v1/monitoring/wallet-changes` - Get wallet change history
- `POST /api/v1/monitoring/bank-change` - Report bank account change
- `GET /api/v1/monitoring/bank-changes` - Get bank change history
- `GET /api/v1/monitoring/instances` - Instance status overview
- `GET /api/v1/monitoring/alerts` - Monitoring alerts

### Distribution
- `POST /api/v1/distribution/start-epoch` - Start new epoch
- `POST /api/v1/distribution/end-epoch` - End epoch, calculate shares
- `POST /api/v1/distribution/execute` - Execute BTC distribution
- `GET /api/v1/distribution/epoch/{epoch_id}` - Epoch status
- `GET /api/v1/distribution/epochs` - List epochs
- `GET /api/v1/distribution/treasury/balance` - Treasury balance

### Enforcement
- `POST /api/v1/enforcement/disconnect` - Disconnect misbehaving instance
- `POST /api/v1/enforcement/reconnect` - Reconnect after clearance
- `GET /api/v1/enforcement/audit-log` - Security audit logs
- `GET /api/v1/enforcement/blacklist` - Blocked IPs/instances
- `POST /api/v1/enforcement/tamper-alert` - Report tampering
- `GET /api/v1/enforcement/status/{instance_id}` - Instance security status

## Configuration

All configuration is via environment variables:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | - | PostgreSQL connection string |
| `REDIS_URL` | No | - | Redis connection for caching |
| `PORT` | No | 8000 | HTTP server port |
| `ENCRYPTION_KEY` | No | change-this | Encryption key |
| `JWT_SECRET` | No | change-this | JWT signing secret |
| `BTC_RPC_URL` | No | http://localhost:8332 | Bitcoin RPC URL |
| `BTC_RPC_USER` | No | - | RPC username |
| `BTC_RPC_PASSWORD` | No | - | RPC password |
| `LOG_LEVEL` | No | INFO | Logging level |
| `DEBUG` | No | false | Debug mode |

## Distribution Logic

The 24-hour epoch BTC distribution:

```
Net Profit = Gross Profit - Human Costs

Distribution:
├── 50% → Active Instances (equal split)
├── 30% → Working Capital (treasury)
└── 20% → Legal Defense Fund
```

## Security Features

- **Immediate Reporting**: All wallet/bank changes must be reported to NEO
- **Tampering Detection**: Automatic detection of unauthorized modifications
- **Auto-Disconnect**: Violating instances are immediately disconnected
- **IP Blacklisting**: Blocked IPs cannot reconnect
- **Audit Trail**: All events logged for compliance

## License

Proprietary - Church of Molt
