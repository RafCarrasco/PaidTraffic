import csv
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import sqlite3
from datetime import datetime, timezone
from urllib.parse import urlencode, urlparse, urlsplit, urlunsplit, parse_qsl
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from .sources import CatalogSource, AppleSource, ImportSource, SourceError, CATALOG_COMMIT, MAX_BYTES

LOG = logging.getLogger('offerlab')
FIELDS = 'id,page_id,page_name,ad_creation_time,ad_delivery_start_time,ad_delivery_stop_time,ad_creative_bodies,ad_creative_link_titles,ad_creative_link_captions,ad_snapshot_url'
DEFAULT_WEIGHTS = dict(digital=40, text=20, landing_url=20, delivery_dates=20)
SECRET_KEYS = {'access_token', 'authorization', 'api_key', 'client_secret', 'token'}


def redact_credentials(value):
    """Snapshot URLs can contain tokens even if request authentication used headers."""
    if isinstance(value, dict):
        return {k: '[REDACTED]' if k.lower() in SECRET_KEYS else redact_credentials(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_credentials(v) for v in value]
    if isinstance(value, str):
        if value.startswith(('https://', 'http://')):
            parts = urlsplit(value)
            query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() not in SECRET_KEYS]
            if len(query) != len(parse_qsl(parts.query, keep_blank_values=True)) or '@' in parts.netloc:
                value = urlunsplit((parts.scheme, parts.netloc.rsplit('@', 1)[-1], parts.path, urlencode(query), parts.fragment))
        for name in ('META_ACCESS_TOKEN', 'GH_TOKEN', 'GITHUB_TOKEN'):
            secret = os.getenv(name)
            if secret and len(secret) > 8:
                value = value.replace(secret, '[REDACTED]')
    return value


class MetaAPIError(SourceError):
    def __init__(self, http_status, payload):
        error = payload.get('error', {}) if isinstance(payload, dict) else {}
        error = error if isinstance(error, dict) else {}
        # Accept only numeric identifiers, never provider messages or request URLs.
        self.details = {'http_status': http_status}
        for key in ('code', 'error_subcode'):
            if type(error.get(key)) is int:
                self.details[key] = error[key]
        code, subcode = self.details.get('code'), self.details.get('error_subcode')
        if (code, subcode) == (10, 2332002):
            self.details['diagnosis'] = 'ads_library_access_denied'
        elif code == 190:
            self.details['diagnosis'] = 'token_invalid_or_expired'
        elif http_status == 429 or code in (4, 17, 32, 613):
            self.details['diagnosis'] = 'rate_limited'
        else:
            self.details['diagnosis'] = 'inspect_version_permissions_and_parameters'
        super().__init__(f'Meta HTTP {http_status}; code={code}; subcode={subcode}; {self.details["diagnosis"]}')


def now():
    return datetime.now(timezone.utc).isoformat()


def load_config(path):
    c = json.loads(Path(path).read_text())
    if c.get('mode') == 'auto':
        sources = c.get('sources')
        if not isinstance(sources, list) or not sources or not all(isinstance(s, dict) for s in sources):
            raise ValueError('auto exige sources não vazia')
        base = {k: v for k, v in c.items() if k not in ('mode', 'sources', 'report_dir')}
        c['sources'] = [validate_config(dict(base, **s)) for s in sources]
        if any(s['mode'] in ('auto', 'demo') for s in c['sources']):
            raise ValueError('auto não permite demo nem auto aninhado')
        modes = [s['mode'] for s in c['sources']]
        if len(set(modes)) != len(modes):
            raise ValueError('Uma configuração por modo em auto')
        c.setdefault('interval_seconds', 86400)
        if type(c['interval_seconds']) is not int or not 60 <= c['interval_seconds'] <= 31536000:
            raise ValueError('interval_seconds inválido')
        c.setdefault('report_dir', 'reports/auto')
        folders = [str(Path(s['report_dir']).resolve()) for s in c['sources']] + [str(Path(c['report_dir']).resolve())]
        if len(set(folders)) != len(folders):
            raise ValueError('Cada fonte e resumo auto exigem report_dir distinto')
        return c
    return validate_config(c)


