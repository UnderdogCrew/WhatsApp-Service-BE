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
from subscriptions import views as subscription_views
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from .settings import SWAGGER_URL

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
   url=SWAGGER_URL,
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    path('send/message', views.SendMessage.as_view(), name='SendMessage'),
    path('dashboard', views.UserDashboard.as_view(), name='UserDashboard'),
    path('webhook', views.FacebookWebhook.as_view(), name='FacebookWebhook'),
    path('message/logs', views.UserMessageLogs.as_view(), name='UserMessageLogs'),
    path('image-generation', views.ImageGeneration.as_view(), name='ImageGeneration'),
    path('text-generation', views.TextGeneration.as_view(), name='TextGeneration'),
    path('verify-business-number', whatsapp_apis.VerifyBusinessPhoneNumber.as_view(), name='VerifyBusinessPhoneNumber'),
    path('message_templates', whatsapp_apis.MessageTemplates.as_view(), name='MessageTemplates'),
    path('sign_up',login_service.SignupView.as_view(),name='SignupView'),
    path('login',login_service.LoginView.as_view(),name='LoginView'),
    path('user-billing', login_service.UserBillingAPIView.as_view(), name='user-billing'),
    path('upload',login_service.FileUploadView.as_view(),name='FileUploadView'),
    path('profile',login_service.ProfileView.as_view(),name='ProfileView'),
    path('otp/generate/', login_service.OTPGenerate.as_view(), name='OTPGenerate'),
    path('otp/verify/', login_service.OTPVerify.as_view(), name='OTPVerify'),      
    path('business-details/', login_service.BusinessDetails.as_view(), name='update_whatsapp_business_details'),
    path('verify-email', login_service.EmailVerificationView.as_view(), name='verify_email'),
    path('refresh-token', login_service.RefreshTokenView.as_view(), name='refresh_token'),
    path('login/admin',login_service.AdminLoginView.as_view(), name='admin_login'),
    path('business-details/verify', login_service.VerifyBusinessDetailsView.as_view(), name='verify_whatsapp_business_details'),
    path('users', login_service.GetAllUsersView.as_view(), name='get_all_users'),
    path('subscriptions', subscription_views.SubscriptionView.as_view(), name='subscription_view'),
    path('subscriptions/cancel', subscription_views.SubscriptionCancelView.as_view(), name='subscription_cancel'),
    path('subscriptions/create-order', subscription_views.CreateOrderView.as_view(), name='create_order'),
    path('subscriptions/plans', subscription_views.PlansView.as_view(), name='plans'),
    path('subscriptions/webhook', subscription_views.WebhookView.as_view(), name='webhook'),
    path('whatsapp-templates/', whatsapp_apis.WhatsAppTemplateView.as_view(), name='whatsapp-templates'),
    path('customers', whatsapp_apis.CustomersView.as_view(), name='customers'),
    path('whatsapp/customers', login_service.CustomerAPIView.as_view(), name='customer'),
    path('whatsapp/customers/detail/', login_service.CustomerDetailAPIView.as_view(), name='customer-detail'),
    path('chat/history', whatsapp_apis.CustomersChatLogs.as_view(), name='customerchatlogs'),
    path('chat/list', whatsapp_apis.UniqueChatList.as_view(), name='UniqueChatList'),
    path('messages', views.WhatsAppMessage.as_view(), name='messages'),
    path('user/status', login_service.UserStatusView.as_view(), name='user-status'),
    path('whatsapp/upload-file/', whatsapp_apis.FacebookFileUploadView.as_view(), name='facebook-file-upload'),
]
