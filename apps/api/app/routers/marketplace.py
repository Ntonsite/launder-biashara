from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import optional_user
from ..models import User
from ..schemas.orders import QuoteRequest
from ..services.marketplace import AREAS, DiscoveryQuery, MarketplaceService, favourite_ids

router = APIRouter(prefix="/marketplace", tags=["Marketplace"])


@router.get("/laundries")
def laundries(lat: float | None = Query(None, ge=-90, le=90), lng: float | None = Query(None, ge=-180, le=180),
              radius_km: float = Query(15, gt=0, le=50), q: str | None = Query(None, max_length=80),
              service: str | None = Query(None, max_length=80), open_now: bool = False, pickup: bool = False,
              min_rating: float | None = Query(None, ge=0, le=5),
              sort: Literal["distance", "rating", "price"] | None = None,
              page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=50),
              db: Session = Depends(get_db), user: User | None = Depends(optional_user)):
    """Public discovery. Only businesses whose marketplace account is ACTIVE are ever returned."""
    query = DiscoveryQuery(lat=lat, lng=lng, radius_km=radius_km, q=q, service=service, open_now=open_now, pickup=pickup,
                           min_rating=min_rating, sort=sort, page=page, page_size=page_size,
                           favourite_ids=favourite_ids(db, user.id if user else None))
    return MarketplaceService(db).discover(query)


@router.get("/laundries/{slug}")
def storefront(slug: str, lat: float | None = Query(None, ge=-90, le=90), lng: float | None = Query(None, ge=-180, le=180),
               db: Session = Depends(get_db), user: User | None = Depends(optional_user)):
    return MarketplaceService(db).storefront(slug, lat, lng, favourite_ids(db, user.id if user else None))


@router.get("/laundries/{slug}/reviews")
def reviews(slug: str, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=50), db: Session = Depends(get_db)):
    service = MarketplaceService(db)
    business, _ = service.visible_business(slug)
    items = service.recent_reviews(business.id, limit=page_size, offset=(page - 1) * page_size)
    return {"items": items, "total": business.review_count, "page": page, "page_size": page_size,
            "rating": float(business.rating)}


@router.get("/laundries/{slug}/pickup-slots")
def pickup_slots(slug: str, days: int = Query(3, ge=1, le=7), db: Session = Depends(get_db)):
    service = MarketplaceService(db)
    business, _ = service.visible_business(slug)
    return {"slots": service.pickup_slots(business, days), "pickup_enabled": business.pickup_enabled}


@router.post("/laundries/{slug}/quote")
def quote(slug: str, payload: QuoteRequest, db: Session = Depends(get_db)):
    """Validates a cart against current prices and availability. Used by cart, checkout and reorder."""
    service = MarketplaceService(db)
    business, _ = service.visible_business(slug)
    return service.quote(business, payload.items, payload.fulfillment).out()


@router.get("/areas")
def areas():
    return {"items": [{"name": name, "latitude": lat, "longitude": lng} for name, lat, lng in AREAS]}
