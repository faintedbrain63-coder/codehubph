from orders.cart import SESSION_KEY


def cart(request):
    return {"cart_count": len(request.session.get(SESSION_KEY, []))}
