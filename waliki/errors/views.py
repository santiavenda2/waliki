# -*- coding: utf-8 -*-
from django.shortcuts import render

from waliki.acl import permission_required


def errors(request, pag=1):
    return render(request, 'waliki/errors.html')


@permission_required('view_page')
def page_errors(request, slug):
    return render(request, 'waliki/page_errors.html')
