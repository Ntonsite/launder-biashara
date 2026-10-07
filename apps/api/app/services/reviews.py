from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.errors import AppError
from ..models import Business, Order, Review, User
from .audit import audit


def recompute_rating(db: Session, business_id: str) -> None:
    avg, count = db.execute(select(func.avg(Review.rating), func.count(Review.id))
                            .where(Review.business_id == business_id, Review.status == "PUBLISHED")).one()
    business = db.get(Business, business_id)
    business.rating = Decimal(str(avg or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    business.review_count = count


class ReviewService:
    def __init__(self, db: Session):
        self.db = db

    def create(self, order: Order, user: User, rating: int, comment: str) -> Review:
        if order.source != "MARKETPLACE":
            raise AppError(409, "NOT_REVIEWABLE", "Only marketplace orders can be reviewed")
        if order.status not in ("DELIVERED", "COMPLETED"):
            raise AppError(409, "NOT_REVIEWABLE", "You can review once your laundry has been delivered")
        if self.db.scalar(select(Review.id).where(Review.order_id == order.id)):
            raise AppError(409, "ALREADY_REVIEWED", "You have already reviewed this order")
        review = Review(order_id=order.id, business_id=order.business_id, user_id=user.id, author_name=user.full_name,
                        rating=rating, comment=comment.strip())
        self.db.add(review)
        try:
            self.db.flush()
        except IntegrityError:
            self.db.rollback()
            raise AppError(409, "ALREADY_REVIEWED", "You have already reviewed this order") from None
        recompute_rating(self.db, order.business_id)
        audit(self.db, user.id, "REVIEW_CREATED", "review", review.id, rating=rating)
        self.db.commit()
        return review

    def moderate(self, review: Review, status: str, actor: User) -> Review:
        review.status = status
        self.db.flush()
        recompute_rating(self.db, review.business_id)
        audit(self.db, actor.id, f"REVIEW_{status}", "review", review.id)
        self.db.commit()
        return review
