export type Metric = {
  value: number;
  previous: number | null;
  change_pct: number | null;
};

export type PeriodInfo = {
  kind: string;
  start_date: string;
  end_date: string;
  in_progress: boolean;
  compare_to:
    | "previous_day_same_weekday"
    | "previous_week"
    | "previous_month"
    | "previous_period";
};

export type Attention = {
  key: string;
  count: number;
  severity: "critical" | "warning" | "info";
  path: string;
  query: Record<string, string>;
  amount?: number;
  soon?: number;
  hours?: number;
  minutes?: number;
};

export type DayPoint = {
  date: string;
  weekday: number;
  orders: number;
  sales: number;
  collected: number;
};

export type Insight = { key: string } & Record<string, string | number>;

export type MarketplaceStats = {
  status: string;
  commission_rate: number;
  orders: number;
  sales: number;
  customers: number;
  average_order: number;
  commission_accrued: number;
  commission_pending: number;
  commission_trial: number;
  commission_standard: number;
  commission_waived: number;
  trial_orders: number;
  net: number;
  share_orders: number | null;
  share_sales: number | null;
  rating: number;
  review_count: number;
};

export type CustomerStats = {
  unique: number;
  new: number;
  returning: number;
  repeat_rate: number | null;
  multi_order: number;
  new_from_marketplace: number;
};

export type Dashboard = {
  business: { name: string; area: string };
  local_date: string;
  role: string;
  capabilities: string[];
  has_orders: boolean;
  first_run: { key: string; done: boolean; path: string }[] | null;
  attention: Attention[];
  pipeline: Record<string, number>;
  today: {
    processing: number;
    ready: number;
    due_today: number;
    overdue: number;
    pickups: number;
    deliveries: number;
    orders: Metric;
    sales?: Metric;
    collected?: number;
    ready_unpaid?: number;
    outstanding?: { count: number; amount: number };
    compare_to?: PeriodInfo["compare_to"];
  };
  performance?: {
    period: PeriodInfo;
    sales: Metric;
    orders: Metric;
    average_order: Metric;
    collected: Metric;
    trend: DayPoint[];
  };
  marketplace?:
    (MarketplaceStats & { sales_metric: Metric; orders_metric: Metric }) | null;
  customers?: CustomerStats & {
    new_metric: Metric;
    repeat_rate_metric: Metric;
  };
  insights?: Insight[];
  performance_locked?: boolean;
};

export type ServiceStat = {
  name: string;
  pricing_model: string;
  orders: number;
  quantity: number;
  revenue: number;
  share_revenue: number | null;
};

export type Report = {
  kind: string;
  sections: string[];
  period: PeriodInfo;
  generated_at: string;
  business: { name: string; branch: string };
  summary: Record<string, Metric> & {
    on_time_rate: number | null;
    outstanding_now: { count: number; amount: number };
    comparable: boolean;
  };
  money: {
    sales: number;
    discounts: number;
    collected: number;
    refunded: number;
    net_collected: number;
    unpaid_from_period: { count: number; amount: number };
    outstanding_now: { count: number; amount: number };
  };
  payments: Record<string, { count: number; amount: number }>;
  sources: {
    source: string;
    orders: number;
    sales: number;
    share_orders: number | null;
    share_sales: number | null;
  }[];
  operations: {
    received: number;
    washing: number;
    ironing: number;
    ready: number;
    delivered: number;
    completed: number;
    cancelled: number;
    ready_on_time: number;
    ready_late: number;
    on_time_rate: number | null;
    delayed: number;
    overdue_now: number;
    average_turnaround_hours: number | null;
    cancellation_rate: number | null;
  };
  customers: CustomerStats;
  marketplace: MarketplaceStats;
  services: {
    total_revenue: number;
    by_revenue: ServiceStat[];
    by_orders: ServiceStat[];
  };
  day_book?: {
    opening: number;
    new: number;
    completed: number;
    cancelled: number;
    carried_forward: number;
  };
  daily?: DayPoint[];
  weekdays?: { weeks: number; orders: number[]; average: number[] };
  top_customers?: {
    id: string;
    name: string;
    phone: string;
    orders: number;
    spend: number;
  }[];
  insights?: Insight[];
  day_close?: DayCloseView | null;
};

export type DayCloseView = {
  date: string;
  expected_cash: number;
  expected_mobile_money: number;
  expected_total: number;
  outstanding_now: { count: number; amount: number };
  carried_forward: number;
  can_close: boolean;
  closed: null | {
    closed_at: string;
    closed_by: string | null;
    expected_cash: number;
    counted_cash: number | null;
    variance: number | null;
    note: string;
  };
};
