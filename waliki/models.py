# -*- coding: utf-8 -*-
import codecs
import os.path
from django.db import models
from django.db.models import Q
from django.db.utils import IntegrityError
from django.conf import settings
from django.core.urlresolvers import reverse
from django.dispatch import receiver
from django.utils.six import string_types
from django.utils.translation import ugettext_lazy as _
from django.contrib.auth.models import Permission, Group, AnonymousUser
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db.models.signals import post_save
import docutils.utils
from . import _markups
from waliki.settings import (get_slug, WALIKI_DEFAULT_MARKUP,
                             WALIKI_MARKUPS_SETTINGS, WALIKI_DATA_DIR,
                             WALIKI_CACHE_TIMEOUT)


class Page(models.Model):
    MARKUP_CHOICES = [(m.name, m.name) for m in _markups.get_all_markups()]
    title = models.CharField(verbose_name=_('Title'), max_length=200)
    slug = models.CharField(max_length=200, unique=True)
    path = models.CharField(max_length=200, unique=True)
    markup = models.CharField(verbose_name=_('Markup'), max_length=20,
                              choices=MARKUP_CHOICES, default=WALIKI_DEFAULT_MARKUP)

    class Meta:
        verbose_name = _('Page')
        verbose_name_plural = _('Pages')
        permissions = (
            ('view_page', 'Can view page'),
        )

    class EditionConflict(Exception):
        pass

    def __str__(self):
        return self.__unicode__()

    def __unicode__(self):
        return self.path

    def get_absolute_url(self):
        return reverse('waliki_detail', args=(self.slug,))

    def get_edit_url(self):
        return reverse('waliki_edit', args=(self.slug,))

    def save(self, *args, **kwargs):
        self.slug = self.slug.strip('/')
        if not self.path:
            self.path = self.slug + self.markup_.file_extensions[0]
        super(Page, self).save(*args, **kwargs)

    @classmethod
    def from_path(cls, path, markup=None):
        filename, ext = os.path.splitext(path)
        if markup and isinstance(markup, string_types):
            markup = _markups.find_markup_class_by_name(markup)
        else:
            markup = _markups.find_markup_class_by_extension(ext)
        page = Page(path=path, slug=get_slug(filename), markup=markup.name)
        try:
            page.title = page._get_part('get_document_title')
        except docutils.utils.SystemMessage:
            pass

        while True:
            try:
                page.save()
                break
            except IntegrityError:
                page.slug += '-new'

        return page

    @property
    def raw(self):
        filename = self.abspath
        if not os.path.exists(filename) or os.path.isdir(filename):
            return ""
        return codecs.open(filename, "r", encoding="utf-8").read()

    @raw.setter
    def raw(self, value):
        filename = os.path.join(WALIKI_DATA_DIR, self.path)
        try:
            os.makedirs(os.path.dirname(filename))
        except OSError:
            pass
        with codecs.open(filename, "w", encoding="utf-8") as f:
            f.write(value)

    @property
    def abspath(self):
        return os.path.abspath(os.path.join(WALIKI_DATA_DIR, self.path))

    @staticmethod
    def get_markup_instance(markup):
        markup_settings = WALIKI_MARKUPS_SETTINGS.get(markup, None)
        markup_class = _markups.find_markup_class_by_name(markup)
        return markup_class(**markup_settings)

    @staticmethod
    def preview(markup, text):
        return Page.get_markup_instance(markup).get_document_body(text)

    @property
    def markup_(self):
        if not hasattr(self, '__markup_instance'):
            self.__markup_instance = Page.get_markup_instance(self.markup)
        return self.__markup_instance

    def _get_part(self, part):
        return getattr(self.markup_, part)(self.raw)

    @property
    def body(self):
        return self.get_cached_content()

    @property
    def stylesheet(self):
        return self._get_part('get_stylesheet')

    @property
    def javascript(self):
        return self._get_part('get_javascript')

    def get_cache_key(self):
        return "waliki:content:%s" % self.slug

    def get_cached_content(self):
        """Returns cached """
        cache_key = self.get_cache_key()
        cached_content = cache.get(cache_key)

        if cached_content is None:
            cached_content = self._get_part('get_document_body')
            cache.set(cache_key, cached_content, WALIKI_CACHE_TIMEOUT)
        return cached_content


