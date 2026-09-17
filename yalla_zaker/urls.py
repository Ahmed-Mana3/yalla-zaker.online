from django.contrib import admin
from django.urls import include, path

from . import middleware, seo

urlpatterns = [
    path('admin/', admin.site.urls),
    path('robots.txt', seo.robots_txt, name='robots'),
    path('sitemap.xml', seo.sitemap_xml, name='sitemap'),
    path('llms.txt', seo.llms_txt, name='llms'),
    path('', include('accounts.urls')),
    path('courses/', include('courses.urls')),
    path('study/', include('studysessions.urls')),
    path('challenges/', include('challenges.urls')),
    path('p/', include('courses.public_urls')),
]

handler500 = middleware.server_error
handler404 = middleware.page_not_found