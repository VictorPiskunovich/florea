/* ─── Общая утилита корзины (localStorage) ─── */
const CART_KEY = 'flowerCart';

function getCart() {
  try { return JSON.parse(localStorage.getItem(CART_KEY)) || []; }
  catch { return []; }
}

function saveCart(cart) {
  localStorage.setItem(CART_KEY, JSON.stringify(cart));
}

function getCartCount() {
  return getCart().reduce((s, i) => s + i.qty, 0);
}

function addToCart(id) {
  const cart = getCart();
  const existing = cart.find(i => i.id === id);
  if (existing) existing.qty++;
  else cart.push({ id: id, qty: 1 });
  saveCart(cart);
  updateCartBadge();
  return getCartCount();
}

function updateCartBadge() {
  const count = getCartCount();
  document.querySelectorAll('.cart-count').forEach(el => el.textContent = count);
}

// Обновляем бейдж при загрузке страницы
document.addEventListener('DOMContentLoaded', updateCartBadge);
