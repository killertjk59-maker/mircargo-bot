import datetime
import sqlite3
from unittest.mock import patch

import config
import database as db
from tests.support import DatabaseTestCase


class AccountingTests(DatabaseTestCase):
    def test_new_database_is_empty(self):
        self.assertEqual(db.account_summary()['outstanding'], 0)
        self.assertTrue(all(value == 0 for value in db.get_statistics().values()))

    def test_customer_phone_is_unique_after_normalization(self):
        customer_id = self.add_customer()
        with self.assertRaisesRegex(ValueError, f'#{customer_id}'):
            self.add_customer('Another name', '+992 (90) 123-45-67')
        self.assertEqual(db.customer_count(), 1)

    def test_invalid_customer_names(self):
        for name in ['', ' ', 'a' * 101, 'a\nb']:
            with self.subTest(name=name), self.assertRaises(ValueError):
                db.create_customer(name, '901234567')

    def test_balance_partial_and_full_payment(self):
        cid = self.add_customer()
        self.post(cid, 'charge', 10010)
        self.post(cid, 'payment', 4005)
        self.assertEqual(db.customer_account(cid)['balance'], 6005)
        self.assertEqual(db.account_summary()['outstanding'], 6005)
        self.post(cid, 'payment', 6005)
        self.assertEqual(db.customer_accounts(debtors_only=True), [])
        self.assertEqual(db.account_summary()['debtors_count'], 0)

    def test_advance_does_not_reduce_another_customers_debt(self):
        c1 = self.add_customer()
        c2 = self.add_customer('Second', '902234567')
        self.post(c1, 'charge', 10000)
        self.post(c1, 'payment', 15000)
        self.post(c2, 'charge', 7000)
        summary = db.account_summary()
        self.assertEqual(summary['outstanding'], 7000)
        self.assertEqual(summary['credit'], 5000)
        self.assertEqual(summary['total_charges'], 17000)
        self.assertEqual(summary['total_payments'], 15000)
        self.assertEqual(summary['debtors_count'], 1)

    def test_operation_keys_are_idempotent(self):
        cid = self.add_customer()
        self.assertTrue(self.post(cid, 'charge', 12550, 'operation1'))
        self.assertFalse(self.post(cid, 'charge', 12550, 'operation1'))
        self.assertEqual(len(db.customer_entries(cid)), 1)
        self.assertEqual(db.customer_account(cid)['balance'], 12550)

    def test_invalid_ledger_entries(self):
        cid = self.add_customer()
        for entry_type, amount in [('wrong', 1), ('charge', -1), ('payment', 0),
                                   ('charge', 1.5), ('charge', True), ('charge', 100000000000)]:
            with self.subTest(entry_type=entry_type, amount=amount), self.assertRaises(ValueError):
                self.post(cid, entry_type, amount)
        with self.assertRaises(ValueError):
            self.post(999999, 'charge', 100)
        with self.assertRaises(ValueError):
            db.record_account_entry(cid, 'charge', 100, 'a' * 501, 9001)
        self.assertEqual(len(db.customer_entries(cid)), 0)

    def test_ledger_history_has_author_and_note(self):
        cid = self.add_customer()
        db.record_account_entry(cid, 'charge', 100, 'Қарзи аввалия', 9001)
        entry = db.customer_entries(cid)[0]
        self.assertEqual(entry['created_by'], 9001)
        self.assertEqual(entry['note'], 'Қарзи аввалия')
        self.assertTrue(entry['created_at'])

    def test_customer_pagination_and_full_debtors(self):
        for i in range(23):
            cid = self.add_customer(f'Name {i}', f'+99290{i:07d}')
            self.post(cid, 'charge', i + 1)
        self.assertEqual(len(db.customer_accounts(limit=8)), 8)
        self.assertEqual(len(db.customer_accounts(limit=8, offset=16)), 7)
        all_debtors = db.customer_accounts(limit=None, debtors_only=True)
        self.assertEqual(len(all_debtors), 23)
        self.assertEqual(all_debtors[0]['balance'], 23)

    def test_data_persists_after_reopening_database(self):
        cid = self.add_customer()
        self.post(cid, 'charge', 10010)
        self.add_track()
        db.set_track_lifecycle('TEST1', 'arrived')
        db.collect_track('TEST1', cid)
        db._conn.close()
        db._conn = None
        db.init_db()
        self.assertEqual(db.customer_account(cid)['balance'], 10010)
        self.assertEqual(db.get_statistics()['collectors'], 1)
        self.assertEqual(db.get_statistics()['collected'], 1)


