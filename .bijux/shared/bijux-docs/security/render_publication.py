#!/usr/bin/env python3
"""Build and qualify one documentation artifact under its actual renderer."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import logging
import os
from pathlib import Path
import sys
import subprocess
import tempfile

sys.dont_write_bytecode=True


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def build_artifact(root: Path, config_name: str, site_name: str, *, site_url='', source_identity=None, strict=True, source_recipe=None, reader_owner=None, interactive_report_owner=None):
    shared=Path(__file__).resolve().parents[1]
    identity=load('bijux_renderer_identity',shared/'security/build_identity.py')
    publication=load('bijux_renderer_publication',shared/'security/publication.py')
    producer=load('bijux_renderer_producer',shared/'security/producer_authority.py')
    policy=load('bijux_renderer_csp',shared/'security/csp.py')
    redirects=load('bijux_renderer_redirects',shared/'security/redirects.py')
    site=publication.site_directory(root,site_name)
    checkpoint=None
    if source_identity:
        if not strict:
            raise ValueError("Publication build: source-qualified publication requires strict rendering")
        checkpoint=json.loads(identity.artifact(root,source_identity).read_text())
        identity.verify_source(root,checkpoint)
        record=checkpoint.get('derivation')
        if record is not None and not isinstance(record,dict):
            raise ValueError('Publication build: typed derivation record required')
        expected_recipe=record.get('recipe') if record else None
        if source_recipe is not None and source_recipe!=expected_recipe:
            raise ValueError('Publication build: recipe differs from owner checkpoint')
        source_recipe=expected_recipe
        selected_config=record['configuration']['path'] if record else checkpoint.get('config',{}).get('path')
        if selected_config!=config_name:
            raise ValueError('Publication build: owner checkpoint must select the actual config')
    from mkdocs.config import load_config
    from mkdocs.commands.build import build
    import material
    catalogue=None
    if source_recipe:
        producer.dependencies(shared,root,publication=checkpoint is not None)
        if reader_owner is not None or interactive_report_owner is not None:
            raise ValueError("Publication build: report readers require a tracked MkDocs config; catalogue recipe composition remains separate")
        catalogue=identity.catalogue_derivation(root,source_recipe,checkpoint.get('derivation') if checkpoint else None)
        if config_name!=catalogue.record['configuration']['path']:
            raise ValueError('Publication build: exact reconstructed configuration required')
        configuration=catalogue.configuration(site)
    else:
        configuration=load_config(config_file=str(identity.regular(root,config_name)),site_dir=str(site))
    actual_url=site_url or configuration.site_url
    publication.validate_url(actual_url)
    if actual_url!=configuration.site_url:
        raise ValueError('Publication build: actual configuration selects another production URL')
    evidence=root/'artifacts/website-security';evidence.mkdir(parents=True,exist_ok=True)
    # Clear prior success receipts before a build can fail. Reports belong outside site.
    for name in ('build-identity','csp','producer-reconstruction','site-verification'):
        destination=identity.artifact(root,'artifacts/website-security/'+name+'.json')
        if destination.is_relative_to(site):raise ValueError('Publication build: evidence cannot be published')
        destination.write_text(json.dumps({'schema':1,'passed':False,'verification_only':True,'error':'Producer qualification incomplete'})+'\n')
    templates=Path(material.__file__).parent/'templates'
    with tempfile.TemporaryDirectory(prefix='renderer-reference-',dir=evidence) as scratch:
        prepared=producer.prepare(root,config_name,shared,templates,Path(scratch)/'site',site,
                                  publication_scope=checkpoint is not None,source_recipe=source_recipe,reader_owner=reader_owner,
                                  interactive_report_owner=interactive_report_owner)
        receipt=identity.begin(root,config_name,site_name,actual_url,source_identity,source_recipe)
        previous_strict=configuration.strict
        configuration.strict=strict
        try:
            producer.render(configuration,catalogue=catalogue is not None)
        finally:
            configuration.strict=previous_strict
        configuration=(catalogue.configuration(site) if catalogue else
                       load_config(config_file=str(identity.regular(root,config_name)),site_dir=str(site)))
        plan=redirects.normalize_redirects(configuration,site,actual_url,write=False,source_root=root if catalogue else None)
        report=(policy.apply(site,shared,templates,plan) if prepared.reader_source is None else
                prepared.reader_source.compose(site,receipt,policy,shared,templates,plan))
        inputs=report['policy_inputs'];inputs['redirects']=plan['policy_inputs']
        report.update(site_url=actual_url,site_dir=site_name,bundle_sha256=publication.public_bundle_identity(site)[1],
                      policy_inputs=inputs,processor_sha256=hashlib.sha256((shared/'security/csp.py').read_bytes()).hexdigest())
        receipt=identity.finish(root,receipt)
        reconstruction=producer.verify(site,prepared,receipt['renderer'],report,actual_url,completed_build=receipt,checkpoint=checkpoint)
        if checkpoint:
            identity.verify_source(root,checkpoint)
    for name,value in [('build-identity',receipt),('csp',report),('producer-reconstruction',reconstruction)]:
        output=identity.artifact(root,'artifacts/website-security/'+name+'.json')
        if output.is_relative_to(site):raise ValueError('Publication build: evidence cannot be published')
        output.write_text(json.dumps(value,indent=2)+'\n')
    environment={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
    if source_identity:environment['DOCS_SOURCE_IDENTITY']=source_identity
    else:environment.pop('DOCS_SOURCE_IDENTITY',None)
    arguments=[sys.executable,str(shared/'tooling/quality/validate_site_routes.py'),
               '--repo-root',str(root),'--site-dir',site_name,'--site-url',actual_url,
               '--output','artifacts/website-security/site-verification.json']
    if reader_owner is not None or interactive_report_owner is not None:
        arguments.extend(['--embedded-csp-report', 'artifacts/website-security/csp.json',
                          '--completed-build-receipt', 'artifacts/website-security/build-identity.json',
                          '--source-sha', prepared.reader_source.source_sha])
        arguments.extend(['--reader-owner', reader_owner] if reader_owner is not None else
                         ['--interactive-report-owner', interactive_report_owner])
        if source_identity: arguments.extend(['--source-identity', source_identity])
    exception=os.environ.get('BIJUX_DOCS_DEVELOPMENT_LINK_POLICY')
    if exception:arguments.extend(['--development-link-policy',exception])
    subprocess.run(arguments,cwd=root,env=environment,check=True)
    if checkpoint:identity.verify_source(root,checkpoint)
    return {'site_url':actual_url,'site_dir':site_name,'bundle_sha256':report['bundle_sha256'],
            'verification_only':checkpoint is None,'producer':reconstruction}


def main():
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(name)s: %(message)s')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True)
    parser.add_argument('--site-dir',required=True)
    parser.add_argument('--site-url',default='')
    parser.add_argument('--source-recipe',choices=['masterclass-catalogue'])
    parser.add_argument('--source-identity',default=os.environ.get('DOCS_SOURCE_IDENTITY'))
    parser.add_argument('--reader-owner', default=os.environ.get('BIJUX_DOCS_READER_OWNER'), help='Explicit committed finite static-reader ownership descriptor')
    parser.add_argument('--interactive-report-owner', help='Explicit committed config-selected interactive report ownership descriptor')
    parser.add_argument('--no-strict',action='store_true')
    args=parser.parse_args()
    try:
        result=build_artifact(Path.cwd().resolve(),args.config,args.site_dir,site_url=args.site_url,
                              source_identity=args.source_identity,strict=not args.no_strict,source_recipe=args.source_recipe,reader_owner=args.reader_owner,
                              interactive_report_owner=args.interactive_report_owner)
        print(json.dumps({key:value for key,value in result.items() if key!='producer'}))
        return 0
    except (OSError,ValueError,KeyError,subprocess.CalledProcessError) as error:
        print('Documentation artifact rejected: '+str(error),file=sys.stderr)
        return 1


if __name__=='__main__':raise SystemExit(main())
