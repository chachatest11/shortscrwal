from .overview import router as overview_router
from .channels import router as channels_router
from .groups import router as groups_router
from .videos import router as videos_router
from .refresh import router as refresh_router
from .keys import router as keys_router
from .settings import router as settings_router
from .export import router as export_router

ALL_ROUTERS = [
    overview_router, channels_router, groups_router, videos_router,
    refresh_router, keys_router, settings_router, export_router,
]