class CargoTests(DatabaseTestCase):
    def test_arrival_is_counted_once(self):
        self.add_track()
        self.assertTrue(db.set_track_lifecycle('TEST1', 'arrived'))
        timestamp = db.get_track('TEST1')['arrived_at']
        self.assertFalse(db.set_track_lifecycle('TEST1', 'arrived'))
        self.assertEqual(db.get_track('TEST1')['arrived_at'], timestamp)
        self.assertEqual(db.get_statistics()['arrived_total'], 1)
        self.assertEqual(db.get_statistics()['awaiting_collection'], 1)

    def test_collection_requires_arrival_and_known_recipient(self):
        cid = self.add_customer()
        self.add_track()
        with self.assertRaises(ValueError):
            db.collect_track('TEST1', cid)
        db.set_track_lifecycle('TEST1', 'arrived')
        with self.assertRaises(ValueError):
            db.collect_track('TEST1', 999999)
        self.assertEqual(db.get_statistics()['collected'], 0)

    def test_collection_counts_unique_recipients_not_track_views(self):
        c1 = self.add_customer()
        c2 = self.add_customer('Second', '902234567')
        for code, cid in [('TEST1', c1), ('TEST2', c1), ('TEST3', c2)]:
            self.add_track(code)
            db.set_track_lifecycle(code, 'arrived')
            db.log_view(111, code)
            db.log_view(222, code)
            self.assertTrue(db.collect_track(code, cid))
            self.assertFalse(db.collect_track(code, cid))
        stats = db.get_statistics()
        self.assertEqual(stats['arrived_total'], 3)
        self.assertEqual(stats['collected'], 3)
        self.assertEqual(stats['collectors'], 2)
        self.assertEqual(stats['awaiting_collection'], 0)
        self.assertEqual(stats['search_users'], 2)
        self.assertEqual(stats['searches'], 6)

    def test_receiving_parcel_does_not_clear_debt(self):
        cid = self.add_customer()
        self.post(cid, 'charge', 10000)
        self.add_track()
        db.set_track_lifecycle('TEST1', 'arrived')
        db.collect_track('TEST1', cid)
        self.assertEqual(db.customer_account(cid)['balance'], 10000)

    def test_duplicate_import_preserves_status_recipient_and_dates(self):
        cid = self.add_customer()
        self.add_track()
        db.set_track_lifecycle('TEST1', 'arrived')
        db.collect_track('TEST1', cid)
        before = dict(db.get_track('TEST1'))
        db.add_track('test1', 'Changed name', 'Душанбе', '15 рӯз', 'warehouse')
        after = db.get_track('TEST1')
        for field in ['cargo_status', 'customer_id', 'arrived_at', 'collected_at', 'received_date', 'auto_status', 'customer_name']:
            self.assertEqual(after[field], before[field], field)
        self.assertEqual(after['arrival_city'], 'Душанбе')
        self.assertEqual(db.get_statistics()['tracks_total'], 1)

    def test_archiving_retains_stats_and_restoring_does_not_duplicate(self):
        cid = self.add_customer()
        self.add_track()
        db.set_track_lifecycle('TEST1', 'arrived')
        db.collect_track('TEST1', cid)
        db.log_view(111, 'TEST1')
        self.assertTrue(db.delete_track('TEST1'))
        self.assertFalse(db.delete_track('TEST1'))
        self.assertIsNone(db.get_track('TEST1'))
        self.assertEqual(db.user_tracks(111), [])
        self.assertEqual(db.all_tracks(), [])
        stats = db.get_statistics()
        self.assertEqual(stats['archived_tracks'], 1)
        self.assertEqual(stats['collected'], 1)
        self.assertEqual(stats['collectors'], 1)
        self.assertEqual(stats['arrived_total'], 1)
        self.add_track()
        self.assertEqual(db.get_statistics()['tracks_total'], 1)
        self.assertEqual(db.get_statistics()['active_tracks'], 1)
        self.assertEqual(db.get_track('TEST1')['cargo_status'], 'collected')

    def test_collected_status_cannot_bypass_recipient_confirmation(self):
        self.add_track()
        with self.assertRaises(ValueError):
            db.update_track_status('TEST1', 'Ба муштарӣ дода шуд ✅')
        with self.assertRaises(ValueError):
            db.set_track_lifecycle('TEST1', 'collected')
        self.assertEqual(db.get_statistics()['collected'], 0)

    def test_collected_track_cannot_be_reset(self):
        cid = self.add_customer()
        self.add_track()
        db.set_track_lifecycle('TEST1', 'arrived')
        db.collect_track('TEST1', cid)
        for status in ['warehouse', 'on_way', 'arrived']:
            with self.subTest(status=status), self.assertRaises(ValueError):
                db.set_track_lifecycle('TEST1', status)
        with self.assertRaises(ValueError):
            db.update_track_status('TEST1', 'Unusual status')

    def test_automatic_on_way_status_is_included_in_statistics(self):
        self.add_track('NEW')
        self.add_track('OLD')
        old_date = (datetime.datetime.utcnow() - datetime.timedelta(days=15)).isoformat()
        with db.get_conn() as conn:
            conn.execute('UPDATE tracks SET received_date=? WHERE track_code=?', (old_date, 'OLD'))
        with patch.object(config, 'AUTO_STATUS_DAYS', 10):
            stats = db.get_statistics()
        self.assertEqual(stats['warehouse'], 1)
        self.assertEqual(stats['on_way'], 1)
        self.assertEqual(stats['arrived_total'], 0)

    def test_manual_status_updates_disable_auto_and_record_arrival(self):
        self.add_track()
        db.update_track_field('TEST1', 'status', 'Расид')
        self.assertEqual(db.get_track('TEST1')['auto_status'], 0)
        self.assertEqual(db.get_statistics()['arrived_total'], 1)
        db.update_track_status('TEST1', 'Needs inspection')
        self.assertEqual(db.get_statistics()['other_status'], 1)
        self.assertEqual(db.get_statistics()['arrived_total'], 1)

    def test_delivery_counts_are_separate_from_parcels_and_accounts(self):
        cid = self.add_customer()
        self.post(cid, 'charge', 15000)
        for status in ['waiting_payment', 'pending_review', 'confirmed', 'rejected']:
            did = db.create_delivery(111, 'TEST', 'Address', 'Name', 'Phone')
            db.set_delivery_status(did, status)
        stats = db.get_statistics()
        self.assertEqual(stats['deliveries_total'], 4)
        self.assertEqual(stats['deliveries_confirmed'], 1)
        self.assertEqual(stats['collected'], 0)
        self.assertEqual(stats['total_payments'], 0)

    def test_conditional_delivery_status_updates(self):
        did = db.create_delivery(111, 'TEST', 'Address', 'Name', 'Phone')
        self.assertFalse(db.set_delivery_status(did, 'confirmed', 'pending_review'))
        self.assertTrue(db.set_delivery_status(did, 'pending_review', 'waiting_payment'))
        self.assertTrue(db.set_delivery_status(did, 'confirmed', 'pending_review'))
        self.assertFalse(db.set_delivery_status(did, 'rejected', 'pending_review'))
        self.assertEqual(db.get_delivery(did)['status'], 'confirmed')


