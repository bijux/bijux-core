"""Build two reviewed source-only minifiers with one frozen wheel toolchain."""
from __future__ import annotations

import argparse
from email.parser import BytesParser
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tarfile
from urllib.parse import urlsplit
from urllib.request import urlopen
import zipfile

SHARED = Path(__file__).resolve().parents[2]
RUNTIME = SHARED / 'security/runtime'
SOURCE_HASHES = {
    ('csscompressor', '0.9.5'): 'afa22badbcf3120a4f392e4d22f9fff485c044a1feda4a950ecc5eba9dd31a05',
    ('jsmin', '3.0.1'): 'c0959a121ef94542e807a674142606f7e90214a2b3d1eb17300244bbb5cc2bfc',
}
BUILDER = {'setuptools': '83.0.0', 'wheel': '0.47.0', 'packaging': '26.2'}


def require(value, message):
    if not value:
        raise ValueError('Publication source wheel: ' + message)


def digest(value):
    return hashlib.sha256(value).hexdigest()


def regular(path):
    require(path.is_file() and not path.is_symlink() and path.stat().st_nlink == 1,
            'regular unlinked input required: ' + str(path))
    return path.read_bytes()


def recipe(document, *, observation=False):
    require(set(document) == {'schema', 'python', 'source_date_epoch', 'builder_packages', 'sources'}
            and document['schema'] == 1 and document['python'] == '3.11.17'
            and document['source_date_epoch'] == 1704067200 and document['builder_packages'] == BUILDER,
            'exact frozen builder recipe required')
    sources = document['sources']
    require(isinstance(sources, list) and len(sources) == 2,
            'exact two source-only distributions required')
    seen = set()
    for row in sources:
        require(isinstance(row, dict) and set(row) in (
            {'name', 'version', 'filename', 'url', 'sha256', 'metadata_url'},
            {'name', 'version', 'filename', 'url', 'sha256', 'metadata_url', 'wheel_filename', 'wheel_sha256'}),
            'typed source and reviewed wheel record required')
        key = (row['name'], row['version'])
        require(key in SOURCE_HASHES and key not in seen and row['sha256'] == SOURCE_HASHES[key],
                'unreviewed or duplicate source distribution')
        seen.add(key)
        expected = row['name'] + '-' + row['version']
        url = urlsplit(row['url'])
        require(row['filename'] == expected + '.tar.gz' and url.scheme == 'https'
                and url.hostname == 'files.pythonhosted.org' and not url.query and not url.fragment
                and url.path.endswith('/' + row['filename'])
                and row['metadata_url'] == 'https://pypi.org/pypi/' + row['name'] + '/' + row['version'] + '/json',
                'exact primary source identity required')
        if not observation:
            require(row.get('wheel_filename') == expected + '-py3-none-any.whl'
                    and isinstance(row.get('wheel_sha256'), str)
                    and re.fullmatch('[0-9a-f]{64}', row['wheel_sha256']),
                    'actual independently reviewed wheel fingerprint required')
    return sources


def archive_files(data, prefix):
    """Inspect every member before extracting any bounded regular source bytes."""
    require(len(data) <= 4 * 1024 * 1024, 'source archive exceeds byte budget')
    result = {}
    seen = set()
    total = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode='r|gz') as archive:
        for index, item in enumerate(archive):
            require(index < 1024, 'source archive exceeds member budget')
            name = item.name.rstrip('/')
            parts = name.split('/')
            require(name not in seen and parts[0] == prefix and '\\' not in name
                    and not PurePosixPath(name).is_absolute()
                    and all(part not in {'', '.', '..'} for part in parts)
                    and (item.isdir() or item.isreg()),
                    'duplicate, escaping or nonregular archive member')
            seen.add(name)
            if item.isdir():
                continue
            total += item.size
            require(0 <= item.size <= 16 * 1024 * 1024 and total <= 64 * 1024 * 1024,
                    'expanded source exceeds byte budget')
            stream = archive.extractfile(item)
            require(stream is not None, 'regular source member unavailable')
            content = stream.read(item.size + 1)
            require(len(content) == item.size, 'source member size differs')
            result[name] = (content, 0o755 if item.mode & 0o100 else 0o644)
    require(prefix + '/setup.py' in result, 'reviewed native setuptools entrypoint missing')
    return result


def wheel_identity(path, source):
    data = regular(path)
    require(path.name == source['name'] + '-' + source['version'] + '-py3-none-any.whl',
            'one exact pure Python wheel required')
    with zipfile.ZipFile(io.BytesIO(data)) as wheel:
        infos = wheel.infolist()
        require(len(infos) <= 1024 and len({info.filename for info in infos}) == len(infos),
                'bounded unique wheel population required')
        for info in infos:
            parts = info.filename.rstrip('/').split('/')
            mode = info.external_attr >> 16
            require(not PurePosixPath(info.filename).is_absolute()
                    and '\\' not in info.filename and all(part not in {'', '.', '..'} for part in parts)
                    and not stat.S_ISLNK(mode) and info.file_size <= 16 * 1024 * 1024,
                    'escaping, symlinked or oversized wheel member')
        metadata = source['name'] + '-' + source['version'] + '.dist-info/'
        fields = BytesParser().parsebytes(wheel.read(metadata + 'METADATA'))
        tags = BytesParser().parsebytes(wheel.read(metadata + 'WHEEL'))
        require(fields.get_all('Name') == [source['name']] and fields.get_all('Version') == [source['version']]
                and tags.get_all('Root-Is-Purelib') == ['true'] and tags.get_all('Tag') == ['py3-none-any'],
                'wheel metadata differs from reviewed source identity')
    return {'filename': path.name, 'sha256': digest(data), 'bytes': len(data)}


