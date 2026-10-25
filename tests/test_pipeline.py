import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from offerlab.pipeline import load_config, run, MetaSource, classify, DEFAULT_WEIGHTS


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.c = load_config('config/demo.json')
        self.c.update(database=self.temp.name + '/test.db', report_dir=self.temp.name + '/reports')

    def test_demo_repeat_upsert_evidence_and_reports(self):
        self.assertTrue(run(self.c))
        self.assertTrue(run(self.c))
        with sqlite3.connect(self.c['database']) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM ads').fetchone()[0], 3)
            self.assertEqual(db.execute('SELECT count(*) FROM observations').fetchone()[0], 6)
            self.assertEqual(db.execute("SELECT count(*) FROM runs WHERE status='success'").fetchone()[0], 2)
        ranking = json.loads((Path(self.c['report_dir']) / 'ranking.json').read_text())
        self.assertEqual([r['score'] for r in ranking], [80, 80, 40])
        self.assertTrue(all(r['fictitious'] for r in ranking))
        self.assertIn('FICTÍCIO', (Path(self.c['report_dir']) / 'ranking.csv').read_text())

    def test_missing_token_is_failure_not_demo(self):
        self.c['mode'] = 'meta'
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(run(self.c))
        with sqlite3.connect(self.c['database']) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM ads').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT status FROM runs').fetchone()[0], 'failed')

    def test_pagination_rebuilds_official_url_and_auth_header(self):
        calls = []
        pages = [dict(data=[dict(id='1')], paging=dict(next='https://evil.invalid/?access_token=SECRET', cursors=dict(after='cursor'))), dict(data=[dict(id='2')])]
        def opener(request, timeout):
            calls.append(request)
            return io.BytesIO(json.dumps(pages.pop(0)).encode())
        self.c['keywords'] = ['curso']
        with patch.dict(os.environ, META_ACCESS_TOKEN='SECRET'):
            source = MetaSource(self.c, opener)
            self.assertEqual([a['id'] for a, k in source.ads()], ['1', '2'])
        self.assertEqual(source.requests, 2)
        self.assertTrue(all(r.full_url.startswith('https://graph.facebook.com/') and 'SECRET' not in r.full_url for r in calls))
        self.assertIn('after=cursor', calls[1].full_url)
        self.assertEqual(calls[0].get_header('Authorization'), 'Bearer SECRET')

    def test_http_error_is_redacted(self):
        def opener(request, timeout):
            raise HTTPError('https://example.invalid/SECRET', 403, 'SECRET', {}, None)
        with patch.dict(os.environ, META_ACCESS_TOKEN='SECRET'):
            with self.assertRaisesRegex(RuntimeError, 'Meta HTTP 403') as ctx:
                list(MetaSource(self.c, opener).ads())
        self.assertNotIn('SECRET', str(ctx.exception))

    def test_global_limits(self):
        self.c['max_ads'] = 1
        self.assertTrue(run(self.c))
        with sqlite3.connect(self.c['database']) as db:
            self.assertEqual(db.execute('SELECT status,processed FROM runs').fetchone(), ('limited', 1))
        self.c['max_requests'] = 1
        def opener(request, timeout):
            return io.BytesIO(b'{"data": [], "paging":{"next":"ignored","cursors":{"after":"x"}}}')
        with patch.dict(os.environ, META_ACCESS_TOKEN='x'):
            source = MetaSource(self.c, opener)
            self.assertEqual(list(source.ads()), [])
            self.assertEqual(source.requests, 1)

    def test_changed_ad_is_updated_and_modes_are_isolated(self):
        class Source:
            requests = 0
            def ads(self):
                yield {'id': 'same', 'page_name': 'Original'}, 'curso'
        source = Source()
        self.assertTrue(run(self.c, source))
        source.ads = lambda: iter([({'id': 'same', 'page_name': 'Atualizado'}, 'curso')])
        self.assertTrue(run(self.c, source))
        with sqlite3.connect(self.c['database']) as db:
            raw = db.execute('SELECT raw FROM ads').fetchone()[0]
            self.assertEqual(json.loads(raw)['page_name'], 'Atualizado')
        self.c['mode'] = 'meta'
        self.assertTrue(run(self.c, source))
        rows = json.loads((Path(self.c['report_dir']) / 'ranking.json').read_text())
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]['fictitious'])

    def test_partial_failure_preserves_progress_and_returns_failure(self):
        class BrokenSource:
            requests = 1
            def ads(self):
                yield {'id': 'partial'}, 'curso'
                raise RuntimeError('Meta HTTP 429; verificar limites')
        self.assertFalse(run(self.c, BrokenSource()))
        with sqlite3.connect(self.c['database']) as db:
            self.assertEqual(db.execute('SELECT status,processed,requests FROM runs').fetchone(), ('failed', 1, 1))
            self.assertEqual(db.execute('SELECT count(*) FROM observations').fetchone()[0], 1)

    def test_scheduler_repeats_and_stops_on_interrupt(self):
        from offerlab.__main__ import main
        with patch('sys.argv', ['offerlab', '--schedule']), patch('offerlab.__main__.load_config', return_value=self.c), patch('offerlab.__main__.time.sleep', side_effect=[None, KeyboardInterrupt]) as sleep:
            self.assertEqual(main(), 130)
        self.assertEqual(sleep.call_count, 2)
        with sqlite3.connect(self.c['database']) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM runs').fetchone()[0], 2)
            self.assertEqual(db.execute('SELECT count(*) FROM ads').fetchone()[0], 3)

    def test_config_validation_and_conservative_scoring(self):
        path = Path(self.temp.name) / 'invalid.json'
        for key, value in [('weights', {'digital': 100}), ('countries', ['portugal']), ('max_ads', 0), ('interval_seconds', 1)]:
            with self.subTest(key=key):
                bad = dict(self.c, **{key: value})
                path.write_text(json.dumps(bad))
                with self.assertRaises(ValueError):
                    load_config(path)
        self.assertEqual(classify({}, DEFAULT_WEIGHTS)['score'], 0)
        self.assertEqual(classify({'ad_snapshot_url': 'https://example.invalid'}, DEFAULT_WEIGHTS)['score'], 0)


if __name__ == '__main__':
    unittest.main()
