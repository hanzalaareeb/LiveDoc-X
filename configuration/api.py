from ninja import NinjaAPI
from ninja_jwt.authentication import JWTAuth
from ninja_jwt.routers.blacklist import blacklist_router
from ninja_jwt.routers.obtain import obtain_pair_router
from ninja_jwt.routers.verify import verify_router

from core.api import router as core_router
from docmanage.api import router as docmanage_router
from user.api import router as user_router

api = NinjaAPI(
    title="LiveDocX API",
    version="1.0.0",
    auth=JWTAuth(),
)

api.add_router("/token/", obtain_pair_router)
api.add_router("/token/", verify_router)
api.add_router("/token/", blacklist_router)
api.add_router("/core/", core_router)
api.add_router("/user/", user_router)
api.add_router("/document/", docmanage_router)
