from django import forms
from django.utils.translation import gettext_lazy as _

from .models import FeedbackKind, FeedbackReport, FeedbackStatus


class FeedbackCreateForm(forms.ModelForm):
    class Meta:
        model = FeedbackReport
        fields = ('kind', 'subject', 'body')
        labels = {
            'kind': _('Kind'),
            'subject': _('Subject'),
            'body': _('Message'),
        }
        widgets = {
            'kind': forms.Select(attrs={'id': 'id_kind'}),
            'subject': forms.TextInput(attrs={'id': 'id_subject'}),
            'body': forms.Textarea(attrs={'rows': 6, 'id': 'id_body'}),
        }


class FeedbackHandleForm(forms.ModelForm):
    class Meta:
        model = FeedbackReport
        fields = ('status', 'staff_reply')
        labels = {
            'status': _('Status'),
            'staff_reply': _('Staff reply'),
        }
        widgets = {
            'staff_reply': forms.Textarea(attrs={'rows': 5}),
        }


class FeedbackCreateFormSimple(FeedbackCreateForm):
    """Русские подписи полей и вариантов выбора для UI."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['kind'].label = 'Тип'
        self.fields['subject'].label = 'Тема'
        self.fields['body'].label = 'Текст обращения'
        self.fields['kind'].choices = [
            (FeedbackKind.PROBLEM, 'Сообщение о проблеме'),
            (FeedbackKind.QUESTION, 'Вопрос'),
            (FeedbackKind.SUGGESTION, 'Предложение'),
        ]


class FeedbackHandleFormSimple(FeedbackHandleForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['status'].label = 'Статус'
        self.fields['staff_reply'].label = 'Ответ'
        self.fields['status'].choices = [
            (FeedbackStatus.NEW, 'Новое'),
            (FeedbackStatus.IN_PROGRESS, 'В работе'),
            (FeedbackStatus.RESOLVED, 'Решено'),
            (FeedbackStatus.REJECTED, 'Отклонено'),
        ]
