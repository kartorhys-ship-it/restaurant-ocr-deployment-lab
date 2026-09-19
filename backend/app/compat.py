"""Compatibility shim providing standard library fallbacks when FastAPI/Pydantic are not installed."""

from typing import Any, Dict, List, Optional, Callable


# --- Pydantic compatibility ---
try:
    from pydantic import BaseModel as _PydanticBaseModel, Field as _PydanticField
    BaseModel = _PydanticBaseModel
    Field = _PydanticField
except ImportError:
    class BaseModel:
        def __init__(self, **kwargs):
            # Apply annotations / class-level defaults
            for k, v in self.__class__.__dict__.items():
                if not k.startswith("_") and not callable(v):
                    setattr(self, k, v)
            for k, v in kwargs.items():
                setattr(self, k, v)

        def dict(self) -> Dict[str, Any]:
            return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

    def Field(default=None, default_factory=None, **kwargs):
        if default_factory is not None:
            return default_factory()
        return default


# --- FastAPI / Starlette compatibility ---
try:
    from fastapi import FastAPI, APIRouter, Response, UploadFile, File, HTTPException, status
    from fastapi.middleware.cors import CORSMiddleware
except ImportError:
    class CORSMiddleware:
        def __init__(self, app=None, **kwargs):
            self.app = app
            self.kwargs = kwargs

    class Response:
        def __init__(self, status_code: int = 200):
            self.status_code = status_code

    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str = ""):
            self.status_code = status_code
            self.detail = detail
            super().__init__(f"{status_code}: {detail}")

    class status:
        HTTP_200_OK = 200
        HTTP_202_ACCEPTED = 202
        HTTP_404_NOT_FOUND = 404
        HTTP_500_INTERNAL_SERVER_ERROR = 500

    def File(*args, **kwargs):
        return None

    class UploadFile:
        def __init__(self, filename: str = "upload.jpg", file_bytes: bytes = b""):
            self.filename = filename
            self._bytes = file_bytes

        async def read(self) -> bytes:
            return self._bytes

    class APIRouter:
        def __init__(self, prefix: str = "", tags: Optional[List[str]] = None):
            self.prefix = prefix
            self.tags = tags or []
            self.routes = []

        def get(self, path: str, **kwargs):
            def decorator(func):
                self.routes.append(("GET", self.prefix + path, func))
                return func
            return decorator

        def post(self, path: str, **kwargs):
            def decorator(func):
                self.routes.append(("POST", self.prefix + path, func))
                return func
            return decorator

    class FastAPI:
        def __init__(self, title: str = "", version: str = "", description: str = ""):
            self.title = title
            self.version = version
            self.description = description
            self.routers = []

        def add_middleware(self, middleware_class, **kwargs):
            pass

        def include_router(self, router: APIRouter):
            self.routers.append(router)
