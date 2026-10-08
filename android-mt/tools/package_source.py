"""Build a reproducible source ZIP from an explicit allowlist; exclude user data."""
from pathlib import Path
import hashlib
import zipfile

project = Path(__file__).resolve().parents[1]
workspace = project.parent
dist = project/'dist'
dist.mkdir(exist_ok=True)
files = []
for name in ('settings.gradle','build.gradle','gradle.properties','gradlew','gradlew.bat',
             'build-local.ps1','README.md','THIRD_PARTY_NOTICES.md','package.json','package-lock.json','.gitignore'):
    files.append((project/name, 'android-mt/'+name))
files.append((project/'app/build.gradle','android-mt/app/build.gradle'))
for directory in ('app/src','gradle/wrapper','tests','tools'):
    for path in (project/directory).rglob('*'):
        if path.is_file() and '__pycache__' not in path.parts and path.suffix not in ('.pyc','.pyo'):
            files.append((path,'android-mt/'+path.relative_to(project).as_posix()))
for path in (workspace/'mt-export').rglob('*'):
    rel = path.relative_to(workspace/'mt-export')
    roots = {'update_mt.py','test_update_mt.py','README.md','DEPENDENCIES.json',
             'sing-box-1.14.schema.json','UPSTREAM-LICENSE','run-android.sh','update-now.sh'}
    if (path.is_file() and '__pycache__' not in path.parts and path.suffix not in ('.pyc','.pyo')
            and (rel.parts[0] == 'vendor' or rel.as_posix() in roots)):
        files.append((path,'mt-export/'+rel.as_posix()))
archive = dist/'MT-Bridge-0.1.2-source.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as output:
    for path, name in sorted(files,key=lambda pair:pair[1]):
        info = zipfile.ZipInfo(name, date_time=(2026,10,8,0,0,0))
        info.compress_type = zipfile.ZIP_DEFLATED
        output.writestr(info,path.read_bytes())
with zipfile.ZipFile(archive) as check:
    assert check.testzip() is None
    assert not any('private-providers' in name or 'config_sfa.json' in name for name in check.namelist())
manifest = []
for path in sorted(dist.glob('*')):
    if path.is_file() and path.suffix in ('.apk','.zip'):
        manifest.append(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+path.name)
(dist/'SHA256SUMS.txt').write_text('\n'.join(manifest)+'\n',encoding='utf-8')
print(f'Source packaged: {len(files)} files; private configs/snapshots excluded.')
