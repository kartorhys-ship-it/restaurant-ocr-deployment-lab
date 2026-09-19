from backend.app.compat import FastAPI
from backend.app.api.health import router as health_router
from backend.app.api.receipts import router as receipts_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="Restaurant Receipt & OCR Expense Platform API",
        version="1.0.0",
        description="Multi-service platform for restaurant expense extraction and review."
    )

    # CORS configuration for frontend
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount API routers
    app.include_router(health_router)
    app.include_router(receipts_router)

    return app


app = create_app()
