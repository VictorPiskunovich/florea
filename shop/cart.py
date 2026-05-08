import copy
from decimal import Decimal

CART_SESSION_KEY = 'cart'
FREE_DELIVERY_THRESHOLD = Decimal('3000')
DELIVERY_COST = Decimal('300')


class Cart:
    def __init__(self, request):
        self.session = request.session
        cart = self.session.get(CART_SESSION_KEY)
        if cart is None:
            cart = self.session[CART_SESSION_KEY] = {}
        self.cart = cart

    def add(self, product, quantity=1, override=False, extras='', price=None):
        pid = str(product.pk)
        stored_price = str(price if price is not None else product.price)
        if pid not in self.cart:
            self.cart[pid] = {'quantity': 0, 'price': stored_price, 'extras': ''}
        if override:
            self.cart[pid]['quantity'] = quantity
        else:
            self.cart[pid]['quantity'] += quantity
        self.cart[pid]['price'] = stored_price
        if extras:
            self.cart[pid]['extras'] = extras
        if self.cart[pid]['quantity'] <= 0:
            del self.cart[pid]
        self.save()

    def remove(self, product):
        pid = str(product.pk)
        if pid in self.cart:
            del self.cart[pid]
            self.save()

    def clear(self):
        self.session[CART_SESSION_KEY] = {}
        self.session.modified = True
        self.cart = self.session[CART_SESSION_KEY]

    def save(self):
        self.session.modified = True

    def __iter__(self):
        from .models import Product, Inventory
        pids = list(self.cart.keys())
        products = {str(p.pk): p for p in Product.objects.filter(pk__in=pids)}
        stocks = {
            str(inv.product_id): inv.quantity
            for inv in Inventory.objects.filter(product_id__in=pids)
        }
        cart = copy.deepcopy(self.cart)
        for pid, item in cart.items():
            product = products.get(pid)
            if product is None:
                continue
            item['product'] = product
            item['price'] = Decimal(item['price'])
            item['subtotal'] = item['price'] * item['quantity']
            item['stock'] = stocks.get(pid)
            item['at_max'] = item['stock'] is not None and item['quantity'] >= item['stock']
            item['extras'] = item.get('extras', '')
            yield item

    def __len__(self):
        return sum(item['quantity'] for item in self.cart.values())

    def __bool__(self):
        return bool(self.cart)

    def get_total_price(self):
        return sum(Decimal(item['price']) * item['quantity'] for item in self.cart.values())

    def get_delivery(self):
        subtotal = self.get_total_price()
        return Decimal('0') if subtotal >= FREE_DELIVERY_THRESHOLD else DELIVERY_COST

    def get_total(self):
        return self.get_total_price() + self.get_delivery()
