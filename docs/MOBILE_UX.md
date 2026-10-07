# Launder customer app — UX and design system

## The one question

Every screen answers *"What laundry can I use near me, and what happens next?"* The first screen after
onboarding shows a greeting, where you are, one search field, four quick actions, and real laundries with
photographs. Account creation is never required to look around.

## Visual identity

| Token | Value | Used for |
|---|---|---|
| Primary | `#0F4C81` | Primary buttons, selected tab, the active-order card, current timeline step |
| Secondary | `#3B82F6` | "You are here" on the map |
| Fresh teal | `#14B8A6` (`#0F766E` for text) | Completed timeline steps, pickup badges, small accents |
| Background | `#F8FAFC` | Screens |
| Text | `#1E293B` | Body and headings |
| White | `#FFFFFF` | Storefront, onboarding copy area, sheets |

Most of the interface is white space, ink and photography. Colour appears where something can be done or
has changed. There are no gradients, card shadows are reserved for the floating map preview, and sections are
separated by spacing and type rather than boxes.

**Logo.** A water drop (cleanliness) crossed by one fabric wave (movement) with a teal "fresh" dot. It works
alone as the launcher icon and next to the "Launder" wordmark. All variants are generated from one geometry
in `backend/launder/brand/generate.py`: horizontal logo, symbol, light/dark/mono variants, Android adaptive
foreground, monochrome notification icon, favicons.

**Typography.** Manrope (600/700/800) for display and headings, DM Sans (400–700) for everything read.
Both are bundled (SIL OFL) so text never waits on the network, and both cover the Latin set Swahili needs.

| Role | Style |
|---|---|
| Display | Manrope 30 / 800 / −0.8 |
| H1 | Manrope 24 / 800 |
| H2 | Manrope 19 / 700 |
| H3 | Manrope 16 / 700 |
| Body | DM Sans 15 / 400 / 1.45 |
| Secondary | DM Sans 14, slate |
| Caption | DM Sans 12 / 500 |
| Button | DM Sans 15 / 600 |
| Price | Manrope 15 / 700, tabular figures |

Spacing scale 4–8–12–16–20–24–32, 20 px gutters. Radii: 10 (small), 14 (inputs, buttons), 18 (cards,
photos), 24 (sheets). Buttons are 52 px high; every touch target is at least 44 px.

## Photography

Real photographs, never vector illustrations. Onboarding: shirts on hangers (calm, clean), a doorstep
handover (pickup), a man ironing a shirt at home (care, progress). Laundry covers show working laundries,
folded linen and pressing. Sources and licences are in [IMAGE_CREDITS.md](IMAGE_CREDITS.md). Covers are
served by the API in two sizes (960 and 480 px) and decoded at slot size.

## Screens

* **Splash** — native splash with the symbol on `#F8FAFC`, held only while preferences and the keystore are
  read (milliseconds). No animation.
* **Onboarding** — three full-bleed photos, short copy, page dots, *Skip* top-right, *EN | SW* top-left.
* **Home** — wordmark, greeting with first name, location ("Mikocheni, Dar es Salaam ▾"), search,
  Near me / Pickup / Open now / Top rated, the active order (status headline + progress) when there is one,
  *Popular near you* rail, *Your favourites*, *Order again* (one tap rebuilds the cart), *Explore nearby*.
* **Explore** — search with debounce, filter chip with count, location chip, quick toggles, sort menu,
  List ↔ Map. Map pins are the same laundries; tapping one shows a compact preview card. Filters open in a
  bottom sheet: distance slider, minimum rating, service, pickup, open now.
* **Laundry** — large photo header with back and favourite, name, rating and reviews, area and distance,
  open-until/opens-at, pickup fee, fastest turnaround, description; services grouped by category with a
  pill-shaped +/− stepper; reviews; opening hours with today in bold. A dark sticky bar
  "7 items · TZS 16,000 — View cart →" appears once something is added.
* **Cart** — laundry name, lines with stepper and a quiet remove icon, server-quoted subtotal, a note that
  fees appear before ordering. Changes from *Order again* are listed explicitly ("Shirt is now TZS 2,500 (was
  TZS 2,000)").
* **Sign in** — phone with +255 prefix → 6-digit code (auto-submits, resend countdown) → name (first time
  only). Opened only when ordering, tracking, or saving favourites.
* **Checkout** — one decision per step with a thin progress bar: Pickup or drop-off → Address (saved or new,
  optional "pin my location") → Time (real windows from opening hours) → Payment (cash or mobile money) →
  Review with every line, fee and total. The button reads "Place order · TZS 18,000".
* **Order confirmed** — a check that settles in, "Order LN-7KQ3XA", the laundry, the pickup window, *Track
  order* and *Back home*. No confetti.
* **Tracking** — the headline is the current state in plain words ("Your clothes are being washed."),
  then a vertical timeline: teal checks with times for completed steps, an emphasised current step, grey
  upcoming steps; stages the laundry skipped disappear. Payment state is always visible. Actions appear only
  when valid: pay with mobile money, confirm receipt, rate, order again, cancel (before acceptance).
* **Orders** — Active / Completed / Cancelled. Active cards lead with *Track order*; finished ones with
  *Order again*.
* **Profile** — name and phone, Addresses, Favourites, Notifications, Payment preference, Language (EN | SW
  inline), Help, Terms, Privacy, Sign out.

## Motion

Short and purposeful: stepper expands as you add (180 ms), cart bar rises in, favourite heart with haptic
tick, page and step cross-fades (200–220 ms), the success check eases in once, timeline dots grow into the
current state, the active-order progress bar fills. Skeletons pulse gently and stop when the system asks for
reduced motion.

## States

* **Loading** — skeletons shaped like the content (rails, list cards, storefront, order cards, timeline).
* **Empty** — "No laundries found around this area yet.", "Your laundry orders will appear here.", "Save
  laundries you love for faster ordering." — each with one next step.
* **Errors** — every API failure maps to a sentence in the current language: offline, timeout, server,
  session ended, wrong/expired/locked code, invalid phone, price changed, item unavailable, pickup slot
  taken, outside pickup area, laundry unavailable, cannot cancel, payment failed. Location denied shows
  manual areas and, when needed, a link to settings.

## Language

All customer text comes from `app_en.arb` / `app_sw.arb`; tests enforce identical keys and no copied English
in Swahili. Natural Tanzanian usage: "laundry" and "oda" as people say them, "Fuatilia oda", "Nguo zako
ziko tayari.", "Tuchukue / Nitazipeleka mwenyewe". Laundry names, service names written by laundries,
addresses, customer names and reviews are never translated. Layouts are tested at 320 px with 130 % text in
both languages.

## Accessibility

Contrast meets WCAG AA for text (teal text uses `#0F766E`). Text scales with the system up to 135 %. Buttons
and steppers expose labels ("Add Shirt", "Remove one Shirt"), headings are marked, status changes and cart
totals are live regions, radio-style options report checked state, and every icon-only control has a tooltip.
