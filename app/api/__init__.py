from .categories import router as categories_router
from .channels import router as channels_router
from .search import router as search_router
from .downloads import router as downloads_router
from .settings import router as settings_router
from .api_keys import router as api_keys_router
from .dashboard import router as dashboard_router

__all__ = [
    "categories_router",
    "channels_router",
    "search_router",
    "downloads_router",
    "settings_router",
    "api_keys_router",
    "dashboard_router"
]
