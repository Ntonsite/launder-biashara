# Launder customer app — architecture

Location: `C:\Users\ntonsite.mwamlima\projects\mobile\launder` (its own git repository, next to the other mobile apps).
Flutter 3.41 · Dart 3.11 · Android + iOS. Customer app only — laundries keep using the web Business app.

## Stack

| Concern | Choice | Why |
|---|---|---|
| State | `flutter_riverpod` 2.6 (Notifier / FutureProvider) | Same convention as the other apps in `projects/mobile` |
| Navigation | `go_router` 17, `StatefulShellRoute` for the 4 tabs | Deep links map 1:1 to web URLs |
| HTTP | `dio` with one `AuthInterceptor` | Token refresh, typed errors |
| Sensitive storage | `flutter_secure_storage` (Keystore / Keychain) | Access + refresh tokens only |
| Preferences | `shared_preferences` | Language, onboarding flag, place, cart, small caches |
| Localisation | `flutter_localizations` + ARB (`lib/l10n/app_en.arb`, `app_sw.arb`) | Generated, type-safe strings |
| Maps | `flutter_map` + OpenStreetMap tiles | No API key needed in Phase 1 |
| Location | `geolocator` behind a `LocationSource` interface | Testable; coarse accuracy |
| Images | `cached_network_image` with `memCacheWidth` | Decode at slot size; disk cache |

JSON models are hand-written (`lib/core/models/`) — small, explicit, no code generation step.

## Layout

```
lib/
  main.dart                 bootstrap: prefs + keystore read, ProviderScope overrides, native splash
  app/                      app.dart (MaterialApp.router, theme, l10n), router.dart, shell.dart (bottom nav)
  core/
    api/                    api_client.dart (Dio, AuthInterceptor, redacted debug log), api_exception.dart
    auth/session.dart       Session/UserProfile + SessionController (secure storage)
    config/app_config.dart  API_BASE_URL from --dart-define
    format/format.dart      money (TZS, integer), dates, status/category labels via l10n
    localization/           LocaleController (persisted EN/SW)
    location/               PlaceController (GPS or chosen neighbourhood), LocationSource
    models/                 laundry.dart, order.dart
    storage/storage.dart    SecureStore, Prefs (+ offline cache)
    theme/app_theme.dart    colours, spacing, radii, type scale, ThemeData
    widgets/                common.dart (buttons, skeletons, states, stepper…), laundry_cards.dart
  features/
    onboarding/ home/ discovery/ laundry/ cart/ auth/ checkout/ orders/ tracking/ profile/ notifications/
    data_providers.dart     shared FutureProviders (discovery, storefront, orders, favourites)
  l10n/                     ARB sources + generated AppLocalizations
```

Each feature folder holds its screens and, where it owns an API area, its repository
(`auth_repository.dart`, `marketplace_repository.dart`, `orders_repository.dart`). There is no extra
"use case" or "domain" layer — repositories return models, providers expose them, screens render them.

## API integration

The app uses the same `/api/v1` as the web. Endpoints used:

| Area | Endpoints |
|---|---|
| Discovery | `GET /marketplace/laundries` (lat, lng, radius_km, q, service, open_now, pickup, min_rating, sort), `GET /marketplace/areas` |
| Storefront | `GET /marketplace/laundries/{slug}`, `GET …/{slug}/pickup-slots`, `POST …/{slug}/quote` |
| Auth | `POST /auth/otp/request`, `POST /auth/otp/verify`, `POST /auth/refresh`, `POST /auth/logout`, `PATCH /auth/me` |
| Orders | `GET/POST /customer/orders` (Idempotency-Key), `GET /customer/orders/{id}`, `…/cancel`, `…/confirm`, `…/review`, `…/reorder`, `…/payments/mobile-money` |
| Account | `/customer/addresses`, `/customer/favourites/{slug}`, `/customer/notifications`, `/customer/notifications/read` |

None of these existed before this phase; see [API_GAPS.md](API_GAPS.md).

### Errors

`ApiException` carries `kind` (network, timeout, server, unauthorized, api), the API's error `code` and
`details`. `ApiException.describe(l10n)` maps known codes to localised human sentences. Screens only ever
show those sentences — never `toString()` of an exception.

### Tokens

