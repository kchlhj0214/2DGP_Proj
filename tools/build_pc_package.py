"""Build the Patch Windows archive from an existing embedded Python with pico2d."""

import argparse
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from tools.generate_data import ROOT, generate


def write_tree(archive, directory, target):
    for path in sorted(directory.rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts:
            archive.write(path, (target / path.relative_to(directory)).as_posix())


def build(runtime, output):
    generate()
    runtime_files = [runtime / 'pythonw.exe', runtime / 'python313.zip', runtime / 'LICENSE.txt']
    packages = runtime / 'Lib/site-packages'
    names = ('pico2d', 'sdl2', 'sdl2dll')
    for path in runtime_files + [packages / name for name in names]:
        if not path.exists():
            raise FileNotFoundError(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        archive.write(runtime_files[0], 'Game.exe')
        archive.write(runtime_files[1], 'python313.zip')
        archive.write(runtime_files[2], 'credits/python-license.txt')
        archive.writestr('python313._pth', 'python313.zip\n.\nLib/site-packages\nimport site\n')
        for pattern in ('*.dll', '*.pyd'):
            for path in sorted(runtime.glob(pattern)):
                archive.write(path, path.name)
        for name in names:
            write_tree(archive, packages / name, Path('Lib/site-packages') / name)
        for pattern in ('pico2d-*.dist-info', 'PySDL2-*.dist-info', 'pysdl2_dll-*.dist-info'):
            for metadata in packages.glob(pattern):
                write_tree(archive, metadata, Path('Lib/site-packages') / metadata.name)
        for path in sorted(ROOT.glob('*.py')):
            archive.write(path, path.name)
        archive.write(ROOT / 'tools/generate_data.py', 'tools/generate_data.py')
        for path in sorted((ROOT / 'data').glob('*.json')):
            archive.write(path, path.relative_to(ROOT).as_posix())
        write_tree(archive, ROOT / 'assets', Path('assets'))
        atlas = ROOT / 'art/sprite-review/atlas.json'
        archive.write(atlas, atlas.relative_to(ROOT).as_posix())
        for clip in json.loads(atlas.read_text(encoding='utf-8'))['clips']:
            if clip['action'] != 'deflected':
                image = atlas.parent / clip['file']
                archive.write(image, image.relative_to(ROOT).as_posix())
        archive.write(ROOT / 'art/background-review-v1/colosseum.png',
                      'art/background-review-v1/colosseum.png')
        archive.write(ROOT / 'assets/audio/CREDITS.md', 'CREDITS.md')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, default=ROOT / '.scratch/python')
    parser.add_argument('--output', type=Path, default=ROOT / '.scratch/patch-build/ShieldAttack.zip')
    args = parser.parse_args()
    build(args.runtime, args.output)
