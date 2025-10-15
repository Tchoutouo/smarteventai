# ai_service/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('api/chat/', views.chat_view, name='chat-api'),
    path('api/chat/health/', views.chat_health_view, name='chat-health'),
    path('api/chat/history/', views.chat_history_view, name='chat-history'),
]