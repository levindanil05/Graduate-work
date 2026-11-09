from django import template

from feedback.utils import build_feedback_create_url

register = template.Library()


@register.simple_tag(takes_context=True)
def feedback_create_url(context, document_id=None):
    """Ссылка «Написать обращение» с source=текущий path."""
    request = context.get('request')
    return build_feedback_create_url(request, document_id=document_id)
