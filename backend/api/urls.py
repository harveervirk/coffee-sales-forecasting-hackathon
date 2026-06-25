from django.urls import path

from . import views

urlpatterns = [
    path('health/',                views.health,           name='health'),
    path('sales/summary/',         views.sales_summary,    name='sales-summary'),
    path('sales/trends/',          views.sales_trends,     name='sales-trends'),
    path('sales/items/',           views.sales_items,      name='sales-items'),
    path('sales/provinces/',       views.sales_provinces,  name='sales-provinces'),
    path('sales/locations/',       views.sales_locations,  name='sales-locations'),
    path('forecast/',              views.forecast,         name='forecast'),
    path('forecast/metrics/',      views.forecast_metrics, name='forecast-metrics'),
    path('recommendations/',       views.recommendations,  name='recommendations'),
]
