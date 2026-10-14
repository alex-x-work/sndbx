#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["pyyaml"]
# ///
"""A port of bin/sndbx to Python that also runs on Windows."""

import json
import os
import posixpath
import re
import shutil
import signal
import subprocess
import sys

try:
    import yaml
except ImportError:
    sys.exit('Error: PyYAML is missing, pip install pyyaml or run via uv run --script.')

VERSION = '0.15.1'
WINDOWS = os.name == 'nt'


class Error(Exception):
    pass


class ParseError(Error):
    pass


def expand_path(path, base=None):
    """Like Ruby's File.expand_path: expands ~ and resolves PATH against BASE, the current directory by default."""
    return os.path.abspath(os.path.join(base or os.getcwd(), os.path.expanduser(path)))


def to_list(value):
    """Like Ruby's Array(): nil is empty, a list stays, anything else is wrapped."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def inspect(value):
    """Prints a YAML value like Ruby's inspect, which the error messages of the Ruby sndbx use."""
    if value is None:
        return 'nil'
    if isinstance(value, bool):
        return str(value).lower()
    return repr(value)


class OptionParser:
    """The part of Ruby's OptionParser that sndbx uses, so both sndbx print the same help and errors."""

    WIDTH = 32
    INDENT = ' ' * 4

    class Option:
        def __init__(self, short, long, arg, handler):
            self.short = short
            self.long = long
            self.arg = arg
            self.handler = handler

    def __init__(self, banner):
        self._lines = [banner]
        self._options = []

    def separator(self, line=''):
        self._lines.append(line)

    def on(self, short, long, *description, handler, arg=None):
        self._options.append(self.Option(short, long, arg, handler))

        left = f'{short}, {long}' + (f'={arg}' if arg else '')
        right = list(description)
        if len(left) > self.WIDTH:
            self._lines.append(self.INDENT + left)
            left = ''
        for line in right:
            self._lines.append(f'{self.INDENT}{left.ljust(self.WIDTH)} {line}')
            left = ''

    def help(self):
        return '\n'.join(self._lines) + '\n'

    def order(self, args, on_positional=lambda arg: False):
        """Parses the options in ARGS in order and passes each positional to ON_POSITIONAL. Stops after -- or at
        the first positional ON_POSITIONAL rejects, and returns the arguments from there on."""
        args = list(args)
        while args:
            arg = args.pop(0)
            if arg == '--':
                return args
            if arg.startswith('--'):
                self._parse_long(arg, args)
            elif arg.startswith('-') and arg != '-':
                self._parse_short(arg, args)
            elif not on_positional(arg):
                return [arg, *args]
        return []

    def permute(self, args):
        """Parses the options anywhere in ARGS, returns the positionals."""
        positionals = []
        rest = self.order(args, lambda arg: positionals.append(arg) or True)
        return positionals + rest

    def _parse_long(self, arg, args):
        name, equals, value = arg.partition('=')
        matches = [option for option in self._options if option.long == name]
        matches = matches or [option for option in self._options if option.long.startswith(name)]
        if not matches:
            raise ParseError(f'invalid option: {arg}')
        if len(matches) > 1:
            raise ParseError(f'ambiguous option: {name}')

        option = matches[0]
        if not option.arg:
            if equals:
                raise ParseError(f'needless argument: {arg}')
            option.handler()
            return

        if not equals:
            if not args:
                raise ParseError(f'missing argument: {name}')
            value = args.pop(0)
        option.handler(value)

    def _parse_short(self, arg, args):
        letters = arg[1:]
        while letters:
            name, letters = f'-{letters[0]}', letters[1:]
            option = next((option for option in self._options if option.short == name), None)
            if option is None:
                raise ParseError(f'invalid option: {name}')
            if not option.arg:
                option.handler()
                continue

            if not letters:
                if not args:
                    raise ParseError(f'missing argument: {name}')
                letters = args.pop(0)
            option.handler(letters)
            return


def help_option(parser):
    def show_help():
        sys.stdout.write(parser.help())
        sys.exit(0)

    parser.on('-h', '--help', 'Print help', handler=show_help)


# Docker

DOCKER = 'docker'
IMAGE_LABEL = 'sndbx.image'


def docker_command(*args):
    # shutil.which honours PATHEXT, so docker.cmd and docker.bat work on Windows
    docker = shutil.which(DOCKER)
    return [docker, *args] if docker else None


