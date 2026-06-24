from django.urls import path

from . import views

urlpatterns = [
    path('health/', views.health, name='health'),
    path('sales/summary/', views.sales_summary, name='sales-summary'),
]
