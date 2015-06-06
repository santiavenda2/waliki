from django.conf.urls import patterns, url
from waliki.settings import WALIKI_SLUG_PATTERN

urlpatterns = patterns('waliki.errors.views',
    url(r'^(?P<slug>' + WALIKI_SLUG_PATTERN + ')/errors', 'page_errors', name='waliki_page_errors'),
    url(r'^_errors/(?P<pag>\d+)$', 'errors', name='waliki_errors'),       # noqa
    url(r'^_errors$', 'errors', {'pag': '1'}, name='waliki_errors'),       # noqa
)
