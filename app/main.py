import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import get_settings

logger = logging.getLogger("setu")
from app.database import Base, SessionLocal, engine
from app.routers import auth, batches, dashboard, maintenance, products, replacements, reports, serials, settings, tally_check, users
from app.services.bootstrap import bootstrap
from app.services.schema import ensure_runtime_schema
from app.services.sync_worker import start_retry_worker, stop_retry_worker


def create_app() -> FastAPI:
    app = FastAPI(title=get_settings().app_name)
    app.mount("/static", StaticFiles(directory="app/static"), name="static")
    app.include_router(auth.router)
    app.include_router(dashboard.router)
    app.include_router(products.router)
    app.include_router(serials.router)
    app.include_router(batches.router)
    app.include_router(reports.router)
    app.include_router(settings.router)
    app.include_router(tally_check.router)
    app.include_router(maintenance.router)
    app.include_router(replacements.router)
    app.include_router(users.router)

    @app.on_event("startup")
    async def startup() -> None:
        if get_settings().using_default_secret:
            logger.warning(
                "APP_SECRET_KEY is using the insecure default value. "
                "Set APP_SECRET_KEY to a long random string before production use."
            )
        Base.metadata.create_all(bind=engine)
        ensure_runtime_schema()
        with SessionLocal() as db:
            bootstrap(db)
        start_retry_worker(app)

    @app.on_event("shutdown")
    async def shutdown() -> None:
        await stop_retry_worker(app)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
