from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from src.api.limiter import limiter
from src.api.routes import alerts, backtest, clv, health, stream
from src.config.settings import Settings

_settings = Settings()
_origins = list({_settings.frontend_origin, "http://localhost:3000"})

app = FastAPI(
    title="NBA +EV Alert API",
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)
app.add_middleware(SlowAPIMiddleware)

app.include_router(alerts.router, prefix="/api")
app.include_router(clv.router, prefix="/api")
app.include_router(backtest.router, prefix="/api")
app.include_router(health.router, prefix="/api")
app.include_router(stream.router, prefix="/api")
