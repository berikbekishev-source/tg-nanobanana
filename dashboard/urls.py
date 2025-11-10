from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.ChatListView.as_view(), name="chat_list"),
    path("chats/<int:pk>/", views.ChatDetailView.as_view(), name="chat_detail"),
    path("messages/<int:pk>/media/", views.MessageMediaProxyView.as_view(), name="message_media"),
]
