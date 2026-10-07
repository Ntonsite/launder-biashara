export type LaundryCardData = {
  id: string;
  slug: string;
  name: string;
  area: string;
  rating: number;
  review_count: number;
  distance_km: number | null;
  open_now: boolean;
  pickup_enabled: boolean;
  pickup_available: boolean;
  starting_price: { amount: number; unit: "PER_ITEM" | "PER_KG" } | null;
  cover_image_url: string | null;
  cover_thumb_url: string | null;
  latitude: number | null;
  longitude: number | null;
  is_favourite: boolean;
};

export type ServiceData = {
  id: string;
  name: string;
  description: string;
  category: string;
  pricing_model: "PER_ITEM" | "PER_KG";
  price: number;
  turnaround_hours: number;
};

export type Storefront = LaundryCardData & {
  description: string;
  address: string;
  phone: string;
  pickup_fee: number;
  fastest_turnaround_hours: number | null;
  hours: {
    weekday: number;
    opens_at: string;
    closes_at: string;
    closed: boolean;
  }[];
  today: { opens_at: string; closes_at: string; closed: boolean } | null;
  service_groups: { category: string; services: ServiceData[] }[];
  reviews: {
    id: string;
    rating: number;
    comment: string;
    author: string;
    created_at: string;
  }[];
};

export type Quote = {
  items: {
    service_id: string;
    name: string;
    pricing_model: string;
    unit_price: number;
    quantity: number;
    line_total: number;
  }[];
  unavailable_service_ids: string[];
  subtotal: number;
  delivery_fee: number;
  total: number;
};

export type OrderSummary = {
  id: string;
  order_number: string;
  status: string;
  fulfillment: "PICKUP" | "DROP_OFF";
  payment_status: string;
  payment_method: string;
  total: number;
  items_preview: string[];
  created_at: string;
  pickup_window_start: string | null;
  laundry: {
    id: string;
    slug: string;
    name: string;
    area: string;
    cover_image_url: string | null;
  };
};

export type OrderDetail = OrderSummary & {
  subtotal: number;
  delivery_fee: number;
  pickup_address: string | null;
  pickup_window_end: string | null;
  cancel_reason: string | null;
  items: {
    service_id: string | null;
    name: string;
    pricing_model: string;
    unit_price: number;
    quantity: number;
    line_total: number;
  }[];
  events: { status: string; note: string | null; at: string }[];
  stages: string[];
  payment: {
    id: string;
    method: string;
    status: string;
    reference: string | null;
    failure_reason: string | null;
  } | null;
  review: { rating: number; comment: string } | null;
  can_cancel: boolean;
  can_review: boolean;
  can_confirm: boolean;
  can_pay: boolean;
};

export type Page<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
};
