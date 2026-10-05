import csv
import datetime
import io
from unittest.mock import patch

import bot
import config
import database as db
import keyboards as kb
import reports
from texts import T, t
from tests.support import DatabaseTestCase


ADMIN = 9001
USER = 111


class BotTests(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        bot.USER_STATE.clear()
        bot.FORWARD_MAP.clear()
        self.admin_patch = patch.object(config, 'ADMIN_IDS', {ADMIN, 9002})
        self.admin_patch.start()
        self.calls = []

        def fake_api(method, params=None, files=None):
            self.calls.append((method, params, files))
            return {'ok': True, 'result': {'message_id': len(self.calls)}}

        self.api_patch = patch.object(bot, 'api', side_effect=fake_api)
        self.api_patch.start()

    def tearDown(self):
        self.api_patch.stop()
        self.admin_patch.stop()
        bot.USER_STATE.clear()
        super().tearDown()

    def message(self, text, user_id=ADMIN):
        bot.handle_message({'from': {'id': user_id, 'username': 'tester'},
                            'chat': {'id': user_id, 'type': 'private'}, 'text': text})

    def callback(self, data, user_id=ADMIN, chat_id=None):
        bot.handle_callback_query({'id': 'callback-test', 'from': {'id': user_id},
                                   'message': {'chat': {'id': chat_id if chat_id is not None else user_id,
                                                        'type': 'private'}}, 'data': data})

    def sent_texts(self):
        return [params['text'] for method, params, files in self.calls if method == 'sendMessage']

    def register(self, user_id=USER):
        db.upsert_user_basic(user_id, 'tester')
        db.register_user(user_id, 'Tester', '+992901234567')

    def prepare_entry(self, cid, entry_type, value):
        self.callback(f"adm_{'charge' if entry_type == 'charge' else 'payment'}_{cid}")
        self.message(value)
        return bot.get_state(ADMIN)['data']['token']

    def test_startup_requires_token_without_contacting_telegram(self):
        with patch.object(config, 'BOT_TOKEN', ''):
            with self.assertRaises(SystemExit):
                bot.main()
        self.assertEqual(self.calls, [])

    def test_failed_update_is_retried_before_offset_advances(self):
        with patch.object(config, 'BOT_TOKEN', 'test-placeholder'), \
                patch.object(bot, 'get_updates', side_effect=[[{'update_id': 5, 'message': {}}], KeyboardInterrupt]) as updates, \
                patch.object(bot, 'handle_message', side_effect=RuntimeError('temporary failure')), \
                patch.object(bot.time, 'sleep'), patch('builtins.print'):
            with self.assertRaises(KeyboardInterrupt):
                bot.main()
        self.assertEqual([call.args[0] for call in updates.call_args_list], [0, 0])

    def test_startup_requests_tezcargo_display_name(self):
        with patch.object(config, 'BOT_TOKEN', 'test-placeholder'), \
                patch.object(bot, 'get_updates', side_effect=KeyboardInterrupt), \
                patch('builtins.print'):
            with self.assertRaises(KeyboardInterrupt):
                bot.main()
        name_calls = [params for method, params, _ in self.calls if method == 'setMyName']
        self.assertEqual(name_calls, [{'name': 'Tezcargo'}])

    def test_existing_registration_flow_still_works(self):
        self.message('/start', USER)
        self.assertEqual(bot.get_state(USER)['action'], 'reg_wait_contact')
        bot.handle_message({'from': {'id': USER}, 'chat': {'id': USER, 'type': 'private'},
                            'contact': {'user_id': USER, 'phone_number': '+992901234567'}})
        self.message('Али Раҳимов', USER)
        self.assertEqual(db.get_user(USER)['registered'], 1)
        self.assertEqual(db.get_user(USER)['full_name'], 'Али Раҳимов')
        self.assertIsNone(bot.get_state(USER))
        buttons = [text for row in self.calls[-1][1]['reply_markup']['keyboard'] for text in row]
        self.assertIn(t('btn_instagram', 'tj'), buttons)

    def test_main_menu_buttons_preempt_active_search_and_contact_states(self):
        self.register()
        bot.set_state(USER, 'search_track')
        before = len(self.calls)
        self.message(t('btn_my_tracks', 'tj'), USER)
        new_texts = self.sent_texts()[before:]
        self.assertIn(t('my_tracks_empty', 'tj'), new_texts)
        self.assertNotIn(t('track_not_found', 'tj', admin=bot.admin_contact('tj')), new_texts)
        self.assertIsNone(bot.get_state(USER))
        self.assertEqual(db.get_statistics()['searches'], 0)

        bot.set_state(USER, 'contact_admin_msg')
        self.message(t('btn_search_track', 'tj'), USER)
        self.assertEqual(bot.get_state(USER)['action'], 'search_track')
        self.assertIn(t('ask_track_code', 'tj'), self.sent_texts())
        self.assertFalse(any('Паём аз ' in value for value in self.sent_texts()))
        self.assertFalse(any(params.get('chat_id') in config.ADMIN_IDS and method == 'sendMessage'
                             for method, params, _ in self.calls))

    def test_registration_rejects_another_users_contact_and_bad_name(self):
        self.message('/start', USER)
        bot.handle_message({'from': {'id': USER}, 'chat': {'id': USER, 'type': 'private'},
                            'contact': {'user_id': USER + 1, 'phone_number': '+992901234567'}})
        self.assertEqual(bot.get_state(USER)['action'], 'reg_wait_contact')
        self.assertEqual(db.get_user(USER)['registered'], 0)

        bot.handle_message({'from': {'id': USER}, 'chat': {'id': USER, 'type': 'private'},
                            'contact': {'user_id': USER, 'phone_number': '+992901234567'}})
        self.message('77', USER)
        self.assertEqual(bot.get_state(USER)['action'], 'reg_wait_name')
        self.assertEqual(db.get_user(USER)['registered'], 0)
        self.message('Али Раҳимов', USER)
        self.assertEqual(db.get_user(USER)['registered'], 1)

    def test_branding_and_instagram_button_in_all_languages(self):
        for lang in ('tj', 'ru', 'en'):
            self.assertIn('Tezcargo', t('ask_contact', lang))
            self.assertIn('Tezcargo', t('main_menu', lang))
            buttons = [text for row in kb.main_menu_reply(lang)['keyboard'] for text in row]
            self.assertIn(t('btn_instagram', lang), buttons)
            for key in ['btn_instagram', 'instagram_intro', 'instagram_unavailable',
                        'btn_open_instagram', 'status_arrived', 'status_collected']:
                self.assertIn(lang, T[key])

    def test_instagram_is_unconfigured_until_admin_sets_it(self):
        self.register()
        self.message(t('btn_instagram', 'tj'), USER)
        self.assertIn(t('instagram_unavailable', 'tj'), self.sent_texts())
        self.callback('adm_edit_instagram')
        self.message('@tezcargo_test')
        self.assertEqual(db.get_setting('instagram_url'), 'https://www.instagram.com/tezcargo_test/')
        self.message(t('btn_instagram', 'tj'), USER)
        message = self.calls[-1][1]
        self.assertEqual(message['reply_markup']['inline_keyboard'][0][0]['url'],
                         'https://www.instagram.com/tezcargo_test/')

    def test_invalid_instagram_does_not_overwrite_saved_link(self):
        db.set_setting('instagram_url', 'https://instagram.com/original/')
        self.callback('adm_edit_instagram')
        self.message('https://example.com/')
        self.assertEqual(db.get_setting('instagram_url'), 'https://instagram.com/original/')
        self.assertEqual(bot.get_state(ADMIN)['action'], 'adm_instagram_input')
        self.message('/cancel')
        self.assertIsNone(bot.get_state(ADMIN))

    def test_instagram_environment_fallback_and_explicit_clear(self):
        with patch.object(config, 'INSTAGRAM_URL', 'https://instagram.com/from_env/'):
            bot.show_instagram(USER, 'en')
            self.assertEqual(self.calls[-1][1]['reply_markup']['inline_keyboard'][0][0]['url'],
                             'https://instagram.com/from_env/')
            self.callback('adm_edit_instagram')
            self.message('/clear')
            bot.show_instagram(USER, 'en')
            self.assertEqual(self.sent_texts()[-1], t('instagram_unavailable', 'en'))

    def test_unregistered_admin_can_complete_customer_creation(self):
        self.message('/admin')
        self.callback('adm_new_customer')
        self.message('Али Раҳимов | 901234567')
        self.assertEqual(db.customer_count(), 1)
        self.assertEqual(db.customer_accounts()[0]['phone'], '+992901234567')
        self.assertIsNone(bot.get_state(ADMIN))
        self.assertEqual(db.get_user(ADMIN)['registered'], 0)

    def test_bad_customer_input_can_be_corrected(self):
        self.callback('adm_new_customer')
        self.message('Only name')
        self.assertEqual(db.customer_count(), 0)
        self.message('Али | 901234567')
        self.assertEqual(db.customer_count(), 1)

    def test_ledger_preview_confirmation_partial_payment_and_debtor_list(self):
        cid = self.add_customer()
        token = self.prepare_entry(cid, 'charge', '100.10 | Қарзи аввалия')
        self.assertEqual(db.customer_account(cid)['balance'], 0)
        self.callback(f'adm_ledger_confirm_{token}')
        self.callback(f'adm_ledger_confirm_{token}')
        self.assertEqual(db.customer_account(cid)['balance'], 10010)
        self.assertEqual(len(db.customer_entries(cid)), 1)
        token = self.prepare_entry(cid, 'payment', '40,05 | Пардохт бо нақд')
        self.callback(f'adm_ledger_confirm_{token}')
        self.assertEqual(db.customer_account(cid)['balance'], 6005)
        self.callback('adm_debtors')
        text = self.sent_texts()[-1]
        self.assertIn('+992901234567', text)
        self.assertIn('60.05', text)

    def test_ledger_cancel_and_stale_confirmation_do_not_post(self):
        cid = self.add_customer()
        old_token = self.prepare_entry(cid, 'charge', '25')
        self.callback(f'adm_ledger_cancel_{old_token}')
        self.assertEqual(db.customer_account(cid)['balance'], 0)
        new_token = self.prepare_entry(cid, 'charge', '70')
        self.callback(f'adm_ledger_confirm_{old_token}')
        self.callback(f'adm_ledger_cancel_{old_token}')
        self.assertEqual(bot.get_state(ADMIN)['data']['token'], new_token)
        self.assertEqual(db.customer_account(cid)['balance'], 0)
        self.callback(f'adm_ledger_confirm_{new_token}')
        self.assertEqual(db.customer_account(cid)['balance'], 7000)

    def test_invalid_ledger_input_does_not_advance(self):
        cid = self.add_customer()
        self.callback(f'adm_charge_{cid}')
        for value in ['NaN', '-15', '12.555', '15 | ' + 'a' * 501]:
            self.message(value)
            self.assertEqual(bot.get_state(ADMIN)['action'], 'adm_ledger_input')
        self.assertEqual(db.customer_account(cid)['balance'], 0)

    def test_admin_commands_and_cancel_are_available(self):
        cid = self.add_customer()
        token = self.prepare_entry(cid, 'charge', '25')
        self.message('/cancel')
        self.callback(f'adm_ledger_confirm_{token}')
        self.assertEqual(db.customer_account(cid)['balance'], 0)
        self.message('/stats')
        self.assertIn('Tezcargo — омори умумӣ', self.sent_texts()[-1])
        self.message('/customers')
        self.assertIn('Али', self.sent_texts()[-1])
        self.message('/debtors')
        self.assertIn('Ҳоло қарздор нест', self.sent_texts()[-1])

    def test_arrival_bulk_deduplicates_and_reports_missing_tracks(self):
        self.add_track('TEST1')
        self.add_track('TEST2')
        self.callback('adm_arrivals')
        self.message('test1\nTEST1\nTEST2\nMISSING')
        self.assertEqual(db.get_statistics()['arrived_total'], 2)
        self.assertIn('MISSING', self.sent_texts()[-1])
        self.callback('adm_arrivals')
        self.message('TEST1\nTEST2')
        self.assertEqual(db.get_statistics()['arrived_total'], 2)

    def test_collection_flow_requires_confirmation_and_is_idempotent(self):
        cid = self.add_customer()
        self.add_track()
        db.set_track_lifecycle('TEST1', 'arrived')
        self.callback('adm_collect')
        self.message('TEST1')
        token = bot.get_state(ADMIN)['data']['token']
        self.callback(f'adm_recipient_{cid}_{token}')
        self.assertEqual(db.get_statistics()['collected'], 0)
        self.callback(f'adm_collect_confirm_{token}')
        self.callback(f'adm_collect_confirm_{token}')
        self.assertEqual(db.get_statistics()['collected'], 1)
        self.assertEqual(db.get_statistics()['collectors'], 1)
        self.assertEqual(db.get_track('TEST1')['customer_id'], cid)

    def test_collection_can_create_customer_inline(self):
        self.add_track()
        db.set_track_lifecycle('TEST1', 'arrived')
        self.callback('adm_collect')
        self.message('TEST1')
        token = bot.get_state(ADMIN)['data']['token']
        self.callback(f'adm_collect_new_{token}')
        self.message('Муштарии нав | 901234567')
        self.assertEqual(bot.get_state(ADMIN)['action'], 'adm_collect_confirm')
        self.assertEqual(db.get_statistics()['collected'], 0)
        self.callback(f'adm_collect_confirm_{token}')
        self.assertEqual(db.get_statistics()['collectors'], 1)

    def test_collection_refuses_not_arrived_and_stale_recipients(self):
        cid = self.add_customer()
        self.add_track('TEST1')
        self.add_track('TEST2')
        self.callback('adm_collect')
        self.message('TEST1')
        self.assertEqual(bot.get_state(ADMIN)['action'], 'adm_collect_input')
        db.set_track_lifecycle('TEST1', 'arrived')
        db.set_track_lifecycle('TEST2', 'arrived')
        self.message('TEST1')
        old_token = bot.get_state(ADMIN)['data']['token']
        self.callback('adm_collect')
        self.message('TEST2')
        new_token = bot.get_state(ADMIN)['data']['token']
        self.callback(f'adm_recipient_{cid}_{old_token}')
        self.assertEqual(bot.get_state(ADMIN)['data']['token'], new_token)
        self.assertEqual(db.get_statistics()['collected'], 0)

    def test_two_admins_cannot_count_one_handover_twice(self):
        cid = self.add_customer()
        self.add_track()
        db.set_track_lifecycle('TEST1', 'arrived')
        tokens = {}
        for aid in [ADMIN, 9002]:
            self.callback('adm_collect', aid)
            self.message('TEST1', aid)
            token = bot.get_state(aid)['data']['token']
            self.callback(f'adm_recipient_{cid}_{token}', aid)
            tokens[aid] = token
        for aid, token in tokens.items():
            self.callback(f'adm_collect_confirm_{token}', aid)
        self.assertEqual(db.get_statistics()['collected'], 1)
        self.assertEqual(db.get_statistics()['collectors'], 1)

    def test_track_editor_uses_safe_callbacks_and_localized_status(self):
        code = 'A' * 40
        self.add_track(code)
        self.callback('adm_edit_track')
        self.message(code)
        self.callback('etf_status')
        token = bot.get_state(ADMIN)['data']['token']
        self.callback(f'ets_arrived_{token}')
        track = db.get_track(code)
        for lang in ['tj', 'ru', 'en']:
            self.assertEqual(bot.track_status_display(track, lang), t('status_arrived', lang))
        self.assertEqual(db.get_statistics()['arrived_total'], 1)

    def test_stale_status_keyboard_does_not_change_another_track(self):
        self.add_track('TEST1')
        self.add_track('TEST2')
        self.callback('adm_edit_track')
        self.message('TEST1')
        self.callback('etf_status')
        token = bot.get_state(ADMIN)['data']['token']
        self.callback('adm_edit_track')
        self.message('TEST2')
        self.callback('etf_status')
        self.callback(f'ets_arrived_{token}')
        self.assertEqual(db.get_statistics()['arrived_total'], 0)

    def test_non_admin_cannot_access_private_accounting_features(self):
        cid = self.add_customer('Private name')
        self.post(cid, 'charge', 10000)
        self.register()
        for data in ['adm_stats', 'adm_customers', 'adm_debtors', 'adm_export_debtors',
                     'adm_new_customer', 'adm_edit_instagram', f'adm_charge_{cid}',
                     f'adm_customer_{cid}', f'adm_history_{cid}', 'adm_collect', 'adm_arrivals']:
            self.callback(data, USER)
        self.assertEqual(self.sent_texts(), [])
        self.assertFalse(any(method == 'sendDocument' for method, _, _ in self.calls))
        self.assertIsNone(bot.get_state(USER))
        self.assertEqual(db.customer_account(cid)['balance'], 10000)

    def test_non_admin_commands_do_not_reveal_stats_or_debts(self):
        self.register()
        for command in ['/stats', '/debtors', '/customers', '/admin']:
            self.message(command, USER)
        self.assertEqual(self.sent_texts(), [])

    def test_admin_features_are_not_exposed_in_groups(self):
        bot.handle_message({'from': {'id': ADMIN}, 'chat': {'id': -100, 'type': 'group'}, 'text': '/stats'})
        self.callback('adm_debtors', ADMIN, chat_id=-100)
        self.assertEqual(self.sent_texts(), [])

    def test_debtor_csv_contains_all_pages_and_protects_spreadsheet_formulas(self):
        for i in range(19):
            cid = self.add_customer(f'=danger {i}' if i == 0 else f'Customer {i}', f'+99290{i:07d}')
            self.post(cid, 'charge', 100 + i)
        self.callback('adm_debtors_1')
        self.assertIn('Саҳифа 2/3', self.sent_texts()[-1])
        self.callback('adm_debtors_999')
        self.assertIn('Саҳифа 3/3', self.sent_texts()[-1])
        self.callback('adm_export_debtors')
        method, params, files = self.calls[-1]
        self.assertEqual(method, 'sendDocument')
        raw = files['document'][1]
        self.assertTrue(raw.startswith(b'\xef\xbb\xbf'))
        rows = list(csv.reader(io.StringIO(raw.decode('utf-8-sig'))))
        self.assertEqual(len(rows), 20)
        formula_row = next(row for row in rows[1:] if 'danger' in row[1])
        self.assertTrue(formula_row[1].startswith("'="))
        self.assertTrue(formula_row[2].startswith("'+"))

    def test_search_does_not_claim_ownership_or_receipt(self):
        self.register()
        self.add_track()
        self.message('TEST1', USER)
        stats = db.get_statistics()
        self.assertEqual(stats['searches'], 1)
        self.assertEqual(stats['customers_total'], 0)
        self.assertEqual(stats['collected'], 0)
        self.assertIsNone(db.get_track('TEST1')['customer_id'])

    def test_payment_callback_checks_ownership_and_cannot_reopen_confirmed_delivery(self):
        self.register()
        self.add_track('TEST1')
        did = db.create_delivery(USER, 'TEST1', '123 Main Street', 'Tester', '+992901234567')
        self.callback(f'paid_{did}', 222)
        self.assertEqual(db.get_delivery(did)['status'], 'waiting_payment')
        self.callback(f'paid_{did}', USER)
        self.callback(f'paid_{did}', USER)
        self.assertEqual(db.get_delivery(did)['status'], 'pending_review')
        self.callback(f'delok_{did}')
        self.callback(f'delno_{did}')
        self.callback(f'paid_{did}', USER)
        self.assertEqual(db.get_delivery(did)['status'], 'confirmed')
        self.assertEqual(db.get_statistics()['collected'], 0)
        self.assertEqual(db.get_statistics()['total_payments'], 0)

    def test_banned_users_are_blocked_from_messages_and_callbacks(self):
        self.register()
        db.set_banned(USER, True)
        self.message(t('btn_search_track', 'tj'), USER)
        self.assertIn(t('user_banned', 'tj'), self.sent_texts())
        self.assertIsNone(bot.get_state(USER))
        self.callback('lang_en', USER)
        self.assertEqual(db.get_language(USER), 'tj')

    def test_admin_ban_commands_enforce_and_remove_restrictions(self):
        self.register(USER)
        self.message(f'/ban {USER}')
        self.assertEqual(db.get_user(USER)['banned'], 1)
        self.message(f'/unban {USER}')
        self.assertEqual(db.get_user(USER)['banned'], 0)
        self.message(f'/ban {ADMIN}')
        self.assertEqual(db.get_user(ADMIN)['banned'], 0)

    def test_delivery_flow_rejects_invalid_fields_and_duplicate_requests(self):
        self.register()
        self.add_track('TRACK1')
        self.message(t('btn_delivery', 'tj'), USER)
        self.message('77', USER)
        self.assertEqual(bot.get_state(USER)['action'], 'delivery_track')
        self.assertEqual(db.get_statistics()['deliveries_total'], 0)

        self.message('TRACK1', USER)
        self.assertEqual(bot.get_state(USER)['action'], 'delivery_address')
        self.message('77', USER)
        self.assertEqual(bot.get_state(USER)['action'], 'delivery_address')
        self.message('123 Main Street', USER)
        self.assertEqual(bot.get_state(USER)['action'], 'delivery_name')
        self.message('77', USER)
        self.assertEqual(bot.get_state(USER)['action'], 'delivery_name')
        self.message('Test Name', USER)
        self.assertEqual(bot.get_state(USER)['action'], 'delivery_phone')
        self.message('77', USER)
        self.assertEqual(bot.get_state(USER)['action'], 'delivery_phone')
        self.message('+992901234567', USER)
        self.assertIsNone(bot.get_state(USER))
        self.assertEqual(db.get_statistics()['deliveries_total'], 1)
        delivery = db.get_delivery(1)
        self.assertEqual(delivery['track_code'], 'TRACK1')
        self.assertEqual(delivery['phone'], '+992901234567')

        self.message(t('btn_delivery', 'tj'), USER)
        self.message('TRACK1', USER)
        self.message('123 Main Street', USER)
        self.message('Test Name', USER)
        self.message('+992901234567', USER)
        self.assertEqual(db.get_statistics()['deliveries_total'], 1)
        self.assertIn(t('delivery_duplicate', 'tj'), self.sent_texts())

    def test_calculator_rejects_non_positive_and_non_finite_values(self):
        self.register()
        for value in ['0', '-1', 'NaN', 'Infinity', '1e309']:
            bot.set_state(USER, 'calc_kg')
            self.message(value, USER)
            self.assertEqual(bot.get_state(USER)['action'], 'calc_kg')
        self.assertEqual(db.get_statistics()['searches'], 0)

        db.set_setting('price_per_kg', 'NaN')
        bot.set_state(USER, 'calc_kg')
        self.message('2', USER)
        self.assertIsNone(bot.get_state(USER))
        self.assertIn(t('calc_unavailable', 'tj'), self.sent_texts())

    def test_price_editor_keeps_state_until_valid_positive_price(self):
        old_price = db.get_setting('price_per_kg')
        self.callback('adm_edit_price')
        for value in ['NaN', 'Infinity', '-5', '0', '25.555']:
            self.message(value)
            self.assertEqual(bot.get_state(ADMIN)['action'], 'adm_edit_price_input')
            self.assertEqual(db.get_setting('price_per_kg'), old_price)
        self.message('29.50')
        self.assertEqual(db.get_setting('price_per_kg'), '29.50')
        self.assertIsNone(bot.get_state(ADMIN))

    def test_persistent_state_and_admin_reply_mapping_survive_cache_reset(self):
        self.register()
        bot.set_state(USER, 'calc_kg', {'example': 'kept'})
        bot.USER_STATE.clear()
        self.assertEqual(bot.get_state(USER), {'action': 'calc_kg', 'data': {'example': 'kept'}})

        db.save_admin_reply_mapping(ADMIN, 7654, USER)
        bot.FORWARD_MAP.clear()
        bot.handle_message({'from': {'id': ADMIN}, 'chat': {'id': ADMIN, 'type': 'private'},
                            'reply_to_message': {'message_id': 7654}, 'text': 'Салом'})
        self.assertTrue(any(params.get('chat_id') == USER and 'Салом' in params.get('text', '')
                            for method, params, _ in self.calls if method == 'sendMessage'))

    def test_contact_admin_forwards_media_and_supports_admin_media_reply(self):
        self.register()
        bot.set_state(USER, 'contact_admin_msg')
        bot.handle_message({'from': {'id': USER}, 'chat': {'id': USER, 'type': 'private'},
                            'message_id': 50, 'photo': [{'file_id': 'photo-id'}]})
        copy_calls = [params for method, params, _ in self.calls if method == 'copyMessage']
        self.assertTrue(copy_calls)
        forwarded_id = next(message_id for (admin_id, message_id), value in bot.FORWARD_MAP.items()
                            if admin_id == ADMIN and value == USER)

        bot.handle_message({'from': {'id': ADMIN}, 'chat': {'id': ADMIN, 'type': 'private'},
                            'message_id': 60, 'reply_to_message': {'message_id': forwarded_id},
                            'photo': [{'file_id': 'reply-photo'}]})
        self.assertTrue(any(method == 'copyMessage' and params.get('chat_id') == USER
                            for method, params, _ in self.calls))

    def test_broadcast_reports_real_failures_and_retries_transient_errors(self):
        self.register(USER)
        second_user = 222
        self.register(second_user)
        attempts = {USER: 0, second_user: 0}
        sent_messages = []

        def fake_send(chat_id, text, reply_markup=None):
            sent_messages.append((chat_id, text))
            if chat_id in attempts:
                attempts[chat_id] += 1
                if chat_id == USER and attempts[chat_id] == 1:
                    return {'ok': False, 'retryable': True}
                if chat_id == second_user:
                    return {'ok': False, 'error_code': 403, 'description': 'blocked'}
            return {'ok': True, 'result': {'message_id': 900}}

        self.callback('adm_broadcast')
        with patch.object(bot, 'send_message', side_effect=fake_send), patch.object(bot.time, 'sleep'):
            self.message('Эълони санҷишӣ')
        self.assertEqual(attempts, {USER: 2, second_user: 1})
        summary = next(text for chat_id, text in reversed(sent_messages)
                       if chat_id == ADMIN and 'Натиҷа:' in text)
        self.assertIn('муваффақ 1/2', summary)
        self.assertIn('ноком 1', summary)
        self.assertIn(str(second_user), summary)

    def test_api_returns_structured_http_errors(self):
        class Response:
            ok = False
            status_code = 400

            @staticmethod
            def json():
                return {'ok': False, 'error_code': 400, 'description': 'Bad Request'}

        self.api_patch.stop()
        try:
            with patch('bot.requests.post', return_value=Response()):
                result = bot.api('sendMessage', {'chat_id': USER, 'text': 'test'})
        finally:
            self.api_patch.start()
        self.assertFalse(result['ok'])
        self.assertEqual(result['error_code'], 400)
        self.assertEqual(result['description'], 'Bad Request')

    def test_admin_cannot_confirm_legacy_delivery_with_invalid_details(self):
        self.register()
        with db.get_conn() as conn:
            cursor = conn.execute("""INSERT INTO deliveries
                (user_id, track_code, address, name, phone, status, created_at)
                VALUES (?, '77', '77', '77', '77', 'pending_review', ?)""", (USER, db.now()))
            delivery_id = cursor.lastrowid
        self.callback(f'delok_{delivery_id}')
        self.assertEqual(db.get_delivery(delivery_id)['status'], 'pending_review')
        alerts = [params['text'] for method, params, _ in self.calls
                  if method == 'answerCallbackQuery' and params.get('text')]
        self.assertIn('тасдиқ манъ аст', alerts[-1])

    def test_malformed_callbacks_are_safe(self):
        for data in ['paid_no', 'paid_99999', 'delok_no', 'adm_customer_no',
                     'adm_recipients_no', 'adm_ledger_confirm_old', 'adm_collect_confirm_old',
                     'etf_bad', 'ets_bad', 'lang_invalid']:
            self.callback(data)
        self.assertIsNone(bot.get_state(ADMIN))

    def test_duplicate_track_import_preserves_collection(self):
        cid = self.add_customer()
        self.add_track()
        db.set_track_lifecycle('TEST1', 'arrived')
        db.collect_track('TEST1', cid)
        self.callback('adm_add_track')
        self.message('TEST1\nTEST1')
        self.assertEqual(db.get_statistics()['collected'], 1)
        self.assertEqual(db.get_statistics()['tracks_total'], 1)
        self.assertEqual(db.get_track('TEST1')['auto_status'], 0)

    def test_automatic_status_is_localized(self):
        self.add_track()
        old = (datetime.datetime.utcnow() - datetime.timedelta(days=15)).isoformat()
        with db.get_conn() as conn:
            conn.execute('UPDATE tracks SET received_date=?', (old,))
        with patch.object(config, 'AUTO_STATUS_DAYS', 10):
            for lang in ['tj', 'ru', 'en']:
                self.assertEqual(bot.track_status_display(db.get_track('TEST1'), lang), t('status_on_way', lang))

    def test_telegram_callback_payloads_fit_64_bytes(self):
        cid = self.add_customer('a' * 100)
        accounts = db.customer_accounts()
        token = 'f' * 32
        keyboards = [kb.admin_panel_kb(), kb.admin_edit_track_field_kb('x' * 100),
                     kb.admin_track_status_kb(token), kb.ledger_confirm_kb(token),
                     kb.customer_account_kb(cid), kb.customer_list_kb(accounts, 1, 3),
                     kb.debtors_kb(accounts, 1, 3), kb.collection_customer_kb(accounts, 1, 3, token),
                     kb.collection_confirm_kb(token)]
        for keyboard in keyboards:
            for row in keyboard['inline_keyboard']:
                for button in row:
                    self.assertLessEqual(len(button['callback_data'].encode('utf-8')), 64)

    def test_long_messages_are_split_by_utf16_units(self):
        markup = kb.back_to_admin_kb()
        bot.send_long_message(ADMIN, '📦' * 5000, markup)
        messages = [params for method, params, _ in self.calls if method == 'sendMessage']
        self.assertEqual(''.join(message['text'] for message in messages), '📦' * 5000)
        self.assertGreater(len(messages), 1)
        for message in messages:
            self.assertLessEqual(len(message['text'].encode('utf-16-le')) // 2, 3500)
        self.assertEqual(messages[-1]['reply_markup'], markup)
        self.assertNotIn('reply_markup', messages[0])

    def test_report_has_legacy_warning_without_inventing_recipients(self):
        self.add_track()
        with db.get_conn() as conn:
            conn.execute("UPDATE tracks SET cargo_status='collected', auto_status=0")
        text = reports.statistics_text(db.get_statistics())
        self.assertIn('муштарии он маълум нест', text)
        self.assertEqual(db.get_statistics()['collectors'], 0)
