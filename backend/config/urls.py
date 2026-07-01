from django.contrib import admin
from django.urls import path, include
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

schema_view = get_schema_view(
    openapi.Info(
        title='TecnoCare API',
        default_version='v1',
        description='API de gestión de mantenimiento de equipos tecnológicos',
    ),
    public=False,
    permission_classes=[permissions.IsAuthenticated],
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('usuarios.urls')),
    path('api/', include('equipos.urls')),
    path('api/', include('mantenimientos.urls')),
    path('api/', include('reportes.urls')),
    path('api/', include('chatbot.urls')),
    path('api/docs/', schema_view.with_ui('swagger', cache_timeout=0), name='swagger-ui'),
    path('api/redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='redoc'),
]
