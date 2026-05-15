"""
Seed Data Command
=================
Generates a realistic 14-month sales dataset for development and demo purposes.

Usage
-----
    python manage.py seed_data              # full seed
    python manage.py seed_data --clear      # wipe existing data first
    python manage.py seed_data --months 6   # shorter window

What gets created
-----------------
  5  categories
  35 products  (7 per category, with realistic margins and stock levels)
  4  branches  (with different revenue profiles)
  80 customers (mix of Retail / Wholesale / VIP / Corporate, across 4 regions)
  ~2 500 sales (14 months, seasonality-aware, weekday-weighted distribution)

Design
------
  - Revenue has a gentle upward trend + seasonal peaks in Nov/Dec and Mar
  - Each branch has a distinct "share" of total sales volume
  - VIP and Corporate customers buy more frequently and in larger quantities
  - ~20% of sales are walk-in (no customer linked)
  - Product stock is NOT manipulated here — signals handle it automatically
    as each Sale is saved. Stocks are set high enough to cover all seed sales.
"""
import random
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.branches.models import Branch
from apps.categories.models import Category
from apps.customers.models import Customer
from apps.products.models import Product
from apps.sales.models import Sale

# ---------------------------------------------------------------------------
# Seed constants
# ---------------------------------------------------------------------------

CATEGORIES = [
    "Electronics",
    "Clothing & Apparel",
    "Food & Beverages",
    "Home & Garden",
    "Sports & Outdoors",
]

PRODUCTS_BY_CATEGORY = {
    "Electronics": [
        ("Wireless Headphones",  "EL-001", 45.00,  89.99,  120, 20),
        ("Smart Watch",          "EL-002", 95.00, 199.99,   80, 15),
        ("Bluetooth Speaker",    "EL-003", 28.00,  59.99,  200, 30),
        ("USB-C Hub",            "EL-004", 12.00,  29.99,  350, 40),
        ("Laptop Stand",         "EL-005",  8.00,  24.99,  400, 50),
        ("Webcam HD",            "EL-006", 25.00,  54.99,  150, 25),
        ("Mechanical Keyboard",  "EL-007", 55.00, 109.99,   90, 15),
    ],
    "Clothing & Apparel": [
        ("Men's Running Shoes",  "CL-001", 30.00,  74.99,  200, 30),
        ("Women's Yoga Pants",   "CL-002", 14.00,  39.99,  300, 40),
        ("Casual T-Shirt",       "CL-003",  5.00,  19.99,  500, 60),
        ("Winter Jacket",        "CL-004", 55.00, 129.99,   80, 15),
        ("Sports Socks (Pack)",  "CL-005",  3.50,  12.99,  800, 80),
        ("Baseball Cap",         "CL-006",  6.00,  18.99,  350, 40),
        ("Gym Gloves",           "CL-007",  7.00,  21.99,  250, 30),
    ],
    "Food & Beverages": [
        ("Protein Powder 1kg",   "FB-001", 18.00,  39.99,  300, 50),
        ("Energy Drink (24pk)",  "FB-002", 14.00,  29.99,  500, 60),
        ("Mixed Nuts 500g",      "FB-003",  7.50,  16.99,  600, 70),
        ("Olive Oil 1L",         "FB-004",  5.00,  12.99,  400, 50),
        ("Green Tea (100 bags)", "FB-005",  3.50,   8.99,  700, 80),
        ("Honey 500g",           "FB-006",  4.50,  10.99,  500, 60),
        ("Coffee Beans 250g",    "FB-007",  6.00,  14.99,  450, 55),
    ],
    "Home & Garden": [
        ("Scented Candle Set",   "HG-001",  8.00,  22.99,  400, 50),
        ("Ceramic Plant Pot",    "HG-002",  4.50,  13.99,  600, 70),
        ("Bamboo Cutting Board", "HG-003",  9.00,  24.99,  250, 35),
        ("LED Desk Lamp",        "HG-004", 15.00,  34.99,  180, 25),
        ("Storage Basket",       "HG-005",  7.00,  18.99,  350, 45),
        ("Garden Trowel",        "HG-006",  5.00,  13.99,  300, 40),
        ("Watering Can 2L",      "HG-007",  6.50,  16.99,  280, 35),
    ],
    "Sports & Outdoors": [
        ("Resistance Bands Set", "SO-001",  9.00,  24.99,  400, 50),
        ("Jump Rope",            "SO-002",  4.00,  11.99,  600, 70),
        ("Yoga Mat",             "SO-003", 12.00,  29.99,  300, 40),
        ("Water Bottle 1L",      "SO-004",  5.50,  14.99,  500, 60),
        ("Foam Roller",          "SO-005", 10.00,  26.99,  250, 35),
        ("Dumbbell 5kg",         "SO-006", 14.00,  34.99,  180, 25),
        ("Exercise Gloves",      "SO-007",  6.00,  17.99,  350, 45),
    ],
}

