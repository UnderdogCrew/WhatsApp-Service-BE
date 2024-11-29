"""
URL configuration for UnderdogCrew project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from ai_apis import views
from whatsapp_apis import views as whatsapp_apis

urlpatterns = [
    path('admin/', admin.site.urls),
    path('send/message', views.SendMessage.as_view(), name='SendMessage'),
    path('webhook', views.FacebookWebhook.as_view(), name='FacebookWebhook'),
    path('image-generation', views.ImageGeneration.as_view(), name='ImageGeneration'),
    path('text-generation', views.TextGeneration.as_view(), name='TextGeneration'),
    path('verify-business-number', whatsapp_apis.VerifyBusinessPhoneNumber.as_view(), name='VerifyBusinessPhoneNumber'),
    path('message_templates', whatsapp_apis.MessageTemplates.as_view(), name='MessageTemplates'),
]