def output_directory(root, value):
    relative = PurePosixPath(value)
    require(not relative.is_absolute() and relative.parts and relative.parts[0] == 'artifacts'
            and all(part not in {'', '.', '..'} for part in value.split('/')) and '\\' not in value,
            'confined repository artifacts output required')
    path = root / relative
    for parent in (path, *path.parents):
        require(not parent.is_symlink(), 'output symlink forbidden')
        if parent == root:
            break
    require(not path.exists(), 'fresh absent output directory required')
    return path


def build(python, directory, *, observation=False):
    root = Path(subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], text=True).strip()).resolve()
    recipe_bytes = regular(RUNTIME/'source-wheels.json')
    lock_bytes = regular(RUNTIME/'build-requirements.lock')
    document = json.loads(recipe_bytes)
    sources = recipe(document, observation=observation)
    observed = json.loads(subprocess.check_output([python, '-I', '-c',
        'import json,platform;print(json.dumps([platform.python_version(),platform.system(),platform.machine()]))'], text=True))
    require(observed == ['3.11.17', 'Linux', 'x86_64'], 'qualified actual Linux x86_64 Python3.11.17 required')
    output = output_directory(root, directory)
    output.mkdir(parents=True)
    (output/'cache').mkdir()
    (output/'scratch').mkdir()
    environment = {key: value for key, value in os.environ.items() if key not in {'PYTHONPATH', 'PYTHONHOME'}}
    environment.update(SOURCE_DATE_EPOCH=str(document['source_date_epoch']), PYTHONNOUSERSITE='1',
        PYTHONDONTWRITEBYTECODE='1', UV_CACHE_DIR=str(output/'cache'), TMPDIR=str(output/'scratch'))
    subprocess.run([python, '-I', '-m', 'venv', '--without-pip', str(output/'builder')], check=True, env=environment)
    executable = output/'builder/bin/python'
    uv = shutil.which('uv')
    require(uv is not None, 'uv installer unavailable')
    with (output/'installer.log').open('w') as log:
        subprocess.run([uv, 'pip', 'install', '--python', str(executable), '--require-hashes',
                        '--only-binary', ':all:', '--no-deps', '--default-index', 'https://pypi.org/simple',
                        '--requirements', str(RUNTIME/'build-requirements.lock')],
                       check=True, env=environment, stdout=log, stderr=subprocess.STDOUT)
    installed = json.loads(subprocess.check_output([str(executable), '-I', '-c',
        'import importlib.metadata as m,json;print(json.dumps({d.metadata["Name"].lower():d.version for d in m.distributions()}))'],
        text=True, env=environment))
    require(installed == BUILDER, 'actual builder dependency population differs')
    records = []
    for source in sources:
        with urlopen(source['url'], timeout=30) as response:
            content = response.read(4 * 1024 * 1024 + 1)
        require(digest(content) == source['sha256'], 'downloaded source archive identity differs')
        files = archive_files(content, source['name'] + '-' + source['version'])
        source_root = output/'sources'
        for name, (data, mode) in files.items():
            destination = source_root/name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
            destination.chmod(mode)
        work = source_root/(source['name'] + '-' + source['version'])
        destination = output/'wheels'
        destination.mkdir(exist_ok=True)
        with (output/(source['name'] + '-build.log')).open('w') as log:
            subprocess.run([str(executable), '-I', 'setup.py', 'bdist_wheel', '--dist-dir', str(destination)],
                           cwd=work, check=True, timeout=180, env=environment,
                           stdout=log, stderr=subprocess.STDOUT)
        record = wheel_identity(destination/(source['name'] + '-' + source['version'] + '-py3-none-any.whl'), source)
        if not observation:
            require(record['sha256'] == source['wheel_sha256'], 'built wheel differs from independently reviewed bytes')
        records.append({**record, 'source': source})
    require(recipe_bytes == regular(RUNTIME/'source-wheels.json') and lock_bytes == regular(RUNTIME/'build-requirements.lock'),
            'source-owned builder recipe changed during execution')
    report = {'schema': 1, 'scope': 'source-wheel-observation' if observation else 'reviewed-source-wheel-build',
              'publication_approved': not observation, 'environment': observed, 'builder_packages': installed,
              'recipe_sha256': digest(recipe_bytes), 'builder_lock_sha256': digest(lock_bytes), 'wheels': records}
    (output/'receipt.json').write_text(json.dumps(report, indent=2)+'\n')
    print(output/'receipt.json')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', required=True)
    parser.add_argument('--directory', default='artifacts/docs/publication/wheels')
    parser.add_argument('--observe', action='store_true', help='Capture candidate wheels; never approve publication')
    arguments = parser.parse_args()
    build(arguments.python, arguments.directory, observation=arguments.observe)


if __name__ == '__main__':
    main()