BRANCHES = [
    ("Downtown Branch",  "City Centre",      0.35),  # 35% of sales volume
    ("North Branch",     "North District",   0.25),
    ("East Branch",      "East Side",        0.22),
    ("South Branch",     "South Quarter",    0.18),
]

REGIONS = ["North", "South", "East", "West"]

CUSTOMER_NAMES = [
    "Alice Johnson", "Bob Martinez", "Catherine Lee", "David Okonkwo",
    "Emma Thompson", "Frank Nguyen", "Grace Kim", "Henry Patel",
    "Irene Costa", "James Wilson", "Karen Brown", "Liam Davis",
    "Mia Garcia", "Noah Anderson", "Olivia Taylor", "Peter White",
    "Quinn Robinson", "Rachel Hall", "Samuel Turner", "Tina Walker",
    "Uma Scott", "Victor Harris", "Wendy Lewis", "Xavier Young",
    "Yara King", "Zoe Wright", "Aaron Mitchell", "Bella Clark",
    "Carlos Rodriguez", "Diana Adams", "Ethan Evans", "Fiona Carter",
    "George Parker", "Hannah Morris", "Ivan Rogers", "Julia Bennett",
    "Kevin Cooper", "Laura Bailey", "Marcus Reed", "Nina Cook",
    "Oscar Bell", "Paula Murphy", "Quincy Howard", "Rosa Ward",
    "Sebastian Torres", "Tessa Long", "Ulric Hill", "Vivian Brooks",
    "Walter Green", "Xena Phillips",
    # Wholesale / Corporate
    "Apex Distributors Ltd", "BlueSky Wholesale Co", "City Retail Group",
    "Delta Supplies Inc", "Eagle Trading LLC", "FirstPro Corp",
    "Global Mart Ltd", "Harbor Imports Co", "Island Retail Chain",
    "JetSpeed Logistics",
    # VIP
    "Ambassador Club #1", "Ambassador Club #2", "Premier Member #1",
    "Premier Member #2", "Elite Account #1", "Elite Account #2",
    "Loyalty Gold #1", "Loyalty Gold #2", "VIP Member #1", "VIP Member #2",
]

CUSTOMER_TYPES_DIST = (
    # (CustomerType, weight, count)
    (Customer.CustomerType.RETAIL,    50, 50),
    (Customer.CustomerType.WHOLESALE, 15, 10),
    (Customer.CustomerType.CORPORATE, 10, 10),
    (Customer.CustomerType.VIP,        5, 10),
)

# Monthly seasonality multipliers (index 0 = January)
SEASONALITY = [0.75, 0.70, 0.95, 0.90, 0.85, 0.80, 0.78, 0.80, 0.90, 0.95, 1.20, 1.30]

# Weekday weights (Mon=0 … Sun=6) — retail peaks Sat/Sun, quieter Mon
WEEKDAY_WEIGHTS = [0.80, 0.85, 0.90, 0.90, 1.00, 1.20, 1.10]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _weighted_choice(items, weights):
    total = sum(weights)
    r     = random.uniform(0, total)
    cumul = 0
    for item, w in zip(items, weights):
        cumul += w
        if r <= cumul:
            return item
    return items[-1]


