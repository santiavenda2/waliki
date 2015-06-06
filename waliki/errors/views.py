# -*- coding: utf-8 -*-

from waliki.acl import permission_required


def errors(request, pag=1):
    pass


@permission_required('view_page')
def page_errors(request, slug):
    pass
