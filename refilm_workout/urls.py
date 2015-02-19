from django.conf.urls import patterns, url

from .basic_navigation import views
# from .basic_navigation import api

urlpatterns = patterns('',
    url(r'^$', views.home, name='home'),
    url(r'^exercise/(?P<exercise_id>\d+)/$', views.exercise, name='exercise'),
    url(r'^remaining$', views.remaining, name='remaining'),
    url(r'^(?P<combo_id>[-\w]+)/', views.home, name="muscle"),
)
