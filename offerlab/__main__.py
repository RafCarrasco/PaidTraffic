import argparse
import logging
import time
from .pipeline import load_config, run_all, run


def main():
    parser = argparse.ArgumentParser(description='OfferLab: pipeline autorizado de pesquisa')
    parser.add_argument('--config', default='config/demo.json')
    parser.add_argument('--schedule', action='store_true', help='Repetir após cada execução; Ctrl+C encerra')
    parser.add_argument('--doctor-meta', action='store_true', help='Uma requisição autenticada Meta, diagnóstico sem token')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    try:
        config = load_config(args.config)
        if args.doctor_meta:
            if config['mode'] == 'auto':
                config = next((s for s in config['sources'] if s['mode'] == 'meta'), {})
            if config.get('mode') != 'meta':
                raise ValueError('doctor-meta requer fonte meta')
            config = dict(config, max_requests=1, max_ads=1, page_size=1, keywords=config['keywords'][:1])
            return 0 if run(config) else 1
        while True:
            ok = run_all(config)
            if not args.schedule:
                return 0 if ok else 1
            time.sleep(config['interval_seconds'])
    except KeyboardInterrupt:
        return 130
    except (ValueError, OSError) as e:
        logging.error('Configuração inválida (%s)', type(e).__name__)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
