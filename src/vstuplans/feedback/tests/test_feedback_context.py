from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from feedback.models import FeedbackKind, FeedbackReport
from feedback.utils import build_feedback_create_url


class FeedbackContextTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user('fb_user', password='password12345')
        self.factory = RequestFactory()
        self.client = Client()
        self.client.force_login(self.user)

    def test_build_feedback_create_url_includes_source(self):
        request = self.factory.get('/plans/?status=new')
        url = build_feedback_create_url(request)
        self.assertIn('/feedback/new/', url)
        self.assertIn('source=', url)
        self.assertIn('%2Fplans%2F', url)

    def test_create_stores_source_path_not_form_url(self):
        response = self.client.post(
            reverse('feedback:create') + '?source=/plans/&document_id=',
            data={
                'kind': FeedbackKind.QUESTION,
                'subject': 'Тест контекста',
                'body': 'Текст обращения для проверки.',
                'source': '/plans/?q=test',
            },
        )
        self.assertEqual(response.status_code, 302)
        report = FeedbackReport.objects.get(author=self.user)
        self.assertEqual(report.context.get('source_path'), '/plans/?q=test')
        self.assertNotIn('/feedback/new', report.context.get('source_path', ''))
        self.assertIn('/plans/', report.context.get('page_url', ''))

    def test_author_sees_body_on_detail(self):
        report = FeedbackReport.objects.create(
            author=self.user,
            kind=FeedbackKind.PROBLEM,
            subject='Тема',
            body='Полный текст обращения',
            staff_reply='Ответ сотрудника',
            context={'source_path': '/'},
        )
        response = self.client.get(reverse('feedback:my_detail', args=[report.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Полный текст обращения')
        self.assertContains(response, 'Ответ сотрудника')

    def test_create_form_labels_russian(self):
        response = self.client.get(reverse('feedback:create') + '?source=/')
        self.assertContains(response, 'Тип')
        self.assertContains(response, 'Тема')
        self.assertContains(response, 'Текст обращения')
        self.assertNotContains(response, '>Kind<')
        self.assertNotContains(response, '>Subject<')
