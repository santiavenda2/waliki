from django.utils.translation import ugettext_lazy as _
from waliki.plugins import BasePlugin, register


class ErrorsPlugin(BasePlugin):
    slug = 'errors'
    urls_page = ['waliki.errors.urls']
    extra_page_actions = {'all': [('waliki_page_errors', _('Errors'))]}
    navbar_links = (('waliki_errors', _('Errors')),)

register(ErrorsPlugin)

