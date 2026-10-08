"""Feature catalogue: what a plan *can* switch on. Which plans include which features is data (plan_features),
managed by administrators; this file only names the features the code knows how to gate.
"""
FEATURES: dict[str, str] = {
    "walk_in_orders": "Counter and walk-in orders",
    "customer_crm": "Customer profiles, segments and notes",
    "advanced_reports": "Weekly, monthly, sales, orders, customers, Marketplace and payments reports",
    "data_export": "CSV exports",
    "team_roles": "Manager, cashier and driver roles",
    "performance_insights": "Business performance, trends and insights on the dashboard",
    "marketplace_eligible": "Can be listed on Launder Marketplace",
}

# Report kinds that need advanced_reports; the end-of-day report is always available.
ADVANCED_REPORTS = {"weekly", "monthly", "sales", "orders", "customers", "marketplace", "payments"}