def system(*args):
    """Runs docker with ARGS, returns None if docker is missing, else whether it succeeded."""
    command = docker_command(*args)
    if command is None:
        return None
    sys.stdout.flush()
    return subprocess.run(command).returncode == 0


def quiet_system(*args):
    command = docker_command(*args)
    if command is None:
        return None
    return subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


def check_docker():
    running = quiet_system('info')
    if running is None:
        raise Error('docker is not installed')
    if not running:
        raise Error('docker is not running')


def image_exists(tag):
    return quiet_system('image', 'inspect', tag)


def running_containers(image):
    command = docker_command('ps', '--filter', f'label={IMAGE_LABEL}={image}', '--format', '{{.Names}}')
    result = command and subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    if not result or result.returncode != 0:
        raise Error('failed to list running containers')

    return result.stdout.splitlines()


def stdin_is_terminal():
    if not sys.stdin or not sys.stdin.isatty():
        return False
    if not WINDOWS:
        return True

    # isatty is also true for NUL, a character device; only a console has a console mode
    import ctypes
    import msvcrt

    mode = ctypes.c_uint32()
    handle = msvcrt.get_osfhandle(sys.stdin.fileno())
    return bool(ctypes.windll.kernel32.GetConsoleMode(handle, ctypes.byref(mode)))


def exec_docker(*args):
    command = docker_command(*args)
    sys.stdout.flush()
    if not WINDOWS:
        os.execv(command[0], [DOCKER, *args])

    # os.exec* on Windows starts a new process and exits, which hands the terminal back to the shell
    # while docker still uses it. Wait for docker instead, and leave Ctrl+C to it.
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    sys.exit(subprocess.run(command).returncode)


# Commands

class RunCommand:
    def call(self, args):
        self.run(**self.parse(args))

    def parse(self, args):
        volumes = []
        ports = []
        workdir = None
        docker_args = []
        if '--' in args:
            separator = args.index('--')
            args, docker_args = args[:separator], args[separator + 1:]

        def set_workdir(name):
            nonlocal workdir
            workdir = name

        def list_images():
            if os.path.exists(Settings.PATH):
                for name in Settings().image_names():
                    print(name)
            sys.exit(0)

        parser = OptionParser('Usage: sndbx run IMAGE [options] [-- DOCKER_ARGS]')
        parser.separator()
        parser.separator(f'Runs a sandboxed image from {Settings.PATH}.')
        parser.separator(f'Mounts the current directory unless a volume is mounted in {Sandbox.MOUNT_ROOT}.')
        parser.separator("Passes DOCKER_ARGS to docker run after the image's docker_args.")
        parser.separator()
        parser.on('-v', '--volume',
                  f'Mount SRC at DST, {Sandbox.MOUNT_ROOT}/<basename> by default,',
                  "with docker's OPTS, e.g. ro, repeatable",
                  arg='SRC[:DST[:OPTS]]', handler=volumes.append)
        parser.on('-w', '--workdir',
                  f"Start in {Sandbox.MOUNT_ROOT}/<NAME>, or NAME if it's absolute,",
                  f'the last directory volume in {Sandbox.MOUNT_ROOT} by default',
                  arg='NAME', handler=set_workdir)
        parser.on('-p', '--publish', 'Publish a port as HOST:CONTAINER, PORT means PORT:PORT, repeatable',
                  arg='PORT', handler=ports.append)
        parser.on('-l', '--list', 'Print image names', handler=list_images)
        help_option(parser)

        positionals = parser.permute(args)
        if len(positionals) != 1:
            raise Error('expected exactly one image')

        return {'image': positionals[0], 'volumes': volumes, 'ports': ports, 'workdir': workdir,
                'docker_args': docker_args}

    def run(self, image, **options):
        Sandbox(image=Settings().image(image), **options).call()


class BuildCommand:
    def call(self, args):
        self.run(**self.parse(args))

    def parse(self, args):
        build_all = False

        def set_all():
            nonlocal build_all
            build_all = True

        def list_images():
            for name in Builder(Settings()).image_names():
                print(name)
            sys.exit(0)

        parser = OptionParser('Usage: sndbx build IMAGE | --all')
        parser.separator()
        parser.separator(f'Builds an image from {Builder.IMAGES_DIR_SETTING}/IMAGE, always without the docker cache.')
        parser.separator(f"Builds {Builder.BASE_NAME} first if the image needs it and it doesn't exist yet.")
        parser.separator()
        parser.on('-a', '--all', f'Build {Builder.BASE_NAME}, then every other image', handler=set_all)
        parser.on('-l', '--list', 'Print image names', handler=list_images)
        help_option(parser)

        positionals = parser.permute(args)
        if not (not positionals if build_all else len(positionals) == 1):
            raise Error('expected exactly one image, or --all')

        return {'image': positionals[0] if positionals else None}

    def run(self, image):
        Builder(Settings()).call(image=image)


