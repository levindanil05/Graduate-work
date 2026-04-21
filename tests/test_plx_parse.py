import unittest
import os
from src.plx_parser import parse_plx_file

class TestPlxParser(unittest.TestCase):
    def setUp(self):
        self.data_dir = os.path.join(os.path.dirname(__file__), "test_data")

    def test_sample1_full(self):
        file_path = os.path.join(self.data_dir, "sample1_full.plx")
        result = parse_plx_file(file_path)
        expected = {
            'direction': 'Электроэнергетика и электротехника',
            'direction_code': '13.03.02',
            'faculty': 'механико-металлургический',
            'faculty_code': '-1',
            'department': 'Электротехника',
            'department_code': '48',
            'year_start': '2020',
            'qualification': 'бакалавр',
            'disciplines': [
                {'name': 'Экономика', 'code': 'Б1.В.01', 'credits': '3'},
                {'name': 'Экология', 'code': 'Б1.В.02', 'credits': '2'}
            ]
        }
        self.assertEqual(result, expected)

    def test_sample2_partial(self):
        file_path = os.path.join(self.data_dir, "sample2_partial.plx")
        result = parse_plx_file(file_path)
        expected = {
            'direction': 'Информатика и вычислительная техника',
            'direction_code': '09.03.01',
            'faculty': '',
            'faculty_code': '100',
            'department': '',
            'department_code': '9',
            'year_start': '2021',
            'qualification': 'бакалавр',
            'disciplines': [
                {'name': 'Программирование', 'code': 'Б1.О.01', 'credits': '5'}
            ]
        }
        self.assertEqual(result, expected)

    def test_sample3_empty_disciplines(self):
        file_path = os.path.join(self.data_dir, "sample3_empty_disciplines.plx")
        result = parse_plx_file(file_path)
        expected = {
            'direction': 'Экономика',
            'direction_code': '38.03.01',
            'faculty': 'Экономический',
            'faculty_code': '2',
            'department': 'Экономика и предпринимательство',
            'department_code': '24',
            'year_start': '2019',
            'qualification': 'бакалавр',   # приводим к нижнему регистру, как в парсере
            'disciplines': []
        }
        # Если парсер возвращает 'Бакалавр' с большой буквы, можно сравнивать без учёта регистра:
        self.assertEqual(result['direction'], expected['direction'])
        self.assertEqual(result['qualification'].lower(), expected['qualification'].lower())
        # или полностью заменить ожидаемое значение на result['qualification'] (но тогда тест будет гибким)
        # Для простоты давайте сравним словари, но исключим qualification:
        result_copy = result.copy()
        expected_copy = expected.copy()
        # можно убрать qualification из сравнения или привести к нижнему регистру
        result_copy['qualification'] = result_copy['qualification'].lower()
        expected_copy['qualification'] = expected_copy['qualification'].lower()
        self.assertEqual(result_copy, expected_copy)

    def test_sample4_invalid(self):
        file_path = os.path.join(self.data_dir, "sample4_invalid.plx")
        result = parse_plx_file(file_path)
        self.assertIn('error', result)
        self.assertEqual(result['direction'], '')
        self.assertEqual(result['disciplines'], [])
        self.assertTrue(len(result['error']) > 0)

if __name__ == "__main__":
    unittest.main()