from django.contrib import admin
from .models import Category, Product, Inventory, Order, OrderItem


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'order')
    list_editable = ('order',)
    prepopulated_fields = {'slug': ('name',)}


class InventoryInline(admin.StackedInline):
    model = Inventory
    extra = 1


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'price', 'is_available', 'get_stock')
    list_filter = ('category', 'is_available')
    prepopulated_fields = {'slug': ('name',)}
    inlines = [InventoryInline]

    def get_stock(self, obj):
        try:
            return obj.inventory.quantity
        except Inventory.DoesNotExist:
            return 0
    get_stock.short_description = 'На складе'


@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = ('product', 'quantity')


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('price', 'subtotal')

    def subtotal(self, obj):
        return obj.subtotal()
    subtotal.short_description = 'Сумма'


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'phone', 'status', 'total_price', 'created_at')
    list_filter = ('status',)
    readonly_fields = ('total_price', 'created_at')
    inlines = [OrderItemInline]
