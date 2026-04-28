import os
import unittest

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
            'qualification': 'бакалавр',
            'disciplines': []
        }
        self.assertEqual(result['direction'], expected['direction'])
        self.assertEqual(result['qualification'].lower(), expected['qualification'].lower())
        result_copy = result.copy()
        expected_copy = expected.copy()
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

    def test_real_plx_file1(self):
        file_path = os.path.join(self.data_dir, "Ucheb_plan_09.03.01_A_VMKSiS_Z_SOKR_MMF_EVM_2020.plx")
        result = parse_plx_file(file_path)

        self.assertEqual(result['direction'], 'Информатика и вычислительная техника')
        self.assertEqual(result['direction_code'], '09.03.01')
        self.assertEqual(result['faculty'].lower(), 'механико-металлургический')
        self.assertEqual(result['faculty_code'], '-1')
        self.assertEqual(result['department'], 'Электронно-вычислительные машины и системы')
        self.assertEqual(result['department_code'], '47')
        self.assertEqual(result['year_start'], '2020')
        self.assertIn(result['qualification'], ('бакалавр', '2'))

        self.assertGreater(len(result['disciplines']), 0)

        disc_by_code = {d['code']: d for d in result['disciplines']}
        expected = {
            'Б1.О.01': ('Архитектура вычислительных систем', '5'),
            'Б1.О.02': ('Базы данных', '5'),
            'Б1.В.01': ('Введение в направление', '2'),
            'Б1.В.02': ('Вычислительная математика', '3'),
        }
        for code, (name, credits) in expected.items():
            self.assertIn(code, disc_by_code)
            self.assertEqual(disc_by_code[code]['name'], name)
            self.assertEqual(disc_by_code[code]['credits'], credits)

if __name__ == "__main__":
    unittest.main()
