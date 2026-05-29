from __future__ import annotations

import argparse
import json

from real_playbook_common import assess_playbook_readiness, fetch_registry_bundle, load_inputs, render_readiness_markdown, request_json


def main() -> None:
    parser = argparse.ArgumentParser(description='Run a real cross-process readiness check for any seeded playbook.')
    parser.add_argument('--api-url', default='http://localhost:8080')
    parser.add_argument('--playbook-key', required=True)
    parser.add_argument('--inputs-json')
    parser.add_argument('--inputs-file')
    parser.add_argument('--format', choices=['json', 'markdown'], default='markdown')
    args = parser.parse_args()

    api_url = args.api_url.rstrip('/')
    health = request_json(f'{api_url}/health')
    if not isinstance(health, dict) or health.get('status') != 'ok':
        raise RuntimeError(f'real API health check failed: {health}')

    sync = request_json(f'{api_url}/hub/sync/yaml', method='POST')
    if not isinstance(sync, dict) or int(sync.get('synced', 0)) <= 0:
        raise RuntimeError(f'real Hub sync failed: {sync}')

    bundle = fetch_registry_bundle(api_url, args.playbook_key)
    inputs = load_inputs(inputs_json=args.inputs_json, inputs_file=args.inputs_file)
    report = assess_playbook_readiness(bundle, inputs=inputs)

    if args.format == 'json':
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(render_readiness_markdown(report))

    if not report['summary']['ready']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
