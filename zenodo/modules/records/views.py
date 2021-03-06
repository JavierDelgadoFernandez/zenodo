# -*- coding: utf-8 -*-
#
# This file is part of Zenodo.
# Copyright (C) 2015, 2016 CERN.
#
# Zenodo is free software; you can redistribute it
# and/or modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 2 of the
# License, or (at your option) any later version.
#
# Zenodo is distributed in the hope that it will be
# useful, but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Zenodo; if not, write to the
# Free Software Foundation, Inc., 59 Temple Place, Suite 330, Boston,
# MA 02111-1307, USA.
#
# In applying this license, CERN does not
# waive the privileges and immunities granted to it by virtue of its status
# as an Intergovernmental Organization or submit itself to any jurisdiction.

"""Blueprint for Zenodo-Records."""

from __future__ import absolute_import, print_function

import copy

import idutils
import six
from flask import Blueprint, current_app, render_template, request
from werkzeug.utils import import_string

from .models import AccessRight, ObjectType

blueprint = Blueprint(
    'zenodo_records',
    __name__,
    template_folder='templates',
    url_prefix='/search'
)


#
# Access right template filters and tests.
#
@blueprint.app_template_test('accessright')
def is_valid_accessright(value):
    """Test if access right is valid."""
    return AccessRight.is_valid(value)


@blueprint.app_template_test('embargoed')
def is_embargoed(embargo_date, accessright=None):
    """Test if date is still embargoed (according to UTC date."""
    if accessright is not None and accessright != AccessRight.EMBARGOED:
        return False
    if embargo_date is not None:
        return AccessRight.is_embargoed(embargo_date)
    return False


@blueprint.app_template_filter()
def accessright_category(value, embargo_date=None):
    """Get category for access right."""
    return AccessRight.as_category(
        AccessRight.get(value, embargo_date=embargo_date))


@blueprint.app_template_filter()
def accessright_title(value, embargo_date=None):
    """Get category for access right."""
    return AccessRight.as_title(
        AccessRight.get(value, embargo_date=embargo_date))


#
# Related identifiers filters.
#
@blueprint.app_template_filter('zenodo_related_links')
def zenodo_related_links(record):
    """Get logos for related links."""
    def apply_rule(item, rule):
        r = copy.deepcopy(rule)
        r['link'] = idutils.to_url(item['identifier'], item['scheme'])
        return r

    def match_rules(item, communities):
        rs = []
        for c in set(communities):
            if c in current_app.config['ZENODO_RELATION_RULES']:
                rules = current_app.config['ZENODO_RELATION_RULES'][c]
                for r in rules:
                    if item['relation'] == r['relation'] and \
                       item['scheme'] == r['scheme'] and \
                       item['identifier'].startswith(r['prefix']):
                        rs.append(r)
        return rs

    ret = []
    communities = record.get('communities', []) + \
        record.get('provisional_communities', [])
    for item in record.get('related_identifiers', []):
        for r in match_rules(item, communities):
            ret.append(apply_rule(item, r))

    return ret


#
# Object type template filters and tests.
#
@blueprint.app_template_filter()
def objecttype(value):
    """Get object type."""
    return ObjectType.get_by_dict(value)


#
# Persistent identifiers template filters
#
@blueprint.app_template_test()
def local_doi(value):
    """Test if a DOI is a local DOI."""
    prefixes = current_app.config.get('ZENODO_LOCAL_DOI_PREFIXES', [])
    return prefixes and any((value.startswith(p + "/") for p in prefixes))


@blueprint.app_template_filter('relation_title')
def relation_title(relation):
    """Map relation type to title."""
    return dict(current_app.config['ZENODO_RELATION_TYPES']).get(relation) or \
        relation


@blueprint.app_template_filter('pid_url')
def pid_url(identifier, scheme=None):
    """Convert persistent identifier into a link."""
    if scheme is None:
        try:
            scheme = idutils.detect_identifier_schemes(identifier)[0]
        except IndexError:
            scheme = None
    if scheme and identifier:
        return idutils.to_url(identifier, scheme)
    return ""


def records_ui_export(pid, record, template=None):
    """Record serialization view.

    Plug this method into your ``RECORDS_UI_ENDPOINTS`` configuration:

    .. code-block:: python

        RECORDS_UI_ENDPOINTS = dict(
            recid=dict(
                # ...
                route='/records/<pid_value/files/<filename>',
                view_imp='zenodo.modules.records.views.records_ui_export',
            )
        )
    """
    formats = current_app.config.get('ZENODO_RECORDS_EXPORTFORMATS')
    fmt = request.view_args.get('format')

    if formats.get(fmt) is None:
        return render_template(
            'zenodo_records/records_export_unsupported.html'), 410
    else:
        serializer = import_string(formats[fmt]['serializer'])
        data = serializer.serialize(pid, record)
        if isinstance(data, six.binary_type):
            data = data.decode('utf8')

        return render_template(
            template, pid=pid, record=record,
            data=data, format_title=formats[fmt]['title'])
