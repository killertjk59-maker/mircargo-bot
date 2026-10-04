import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import config
import database as db


class DatabaseTestCase(unittest.TestCase):
    def setUp(self):
        if db._conn is not None:
            db._conn.close()
        db._conn = None
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / 'test.db')
        self.db_path_patch = patch.object(config, 'DB_PATH', self.path)
        self.db_path_patch.start()
        self.instagram_patch = patch.object(config, 'INSTAGRAM_URL', '')
        self.instagram_patch.start()
        db.init_db()

    def tearDown(self):
        if db._conn is not None:
            db._conn.close()
        db._conn = None
        self.instagram_patch.stop()
        self.db_path_patch.stop()
        self.temp.cleanup()

    def add_track(self, code='TEST1'):
        db.add_track(code, 'Customer', 'Хуҷанд', '20 рӯз', 'Дар анбори Чин 🇨🇳 (Омода барои фиристодан)')
        return db.get_track(code)

    def add_customer(self, name='Али', phone='901234567'):
        return db.create_customer(name, phone)

    def post(self, customer_id, entry_type, amount, key=None):
        return db.record_account_entry(customer_id, entry_type, amount, '', 9001, key)