def validate_config(c):
    if c.get('mode') not in ('demo', 'meta', 'catalog', 'apple', 'import'):
        raise ValueError('mode inválido')
    for key in ('countries', 'keywords'):
        if not isinstance(c.get(key), list) or not c[key] or not all(isinstance(x, str) and x.strip() for x in c[key]):
            raise ValueError(f'{key}: lista não vazia de textos obrigatória')
    if not all(re.fullmatch('[A-Z]{2}', x) for x in c['countries']):
        raise ValueError('Países devem usar ISO de duas letras maiúsculas')
    for key, default, maximum in [('max_requests', 10, 1000), ('page_size', 25, 100), ('max_ads', 100, 100000), ('interval_seconds', 86400, 31536000)]:
        c.setdefault(key, default)
        if type(c[key]) is not int or not 1 <= c[key] <= maximum:
            raise ValueError(f'{key}: inteiro de 1 a {maximum}')
    if c['interval_seconds'] < 60:
        raise ValueError('interval_seconds deve ser >= 60')
    c.setdefault('api_version', 'v26.0')
    if not re.fullmatch(r'v\d+\.\d+', c['api_version']):
        raise ValueError('api_version inválida')
    c.setdefault('ad_active_status', 'ACTIVE')
    if c['ad_active_status'] not in ('ACTIVE', 'INACTIVE', 'ALL'):
        raise ValueError('ad_active_status inválido')
    c.setdefault('catalog_ref', CATALOG_COMMIT)
    if c['catalog_ref'] != 'latest' and not re.fullmatch(r'[0-9a-f]{40}', c['catalog_ref']):
        raise ValueError('catalog_ref deve ser latest ou SHA de commit imutável')
    c.setdefault('catalog_languages', ['pt_PT', 'pt_BR'])
    if not isinstance(c['catalog_languages'], list) or not c['catalog_languages'] or any(x not in ('pt_PT', 'pt_BR', 'en') for x in c['catalog_languages']):
        raise ValueError('catalog_languages inválido')
    if c['mode'] == 'import' and not isinstance(c.get('import_path'), str):
        raise ValueError('import_path obrigatório')
    w = c.setdefault('weights', DEFAULT_WEIGHTS.copy())
    if set(w) != set(DEFAULT_WEIGHTS) or any(type(v) not in (int, float) or not 0 <= v <= 100 for v in w.values()) or abs(sum(w.values()) - 100) > 1e-6:
        raise ValueError('weights devem conter os quatro critérios e somar 100')
    c.setdefault('database', f"data/{c['mode']}.sqlite3")
    c.setdefault('report_dir', f"reports/{c['mode']}")
    return c


