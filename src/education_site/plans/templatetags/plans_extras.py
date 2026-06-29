from django import template

from documents.workflow_ui import target_status_label

register = template.Library()


@register.filter
def status_label(status):
    return target_status_label(status)
