#!/usr/bin/env python3
"""Qualify links, route canonicals, sitemaps and search in one explicit artifact."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import os
import json
from pathlib import Path
from publication import routes, search
from validate_production_url import validate as validate_url


SCOPES = ['PUBLIC-ROUTES', 'SEARCH-DELIVERY', 'PRODUCTION-URLS']


def bundle_identity(site: Path) -> tuple[list[dict], str]:
    policy_path = Path(__file__).resolve().parents[2]/'security/publication.py'
    spec = importlib.util.spec_from_file_location('bijux_public_bundle_policy',policy_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.public_bundle_identity(site)


def link_exceptions(path: Path | None) -> tuple[list[dict], str | None]:
    if path is None:
        return [], None
    raw = path.read_bytes()
    body = json.loads(raw)
    if body.get('schema') != 1 or not isinstance(body.get('exceptions'),list):
        raise ValueError('Development link policy requires schema1 and an exceptions list')
    seen = set()
    for item in body['exceptions']:
        if not isinstance(item,dict) or set(item) != {'route','url','purpose'}:
            raise ValueError('Development link exception requires exact route, URL and documented purpose')
        if not all(isinstance(value,str) and value for value in item.values()):
            raise ValueError('Development link exception fields cannot be empty')
        if not item['route'].endswith('.html') or any(part == '..' for part in Path(item['route']).parts) or item['route'].startswith('/') or any(c in item['route'] for c in '*?[]'):
            raise ValueError('Development link exception requires one exact built HTML route')
        if len(item['purpose'].strip()) < 10 or not item['url'].startswith(('http://','https://')):
            raise ValueError('Development link exception requires an absolute URL and substantive purpose')
        identity = (item['route'],item['url'])
        if identity in seen:
            raise ValueError('Duplicate development link exception')
        seen.add(identity)
    return body['exceptions'],hashlib.sha256(raw).hexdigest()


def qualify(site: Path, site_url: str, network_urls: list[str], exceptions: list[dict] | None = None) -> dict:
    validate_url(site_url)
    site = site.resolve()
    files, identity = bundle_identity(site)
    docs = routes.inventory(site,site_url)
    observations = []
    route_errors = routes.validate(site,site_url,docs,network_urls,exceptions,observations)
    search_errors, count = search.validate(site,site_url,docs)
    errors = [*route_errors,*search_errors]
    production_errors = [error for error in route_errors if any(value in error for value in
                         ('canonical','production','public URL','public link URL','public asset URL','insecure active','sitemap.xml'))]
    checks = [dict(id='PUBLIC-ROUTES',passed=not route_errors,errors=route_errors),
              dict(id='SEARCH-DELIVERY',passed=not search_errors,errors=search_errors),
              dict(id='PRODUCTION-URLS',passed=not production_errors,errors=production_errors)]
    return dict(schema=1,scope=SCOPES,passed=not errors,result='fail' if errors else 'pass',
                verification_only=not bool(os.environ.get('DOCS_SOURCE_IDENTITY')) or
                                  os.environ.get('BIJUX_STD_LOCAL_VERIFY') == '1' or
                                  os.environ.get('BIJUX_STD_ALLOW_LOCAL_SOURCE') == '1',
                site_dir=str(site),site_url=site_url,bundle_sha256=identity,
                artifact_inventory_sha256=identity,files=files,
                route_count=len(docs),search_entries=count,errors=errors,checks=checks,
                development_links=observations,routes=routes.records(site,docs))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root',type=Path,default=Path.cwd())
    parser.add_argument('--site-dir',required=True,type=Path)
    parser.add_argument('--site-url',required=True)
    parser.add_argument('--hub-links',type=Path,default=Path(__file__).resolve().parents[2]/'config/hub-links.json')
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--development-link-policy',type=Path)
    args = parser.parse_args()
    root = args.repo_root.resolve()
    site = (root/args.site_dir).resolve()
    output = (root/args.output).resolve()
    try:
        if not site.is_relative_to(root/'artifacts') or not output.is_relative_to(root/'artifacts') or output.is_relative_to(site):
            raise ValueError('Select an explicit artifacts/ site and report outside that published bundle')
        registry = json.loads(args.hub_links.read_text())
        urls = [entry['url'] for entry in registry]
        policy = (root/args.development_link_policy).resolve() if args.development_link_policy else None
        if policy is not None and (not policy.is_relative_to(root) or policy.is_relative_to(site)):
            raise ValueError('Development link policy must be reviewed repository source outside the public artifact')
        exceptions, policy_digest = link_exceptions(policy)
        report = qualify(site,args.site_url,urls,exceptions)
        report.update(site_dir=site.relative_to(root).as_posix(),
                      development_link_policy_sha256=policy_digest,
                      development_link_policy=policy.relative_to(root).as_posix() if policy else None)

        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(report,indent=2)+'\n')
    except (OSError,ValueError,KeyError) as exc:
        if output.is_relative_to(root/'artifacts') and not output.is_relative_to(site):
            output.parent.mkdir(parents=True,exist_ok=True)
            output.write_text(json.dumps(dict(schema=1,scope=SCOPES,passed=False,result='fail',
                              verification_only=True,checks=[],errors=[str(exc)]),indent=2)+'\n')
        parser.exit(1,f'ERROR: {exc}\n')
    print(f'{report["result"].upper()}: {report["route_count"]} built routes, {report["search_entries"]} search entries; report {output}')
    return 0 if report['result']=='pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