class ExecCommand:
    def call(self, args):
        self.run(**self.parse(args))

    def parse(self, args):
        user = None
        list_containers = False
        positionals = []

        def set_user(name):
            nonlocal user
            if not name:
                raise Error('expected a user')
            user = name

        def set_list():
            nonlocal list_containers
            list_containers = True

        parser = OptionParser('Usage: sndbx exec IMAGE CONTAINER COMMAND [ARGS] | IMAGE --list')
        parser.separator()
        parser.separator('Runs COMMAND in a running sandbox of IMAGE, like docker exec -i,')
        parser.separator('with -t when stdin is a terminal.')
        parser.separator('Options go before COMMAND, everything from COMMAND on goes to it.')
        parser.separator()
        parser.on('-u', '--user', "Run COMMAND as USER, the container's user by default", arg='USER',
                  handler=set_user)
        parser.on('-l', '--list', "Print IMAGE's running containers", handler=set_list)
        help_option(parser)

        # Stop at COMMAND, the third positional, so its own options reach it
        def take_positional(arg):
            if len(positionals) == 2:
                return False
            positionals.append(arg)
            return True

        rest = parser.order(args, take_positional)

        # -- ends the options, the words after it start with the missing positionals
        while len(positionals) < 2 and rest:
            positionals.append(rest.pop(0))

        if list_containers:
            if len(positionals) != 1 or rest:
                raise Error('expected exactly one image')

            return {'image': positionals[0], 'list_containers': True}

        if len(positionals) != 2 or not rest:
            raise Error('expected an image, a container and a command')

        return {'image': positionals[0], 'container': positionals[1], 'command': rest, 'user': user}

    def run(self, image, list_containers=False, **options):
        if list_containers:
            check_docker()
            for name in running_containers(image):
                print(name)
        else:
            Settings().image(image)
            self.exec_in(image, **options)

    def exec_in(self, image, container, command, user):
        check_docker()
        containers = running_containers(image)
        if not containers:
            raise Error(f'no running {image} sandbox')
        if container not in containers:
            raise Error(f"container '{container}' is not a running {image} sandbox, "
                        f"expected one of: {', '.join(containers)}")

        # Without a terminal on stdin docker refuses -t, which breaks pipes and scripts
        tty_args = ['-it'] if stdin_is_terminal() else ['-i']
        user_args = [f'--user={user}'] if user else []
        exec_docker('exec', *tty_args, *user_args, container, *command)


class CompleteCommand:
    """Prints the completions of the words in SNDBX_COMPLETE, a JSON list that ends with the word being
    completed, one per line. completions/sndbx.ps1 calls it, an environment variable passes empty words and
    quotes through that PowerShell 5.1 mangles in arguments.

    With --python it prints the python and the script it runs with instead, so that completions can skip
    sndbx.cmd and uv, which take longer than the completion itself."""

    ENV = 'SNDBX_COMPLETE'

    def call(self, args):
        if args == ['--python']:
            print(sys.executable)
            print(os.path.realpath(__file__))
            return

        try:
            words = json.loads(os.environ.get(self.ENV, ''))
        except ValueError:
            words = None
        if not (isinstance(words, list) and words and all(isinstance(word, str) for word in words)):
            raise Error(f'expected a JSON list of words in {self.ENV}')

        # PowerShell reads it as UTF-8, whatever the console's code page
        sys.stdout.reconfigure(encoding='utf-8')
        for candidate in Completer(words[:-1], words[-1]).candidates():
            print(candidate)


