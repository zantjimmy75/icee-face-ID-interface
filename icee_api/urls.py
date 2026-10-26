from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views
urlpatterns = [
 path('api/auth/login/', views.login_view, name='login'),
 path('api/auth/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
 path('api/individuals/', views.individual_list, name='individual-list'),
 path('api/individuals/<str:record_id>/', views.individual_detail, name='individual-detail'),
 path('api/face/enroll/', views.face_enroll, name='face-enroll'),
 path('api/face/verify/', views.face_verify, name='face-verify'),
 path('api/face/identify/', views.face_identify, name='face-identify'),
 path('api/checkins/', views.checkin, name='checkin'),
 path('api/reports/attendance/', views.attendance_report, name='attendance-report'),
]
