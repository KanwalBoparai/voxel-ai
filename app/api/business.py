"""
Business configuration API — lets the dashboard's "AI Settings" / "Business
Information" pages read and edit config/business.json without touching code.
"""
from fastapi import APIRouter

from app.core.business_config import (
    BusinessConfig,
    business_config,
    save_business_config,
    reload_business_config,
)

router = APIRouter(prefix="/api/business-config", tags=["business-config"])


@router.get("")
async def get_business_config() -> BusinessConfig:
    return business_config


@router.put("")
async def update_business_config(config: BusinessConfig) -> BusinessConfig:
    save_business_config(config)
    return reload_business_config()
