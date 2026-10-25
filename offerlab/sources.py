"""Fontes autorizadas. Catálogo licenciado não equivale a anúncio ou venda."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
import unicodedata
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

CATALOG_REPO = 'EbookFoundation/free-programming-books'
CATALOG_COMMIT = '52e40c13216706ff4a0b63c3224c34abaa266e1d'
LICENSE_URL = f'https://github.com/{CATALOG_REPO}/blob/{CATALOG_COMMIT}/LICENSE'
LICENSE_SHA256 = 'f5b745ef98087f531e719ee8ca6a96809444573ecc7173c6fa68eaad39b3cc3f'
MAX_BYTES = 2_000_000


class SourceError(RuntimeError):
    """Mensagem pública definida pelo programa; nunca inclui erro remoto bruto."""


def read_public_json(url, opener=urlopen):
    try:
        with opener(Request(url, headers={'User-Agent': 'OfferLab/0.2 (public metadata research)'}), timeout=30) as response:
            raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise SourceError('Resposta excede limite de 2 MB')
        return json.loads(raw)
    except HTTPError as e:
        raise SourceError(f'API pública HTTP {int(e.code)}; verificar rede e limites') from None
    except (URLError, OSError, ValueError):
        raise SourceError('API pública indisponível ou resposta inválida') from None


def fold(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text.lower()) if not unicodedata.combining(c))


def resolve_catalog_revision():
    try:
        result = subprocess.run(['git', 'ls-remote', f'https://github.com/{CATALOG_REPO}.git', 'refs/heads/main'], capture_output=True, text=True, timeout=30, check=True)
    except (OSError, subprocess.SubprocessError):
        raise SourceError('Não foi possível resolver revisão oficial do catálogo') from None
    match = re.fullmatch(r'([0-9a-f]{40})\s+refs/heads/main\s*', result.stdout)
    if not match:
        raise SourceError('Revisão oficial do catálogo inválida')
    return match[1]


def parse_catalog(text, keywords):
    category = ''
    for number, line in enumerate(text.splitlines(), 1):
        if line.startswith('### '):
            category = line[4:].strip()
        match = re.match(r'^\s*\* \[([^\]]+)\]\((https?://[^\s)]+)\)(.*)$', line)
        if not match:
            continue
        title, url, byline = match.groups()
        if not urlparse(url).hostname:
            continue
        searchable = fold(title + ' ' + category)
        matched = [word for word in keywords if fold(word) in searchable]
        if matched:
            yield dict(title=title, url=url, byline=byline.strip(' -'), category=category,
                       line_number=number, original_line=line, matched_keywords=matched)


class CatalogSource:
    """Somente metadados CC BY 4.0; nunca visita ou baixa o produto vinculado."""
    def __init__(self, config, opener=urlopen):
        self.c, self.opener, self.requests = config, opener, 0

    def ads(self):
        self.completed = False
        ref = self.c.get('catalog_ref', CATALOG_COMMIT)
        if ref == 'latest':
            if self.c['max_requests'] < 2:
                raise SourceError('Catálogo latest exige orçamento para resolver revisão e licença')
            self.requests += 1
            ref = resolve_catalog_revision()
        if ref != CATALOG_COMMIT or self.c.get('catalog_ref') == 'latest':
            if self.requests >= self.c['max_requests']:
                return
            self.requests += 1
            try:
                with self.opener(Request(f'https://github.com/{CATALOG_REPO}/raw/{ref}/LICENSE', headers={'User-Agent': 'OfferLab/0.2'}), timeout=30) as response:
                    license_bytes = response.read(MAX_BYTES + 1)
            except (OSError, URLError):
                raise SourceError('Não foi possível verificar licença do catálogo') from None
            if hashlib.sha256(license_bytes).hexdigest() != LICENSE_SHA256:
                raise SourceError('Licença do catálogo mudou; revisão humana necessária antes de coletar')
        for language in self.c.get('catalog_languages', ['pt_PT', 'pt_BR']):
            if self.requests >= self.c['max_requests']:
                return
            url = f'https://github.com/{CATALOG_REPO}/raw/{ref}/books/free-programming-books-{language}.md'
            self.requests += 1
            try:
                with self.opener(Request(url, headers={'User-Agent': 'OfferLab/0.2 (CC-BY catalog research)'}), timeout=30) as response:
                    raw = response.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES:
                    raise SourceError('Catálogo excede limite de 2 MB')
                text = raw.decode('utf-8')
            except HTTPError as e:
                raise SourceError(f'Catálogo HTTP {int(e.code)}; verificar rede ou revisão configurada') from None
            except (URLError, OSError, UnicodeError):
                raise SourceError('Catálogo indisponível ou resposta inválida') from None
            digest = hashlib.sha256(raw).hexdigest()
            for entry in parse_catalog(text, self.c['keywords']):
                yield dict(
                    id=hashlib.sha256((language + '\n' + entry['url']).encode()).hexdigest(),
                    record_kind='licensed_catalog_entry', title=entry['title'],
                    page_name='', ad_creative_bodies=[entry['title']],
                    ad_creative_link_captions=[entry['url']], landing_url=entry['url'],
                    evidence_url=url + '#L' + str(entry['line_number']),
                    language=language.replace('_', '-'), market_country=None,
                    price=None, currency=None, free_resource_listed=True,
                    catalog_category=entry['category'], catalog_byline=entry['byline'],
                    evidence=dict(source_url=url, source_revision=ref, source_sha256=digest,
                                  line=entry['line_number'], quote=entry['original_line'],
                                  attribution='Ebook Foundation / free-programming-books contributors',
                                  license='CC BY 4.0 (catalog metadata only)', license_url=f'https://github.com/{CATALOG_REPO}/blob/{ref}/LICENSE'),
                    limitations='Referência de recurso gratuito segundo o catálogo. Disponibilidade, licença do livro e mercado PT não verificados; não é anúncio ou evidência de vendas.'
                ), ', '.join(entry['matched_keywords'])
        self.completed = True


class AppleSource:
    """Metadados de ebooks da API oficial de busca; disponibilidade por storefront."""
    def __init__(self, config, opener=urlopen, sleep=time.sleep):
        self.c, self.opener, self.sleep, self.requests = config, opener, sleep, 0

    def ads(self):
        self.completed = False
        for country in self.c['countries']:
            for keyword in self.c['keywords']:
                if self.requests >= self.c['max_requests']:
                    return
                if self.requests:
                    self.sleep(3)  # <= 20 solicitações/minuto por processo
                params = dict(term=keyword, country=country, media='ebook', entity='ebook', limit=self.c['page_size'])
                url = 'https://itunes.apple.com/search?' + urlencode(params)
                self.requests += 1
                body = read_public_json(url, self.opener)
                if not isinstance(body, dict) or not isinstance(body.get('results'), list):
                    raise SourceError('Apple retornou formato inesperado')
                for book in body['results']:
                    if not isinstance(book, dict) or not book.get('trackId'):
                        raise SourceError('Apple retornou registro sem identificador')
                    yield dict(id=f"{country}:{book['trackId']}", record_kind='marketplace_ebook',
                               title=book.get('trackName', ''), page_name=book.get('artistName', ''),
                               ad_creative_bodies=[book.get('trackName', '')],
                               landing_url=book.get('trackViewUrl', ''),
                               ad_creative_link_captions=[book.get('trackViewUrl', '')],
                               evidence_url=url, market_country=country,
                               price=book.get('price'), currency=book.get('currency'),
                               release_date=book.get('releaseDate'),
                               evidence=dict(source_url=url, returned_metadata=book),
                               limitations='Catálogo Apple Books no storefront consultado; não é anúncio nem prova de vendas, procura ou margem.'), keyword
        self.completed = True


class ImportSource:
    """Exportação JSON autorizada; o manifesto registra origem e autorização."""
    requests = 0

    def __init__(self, config):
        self.c = config

    def ads(self):
        path = Path(self.c['import_path'])
        if path.stat().st_size > MAX_BYTES:
            raise SourceError('Exportação excede limite de 2 MB')
        raw = path.read_bytes()
        try:
            body = json.loads(raw)
        except (ValueError, UnicodeError):
            raise SourceError('Exportação JSON inválida') from None
        if not isinstance(body, dict) or not isinstance(body.get('records'), list):
            raise SourceError('Exportação deve conter records')
        if body.get('authorized') is not True or not isinstance(body.get('source_url'), str) or not urlparse(body['source_url']).hostname or not body.get('authorization_basis'):
            raise SourceError('Exportação exige authorized=true, source_url e authorization_basis')
        for record in body['records']:
            if not isinstance(record, dict) or not record.get('id') or not isinstance(record.get('text'), str):
                raise SourceError('Registro importado exige id e text')
            yield dict(id=str(record['id']), record_kind='authorized_export',
                       title=record.get('title', ''), page_name=record.get('advertiser', ''),
                       ad_creative_bodies=[record['text']],
                       ad_creative_link_captions=[record.get('url', '')],
                       landing_url=record.get('url', ''), evidence_url=body['source_url'],
                       market_country=record.get('country'), price=record.get('price'),
                       currency=record.get('currency'), language=record.get('language'),
                       evidence=dict(source_url=body['source_url'], authorization_basis=body['authorization_basis'],
                                     export_sha256=hashlib.sha256(raw).hexdigest(), record=record),
                       limitations='Exportação declarada autorizada pelo operador; declaração não verifica licença, autenticidade ou direitos de terceiros.'), 'import'