class CLI:
    COMMANDS = {'run': RunCommand, 'build': BuildCommand, 'exec': ExecCommand}
    HIDDEN_COMMANDS = {'__complete': CompleteCommand}

    def call(self, args):
        args = args or ['-h']

        def show_version():
            print(f'sndbx {VERSION}')
            sys.exit(0)

        parser = OptionParser('Usage: sndbx command [options]')
        parser.separator()
        parser.separator('Commands:')
        parser.separator('    run IMAGE                       Run a sandboxed image')
        parser.separator('    build IMAGE                     Build an image')
        parser.separator('    exec IMAGE CONTAINER COMMAND    Run a command in a running sandbox')
        parser.separator()
        parser.separator("Run 'sndbx command --help' for a command's options.")
        parser.separator()
        parser.on('-V', '--version', 'Print version', handler=show_version)
        help_option(parser)

        rest = parser.order(args)
        if not rest:
            sys.stderr.write(parser.help())
            sys.exit(1)

        name = rest.pop(0)
        command = self.COMMANDS.get(name) or self.HIDDEN_COMMANDS.get(name)
        if command is None:
            raise Error(f"unknown command '{name}', expected one of: {', '.join(self.COMMANDS)}")

        command().call(rest)


# Settings, builds and sandboxes

class Settings:
    DIR = os.path.join(os.path.expanduser('~'), '.config', 'sndbx')
    PATH = os.path.join(DIR, 'settings.yml')
    HOME_ROOT = '/home'
    DEFAULT_TAG_PREFIX = 'sndbx'
    TAG_PREFIX_FORMAT = re.compile(r'[a-z0-9]+(?:[._/-][a-z0-9]+)*')

    EXAMPLE = """\
# tag_prefix: sndbx # optional, images are tagged <tag_prefix>:<name>
images:
  - name: claude
    user: ubuntu
    # tag: my-claude:latest # optional, defaults to <tag_prefix>:<name>
    # config_dir: ~/.claude_docker # optional, relative paths resolve against ~/.config/sndbx, defaults to ~/.config/sndbx/<name>
    # config_target: .claude # optional, relative to the user's home, defaults to .<name>
    # ports: ['3000'] # optional, always published; quote them, YAML reads 8080:22 as a number
    # docker_args: ['--memory=8g'] # optional, extra docker run arguments
# images_dir: ~/src/sndbx/images # optional, where build finds images, defaults to images/ next to bin/
"""

    def __init__(self):
        self._settings = None

    def image(self, name):
        image = next((entry for entry in self._images() if entry['name'] == name), None)
        if image is None:
            raise Error(f"unknown image '{name}', expected one of: {', '.join(self.image_names())}")

        user = image.get('user')
        if user is None or user is False:
            raise Error(f"image '{name}' has no user in {self.PATH}")

        ports = to_list(image.get('ports'))
        for port in ports:
            if not isinstance(port, str):
                raise Error(f"image '{name}' has an unquoted port in {self.PATH}, YAML read it as {inspect(port)}; "
                            'quote it, e.g. "3000"')

        docker_args = to_list(image.get('docker_args'))
        if not all(isinstance(arg, str) for arg in docker_args):
            raise Error(f"image '{name}' has docker_args that aren't strings in {self.PATH}")

        config_dir = image.get('config_dir')
        if not (config_dir is None or (isinstance(config_dir, str) and config_dir)):
            raise Error(f"image '{name}' has a config_dir that isn't a path in {self.PATH}")

        config_target = image.get('config_target') or f'.{name}'
        return {
            'name': name,
            'tag': image.get('tag') or f'{self.tag_prefix()}:{name}',
            'user': user,
            'config_dir': expand_path(config_dir or name, self.DIR),
            'config_target': posixpath.join(self.HOME_ROOT, str(user), config_target.lstrip('/')),
            'ports': ports,
            'docker_args': docker_args,
        }

    def image_names(self):
        return [entry['name'] for entry in self._images()]

    def tag_prefix(self):
        return self._optional_setting('tag_prefix') or self.DEFAULT_TAG_PREFIX

    # realpath resolves symlinks, so the default finds the repo when bin/sndbx.py is linked into PATH,
    # but not when it's copied.
    def images_dir(self):
        images_dir = self._optional_setting('images_dir')
        if images_dir:
            return expand_path(images_dir, self.DIR)

        return os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), 'images')

    def _images(self):
        return self._load_settings().get('images') or []

    def _optional_setting(self, key):
        return self._load_settings().get(key) if os.path.exists(self.PATH) else None

    def _load_settings(self):
        if self._settings is None:
            self._settings = self._validate(self._load())
        return self._settings

    def _validate(self, settings):
        if not isinstance(settings, dict):
            raise Error(f'invalid {self.PATH}: expected a mapping with an images list')

        prefix = settings.get('tag_prefix')
        if not (prefix is None or (isinstance(prefix, str) and self.TAG_PREFIX_FORMAT.fullmatch(prefix))):
            raise Error(f'invalid {self.PATH}: tag_prefix must be a lowercase image name, e.g. sndbx')

        images_dir = settings.get('images_dir')
        if not (images_dir is None or isinstance(images_dir, str)):
            raise Error(f'invalid {self.PATH}: images_dir must be a path')

        images = settings.get('images') or []
        if not isinstance(images, list):
            raise Error(f'invalid {self.PATH}: images must be a list')

        for number, entry in enumerate(images, 1):
            if not (isinstance(entry, dict) and isinstance(entry.get('name'), str)):
                raise Error(f'invalid {self.PATH}: image {number} must be a mapping with a name')

        return settings

    def _load(self):
        if not os.path.exists(self.PATH):
            self._create_example()

        try:
            with open(self.PATH, encoding='utf-8') as file:
                settings = yaml.safe_load(file)
        except yaml.YAMLError as error:
            raise Error(f'invalid {self.PATH}: {yaml_message(error)}')

        return {} if settings is None else settings

    def _create_example(self):
        os.makedirs(self.DIR, exist_ok=True)
        with open(self.PATH, 'w', encoding='utf-8') as file:
            file.write(self.EXAMPLE)

        sys.exit(f'Created an example config at {self.PATH}, edit it and run again.')