* Access (30 min) and refresh (30 days, rotating) tokens are stored **only** in secure storage.
* `AuthInterceptor` is a `QueuedInterceptor`: on a 401 for an authenticated request it refreshes once,
  replays the request, and queued requests reuse the new token (verified by `test/api/api_client_test.dart`).
* A rejected refresh clears the session and the shell shows "Your session has ended".
* Logout revokes the refresh-token family on the server, then clears local state even if offline.

### Offline / poor networks

* Discovery and storefront responses are cached (last good result per query). When offline the cached
  result is shown with an "offline, showing saved results" banner.
* Lists use 480 px `-sm` cover variants; images decode at their on-screen width.
* Tracking polls at 20 s backing off to 60 s, only while the order is active and the app is in the foreground.

## Configuration

| Define | Default | Notes |
|---|---|---|
| `API_BASE_URL` | Android emulator `http://10.0.2.2:8000`, otherwise `http://127.0.0.1:8000` | Set for devices and production |
| `SANDBOX_PAYMENTS` | `true` (debug builds only) | Shows "Sandbox: approve payment"; never in release |

Physical Android device over USB (no firewall changes needed):

```
adb reverse tcp:8000 tcp:8000
flutter run --dart-define=API_BASE_URL=http://127.0.0.1:8000
```

Over Wi-Fi instead: `--dart-define=API_BASE_URL=http://<PC LAN IP>:8000` and allow TCP 8000 in Windows Firewall.

## Deep links

Routes mirror web URLs: `/laundries/{slug}`, `/orders/{id}` (and the web alias `/account/orders/{id}`).

* Android: `AndroidManifest.xml` declares an auto-verified App Link for `https://launder.co.tz/laundries/…`,
  `/orders/…`, `/account/orders/…` and the `launder://` scheme. Verification requires hosting
  `https://launder.co.tz/.well-known/assetlinks.json` with the release signing certificate's SHA-256.
* iOS: `FlutterDeepLinkingEnabled` and the `launder` URL scheme are set in `Info.plist`. Universal Links need
  an Apple team: add the *Associated Domains* capability `applinks:launder.co.tz` in Xcode and host
  `apple-app-site-association`.
* Deep links skip onboarding so a shared laundry opens directly.

## Notifications

Phase 1 has no FCM/APNs credentials. `PushService` is an interface with one implementation,
`DisabledPushService`, which never requests a token and never claims delivery. The API records in-app
notifications for meaningful status changes (`push_status = NOT_CONFIGURED`); the app shows them in
Profile → Notifications and on the tracking screen. To enable push: implement `PushService` with
`firebase_messaging`, register tokens with `POST /customer/devices`, and route taps with `routeForNotification`.

## Security

* Tokens only in Keystore/Keychain (`first_unlock_this_device`); `android:allowBackup="false"`.
* Release builds: HTTPS only (`network_security_config.xml`); cleartext is allowed only by the debug-only
  config in `src/debug`. iOS allows plain HTTP only to local-network hosts (`NSAllowsLocalNetworking`).
* The OTP screen sets Android `FLAG_SECURE` (MethodChannel `tz.co.launder/secure_screen` in `MainActivity`).
* Debug network logging prints method, path and status only — no headers, bodies, tokens, phones or codes.
  Release builds install no logger.
* The development OTP code is displayed only when `kDebugMode` **and** the API returns it (development API).
* Release builds are minified and resource-shrunk. Signing reads `android/key.properties` (git-ignored); without
  it release builds fall back to the debug key and must not be published.
* No secrets are compiled into the app; `API_BASE_URL` is public configuration.

## Building

```
flutter pub get
flutter gen-l10n                     # also runs automatically on build
flutter analyze
flutter test                         # unit, repository and widget tests
flutter build apk --release --dart-define=API_BASE_URL=https://api.launder.co.tz
flutter build appbundle --release --dart-define=API_BASE_URL=https://api.launder.co.tz
```

iOS (on a Mac with Xcode): `cd ios && pod install`, open `Runner.xcworkspace`, set the team and bundle id
`tz.co.launder.launder`, then `flutter build ipa --dart-define=API_BASE_URL=…`. iOS was not built in this
environment (Windows).

Icons and splash are generated from `assets/brand/` (produced by `backend/launder/brand/generate.py`):
`dart run flutter_launcher_icons` and `dart run flutter_native_splash:create`.
