# API gaps found and closed

Before this phase the API exposed only staff login, business registration/onboarding/services/orders,
a read-only admin, an unauthenticated `POST /orders` that trusted a client-supplied total, and a
marketplace list without location. Nothing a customer app needs existed. Every endpoint below was built in
`apps/api`, covered by tests in `apps/api/tests`, and is consumed by the web and/or the mobile app.

| Need | Gap | Endpoint(s) now | Tests |
|---|---|---|---|
| Customer identity | No customer auth at all | `POST /auth/otp/request`, `POST /auth/otp/verify`, `PATCH /auth/me` | `test_auth.py` (formats, cooldown, attempts, lockout) |
| Session lifecycle | 8-hour tokens, no refresh/logout | `POST /auth/refresh` (rotation + reuse detection), `POST /auth/logout` | `test_auth.py` |
| Nearby discovery | No coordinates, distance or filters | `GET /marketplace/laundries?lat&lng&radius_km&q&service&open_now&pickup&min_rating&sort` (PostGIS) | `test_marketplace.py` |
| Manual location | — | `GET /marketplace/areas` | `test_marketplace.py` |
| Storefront | Web used hardcoded data | `GET /marketplace/laundries/{slug}` (services by category, hours, today, reviews, distance) | `test_marketplace.py` |
| Pickup scheduling | — | `GET /marketplace/laundries/{slug}/pickup-slots` | `test_marketplace.py`, `test_orders.py` |
| Server pricing | Client sent totals | `POST /marketplace/laundries/{slug}/quote` | `test_marketplace.py` |
| Place order | Unauthenticated, unpriced, no items | `POST /customer/orders` (Idempotency-Key, PRICE_CHANGED, pickup validation) | `test_orders.py` |
| Track / history | — | `GET /customer/orders?group=`, `GET /customer/orders/{id}` (events, stages, payment, flags) | `test_orders.py` |
| Cancel / confirm | — | `POST /customer/orders/{id}/cancel`, `…/confirm` | `test_orders.py` |
| Review | Reviews unlinked; rating static | `POST /customer/orders/{id}/review`; rating recomputed | `test_orders.py`, `test_business_admin.py` |
| Reorder | — | `GET /customer/orders/{id}/reorder` (current prices + change list) | `test_orders.py` |
| Mobile money | Only a status column | `POST /customer/orders/{id}/payments/mobile-money`, signed `POST /payments/webhooks/sandbox`, dev-only simulate | `test_orders.py` |
| Addresses | — | `GET/POST /customer/addresses`, `DELETE /customer/addresses/{id}` | via journeys |
| Favourites | — | `GET /customer/favourites`, `PUT/DELETE /customer/favourites/{slug}` | via journeys |
| Notifications | — | `GET /customer/notifications`, `POST /customer/notifications/read`, `POST /customer/devices` | `test_orders.py` |
| Order processing (business) | No status endpoint | `GET /business/orders/{id}`, `POST /business/orders/{id}/status`, `POST …/payments/cash` | `test_orders.py` |
| Marketplace application | No apply step | `GET /business/marketplace` (checklist), `POST /business/marketplace/application` | `test_business_admin.py` |
| Business setup | Onboarding stored an opaque blob | `PUT /business/profile`, `PUT /business/hours`, `GET/POST/DELETE /business/staff`, `GET /business/reviews` | `test_business_admin.py` |
| Admin control | Read-only, no preconditions | application detail, approve/reject/suspend/reinstate rules, payments + refund, review hide/publish, paginated lists, audit actors | `test_business_admin.py` |

## Deliberately not built in Phase 1

* A real SMS gateway and mobile-money aggregator: provider interfaces exist (`OtpService._deliver`,
  `payments.provider()`); only development implementations ship. See IMPLEMENTATION_STATUS.md.
* Push delivery (no FCM/APNs credentials): device tokens are stored; nothing claims delivery.
* Server-sent events/WebSockets for tracking: polling with back-off is sufficient at Phase 1 volumes.