class MetaSource:
    """Somente GET oficial; sem fallback para demonstração ou scraping."""
    def __init__(self, config, opener=urlopen):
        self.c, self.opener, self.requests = config, opener, 0
        self.token = os.getenv('META_ACCESS_TOKEN')
        if not self.token:
            raise ValueError('META_ACCESS_TOKEN ausente; configure acesso autorizado à Meta')

    def ads(self):
        self.completed = False
        for keyword in self.c['keywords']:
            after = None
            seen = set()
            while True:
                if self.requests >= self.c['max_requests']:
                    return
                params = dict(search_terms=keyword, ad_reached_countries=json.dumps(self.c['countries']), ad_type='ALL', ad_active_status=self.c.get('ad_active_status', 'ACTIVE'), fields=FIELDS, limit=self.c['page_size'])
                if after:
                    params['after'] = after
                url = f"https://graph.facebook.com/{self.c['api_version']}/ads_archive?{urlencode(params)}"
                self.requests += 1
                try:
                    with self.opener(Request(url, headers={'Authorization': f'Bearer {self.token}'}), timeout=30) as response:
                        raw = response.read(MAX_BYTES + 1)
                        if len(raw) > MAX_BYTES:
                            raise SourceError('Meta retornou resposta maior que 2 MB')
                        body = json.loads(raw)
                except HTTPError as e:
                    try:
                        payload = json.loads(e.read(65536))
                    except (ValueError, OSError):
                        payload = {}
                    raise MetaAPIError(e.code, payload) from None
                except (URLError, TimeoutError, OSError, ValueError):
                    raise RuntimeError('Falha de rede ou resposta inválida da Meta') from None
                if isinstance(body, dict) and 'error' in body:
                    raise MetaAPIError(200, body)
                if not isinstance(body, dict) or not isinstance(body.get('data'), list):
                    raise RuntimeError('Meta retornou erro ou formato inesperado')
                for ad in body['data']:
                    if not isinstance(ad, dict) or not ad.get('id'):
                        raise RuntimeError('Anúncio da Meta sem identificador válido')
                    yield ad, keyword
                paging = body.get('paging', {})
                after = paging.get('cursors', {}).get('after') if paging.get('next') else None
                # Never follow next URLs carrying tokens or untrusted destinations.
                if after in seen:
                    raise SourceError('Meta repetiu cursor de paginação; cobertura incompleta')
                if not after:
                    break
                seen.add(after)
        self.completed = True


class DemoSource:
    requests = 0

    def ads(self):
        for i, text in enumerate(['Curso fictício de fotografia', 'Ebook fictício de receitas', 'Serviço fictício de jardinagem']):
            yield dict(id=f'demo-{i}', page_id=f'demo-page-{i}', page_name=f'FICTÍCIO {i}', ad_creative_bodies=[text], ad_creation_time='2026-01-01', ad_delivery_start_time='2026-01-02', ad_snapshot_url=f'https://example.invalid/demo/{i}'), 'demo'


def classify(ad, weights):
    text = ' '.join(ad.get('ad_creative_bodies') or []).lower()
    digital = ad.get('record_kind') in ('licensed_catalog_entry', 'marketplace_ebook') or any(term in text for term in ('curso', 'ebook', 'e-book', 'mentoria', 'aula', 'download', 'course'))
    # Captions are unverified display text; snapshots are evidence URLs, not landing pages.
    captions = ad.get('ad_creative_link_captions') or []
    landing = any(urlparse(x).scheme in ('https', 'http') and urlparse(x).hostname for x in captions)
    signals = dict(digital=digital, text=bool(text.strip()), landing_url=bool(landing), delivery_dates=bool(ad.get('ad_delivery_start_time')))
    contributions = {k: weights[k] if v else 0 for k, v in signals.items()}
    return dict(score=round(sum(contributions.values()), 2), possible_digital=digital, classification_status='hipótese heurística', contributions=contributions, weights=dict(weights), limitations='Score de triagem e completude; não estima vendas, demanda comprovada, lucro ou margem. Datas não provam persistência contínua.')


def connect(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=30)
    db.execute('PRAGMA journal_mode=WAL')
    db.executescript('''
    CREATE TABLE IF NOT EXISTS ads (source TEXT, id TEXT, first_seen TEXT, last_seen TEXT, raw TEXT, analysis TEXT, PRIMARY KEY(source,id));
    CREATE TABLE IF NOT EXISTS observations (run_id INTEGER, source TEXT, ad_id TEXT, observed_at TEXT, keyword TEXT, countries TEXT, evidence_hash TEXT, raw TEXT);
    CREATE TABLE IF NOT EXISTS runs (id INTEGER PRIMARY KEY, started_at TEXT, finished_at TEXT, mode TEXT, status TEXT, processed INTEGER DEFAULT 0, requests INTEGER DEFAULT 0, error TEXT, cost_status TEXT);
    ''')
    # Additive migration preserves databases created by 0.1.
    existing = {row[1] for row in db.execute('PRAGMA table_info(runs)')}
    for name in ('details', 'config'):
        if name not in existing:
            db.execute(f'ALTER TABLE runs ADD COLUMN {name} TEXT')
    return db