class ACLRule(models.Model):
    TO_ANY = 'any'
    TO_LOGGED = 'logged'
    TO_STAFF = 'staff'
    TO_SUPERUSERS = 'superusers'
    TO_EXPLICIT_LIST = 'explicit'
    APPLY_TO_CHOICES = (
        (TO_ANY, _('Any user')),
        (TO_LOGGED, _('Any authenticated user')),
        (TO_STAFF, _('Any staff member')),
        (TO_SUPERUSERS, _('Any superuser')),
        (TO_EXPLICIT_LIST, _('Any user/group explicitly defined')),
    )

    name = models.CharField(verbose_name=_('Name'), max_length=200, unique=True)
    slug = models.CharField(max_length=200)
    as_namespace = models.BooleanField(verbose_name=_('As namespace'),
                                       default=False)
    permissions = models.ManyToManyField(Permission, limit_choices_to={'content_type__app_label': 'waliki'})
    apply_to = models.CharField(max_length=25, choices=APPLY_TO_CHOICES, default=TO_EXPLICIT_LIST)
    users = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True)
    groups = models.ManyToManyField(Group, blank=True)

    def __unicode__(self):
        return _('Rule: %(name)s for /%(slug)s') % {'name': self.name, 'slug': self.slug}

    def __str__(self):
        return self.__unicode__()

    class Meta:
        verbose_name = _('ACL rule')
        verbose_name_plural = _('ACL rules')

    @classmethod
    def get_rules_for(cls, perms, slug):
        """return rules with ``perms`` for the given ``slug``

        ``perms`` could be the permission name or an iterable
         of permissions names
        """
        def parents_for(slug):
            parent_slugs = []
            for f in slug.rsplit('/'):
                try:
                    parent = parent_slugs[-1] + '/' + f
                except IndexError:
                    parent = f
                parent_slugs.append(parent)
            return parent_slugs

        if isinstance(perms, string_types):
            perms = (perms,)

        rules = cls.objects.all()
        parent_slugs = parents_for(slug)
        for perm in perms:
            lookup = Q(permissions__codename=perm, as_namespace=False, slug=slug)
            for parent in parent_slugs:
                lookup |= Q(permissions__codename=perm, as_namespace=True, slug=parent)
            rules = rules.filter(lookup)
        return rules.distinct()

    @classmethod
    def get_users_for(cls, perms, slug):
        """
        return users with ``perms`` for the given ``slug``.

        ``perms`` could be the permission name or an iterable
         of permissions names
        """

        rules = cls.get_rules_for(perms, slug)
        if rules.filter(apply_to=ACLRule.TO_ANY).exists():
            return {AnonymousUser()} | set(get_user_model().objects.all())
        elif rules.filter(apply_to=ACLRule.TO_LOGGED).exists():
            return get_user_model().objects.all()

        allowed = []
        for rule in rules:
            if rule.apply_to == ACLRule.TO_STAFF:
                allowed += get_user_model().objects.filter(is_staff=True).values_list('id', flat=True)
            elif rule.apply_to == ACLRule.TO_SUPERUSERS:
                allowed += get_user_model().objects.filter(is_superuser=True).values_list('id', flat=True)
            else:
                allowed += get_user_model().objects.filter(Q(aclrule=rule) |
                                                           Q(groups__aclrule=rule)).values_list('id',
                                                                                                flat=True)
        return get_user_model().objects.filter(id__in=allowed).distinct()


######################################################
# SIGNAL HANDLERS
######################################################

@receiver(post_save, sender=Page)
def on_page_save_clear_cache(instance, **kwargs):
    cache.delete(instance.get_cache_key())
