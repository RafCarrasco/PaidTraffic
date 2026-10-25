import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from offerlab.pipeline import load_config, run, run_all, MetaSource, MetaAPIError, connect
from offerlab.sources import CatalogSource, AppleSource, ImportSource, SourceError, parse_catalog, CATALOG_COMMIT


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.c = load_config('config/catalog.json')
        self.c.update(database=self.temp.name + '/shared.db', report_dir=self.temp.name + '/catalog', catalog_ref=CATALOG_COMMIT)

    def test_catalog_parser_matches_accents_and_category_not_index(self):
        text = '### Índice\n* [Python](#python)\n### Programação\n* [Título](https://example.invalid/book) - Autor (PDF)\n'
        rows = list(parse_catalog(text, ['programacao']))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['category'], 'Programação')
        self.assertEqual(rows[0]['line_number'], 4)
        self.assertEqual(list(parse_catalog(text, ['receitas'])), [])

    def test_catalog_evidence_upsert_and_limits(self):
        raw = b'### Python\n* [Python Test](https://example.invalid/book) - Autor\n'
        self.c['max_requests'] = 1
        source = lambda: CatalogSource(self.c, lambda *a, **kw: io.BytesIO(raw))
        self.assertTrue(run(self.c, source()))
        self.assertTrue(run(self.c, source()))
        with connect(self.c['database']) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM ads').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT count(*) FROM observations').fetchone()[0], 2)
            details = json.loads(db.execute('SELECT details FROM runs ORDER BY id DESC').fetchone()[0])
            self.assertEqual((details['new'], details['updated']), (0, 1))
        row = json.loads((Path(self.c['report_dir']) / 'ranking.json').read_text())[0]
        self.assertFalse(row['fictitious'])
        self.assertEqual(row['record_kind'], 'licensed_catalog_entry')
        self.assertIsNone(row['price'])
        self.assertIsNone(row['market_country'])
        self.assertEqual(len(row['evidence']['source_sha256']), 64)
        self.assertIn('CC BY', row['evidence']['license'])

    def test_snapshot_credentials_are_removed_before_persistence(self):
        class TokenSource:
            requests = 1
            def ads(self):
                yield {'id': '1', 'ad_snapshot_url': 'https://www.facebook.com/ad?id=1&access_token=REMOTE_SECRET', 'nested': {'access_token': 'REMOTE_SECRET'}}, 'curso'
        self.assertTrue(run(self.c, TokenSource()))
        with sqlite3.connect(self.c['database']) as db:
            for table in ('ads', 'observations'):
                raw = db.execute(f'SELECT raw FROM {table}').fetchone()[0]
                self.assertNotIn('REMOTE_SECRET', raw)
                self.assertNotIn('access_token=', raw)
        report = (Path(self.c['report_dir']) / 'ranking.json').read_text()
        self.assertNotIn('REMOTE_SECRET', report)

    def test_latest_catalog_resolves_revision_and_checks_license(self):
        self.c.update(catalog_ref='latest', max_requests=4)
        license_bytes = Path('docs/licenses/free-programming-books-CC-BY-4.0.txt').read_bytes()
        responses = [license_bytes, b'### Python\n* [Python](https://example.invalid/book)\n', b'']
        def opener(*args, **kwargs):
            return io.BytesIO(responses.pop(0))
        with patch('offerlab.sources.resolve_catalog_revision', return_value=CATALOG_COMMIT):
            source = CatalogSource(self.c, opener)
            rows = list(source.ads())
        self.assertEqual(source.requests, 4)
        self.assertTrue(source.completed)
        self.assertEqual(rows[0][0]['evidence']['source_revision'], CATALOG_COMMIT)
        with patch('offerlab.sources.resolve_catalog_revision', return_value=CATALOG_COMMIT):
            with self.assertRaisesRegex(SourceError, 'Licença do catálogo mudou'):
                list(CatalogSource(self.c, lambda *a, **kw: io.BytesIO(b'changed license')).ads())

    def test_meta_precise_error_without_remote_secrets(self):
        payload = {'error': {'code': 10, 'error_subcode': 2332002, 'message': 'SECRET', 'type': 'SECRET'}}
        def opener(*args, **kwargs):
            raise HTTPError('https://example.invalid/SECRET', 400, 'SECRET', {}, io.BytesIO(json.dumps(payload).encode()))
        c = dict(self.c, mode='meta')
        with patch.dict(os.environ, META_ACCESS_TOKEN='SECRET'):
            self.assertFalse(run(c, MetaSource(c, opener)))
        summary = (Path(c['report_dir']) / 'latest-run.json').read_text()
        self.assertNotIn('SECRET', summary)
        details = json.loads(summary)['details']
        self.assertEqual(details['error_subcode'], 2332002)
        self.assertEqual(details['diagnosis'], 'ads_library_access_denied')
        self.assertEqual(MetaAPIError(400, {'error': {'code': 190}}).details['diagnosis'], 'token_invalid_or_expired')
        self.assertEqual(MetaAPIError(429, {}).details['diagnosis'], 'rate_limited')

    def test_apple_maps_price_and_storefront_without_faking_ad(self):
        body = dict(results=[dict(trackId=7, trackName='Curso Python', artistName='Autor', trackViewUrl='https://books.apple.com/pt/book/7', price=4.99, currency='EUR')])
        sleeps, requests = [], []
        def opener(request, **kwargs):
            requests.append(request.full_url)
            return io.BytesIO(json.dumps(body).encode())
        self.c.update(mode='apple', keywords=['python', 'curso'])
        source = AppleSource(self.c, opener, sleeps.append)
        records = list(source.ads())
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0][0]['id'], 'PT:7')
        self.assertEqual(records[0][0]['price'], 4.99)
        self.assertEqual(records[0][0]['record_kind'], 'marketplace_ebook')
        self.assertEqual(sleeps, [3])
        self.assertIn('country=PT', requests[0])
        self.assertNotIn('Authorization', requests[0])

    def test_import_requires_provenance_and_tracks_hash(self):
        path = Path(self.temp.name) / 'export.json'
        body = dict(authorized=True, source_url='https://example.invalid/authorized-export', authorization_basis='fixture test only', records=[dict(id='1', text='Ebook fictício', url='https://example.invalid/ebook')])
        self.c.update(mode='import', import_path=str(path))
        path.write_text(json.dumps(body))
        rows = list(ImportSource(self.c).ads())
        self.assertEqual(rows[0][0]['record_kind'], 'authorized_export')
        self.assertEqual(len(rows[0][0]['evidence']['export_sha256']), 64)
        del body['authorization_basis']
        path.write_text(json.dumps(body))
        with self.assertRaises(SourceError):
            list(ImportSource(self.c).ads())

    def test_auto_continues_after_meta_denial_without_demo_or_stale_ranking(self):
        cfg = load_config('config/auto.json')
        cfg['report_dir'] = self.temp.name + '/auto'
        for child in cfg['sources']:
            child['catalog_ref'] = CATALOG_COMMIT
            child['database'] = self.c['database']
            child['report_dir'] = self.temp.name + '/' + child['mode']
        class Denied:
            requests = 1
            def __init__(self, c): pass
            def ads(self):
                raise MetaAPIError(400, {'error': {'code': 10, 'error_subcode': 2332002}})
                yield
        def catalog(c):
            return CatalogSource(c, lambda *args, **kwargs: io.BytesIO(b'### Python\n* [Python](https://example.invalid/book)\n'))
        with patch('offerlab.pipeline.MetaSource', Denied), patch('offerlab.pipeline.CatalogSource', catalog):
            run_all(cfg)
        result = json.loads((Path(cfg['report_dir']) / 'latest-run.json').read_text())
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['sources'][0]['status'], 'failed')
        rows = json.loads((Path(cfg['report_dir']) / 'ranking.json').read_text())
        self.assertTrue(rows)
        self.assertTrue(all(r['source'] == 'catalog' and not r['fictitious'] for r in rows))
        self.assertTrue((Path(cfg['report_dir']) / 'ranking.csv').exists())

    def test_config_prevents_demo_fallback_and_shared_reports(self):
        path = Path(self.temp.name) / 'config.json'
        cfg = json.loads(Path('config/auto.json').read_text())
        cfg['sources'][1]['mode'] = 'demo'
        path.write_text(json.dumps(cfg))
        with self.assertRaises(ValueError): load_config(path)
        cfg['sources'][1]['mode'] = 'catalog'
        cfg['sources'][1]['report_dir'] = cfg['sources'][0]['report_dir']
        path.write_text(json.dumps(cfg))
        with self.assertRaises(ValueError): load_config(path)

    def test_additive_migration_preserves_old_rows(self):
        with sqlite3.connect(self.c['database']) as db:
            db.execute('CREATE TABLE runs (id INTEGER PRIMARY KEY, started_at TEXT, finished_at TEXT, mode TEXT, status TEXT, processed INTEGER DEFAULT 0, requests INTEGER DEFAULT 0, error TEXT, cost_status TEXT)')
            db.execute("INSERT INTO runs(mode,status) VALUES ('demo','success')")
        db = connect(self.c['database'])
        try:
            self.assertEqual(db.execute('SELECT mode,status,details FROM runs').fetchone(), ('demo', 'success', None))
        finally:
            db.close()


if __name__ == '__main__':
    unittest.main()
