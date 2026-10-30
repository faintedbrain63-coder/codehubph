"""Session cart. Digital products have no quantity, so the cart is a list of product IDs."""

from catalog.models import Product

SESSION_KEY = "cart"


class Cart:
    def __init__(self, request):
        self.session = request.session
        stored = self.session.get(SESSION_KEY, [])
        self.ids = []
        if isinstance(stored, list):
            for item in stored:
                value = str(item)
                if value.isascii() and value.isdigit() and len(value) <= 19:
                    number = int(value)
                    if 0 < number <= 9223372036854775807 and number not in self.ids:
                        self.ids.append(number)
        if self.ids != stored:
            self._save()

    def _save(self):
        self.session[SESSION_KEY] = self.ids
        self.session.modified = True

    def add(self, product):
        if product.pk not in self.ids:
            self.ids.append(product.pk)
            self._save()
            return True
        return False

    def remove(self, product):
        if product.pk in self.ids:
            self.ids.remove(product.pk)
            self._save()

    def clear(self):
        self.ids = []
        self._save()

    def products(self):
        products = Product.objects.published().filter(pk__in=self.ids)
        valid_ids = [p.pk for p in products]
        if len(valid_ids) != len(self.ids):  # drop products that were unpublished meanwhile
            self.ids = [i for i in self.ids if i in valid_ids]
            self._save()
        return products

    def __len__(self):
        return len(self.ids)

    def __contains__(self, product):
        return product.pk in self.ids