def yaml_message(error):
    """PyYAML's messages span several lines, keep the problem and where it is."""
    message = getattr(error, 'problem', None) or str(error)
    mark = getattr(error, 'problem_mark', None)
    if mark is not None:
        message += f' at line {mark.line + 1} column {mark.column + 1}'
    return message


class Builder:
    BASE_NAME = 'base'
    BASE_FROM_FORMAT = re.compile(rf'^FROM\s+\$\{{TAG_PREFIX\}}:{BASE_NAME}(?:\s|$)', re.MULTILINE)
    IMAGES_DIR_SETTING = 'images_dir'

    def __init__(self, settings):
        self._tag_prefix = settings.tag_prefix()
        self._images_dir = settings.images_dir()

    def image_names(self):
        self._check_images_dir()
        return sorted(name for name in os.listdir(self._images_dir)
                      if not name.startswith('.') and os.path.isfile(os.path.join(self._images_dir, name, 'Dockerfile')))

    def call(self, image):
        names = self.image_names()
        if image is not None and image not in names:
            raise Error(f"unknown image '{image}', expected one of: {', '.join(names)}")

        check_docker()

        if image is not None:
            self._build_with_base(image)
        else:
            for name in [self.BASE_NAME, *(name for name in names if name != self.BASE_NAME)]:
                self._build_with_base(name)

    def _build_with_base(self, name):
        if name != self.BASE_NAME and self._needs_base(name) and not self._base_exists():
            print(f"==> {self._tag_for(self.BASE_NAME)} doesn't exist yet")
            self._build(self.BASE_NAME)

        self._build(name)

    def _build(self, name):
        tag = self._tag_for(name)

        # Only images FROM ${TAG_PREFIX}:base declare the arg, docker warns about unused ones.
        args = ['--build-arg', f'TAG_PREFIX={self._tag_prefix}'] if self._needs_base(name) else []

        print(f'==> Building {tag} from {self._image_dir(name)}')
        if not system('build', '--no-cache', *args, '-t', tag, self._image_dir(name)):
            raise Error(f'failed to build {tag}')

    def _needs_base(self, name):
        with open(os.path.join(self._image_dir(name), 'Dockerfile'), encoding='utf-8') as file:
            return bool(self.BASE_FROM_FORMAT.search(file.read()))

    def _base_exists(self):
        return image_exists(self._tag_for(self.BASE_NAME))

    def _tag_for(self, name):
        return f'{self._tag_prefix}:{name}'

    def _image_dir(self, name):
        return os.path.join(self._images_dir, name)

    def _check_images_dir(self):
        if os.path.isdir(self._images_dir):
            return

        raise Error(f'images directory {self._images_dir} does not exist, '
                    f'set {self.IMAGES_DIR_SETTING} in {Settings.PATH}')


