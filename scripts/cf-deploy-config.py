#!/usr/bin/env python3
"""Prepare a fail-closed deployment of an EXISTING Worker; never provision storage."""
import copy
import json
import os
from pathlib import Path
import re
import tomllib
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def prepare(settings, worker, routes, domains, subdomain, schedules):
    bindings = settings.get('bindings', [])
    names = {b['name'] for b in bindings}
    if 'DB' not in names or not ({'ATTACHMENTS', 'ATTACHMENTS_KV'} & names):
        raise ValueError('Existing Worker must have DB and ATTACHMENTS or ATTACHMENTS_KV bindings')
    template = 'wrangler.toml' if 'ATTACHMENTS' in names else 'wrangler.kv.toml'
    config = tomllib.loads((ROOT / template).read_text())
    config = copy.deepcopy(config)
    config['name'] = worker
    config['keep_vars'] = True
    config['workers_dev'] = subdomain['enabled']
    config['preview_urls'] = subdomain.get('previews_enabled', False)
    for key in ('d1_databases', 'r2_buckets', 'kv_namespaces', 'durable_objects'):
        config.pop(key, None)
    for b in bindings:
        kind, name = b['type'], b['name']
        if kind in ('plain_text', 'json', 'secret_text', 'assets'):
            continue  # Dashboard vars/secrets are preserved; assets come from the build.
        if kind == 'd1':
            if not b.get('id'): raise ValueError('D1 binding has no database ID')
            config.setdefault('d1_databases', []).append({'binding': name, 'database_id': b['id'], 'database_name': b.get('database_name', name)})
        elif kind == 'kv_namespace':
            if not b.get('namespace_id'): raise ValueError('KV binding has no namespace ID')
            config.setdefault('kv_namespaces', []).append({'binding': name, 'id': b['namespace_id']})
        elif kind == 'r2_bucket':
            if not b.get('bucket_name'): raise ValueError('R2 binding has no bucket name')
            item = {'binding': name, 'bucket_name': b['bucket_name']}
            if b.get('jurisdiction'): item['jurisdiction'] = b['jurisdiction']
            config.setdefault('r2_buckets', []).append(item)
        elif kind == 'durable_object_namespace':
            item = {'name': name, 'class_name': b['class_name']}
            if b.get('script_name') and b['script_name'] != worker: item['script_name'] = b['script_name']
            if b.get('environment'): item['environment'] = b['environment']
            config.setdefault('durable_objects', {}).setdefault('bindings', []).append(item)
        else:
            raise ValueError(f'Unsupported existing binding type {kind}; refusing to remove it')
    required = {'NOTIFICATIONS_HUB', 'BACKUP_TRANSFER_RUNNER'}
    existing_do = {b['name'] for b in config.get('durable_objects', {}).get('bindings', [])}
    # These are the only new namespaces allowed: upstream-defined DO migrations, not vault storage.
    for binding, cls in [('NOTIFICATIONS_HUB', 'NotificationsHub'), ('BACKUP_TRANSFER_RUNNER', 'BackupTransferRunner')]:
        if binding not in existing_do:
            config.setdefault('durable_objects', {}).setdefault('bindings', []).append({'name': binding, 'class_name': cls})
    remote_tag = settings.get('migration_tag')
    if remote_tag and remote_tag not in {m['tag'] for m in config.get('migrations', [])}:
        raise ValueError('Remote Durable Object migration tag is not in upstream config; review required')
    config['routes'] = [{'pattern': r['pattern'], **({'zone_id': r['zone_id']} if r.get('zone_id') else {})} for r in routes]
    config['routes'] += [{'pattern': d['hostname'], 'custom_domain': True, 'zone_id': d['zone_id']} for d in domains if d.get('service') == worker and d.get('environment', 'production') == 'production']
    config['triggers'] = {'crons': [s['cron'] for s in schedules]}
    if settings.get('compatibility_date'): config['compatibility_date'] = settings['compatibility_date']
    if 'compatibility_flags' in settings: config['compatibility_flags'] = settings['compatibility_flags']
    if 'observability' in settings: config['observability'] = settings['observability']
    if 'logpush' in settings: config['logpush'] = settings['logpush']
    return config


def api(path):
    token = os.environ['CLOUDFLARE_API_TOKEN']
    req = urllib.request.Request('https://api.cloudflare.com/client/v4' + path, headers={'Authorization': 'Bearer ' + token})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            body = json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError(f'Cloudflare read failed (HTTP {error.code}); check account, Worker name and token permissions') from None
    if not body.get('success'):
        raise RuntimeError('Cloudflare read failed; refusing to deploy')
    if body.get('result_info', {}).get('total_pages', 1) > 1:
        raise RuntimeError('Cloudflare response is paginated; review required before deployment')
    return body['result']


def main():
    account = os.environ['CLOUDFLARE_ACCOUNT_ID']
    worker = os.environ['CF_WORKER_NAME']
    if not re.fullmatch(r'[a-fA-F0-9]{32}', account): raise ValueError('Invalid Cloudflare account ID')
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,62}', worker): raise ValueError('Invalid existing Worker name')
    base = f'/accounts/{account}/workers/scripts/{worker}'
    settings = api(base + '/settings')  # A missing Worker is fatal, never create a new one.
    config = prepare(settings, worker, api(f'/accounts/{account}/workers/services/{worker}/environments/production/routes?show_zonename=true'), api(f'/accounts/{account}/workers/domains'), api(base + '/subdomain'), api(base + '/schedules')['schedules'])
    output = ROOT / '.cf-deploy.json'
    output.write_text(json.dumps(config, indent=2) + '\n')
    output.chmod(0o600)
    print('Existing Worker verified; deployment config preserves live storage, routes, schedules and runtime variables.')


if __name__ == '__main__':
    main()
