# server/main.py
from __future__ import annotations

import os
import sys

# Get the absolute path to the server directory
server_dir = os.path.dirname(os.path.abspath(__file__))

# Add server directory to path BEFORE any imports
# This ensures it's available in uvicorn subprocesses
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from utils.config import settings
from db.database import Base, engine
from routers import workflow, history, files
from routers import auth, recruitments, applications


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version="0.1.0",
    )

    # CORS 설정
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # DB 테이블 생성
    Base.metadata.create_all(bind=engine)

    # 루트 경로 핸들러 추가 (404 방지)
    @app.get("/")
    async def root():
        return JSONResponse(
            content={
                "message": "AI Interview Agent API",
                "version": "0.1.0",
                "status": "running",
                "docs": "/docs",
            }
        )

    # 헬스체크 엔드포인트
    @app.get("/health")
    async def health_check():
        return JSONResponse(content={"status": "healthy"})

    # 라우터 등록
    app.include_router(workflow.router)
    app.include_router(history.router)
    app.include_router(files.router)  # 파일 관리 라우터 추가
    app.include_router(auth.router)
    app.include_router(recruitments.router)
    app.include_router(applications.router)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    # Use absolute path to avoid subprocess issues
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=9898,
        reload=False,  # Disable auto-reload to avoid subprocess issues
    )