class Sandbox:
    RUN_OPTIONS = ['run', '--rm', '-it']
    MOUNT_ROOT = '/workspace'
    PORT_FORMAT = re.compile(r'(?:[\d.]+:)?\d+(?::\d+)?(?:/(?:tcp|udp))?', re.ASCII)
    BARE_PORT_FORMAT = re.compile(r'(\d+)(/(?:tcp|udp))?', re.ASCII)
    MAX_PORT = 65_535
    # On Windows SRC may start with a drive letter, whose colon doesn't end it
    VOLUME_FORMAT = re.compile(r'((?:[A-Za-z]:)?[^:]+)(?::([^:]+))?(?::([^:]+))?' if WINDOWS else
                               r'([^:]+)(?::([^:]+))?(?::([^:]+))?')

    def __init__(self, image, volumes, ports, workdir, docker_args):
        self._image = image
        self._docker_args = image['docker_args'] + docker_args
        self._volumes = self._parse_volumes(volumes)
        self._ports = list(dict.fromkeys(self._normalize_port(port) for port in image['ports'] + ports))
        self._workdir = self._workdir_target(workdir) if workdir else self._default_workdir()

    def call(self):
        check_docker()
        self._check_image()
        self._check_workdir()
        os.makedirs(self._image['config_dir'], exist_ok=True)

        exec_docker(*self.RUN_OPTIONS, f"--label={IMAGE_LABEL}={self._image['name']}", f'--workdir={self._workdir}',
                    *self._volume_args(), *self._port_args(), *self._docker_args, self._image['tag'])

    def _parse_volumes(self, specs):
        volumes = [self._parse_volume(spec) for spec in specs]
        if not any(self._workspace(volume['target']) for volume in volumes):
            volumes.insert(0, self._parse_volume(os.getcwd()))

        targets = [volume['target'] for volume in volumes]
        for target in dict.fromkeys(targets):
            if targets.count(target) > 1:
                raise Error(f'more than one volume is mounted at {target}')

        return volumes

    # Docker's -v syntax, SRC[:DST[:OPTS]], except that SRC is always a host path
    # and DST defaults to MOUNT_ROOT/<basename>. DST is a container path, so always POSIX.
    def _parse_volume(self, spec):
        match = self.VOLUME_FORMAT.fullmatch(spec)
        if not match:
            raise Error(f"invalid volume '{spec}', expected SRC[:DST[:OPTS]]")

        source = expand_path(match[1])
        if not os.path.exists(source):
            raise Error(f'{source} does not exist')
        if self._forbidden(source):
            raise Error(f'refusing to mount {source}')

        if match[2]:
            if not match[2].startswith('/'):
                raise Error(f"invalid volume '{spec}', DST must be an absolute path")

            target = posixpath.normpath(match[2])
        else:
            if not os.path.isdir(source):
                raise Error(f'{source} is not a directory')

            target = self._mount_target(os.path.basename(source))

        return {'source': source, 'target': target, 'options': match[3]}

    @staticmethod
    def _forbidden(source):
        """The home directory, or a filesystem root such as / or C:\\, also through links."""
        real = os.path.realpath(source)
        if os.path.dirname(real) == real:
            return True
        try:
            return os.path.samefile(os.path.expanduser('~'), source)
        except OSError:
            return False

    def _volume_args(self):
        volumes = [':'.join(part for part in (volume['source'], volume['target'], volume['options']) if part)
                   for volume in self._volumes]
        volumes.append(f"{self._image['config_dir']}:{self._image['config_target']}")
        return [arg for volume in volumes for arg in ('-v', volume)]

    def _directory_targets(self):
        return [volume['target'] for volume in self._volumes if os.path.isdir(volume['source'])]

    def _default_workdir(self):
        targets = self._directory_targets()
        workspace_targets = [target for target in targets if self._workspace(target)]
        return (workspace_targets or targets or [None])[-1]

    def _workdir_target(self, name):
        return posixpath.normpath(name) if name.startswith('/') else self._mount_target(name)

    def _workdir_name(self, target):
        prefix = f'{self.MOUNT_ROOT}/'
        return target[len(prefix):] if target.startswith(prefix) else target

    def _workspace(self, target):
        return target == self.MOUNT_ROOT or target.startswith(f'{self.MOUNT_ROOT}/')

    def _normalize_port(self, port):
        if not self.PORT_FORMAT.fullmatch(port):
            raise Error(f"invalid port '{port}', expected PORT or HOST:CONTAINER")

        if any(number > self.MAX_PORT for number in self._port_numbers(port)):
            raise Error(f"invalid port '{port}', ports go up to {self.MAX_PORT}")

        match = self.BARE_PORT_FORMAT.fullmatch(port)
        return f'{match[1]}:{match[1]}{match[2] or ""}' if match else port

    @staticmethod
    def _port_numbers(port):
        return [int(number) for number in port.split('/')[0].split(':')[-2:]]

    def _port_args(self):
        return [arg for port in self._ports for arg in ('-p', port)]

    def _mount_target(self, name):
        return posixpath.join(self.MOUNT_ROOT, name)

    def _check_image(self):
        if not image_exists(self._image['tag']):
            raise Error(f"docker image '{self._image['tag']}' does not exist")

    def _check_workdir(self):
        names = [self._workdir_name(target) for target in self._directory_targets()]
        if not names:
            raise Error('no directory volume to start in')
        if self._workdir in self._directory_targets():
            return

        raise Error(f"workdir '{self._workdir_name(self._workdir)}' is not a directory volume, "
                    f"expected one of: {', '.join(names)}")


