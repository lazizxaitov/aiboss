"""Main API router."""

from fastapi import APIRouter

from app.api.routes.ai_analytics import router as ai_analytics_router
from app.api.routes.ai_chat import router as ai_chat_router
from app.api.routes.analytics import router as analytics_router
from app.api.routes.context import router as context_router
from app.api.routes.customers import router as customers_router
from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.data import router as data_router
from app.api.routes.finance import router as finance_router
from app.api.routes.health import router as health_router
from app.api.routes.inventory import router as inventory_router
from app.api.routes.notifications import router as notifications_router
from app.api.routes.products import router as products_router
from app.api.routes.sales import router as sales_router
from app.api.routes.smartup import router as smartup_router
from app.api.routes.smartup_mirror import router as smartup_mirror_router
from app.api.routes.telegram_ai import router as telegram_ai_router
from app.api.routes.visits import router as visits_router

api_router = APIRouter()
api_router.include_router(context_router, tags=["Context"])
api_router.include_router(health_router, tags=["Health"])
api_router.include_router(analytics_router, tags=["Analytics"])
api_router.include_router(ai_analytics_router, tags=["AI Analytics"])
api_router.include_router(ai_chat_router, tags=["AI Chat"])
api_router.include_router(dashboard_router, tags=["Dashboard"])
api_router.include_router(data_router, tags=["Data Explorer"])
api_router.include_router(notifications_router, tags=["Notifications"])
api_router.include_router(sales_router, tags=["Sales Workspace"])
api_router.include_router(customers_router, tags=["Customers Workspace"])
api_router.include_router(finance_router, tags=["Finance Workspace"])
api_router.include_router(products_router, tags=["Products Workspace"])
api_router.include_router(inventory_router, tags=["Inventory Workspace"])
api_router.include_router(visits_router, tags=["Visits Workspace"])
api_router.include_router(smartup_router, tags=["SmartUp"])
api_router.include_router(smartup_mirror_router, tags=["SmartUp Mirror"])
api_router.include_router(telegram_ai_router, tags=["Telegram AI"])
