#!/usr/bin/env python3
"""Check local skill packaging. Requires PyYAML; no network or host mutations."""
import argparse
import ast
from pathlib import Path
import re
import sys

try:
    import yaml
except ImportError:
    sys.exit('PyYAML is required; run in an environment with PyYAML installed.')

EXPECTED = {
    'samo-evolution-engineering', 'samo-research-methodology',
    'samo-sandbox-security', 'samo-observatory-design',
}


class UniqueLoader(yaml.SafeLoader):
    pass


def unique_mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise ValueError('duplicate YAML key: ' + str(key))
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
                             unique_mapping)


def check(root):
    errors = []
    names = {path.name for path in root.iterdir() if path.is_dir()}
    if names != EXPECTED:
        errors.append('unexpected/missing skill directories: ' + str(names ^ EXPECTED))
    documents = sorted(root.rglob('*.md'))
    link_count = 0
    for name in sorted(EXPECTED):
        path = root / name / 'SKILL.md'
        if not path.is_file():
            errors.append(str(path) + ': missing entrypoint')
            continue
        text = path.read_text(encoding='utf-8')
        match = re.match(r'\A---\n(.*?)\n---\n(.+)\Z', text, re.S)
        if not match:
            errors.append(str(path) + ': invalid frontmatter/body')
            continue
        try:
            data = yaml.load(match[1], Loader=UniqueLoader)
            if not isinstance(data, dict):
                raise ValueError('frontmatter is not a mapping')
            if data.get('name') != name or len(name) >= 64:
                raise ValueError('name mismatch or too long')
            desc = data.get('description')
            if not isinstance(desc, str) or not 1 <= len(desc.strip()) <= 1024:
                raise ValueError('description missing or too long')
        except (yaml.YAMLError, ValueError, TypeError) as error:
            errors.append(str(path) + ': ' + str(error))
    for path in documents:
        text = path.read_text(encoding='utf-8')
        if '[TODO:' in text:
            errors.append(str(path) + ': unfinished scaffold')
        # All links in this package use ordinary inline Markdown destinations.
        for destination in re.findall(r'\]\(([^)]+)\)', text):
            link_count += 1
            if destination.startswith(('https://', 'http://', '#')):
                continue
            if '://' in destination or destination.startswith('/'):
                errors.append(str(path) + ': nonportable link ' + destination)
                continue
            target = (path.parent / destination.split('#', 1)[0]).resolve()
            if root.resolve() not in target.parents or not target.is_file():
                errors.append(str(path) + ': broken/outside link ' + destination)
    scripts = sorted(root.rglob('*.py'))
    for path in scripts:
        try:
            ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
        except SyntaxError as error:
            errors.append(str(error))
    if errors:
        for error in errors:
            print('FAIL: ' + error, file=sys.stderr)
        return 1
    print(f'PASS: {len(EXPECTED)} skills, {len(documents)} Markdown files, '
          f'{link_count} links, {len(scripts)} Python scripts; '
          'remote URLs and runtime behavior are not checked here')
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path, help='prepared-skills or .agents/skills')
    args = parser.parse_args()
    if not args.root.is_dir():
        parser.error('root is not a directory')
    return check(args.root)


if __name__ == '__main__':
    sys.exit(main())