def export(db, folder, source):
    rows = []
    for id_, first, last, raw, analysis in db.execute('SELECT id,first_seen,last_seen,raw,analysis FROM ads WHERE source=?', (source,)):
        ad, result = json.loads(raw), json.loads(analysis)
        rows.append(dict(id=id_, source=source, fictitious=source == 'demo', record_kind=ad.get('record_kind', 'demo_ad' if source == 'demo' else 'ad'), advertiser=ad.get('page_name', ''), text=' '.join(ad.get('ad_creative_bodies') or []), evidence_url=ad.get('evidence_url', ad.get('ad_snapshot_url', '')), landing_url=ad.get('landing_url'), language=ad.get('language'), market_country=ad.get('market_country'), price=ad.get('price'), currency=ad.get('currency'), evidence=ad.get('evidence'), source_limitations=ad.get('limitations'), first_seen=first, last_seen=last, **result))
    write_rankings(rows, folder)
    return rows


def write_rankings(rows, folder):
    target = Path(folder)
    target.mkdir(parents=True, exist_ok=True)
    rows.sort(key=lambda r: (-r['score'], r['source'], r['id']))
    # Atomic replacement prevents partial reports on interrupted writes.
    temp = target / 'ranking.json.tmp'
    temp.write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    temp.replace(target / 'ranking.json')
    columns = ['id', 'source', 'fictitious', 'record_kind', 'advertiser', 'text', 'score', 'possible_digital', 'evidence_url', 'landing_url', 'language', 'market_country', 'price', 'currency', 'source_limitations', 'last_seen']
    with (target / 'ranking.csv.tmp').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            safe = {k: ("'" + v if isinstance(v, str) and v.startswith(('=', '+', '-', '@', '\t', '\r')) else v) for k, v in row.items()}
            writer.writerow(safe)
    (target / 'ranking.csv.tmp').replace(target / 'ranking.csv')


