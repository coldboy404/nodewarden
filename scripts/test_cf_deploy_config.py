import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('cf_config', Path(__file__).with_name('cf-deploy-config.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DeploymentConfigTests(unittest.TestCase):
    def settings(self, kind='r2_bucket'):
        attachment = {'type': kind, 'name': 'ATTACHMENTS' if kind == 'r2_bucket' else 'ATTACHMENTS_KV', 'bucket_name': 'existing-files', 'namespace_id': 'a' * 32}
        return {'bindings': [
            {'type': 'd1', 'name': 'DB', 'id': 'existing-vault-id'}, attachment,
            {'type': 'secret_text', 'name': 'JWT_SECRET'},
            {'type': 'plain_text', 'name': 'HIDE_WEB_VAULT', 'text': '1'},
            {'type': 'durable_object_namespace', 'name': 'NOTIFICATIONS_HUB', 'class_name': 'NotificationsHub', 'script_name': 'my-existing-worker'},
        ], 'migration_tag': 'v1-notifications-hub', 'compatibility_date': '2024-01-01'}

    def prepare(self, settings):
        return module.prepare(settings, 'my-existing-worker', [{'pattern': 'example.com/*', 'zone_id': 'zone'}], [{'hostname': 'vault.example.com', 'zone_id': 'zone', 'service': 'my-existing-worker', 'environment': 'production'}, {'hostname': 'other.example.com', 'zone_id': 'zone', 'service': 'another-worker'}], {'enabled': False}, [{'cron': '*/5 * * * *'}])

    def test_existing_r2_storage_routes_and_secrets(self):
        c = self.prepare(self.settings())
        self.assertEqual(c['name'], 'my-existing-worker')
        self.assertEqual(c['d1_databases'][0]['database_id'], 'existing-vault-id')
        self.assertEqual(c['r2_buckets'][0]['bucket_name'], 'existing-files')
        self.assertNotIn('kv_namespaces', c)
        self.assertNotIn('vars', c)
        self.assertNotIn('JWT_SECRET', str(c))
        self.assertNotIn('script_name', c['durable_objects']['bindings'][0])
        self.assertTrue(c['keep_vars'])
        self.assertFalse(c['workers_dev'])
        self.assertEqual(len(c['routes']), 2)
        self.assertEqual(c['triggers']['crons'], ['*/5 * * * *'])
        self.assertEqual(len(c['durable_objects']['bindings']), 2)

    def test_kv_reuses_namespace(self):
        c = self.prepare(self.settings('kv_namespace'))
        self.assertNotIn('r2_buckets', c)
        self.assertEqual(c['kv_namespaces'][0]['id'], 'a' * 32)

    def test_missing_storage_stops(self):
        s = self.settings(); s['bindings'] = []
        with self.assertRaises(ValueError): self.prepare(s)

    def test_missing_id_stops(self):
        s = self.settings(); del s['bindings'][0]['id']
        with self.assertRaises(ValueError): self.prepare(s)

    def test_unknown_binding_stops(self):
        s = self.settings(); s['bindings'].append({'name': 'QUEUE', 'type': 'queue'})
        with self.assertRaises(ValueError): self.prepare(s)

    def test_unknown_migration_stops(self):
        s = self.settings(); s['migration_tag'] = 'future-unknown-tag'
        with self.assertRaises(ValueError): self.prepare(s)


if __name__ == '__main__':
    unittest.main()