class MigrationTests(DatabaseTestCase):
    def install_legacy_schema(self):
        db._conn.close()
        db._conn = None
        with sqlite3.connect(self.path) as conn:
            conn.executescript('''
                DROP TABLE tracks;
                CREATE TABLE tracks (
                    track_code TEXT PRIMARY KEY, customer_name TEXT, status TEXT,
                    auto_status INTEGER DEFAULT 1, received_date TEXT, estimated_days TEXT,
                    arrival_city TEXT, created_at TEXT
                );
            ''')
            for code, status, auto in [('AUTO', 'Дар анбори Чин', 1),
                                       ('ARRIVED', 'Бор расид 📦', 0),
                                       ('COLLECTED', 'Выдан получателю', 0),
                                       ('CUSTOM', 'Needs inspection', 0)]:
                conn.execute('INSERT INTO tracks VALUES (?,?,?,?,?,?,?,?)',
                             (code, 'Original customer', status, auto, db.now(), '20', 'Хуҷанд', db.now()))
            conn.execute("UPDATE settings SET value=? WHERE key='warehouse_address_tj'", ('Custom address',))
            conn.execute("UPDATE settings SET value=? WHERE key='warehouse_address_ru'",
                         (db._warehouse_defaults('Mirsaid Cargo')['warehouse_address_ru'],))
            conn.execute("UPDATE settings SET value='29' WHERE key='price_per_kg'")
            conn.execute("INSERT INTO users (user_id, full_name, phone, registered) VALUES (111,'Original','901234567',1)")
            conn.execute("INSERT INTO deliveries (user_id, status) VALUES (111,'confirmed')")

    def test_legacy_database_migrates_without_losing_data(self):
        self.install_legacy_schema()
        db.init_db()
        self.assertEqual(db.get_track('ARRIVED')['cargo_status'], 'arrived')
        self.assertEqual(db.get_track('COLLECTED')['cargo_status'], 'collected')
        self.assertEqual(db.get_track('CUSTOM')['cargo_status'], 'custom')
        self.assertIsNone(db.get_track('COLLECTED')['customer_id'])
        self.assertIsNone(db.get_track('COLLECTED')['collected_at'])
        self.assertEqual(db.get_user(111)['full_name'], 'Original')
        self.assertEqual(db.get_setting('warehouse_address_tj'), 'Custom address')
        self.assertIn('Tezcargo', db.get_setting('warehouse_address_ru'))
        self.assertEqual(db.get_setting('price_per_kg'), '29')
        stats = db.get_statistics()
        self.assertEqual(stats['tracks_total'], 4)
        self.assertEqual(stats['arrived_total'], 2)
        self.assertEqual(stats['collectors'], 0)
        self.assertEqual(stats['unassigned_collected'], 1)
        self.assertEqual(stats['deliveries_confirmed'], 1)
        db.init_db()
        self.assertEqual(db.get_statistics(), stats)

    def test_ddl_migration_rolls_back_on_failure(self):
        self.install_legacy_schema()
        with patch.object(db, '_warehouse_defaults', side_effect=RuntimeError('test migration failure')):
            with self.assertRaises(RuntimeError):
                db.init_db()
        columns = {row['name'] for row in db.get_conn().execute('PRAGMA table_info(tracks)')}
        self.assertNotIn('cargo_status', columns)
        self.assertEqual(db.get_conn().execute('SELECT COUNT(*) FROM tracks').fetchone()[0], 4)
        db.init_db()
        self.assertIn('cargo_status', {row['name'] for row in db.get_conn().execute('PRAGMA table_info(tracks)')})
