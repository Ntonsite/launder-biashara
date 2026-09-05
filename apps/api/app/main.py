from fastapi import Depends,FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session
from .core.config import settings
from .database import get_db
from .routers import admin,auth,business,marketplace,orders
from .seed import seed_database
seed_database()
app=FastAPI(title="Launder API",version="1.0.0",docs_url="/api/docs",openapi_url="/api/openapi.json")
app.add_middleware(CORSMiddleware,allow_origins=list(settings.cors_origins),allow_methods=["*"],allow_headers=["*"],allow_credentials=True)
@app.get("/health",tags=["System"])
def health(db:Session=Depends(get_db)):db.execute(select(1));return {"status":"healthy","database":"connected"}
for router in (auth.router,marketplace.router,orders.router,business.router,admin.router):app.include_router(router,prefix="/api/v1")
