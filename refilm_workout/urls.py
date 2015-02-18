from django.conf.urls import patterns, url

from .basic_navigation import views
# from .basic_navigation import api

urlpatterns = patterns('',
    url(r'^$', views.home, name='home'),
    url(r'^(?P<combo_id>[-\w]+)/', views.home, name="muscle"),
)
