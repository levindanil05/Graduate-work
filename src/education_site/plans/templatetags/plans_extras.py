from django import template

from documents.workflow_ui import action_label, target_status_label

register = template.Library()


@register.filter
def status_label(status):
    return target_status_label(status)


@register.filter
def action_label_filter(action):
    return action_label(action)
