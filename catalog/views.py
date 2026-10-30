from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from catalog.models import Product
from core.sales import product_sales_only
from orders.models import OrderItem

SORT_OPTIONS = {
    "newest": ("-published_at", "Newest first"),
    "price_asc": ("price", "Price: low to high"),
    "price_desc": ("-price", "Price: high to low"),
    "name": ("name", "Name (A–Z)"),
}


@product_sales_only
def product_list(request):
    products = Product.objects.published()
    query = request.GET.get("q", "").strip()[:100]
    category = request.GET.get("category", "")
    if category == "web_app":  # old links: web apps moved to the capstone catalog
        return redirect(f"{reverse('capstone:list')}?field=web", permanent=True)
    sort = request.GET.get("sort", "newest")

    if query:
        products = products.filter(
            Q(name__icontains=query)
            | Q(short_description__icontains=query)
            | Q(description__icontains=query)
            | Q(features__icontains=query)
            | Q(tech_stack__icontains=query)
        )
    if category in Product.Category.values:
        products = products.filter(category=category)
    else:
        category = ""
    if sort not in SORT_OPTIONS:
        sort = "newest"
    ordering = [SORT_OPTIONS[sort][0], "-id"]
    if sort == "newest":
        ordering.insert(0, "-is_featured")
    products = products.order_by(*ordering)

    page = Paginator(products, 12).get_page(request.GET.get("page"))
    # Category tabs keep the current search and a non-default sort.
    tab_params = urlencode({k: v for k, v in (("sort", sort if sort != "newest" else ""), ("q", query)) if v})
    context = {
        "tab_params": tab_params,
        "page_obj": page,
        "products": page.object_list,
        "query": query,
        "category": category,
        "sort": sort,
        "category_tabs": [
            (Product.Category.SOFTWARE, "Software"),
            (Product.Category.MOBILE_APP, "Mobile Apps"),
        ],
        "sort_options": [(k, v[1]) for k, v in SORT_OPTIONS.items()],
    }
    return render(request, "catalog/product_list.html", context)


@product_sales_only
def product_detail(request, slug):
    product = get_object_or_404(Product.objects.published().prefetch_related("images"), slug=slug)
    owned_item = None
    if request.user.is_authenticated:
        owned_item = (
            OrderItem.objects.filter(order__user=request.user, order__status="paid", product=product)
            .select_related("order")
            .first()
        )
    related = (
        Product.objects.published().filter(category=product.category).exclude(pk=product.pk)[:3]
    )
    return render(
        request,
        "catalog/product_detail.html",
        {"product": product, "owned_item": owned_item, "related": related},
    )
