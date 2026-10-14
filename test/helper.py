"""Shared setup for the tests of bin/sndbx.py: a temporary HOME and a fake docker that records its arguments."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from dataclasses import dataclass

import yaml

BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'bin', 'sndbx.py')
WINDOWS = os.name == 'nt'

# Logs its arguments as JSON to DOCKER_LOG and answers like docker from the files the tests write
FAKE_DOCKER = textwrap.dedent('''\
    import json, os, sys

    args = sys.argv[1:]
    with open(os.environ['DOCKER_LOG'], 'a', encoding='utf-8') as log:
        log.write(json.dumps(args) + '\\n')

    def read_lines(name):
        path = os.environ[name]
        if not os.path.exists(path):
            return []
        with open(path, encoding='utf-8') as file:
            return file.read().splitlines()

    if args == ['info']:
        sys.exit(1 if 'DOCKER_STOPPED' in os.environ else 0)
    if args[:2] == ['image', 'inspect']:
        sys.exit(0 if args[2] in read_lines('DOCKER_IMAGES') else 1)
    if args[:1] == ['ps']:
        for line in read_lines('DOCKER_CONTAINERS'):
            image, name = line.split()
            if args[2] == f'label=sndbx.image={image}':
                print(name)
        sys.exit(0)
    if args[:1] == ['build']:
        tag = args[args.index('-t') + 1]
        if os.environ.get('DOCKER_BROKEN') == tag:
            sys.exit(1)
        with open(os.environ['DOCKER_IMAGES'], 'a', encoding='utf-8') as file:
            file.write(tag + '\\n')
        sys.exit(0)
    if args[:1] == ['__complete']:
        # Fails like docker before 26 without DOCKER_COMPLETIONS
        path = os.environ['DOCKER_COMPLETIONS']
        if not os.path.exists(path):
            sys.exit(1)
        with open(path, encoding='utf-8') as file:
            sys.stdout.write(file.read())
''')


@dataclass
class Result:
    out: str
    err: str
    returncode: int

    @property
    def success(self):
        return self.returncode == 0


class SndbxTestCase(unittest.TestCase):
    def setUp(self):
        self.root = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.home = self.mkdir('home')
        self.bin = self.mkdir('bin')
        self.no_bin = self.mkdir('no-bin')
        self.work = self.mkdir('work/project')
        self.images_dir = self.mkdir('images')
        self.docker_log = os.path.join(self.root, 'docker.log')
        self.docker_images = os.path.join(self.root, 'docker-images')
        self.docker_containers = os.path.join(self.root, 'docker-containers')
        self.docker_completions = os.path.join(self.root, 'docker-completions')
        self.write_fake_docker()

    def mkdir(self, path):
        directory = os.path.join(self.root, *path.split('/'))
        os.makedirs(directory, exist_ok=True)
        return directory

    def write_file(self, path, content=''):
        with open(path, 'w', encoding='utf-8') as file:
            file.write(content)

    def write_fake_docker(self):
        script = os.path.join(self.root, 'fake_docker.py')
        self.write_file(script, FAKE_DOCKER)
        if WINDOWS:
            self.write_file(os.path.join(self.bin, 'docker.cmd'), f'@"{sys.executable}" "{script}" %*\n')
        else:
            docker = os.path.join(self.bin, 'docker')
            self.write_file(docker, f'#!{sys.executable}\n' + FAKE_DOCKER)
            os.chmod(docker, 0o755)

    def env(self, docker=True, **env):
        return {
            **os.environ,
            'HOME': self.home,
            'USERPROFILE': self.home,
            'PATH': self.bin if docker else self.no_bin,
            'DOCKER_LOG': self.docker_log,
            'DOCKER_IMAGES': self.docker_images,
            'DOCKER_CONTAINERS': self.docker_containers,
            'DOCKER_COMPLETIONS': self.docker_completions,
            **env,
        }

    def sndbx(self, *args, docker=True, stdin=subprocess.DEVNULL, **env):
        result = subprocess.run([sys.executable, BIN, *args], cwd=self.work, env=self.env(docker, **env),
                                stdin=stdin, capture_output=True, text=True, encoding='utf-8')
        return Result(result.stdout, result.stderr, result.returncode)

    def settings_path(self, home=None):
        return os.path.join(home or self.home, '.config', 'sndbx', 'settings.yml')

    def write_settings(self, home=None, **settings):
        self.write_settings_file(yaml.safe_dump(settings), home=home)

    def write_settings_file(self, content, home=None):
        path = self.settings_path(home)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.write_file(path, content)

    def write_dockerfile(self, name, content):
        self.write_file(os.path.join(self.mkdir(f'images/{name}'), 'Dockerfile'), content)

    def add_docker_image(self, tag):
        with open(self.docker_images, 'a', encoding='utf-8') as file:
            file.write(f'{tag}\n')

    def add_docker_container(self, image, name):
        with open(self.docker_containers, 'a', encoding='utf-8') as file:
            file.write(f'{image} {name}\n')

    def docker_calls(self):
        if not os.path.exists(self.docker_log):
            return []
        with open(self.docker_log, encoding='utf-8') as file:
            return [json.loads(line) for line in file]
