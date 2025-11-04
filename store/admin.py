from django.contrib import admin
from .models import Product
# Register your models here.

class ProductAdmin(models.ModelAdmin):
    list_display =('product_name','price','stock','category','modified_date')

admin.site.register(Product)
