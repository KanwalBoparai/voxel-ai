"""
Business configuration API — lets the dashboard's "AI Settings" / "Business
Information" pages edit the agent's business details without touching code.

Reads come from the in-memory config (config/business.json as the committed
baseline, with any saved edits overlaid); writes go to the database, because
the deployment directory is read-only on serverless hosts.
"""
from fastapi import APIRouter

from app.core.business_config import (
    BusinessConfig,
    business_config,
    save_business_config_to_db,
)

router = APIRouter(prefix="/api/business-config", tags=["business-config"])


@router.get("")
async def get_business_config() -> BusinessConfig:
    return business_config


@router.put("")
async def update_business_config(config: BusinessConfig) -> BusinessConfig:
    return await save_business_config_to_db(config)