def _month_offset(base_date, months):
    """Return the first day of the month `months` before base_date."""
    year  = base_date.year  + (base_date.month - months - 1) // 12
    month = (base_date.month - months - 1) % 12 + 1
    return date(year, month, 1)


class Command(BaseCommand):
    help = "Seed the database with 14 months of realistic demo sales data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear", action="store_true",
            help="Delete all existing data before seeding.",
        )
        parser.add_argument(
            "--months", type=int, default=14,
            help="Number of historical months to generate (default 14).",
        )
        parser.add_argument(
            "--sales-per-day", type=int, default=6,
            help="Average sales transactions per day (default 6, ~2500 total over 14 months).",
        )

    def handle(self, *args, **options):
        random.seed(42)  # deterministic output

        if options["clear"]:
            self.stdout.write("Clearing existing data …")
            Sale.objects.all().delete()
            Customer.objects.all().delete()
            Product.objects.all().delete()
            Category.objects.all().delete()
            Branch.objects.all().delete()
            self.stdout.write(self.style.WARNING("All data cleared."))

        with transaction.atomic():
            categories = self._create_categories()
            products   = self._create_products(categories)
            branches   = self._create_branches()
            customers  = self._create_customers()
            count      = self._create_sales(
                products, branches, customers,
                months=options["months"],
                avg_per_day=options["sales_per_day"],
            )

        self.stdout.write(self.style.SUCCESS(
            f"\nSeed complete: {len(categories)} categories, {len(products)} products, "
            f"{len(branches)} branches, {len(customers)} customers, {count} sales."
        ))

    # ------------------------------------------------------------------ #
    # Creators
    # ------------------------------------------------------------------ #

    def _create_categories(self):
        created = {}
        for name in CATEGORIES:
            cat, _ = Category.objects.get_or_create(category_name=name)
            created[name] = cat
            self.stdout.write(f"  Category: {name}")
        return created

    def _create_products(self, categories):
        products = []
        for cat_name, items in PRODUCTS_BY_CATEGORY.items():
            category = categories[cat_name]
            for product_name, sku, cost, price, stock, min_stock in items:
                # Add variance to stock to make low-stock rules fire on some products
                jitter     = random.randint(-10, 20)
                final_stock = max(min_stock, stock + jitter)

                product, created = Product.objects.get_or_create(
                    sku=sku,
                    defaults={
                        "product_name":       product_name,
                        "category":           category,
                        "cost_price":         Decimal(str(cost)),
                        "selling_price":      Decimal(str(price)),
                        "stock_quantity":     final_stock,
                        "minimum_stock_level": min_stock,
                        "is_active":          True,
                    },
                )
                if created:
                    self.stdout.write(f"  Product: {product_name} ({sku})")
                products.append(product)
        return products

    def _create_branches(self):
        branches = []
        for name, location, _ in BRANCHES:
            branch, created = Branch.objects.get_or_create(
                branch_name=name,
                defaults={"location": location, "is_active": True},
            )
            if created:
                self.stdout.write(f"  Branch: {name}")
            branches.append((branch, _))  # (Branch, share)
        return branches

    def _create_customers(self):
        retail_names    = CUSTOMER_NAMES[:50]
        wholesale_names = CUSTOMER_NAMES[50:60]
        corporate_names = CUSTOMER_NAMES[60:70]
        vip_names       = CUSTOMER_NAMES[70:80]

        all_customers = []
        for names, ctype in [
            (retail_names,    Customer.CustomerType.RETAIL),
            (wholesale_names, Customer.CustomerType.WHOLESALE),
            (corporate_names, Customer.CustomerType.CORPORATE),
            (vip_names,       Customer.CustomerType.VIP),
        ]:
            for name in names:
                region   = random.choice(REGIONS)
                customer, created = Customer.objects.get_or_create(
                    full_name=name,
                    defaults={
                        "customer_type": ctype,
                        "region":        region,
                        "email":         f"{name.lower().replace(' ', '.')[:20]}@example.com",
                    },
                )
                if created:
                    all_customers.append(customer)
                else:
                    all_customers.append(customer)

        self.stdout.write(f"  Customers: {len(all_customers)}")
        return all_customers

    def _create_sales(self, products, branches, customers, months=14, avg_per_day=6):
        today     = date.today()
        start     = _month_offset(today, months - 1)
        end       = today - timedelta(days=1)  # exclude today

        # Branch weights from share tuples
        branch_objs    = [b for b, _ in branches]
        branch_weights = [w for _, w in branches]

        # Customer type weights for frequency
        ctype_weights = {
            Customer.CustomerType.RETAIL:    1,
            Customer.CustomerType.WHOLESALE: 2,
            Customer.CustomerType.CORPORATE: 2,
            Customer.CustomerType.VIP:       3,
        }

        # Pre-group customers by type for weighted selection
        customers_by_type = {}
        for c in customers:
            customers_by_type.setdefault(c.customer_type, []).append(c)

        # Trend: mild upward slope over 14 months
        total_days = (end - start).days + 1

        count    = 0
        sale_day = start

        # bulk_create does NOT call .save() and does NOT fire Django signals.
        # Stock signals are therefore never triggered for bulk-inserted rows.
        # We set product stock to realistic levels manually after seeding.
        bulk_sales = []

        while sale_day <= end:
            day_of_week  = sale_day.weekday()
            month_idx    = sale_day.month - 1
            days_elapsed = (sale_day - start).days

            # Daily volume = base × seasonality × weekday weight × trend
            trend_factor = 1.0 + (days_elapsed / total_days) * 0.20
            daily_volume = int(
                avg_per_day
                * SEASONALITY[month_idx]
                * WEEKDAY_WEIGHTS[day_of_week]
                * trend_factor
                + random.gauss(0, 1)
            )
            daily_volume = max(0, daily_volume)

            for _ in range(daily_volume):
                product = random.choice(products)
                branch  = _weighted_choice(branch_objs, branch_weights)

                # Walk-in 20% of the time
                customer = None
                if random.random() > 0.20:
                    ctype_keys  = list(customers_by_type.keys())
                    ctype_wts   = [ctype_weights.get(k, 1) for k in ctype_keys]
                    chosen_type = _weighted_choice(ctype_keys, ctype_wts)
                    pool        = customers_by_type.get(chosen_type, customers)
                    customer    = random.choice(pool)

                # Quantity varies by customer type
                if customer and customer.customer_type in (
                    Customer.CustomerType.WHOLESALE,
                    Customer.CustomerType.CORPORATE,
                ):
                    qty = random.randint(3, 15)
                elif customer and customer.customer_type == Customer.CustomerType.VIP:
                    qty = random.randint(2, 8)
                else:
                    qty = random.randint(1, 4)

                # Unit price: selling_price ± small random discount (0–8%)
                base_price = float(product.selling_price)
                discount   = random.uniform(0, 0.08)
                unit_price = round(base_price * (1 - discount), 2)
                unit_price = max(unit_price, float(product.cost_price))

                sale = Sale(
                    product      = product,
                    customer     = customer,
                    branch       = branch,
                    quantity     = qty,
                    unit_price   = Decimal(str(unit_price)),
                    sale_date    = sale_day,
                    total_amount = Decimal("0"),
                    total_cost   = Decimal("0"),
                    total_profit = Decimal("0"),
                )
                sale.calculate_financials()
                bulk_sales.append(sale)

            sale_day += timedelta(days=1)

        Sale.objects.bulk_create(bulk_sales, batch_size=500)
        count = len(bulk_sales)

        # Set product stock to realistic post-seeding levels.
        # bulk_create skipped signals, so stock was never decremented.
        # We assign a plausible remaining quantity for each product directly
        # via update() to bypass model save() and signals again.
        for product in products:
            if random.random() < 0.12:
                # ~12% of products deliberately low / out for demo rule-engine triggers
                new_stock = random.randint(0, product.minimum_stock_level)
            else:
                new_stock = random.randint(
                    product.minimum_stock_level + 1,
                    product.minimum_stock_level + 60,
                )
            Product.objects.filter(pk=product.pk).update(
                stock_quantity=max(0, new_stock)
            )

        self.stdout.write(f"  Sales: {count} transactions over {months} months")
        return count
