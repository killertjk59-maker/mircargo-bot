import unittest

from domain import (format_money, lifecycle_from_status, normalize_instagram_url,
                    normalize_phone, normalize_track_code, parse_money)


class DomainTests(unittest.TestCase):
    def test_exact_money(self):
        for value, expected in [('0.01', 1), ('125,50', 12550), ('100', 10000),
                                (' 40.05 ', 4005), ('999999999.99', 99999999999)]:
            with self.subTest(value=value):
                self.assertEqual(parse_money(value), expected)
        self.assertEqual(parse_money('0.10') + parse_money('0.20'), 30)

    def test_invalid_money(self):
        for value in ['', '0', '-1', '+1', '1.001', 'NaN', 'Infinity', '1e3',
                      '1000000000', '1 000', '12.3.4', '💵', '.50']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_money(value)

    def test_money_formatting(self):
        self.assertEqual(format_money(12550), '125.50')
        self.assertEqual(format_money(1), '0.01')
        self.assertEqual(format_money(-1), '-0.01')
        self.assertEqual(format_money(0), '0.00')

    def test_normalize_phone_identity(self):
        for phone in ['901234567', '+992901234567', '992901234567',
                      '00992901234567', '+992 (90) 123-45-67']:
            with self.subTest(phone=phone):
                self.assertEqual(normalize_phone(phone), '+992901234567')
        self.assertEqual(normalize_phone('+7 999 123-45-67'), '+79991234567')

    def test_invalid_phones(self):
        for phone in ['', 'phone', '123', '+992+901234567', '1' * 16, '90/1234567']:
            with self.subTest(phone=phone), self.assertRaises(ValueError):
                normalize_phone(phone)

    def test_instagram_url_and_handle(self):
        self.assertEqual(normalize_instagram_url(' @tezcargo.test '),
                         'https://www.instagram.com/tezcargo.test/')
        self.assertEqual(normalize_instagram_url('https://INSTAGRAM.com/page/#bio'),
                         'https://instagram.com/page/')
        self.assertEqual(normalize_instagram_url('https://www.instagram.com/'),
                         'https://www.instagram.com/')

    def test_instagram_rejects_lookalikes_and_unsafe_urls(self):
        for url in ['', 'http://instagram.com/page/', 'https://instagram.com.evil.test/a',
                    'https://evil.test/?instagram.com', 'https://instagram.com@evil.test/',
                    'https://a:secret@instagram.com/', 'https://instagram.com:443/',
                    'https://instagram.com:bad/', 'https://instagram.com/a b',
                    'https://instagram.com/\\evil', '@invalid/name', '@a' + 'b' * 30,
                    'javascript:alert(1)']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                normalize_instagram_url(url)

    def test_track_codes(self):
        self.assertEqual(normalize_track_code(' abc_12-3/4.5 '), 'ABC_12-3/4.5')
        for value in ['', 'a' * 41, 'код123', 'ABC|Name', 'A B', '/ABC']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_track_code(value)

    def test_legacy_status_aliases(self):
        for value, expected in [('Дар анбори Чин 🇨🇳', 'warehouse'), ('Дар роҳ 🚚', 'on_way'),
                                ('Бор расид 📦', 'arrived'), ('ПРИБЫЛ', 'arrived'),
                                ('Выдано получателю', 'collected'), ('Выдан получателю', 'collected'),
                                ('collected', 'collected'), ('Ба муштарӣ дода шуд ✅', 'collected'),
                                ('✅ Выдано получателю', 'collected'), ('📦 Бор расид', 'arrived'),
                                ('At China warehouse 🇨🇳 (Ready to ship)', 'warehouse'),
                                ('An unusual status', 'custom')]:
            with self.subTest(value=value):
                self.assertEqual(lifecycle_from_status(value), expected)


if __name__ == '__main__':
    unittest.main()