# Completion

def complete_paths(prefix, directories_only=False):
    """Returns the files, or only the directories, whose path starts with PREFIX, spelled the way PREFIX is."""
    separators = '/\\' if WINDOWS else '/'
    cut = max(prefix.rfind(separator) for separator in separators) + 1
    if WINDOWS and cut < 2 and re.match(r'[A-Za-z]:', prefix):
        cut = 2
    head, name = prefix[:cut], prefix[cut:]

    try:
        entries = list(os.scandir(os.path.expanduser(head) if head else '.'))
    except OSError:
        return []

    return sorted(f'{head}{entry.name}' for entry in entries
                  if (name.startswith('.') or not entry.name.startswith('.'))
                  and os.path.normcase(entry.name).startswith(os.path.normcase(name))
                  and (not directories_only or entry.is_dir()))


class Completer:
    """Completes like completions/_sndbx, on whole words: PowerShell doesn't split them at = and :."""

    COMMANDS = ['run', 'build', 'exec']
    CLI_OPTIONS = ['-V', '--version', '-h', '--help']
    RUN_OPTIONS = ['-v', '--volume', '-w', '--workdir', '-p', '--publish', '-l', '--list', '-h', '--help']
    BUILD_OPTIONS = ['-a', '--all', '-l', '--list', '-h', '--help']
    EXEC_OPTIONS = ['-u', '--user', '-l', '--list', '-h', '--help']
    VOLUME = ('-v', '--volume')
    WORKDIR = ('-w', '--workdir')
    PUBLISH = ('-p', '--publish')
    USER = ('-u', '--user')

    def __init__(self, words, current):
        self._words = words
        self._current = current

    def candidates(self):
        if not self._words:
            return self._matching(self.CLI_OPTIONS if self._current.startswith('-') else self.COMMANDS)

        command, words = self._words[0], self._words[1:]
        # Everything after -- goes to docker run
        if command == 'run' and '--' in words:
            return self._docker_args(words[words.index('--') + 1:])
        if command == 'run':
            return self._run(words)
        if command == 'build':
            return self._build(words)
        if command == 'exec':
            return self._exec(words)
        return []

    def _matching(self, candidates, prefix=None):
        prefix = self._current if prefix is None else prefix
        return [candidate for candidate in candidates if candidate.startswith(prefix)]

    def _option_value(self, words, options):
        """Returns the option, what precedes the value in the current word and the value when the current word
        is the value of one of OPTIONS, given after it or after = in the same word."""
        option, equals, value = self._current.partition('=')
        if equals and option in options:
            return option, f'{option}=', value
        if words and words[-1] in options:
            return words[-1], '', self._current
        return None

    def _run(self, words):
        has_image, has_workspace, workdirs = self._scan(words)
        value = self._option_value(words, self.VOLUME + self.WORKDIR + self.PUBLISH)

        if value is None:
            if self._current.startswith('-'):
                return self._matching(self.RUN_OPTIONS)
            return [] if has_image else self._matching(self._run_images())

        option, lead, prefix = value
        if option in self.VOLUME:
            # Nothing completes DST or OPTS, after a colon that isn't a drive letter's
            source = prefix[2:] if WINDOWS and re.match(r'[A-Za-z]:', prefix) else prefix
            if ':' in source:
                return []
            return [lead + path for path in complete_paths(prefix, directories_only=True)]
        if option in self.WORKDIR:
            # The current directory is mounted unless a volume is in /workspace
            if not has_workspace:
                workdirs.append(os.path.basename(os.getcwd()))
            return [lead + workdir for workdir in dict.fromkeys(workdirs) if workdir.startswith(prefix)]
        return []

    def _scan(self, words):
        """Looks for an image and volumes in WORDS, skipping option values."""
        has_image = has_workspace = False
        workdirs = []
        words = iter(words)
        for word in words:
            option, equals, value = word.partition('=') if word.startswith('--') else (word, '', '')
            if option in self.VOLUME + self.WORKDIR + self.PUBLISH:
                value = value if equals else next(words, None)
                if option in self.VOLUME and value is not None:
                    workdir = self._volume_workdir(value)
                    if workdir:
                        workdirs.append(workdir[0])
                        has_workspace = has_workspace or workdir[1]
            elif word in ('-a', '--all') or not word.startswith('-'):
                has_image = True
        return has_image, has_workspace, workdirs

    @staticmethod
    def _volume_workdir(spec):
        """Returns how -w names a directory volume, by its path in /workspace or else its absolute path, and
        whether it's in /workspace."""
        match = Sandbox.VOLUME_FORMAT.fullmatch(re.sub('["\']', '', spec))
        if not match or not os.path.isdir(expand_path(match[1])):
            return None

        if not match[2]:
            return os.path.basename(expand_path(match[1])), True
        target = posixpath.normpath(match[2])
        if target.startswith(f'{Sandbox.MOUNT_ROOT}/'):
            return target[len(Sandbox.MOUNT_ROOT) + 1:], True
        return target, target == Sandbox.MOUNT_ROOT

    def _build(self, words):
        has_image = self._scan(words)[0]
        if self._current.startswith('-'):
            return self._matching(self.BUILD_OPTIONS)
        if has_image:
            return []
        try:
            return self._matching(Builder(Settings()).image_names())
        except Error:
            return []

    def _exec(self, words):
        positionals = []
        options_done = list_containers = False

        # Count the positionals, skipping option values; COMMAND, the third, ends the options
        words_left = iter(words)
        for word in words_left:
            if options_done:
                positionals.append(word)
            elif word in self.USER:
                next(words_left, None)
            elif word == '--':
                options_done = True
            elif word in ('-l', '--list'):
                list_containers = True
            elif not word.startswith('-'):
                positionals.append(word)
            if len(positionals) >= 3:
                break

        if len(positionals) >= 3 or (list_containers and positionals):
            return []
        if self._option_value(words, self.USER):
            return []
        if self._current.startswith('-') and not options_done:
            return self._matching(self.EXEC_OPTIONS)
        if not positionals:
            return self._matching(self._run_images())
        if len(positionals) == 1:
            try:
                check_docker()
                return self._matching(running_containers(positionals[0]))
            except Error:
                return []
        return []

    def _run_images(self):
        if not os.path.exists(Settings.PATH):
            return []
        try:
            return Settings().image_names()
        except Error:
            return []

    def _docker_args(self, args):
        """Completes with docker's own completion, files if docker has none."""
        # Docker completes the value of --flag=value without the flag
        lead, equals, prefix = self._current.partition('=') if self._current.startswith('-') else ('', '', '')
        lead, prefix = (f'{lead}=', prefix) if equals else ('', self._current)

        # Docker 26+ prints one candidate per line, optionally followed by a tab and a description, then :DIRECTIVE
        command = docker_command('__complete', 'run', *args, self._current)
        result = command and subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        lines = result.stdout.splitlines() if result and result.returncode == 0 else []
        directive = -1
        if lines and re.fullmatch(r':\d+', lines[-1]):
            directive = int(lines.pop()[1:])

        # 1: error
        if directive > 0 and directive & 1:
            return []

        candidates = [lead + line for line in (line.split('\t')[0] for line in lines) if line.startswith(prefix)]
        if candidates:
            return candidates
        # 4: no file completion
        if directive > 0 and directive & 4:
            return []
        # 16: directories only
        return [lead + path for path in complete_paths(prefix, directories_only=directive > 0 and directive & 16)]


def main():
    try:
        CLI().call(sys.argv[1:])
    except Error as error:
        sys.exit(f'Error: {error}.')
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == '__main__':
    main()