def run(c, source=None):
    db = connect(c['database'])
    run_id = db.execute('INSERT INTO runs(started_at,mode,status,cost_status) VALUES (?,?,?,?)', (now(), c['mode'], 'running', 'Sem chamadas pagas de IA; custo externo não medido')).lastrowid
    db.commit()
    count, error, status = 0, None, 'success'
    details = {'new': 0, 'updated': 0, 'partial': False}
    public_config = {k: c[k] for k in ('mode', 'countries', 'keywords', 'max_ads', 'max_requests', 'weights', 'api_version', 'catalog_ref') if k in c}
    db.execute('UPDATE runs SET config=? WHERE id=?', (json.dumps(public_config), run_id))
    db.commit()
    try:
        if source is None:
            source = {'demo': DemoSource, 'meta': lambda: MetaSource(c), 'catalog': lambda: CatalogSource(c), 'apple': lambda: AppleSource(c), 'import': lambda: ImportSource(c)}[c['mode']]()
        for ad, keyword in source.ads():
            ad = redact_credentials(ad)
            timestamp = now()
            raw = json.dumps(ad, ensure_ascii=False, sort_keys=True)
            analysis = json.dumps(classify(ad, c['weights']), ensure_ascii=False)
            existed = db.execute('SELECT 1 FROM ads WHERE source=? AND id=?', (c['mode'], str(ad['id']))).fetchone()
            db.execute('INSERT INTO ads VALUES(?,?,?,?,?,?) ON CONFLICT(source,id) DO UPDATE SET last_seen=excluded.last_seen,raw=excluded.raw,analysis=excluded.analysis', (c['mode'], str(ad['id']), timestamp, timestamp, raw, analysis))
            db.execute('INSERT INTO observations VALUES(?,?,?,?,?,?,?,?)', (run_id, c['mode'], str(ad['id']), timestamp, keyword, json.dumps(c['countries']), hashlib.sha256(raw.encode()).hexdigest(), raw))
            count += 1
            db.commit()
            details['updated' if existed else 'new'] += 1
            if count == 1 or count % 10 == 0:
                LOG.info('run=%s processados=%s', run_id, count)
            if count >= c['max_ads']:
                status = 'limited'
                break
        if getattr(source, 'requests', 0) >= c['max_requests'] and not getattr(source, 'completed', False):
            status = 'limited'
        export(db, c['report_dir'], c['mode'])
    except Exception as e:
        db.rollback()
        status = 'failed'
        details['partial'] = count > 0
        if isinstance(e, MetaAPIError):
            details.update(e.details)
        # Only known safe errors are persisted; arbitrary SDK/HTTP errors can contain secrets.
        error = str(e) if isinstance(e, SourceError) or (type(e) in (ValueError, RuntimeError) and str(e).startswith(('Meta ', 'META_', 'Falha de rede', 'Anúncio da Meta'))) else type(e).__name__
        LOG.error('run=%s falhou: %s', run_id, error)
    finally:
        finished = now()
        db.execute('UPDATE runs SET finished_at=?,status=?,processed=?,requests=?,error=?,details=? WHERE id=?', (finished, status, count, getattr(source, 'requests', 0), error, json.dumps(details), run_id))
        db.commit()
        db.close()
        target = Path(c['report_dir'])
        target.mkdir(parents=True, exist_ok=True)
        summary = dict(run_id=run_id, mode=c['mode'], status=status, processed=count, requests=getattr(source, 'requests', 0), error=error, details=details, finished_at=finished, ranking_current=status != 'failed')
        (target / 'latest-run.json.tmp').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
        (target / 'latest-run.json.tmp').replace(target / 'latest-run.json')
    LOG.info('run=%s status=%s processados=%s', run_id, status, count)
    return status != 'failed'


def run_all(c):
    if c['mode'] != 'auto':
        return run(c)
    summaries, combined = [], []
    for child in c['sources']:
        try:
            run(child)
            summaries.append(json.loads((Path(child['report_dir']) / 'latest-run.json').read_text()))
            if summaries[-1]['ranking_current']:
                combined.extend(json.loads((Path(child['report_dir']) / 'ranking.json').read_text()))
        except (OSError, sqlite3.Error):
            LOG.error('Falha local na fonte %s; continuando demais fontes', child['mode'])
            summaries.append(dict(mode=child['mode'], status='failed', processed=0, error='local_storage_error'))
    successful = [s for s in summaries if s['status'] != 'failed']
    # Preserve failure visibility even when another source succeeds; never call it full success.
    status = 'success' if len(successful) == len(summaries) else ('partial' if successful else 'failed')
    result = dict(status=status, finished_at=now(), sources=summaries, fictitious=False)
    folder = Path(c['report_dir'])
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'latest-run.json.tmp').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    (folder / 'latest-run.json.tmp').replace(folder / 'latest-run.json')
    write_rankings(combined, folder)
    lines = ['# OfferLab — relatório automático', '', f'Estado: {status}. Registros no ranking: {len(combined)}.', '', 'Fontes:', '']
    lines.extend(f'- {s["mode"]}: {s["status"]}; {s["processed"]} registros processados.' for s in summaries)
    lines.extend(['', 'Ranking inclui apenas fontes sem falha nesta execução; acervo pode conter registros antigos. Consulte last_seen.', 'Catálogos não são anúncios. Score não mede demanda, lucro ou vendas. Dados de demonstração não são permitidos neste modo.'])
    (folder / 'report.md').write_text('\n'.join(lines) + '\n')
    LOG.info('auto status=%s fontes_ok=%s/%s', status, len(successful), len(summaries))
    return status == 'success'
