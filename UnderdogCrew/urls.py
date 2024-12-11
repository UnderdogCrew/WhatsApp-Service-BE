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
from login_apis import views as login_service
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

schema_view = get_schema_view(
   openapi.Info(
      title="Whatsapp-Service-API",
      default_version='v1',
      description="API documentation",
      terms_of_service="https://privacy-policy.theunderdogcrew.com/",
      contact=openapi.Contact(email="hello@theunderdogcrew.com"),
      license=openapi.License(name="BSD License"),
   ),
   public=True,
   permission_classes=(permissions.AllowAny,),
   # url='https://whatsapp-api.theunderdogcrew.com/',
   url='http://127.0.0.1:8000/',
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    path('send/message', views.SendMessage.as_view(), name='SendMessage'),
    path('webhook', views.FacebookWebhook.as_view(), name='FacebookWebhook'),
    path('image-generation', views.ImageGeneration.as_view(), name='ImageGeneration'),
    path('text-generation', views.TextGeneration.as_view(), name='TextGeneration'),
    path('verify-business-number', whatsapp_apis.VerifyBusinessPhoneNumber.as_view(), name='VerifyBusinessPhoneNumber'),
    path('message_templates', whatsapp_apis.MessageTemplates.as_view(), name='MessageTemplates'),
    path('sign_up',login_service.SignupView.as_view(),name='SignupView'),
    path('login',login_service.LoginView.as_view(),name='LoginView'),
    path('upload',login_service.FileUploadView.as_view(),name='FileUploadView'),
    path('otp/generate/', login_service.OTPGenerate.as_view(), name='OTPGenerate'),
    path('otp/verify/', login_service.OTPVerify.as_view(), name='OTPVerify'),      
    path('business-details/', login_service.BusinessDetails.as_view(), name='update_whatsapp_business_details'),
]
