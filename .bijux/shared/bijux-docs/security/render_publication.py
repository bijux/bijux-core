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


def build_artifact(root: Path, config_name: str, site_name: str, *, site_url='', source_identity=None, strict=True):
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
        if checkpoint.get('config',{}).get('path')!=config_name:
            raise ValueError('Publication build: owner checkpoint must select the actual config')
    from mkdocs.config import load_config
    from mkdocs.commands.build import build
    import material
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
                                  publication_scope=checkpoint is not None)
        receipt=identity.begin(root,config_name,site_name,actual_url,source_identity)
        previous_strict=configuration.strict
        configuration.strict=strict
        try:
            build(configuration)
        finally:
            configuration.strict=previous_strict
        configuration=load_config(config_file=str(identity.regular(root,config_name)),site_dir=str(site))
        plan=redirects.normalize_redirects(configuration,site,actual_url,write=False)
        report=policy.apply(site,shared,templates,plan)
        inputs=policy.policy_inputs(shared,templates);inputs['redirects']=plan['policy_inputs']
        report.update(site_url=actual_url,site_dir=site_name,bundle_sha256=publication.public_bundle_identity(site)[1],
                      policy_inputs=inputs,processor_sha256=hashlib.sha256((shared/'security/csp.py').read_bytes()).hexdigest())
        receipt=identity.finish(root,receipt)
        reconstruction=producer.verify(site,prepared,receipt['renderer'],report,actual_url)
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
    parser.add_argument('--source-identity',default=os.environ.get('DOCS_SOURCE_IDENTITY'))
    parser.add_argument('--no-strict',action='store_true')
    args=parser.parse_args()
    try:
        result=build_artifact(Path.cwd().resolve(),args.config,args.site_dir,site_url=args.site_url,
                              source_identity=args.source_identity,strict=not args.no_strict)
        print(json.dumps({key:value for key,value in result.items() if key!='producer'}))
        return 0
    except (OSError,ValueError,KeyError,subprocess.CalledProcessError) as error:
        print('Documentation artifact rejected: '+str(error),file=sys.stderr)
        return 1


if __name__=='__main__':raise SystemExit(main())
