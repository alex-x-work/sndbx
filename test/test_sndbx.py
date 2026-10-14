"""Tests of bin/sndbx.py, ported from test/sndbx_test.rb."""

import contextlib
import os
import re
import shlex
import subprocess
import sys
import threading
import time
import unittest

import yaml

from helper import BIN, WINDOWS, SndbxTestCase

REPO_IMAGES_DIR = os.path.join(os.path.dirname(os.path.dirname(BIN)), 'images')


class SndbxTest(SndbxTestCase):
    def sndbx(self, *args, home=None, **kwargs):
        if home is not None:
            kwargs.update(HOME=home, USERPROFILE=home)
        return super().sndbx(*args, **kwargs)

    def test_no_arguments_prints_help(self):
        self.assert_help('Usage: sndbx command [options]', self.sndbx())

    def test_help(self):
        self.assert_help('Usage: sndbx command [options]', self.sndbx('-h'))

    def test_run_help(self):
        self.assert_help('Usage: sndbx run IMAGE [options] [-- DOCKER_ARGS]', self.sndbx('run', '-h'))

    def test_build_help(self):
        self.assert_help('Usage: sndbx build IMAGE | --all', self.sndbx('build', '--help'))

    def test_exec_help(self):
        self.assert_help('Usage: sndbx exec IMAGE CONTAINER COMMAND [ARGS] | IMAGE --list', self.sndbx('exec', '-h'))

    def test_resume_help(self):
        self.assert_help('Usage: sndbx resume IMAGE CONTAINER | IMAGE --list', self.sndbx('resume', '-h'))

    def test_logs_help(self):
        self.assert_help('Usage: sndbx logs [options]', self.sndbx('logs', '-h'))

    def test_version(self):
        result = self.sndbx('-V')

        self.assertTrue(result.success)
        self.assertRegex(result.out, r'\Asndbx \d+\.\d+\.\d+\n\Z')

    def test_unknown_command(self):
        self.assert_error("unknown command 'foo', expected one of: run, build, exec, resume, logs", self.sndbx('foo'))

    def test_invalid_option(self):
        self.assert_error('invalid option: --bogus', self.sndbx('--bogus'))

    def test_first_run_creates_example_settings(self):
        result = self.sndbx('run', 'claude')

        self.assertFalse(result.success)
        self.assertEqual(f'Created an example config at {self.settings_path()}, edit it and run again.\n', result.err)
        with open(self.settings_path(), encoding='utf-8') as file:
            self.assertEqual(['claude'], [image['name'] for image in yaml.safe_load(file)['images']])

    def test_unknown_image(self):
        self.write_settings(images=[{'name': 'claude', 'user': 'ubuntu'}, {'name': 'codex', 'user': 'ubuntu'}])

        self.assert_error("unknown image 'nope', expected one of: claude, codex", self.sndbx('run', 'nope'))

    def test_image_without_user(self):
        self.write_settings(images=[{'name': 'claude'}])

        self.assert_error(f"image 'claude' has no user in {self.settings_path()}", self.sndbx('run', 'claude'))

    def test_unquoted_port(self):
        self.write_settings(images=[{'name': 'claude', 'user': 'ubuntu', 'ports': [3000]}])

        self.assert_error(f"image 'claude' has an unquoted port in {self.settings_path()}, YAML read it as 3000; "
                          'quote it, e.g. "3000"',
                          self.sndbx('run', 'claude'))

    def test_docker_args_must_be_strings(self):
        self.write_settings(images=[{'name': 'claude', 'user': 'ubuntu', 'docker_args': [8]}])

        self.assert_error(f"image 'claude' has docker_args that aren't strings in {self.settings_path()}",
                          self.sndbx('run', 'claude'))

    def test_invalid_tag_prefix(self):
        self.write_settings(tag_prefix='Not Valid', images=[])

        self.assert_error(f'invalid {self.settings_path()}: tag_prefix must be a lowercase image name, e.g. sndbx',
                          self.sndbx('run', 'claude'))

    def test_images_must_be_a_list(self):
        self.write_settings(images='claude')

        self.assert_error(f'invalid {self.settings_path()}: images must be a list', self.sndbx('run', 'claude'))

    def test_images_need_a_name(self):
        self.write_settings(images=[{'user': 'ubuntu'}])

        self.assert_error(f'invalid {self.settings_path()}: image 1 must be a mapping with a name',
                          self.sndbx('run', 'claude'))

    def test_settings_must_be_a_mapping(self):
        self.write_settings_file('- claude\n')

        self.assert_error(f'invalid {self.settings_path()}: expected a mapping with an images list',
                          self.sndbx('run', 'claude'))

    def test_invalid_yaml(self):
        self.write_settings_file('images: [\n')

        result = self.sndbx('run', 'claude')

        self.assertFalse(result.success)
        self.assertRegex(result.err, rf'\AError: invalid {re.escape(self.settings_path())}: ')

    def test_run_mounts_the_current_directory(self):
        self.write_claude_settings()

        result = self.sndbx('run', 'claude')

        self.assertTrue(result.success, result.err)
        self.assertEqual([*self.run_options('project'), *self.volume('project'), *self.config_volume(), 'sndbx:claude'],
                         self.docker_calls()[-1])
        self.assertTrue(os.path.isdir(self.default_config_dir()))

    def test_run_checks_docker_before_running(self):
        self.write_claude_settings()

        self.sndbx('run', 'claude')

        self.assertEqual([['info'], ['image', 'inspect', 'sndbx:claude']], self.docker_calls()[:2])

    def test_run_with_volumes_starts_in_the_last_one(self):
        self.write_claude_settings()
        api = self.mkdir('work/api')
        web = self.mkdir('work/web')

        self.sndbx('run', 'claude', '-v', api, '-v', web)

        self.assertEqual([*self.run_options('web'), *self.volume('api', api), *self.volume('web', web),
                          *self.config_volume(), 'sndbx:claude'],
                         self.docker_calls()[-1])

    def test_run_with_relative_volume(self):
        self.write_claude_settings()
        api = self.mkdir('work/api')

        self.sndbx('run', 'claude', '-v', '../api')

        self.assertEqual([*self.run_options('api'), *self.volume('api', api), *self.config_volume(), 'sndbx:claude'],
                         self.docker_calls()[-1])

    def test_run_with_workdir(self):
        self.write_claude_settings()
        api = self.mkdir('work/api')
        web = self.mkdir('work/web')

        self.sndbx('run', 'claude', '-v', api, '-v', web, '-w', 'api')

        self.assertIn('--workdir=/workspace/api', self.docker_calls()[-1])

    def test_workdir_must_be_a_volume(self):
        self.write_claude_settings()

        self.assert_error("workdir 'api' is not a directory volume, expected one of: project",
                          self.sndbx('run', 'claude', '-w', 'api'))

    def test_run_with_volume_target_and_options_keeps_the_current_directory(self):
        self.write_claude_settings()
        sdk = self.mkdir('work/garmin/sdk')

        self.sndbx('run', 'claude', '-v', '../garmin/sdk:/opt/garmin/sdk:ro')

        self.assertEqual([*self.run_options('project'), *self.volume('project'), '-v', f'{sdk}:/opt/garmin/sdk:ro',
                          *self.config_volume(), 'sndbx:claude'],
                         self.docker_calls()[-1])

    def test_run_with_volume_target_in_the_workspace_replaces_the_current_directory(self):
        self.write_claude_settings()
        api = self.mkdir('work/api')

        self.sndbx('run', 'claude', '-v', f'{api}:/workspace/backend/')

        self.assertEqual([*self.run_options('backend'), *self.volume('backend', api), *self.config_volume(),
                          'sndbx:claude'],
                         self.docker_calls()[-1])

    def test_run_with_file_volume(self):
        self.write_claude_settings()
        gitconfig = os.path.join(self.home, '.gitconfig')
        self.write_file(gitconfig)

        self.sndbx('run', 'claude', '-v', '~/.gitconfig:/home/ubuntu/.gitconfig:ro')

        self.assertEqual([*self.run_options('project'), *self.volume('project'),
                          '-v', f'{gitconfig}:/home/ubuntu/.gitconfig:ro', *self.config_volume(), 'sndbx:claude'],
                         self.docker_calls()[-1])

    def test_run_with_absolute_workdir(self):
        self.write_claude_settings()
        sdk = self.mkdir('work/sdk')

        self.sndbx('run', 'claude', '-v', f'{sdk}:/opt/sdk', '-w', '/opt/sdk')

        self.assertIn('--workdir=/opt/sdk', self.docker_calls()[-1])

    def test_workdir_must_be_a_directory_volume(self):
        self.write_claude_settings()
        self.write_file(os.path.join(self.work, 'notes.txt'))

        self.assert_error("workdir '/notes.txt' is not a directory volume, expected one of: project",
                          self.sndbx('run', 'claude', '-v', 'notes.txt:/notes.txt', '-w', '/notes.txt'))

    def test_run_with_volume_at_the_workspace_root(self):
        self.write_claude_settings()
        api = self.mkdir('work/api')

        self.sndbx('run', 'claude', '-v', f'{api}:/workspace', '-v', '.:/opt/project')

        self.assertEqual(['run', '--rm', '-it', '--label=sndbx.image=claude', '--workdir=/workspace',
                          '-v', f'{api}:/workspace', '-v', f'{self.work}:/opt/project', *self.config_volume(),
                          'sndbx:claude'],
                         self.docker_calls()[-1])

    def test_workdir_at_the_workspace_root(self):
        self.write_claude_settings()

        self.assert_error("workdir 'api' is not a directory volume, expected one of: /workspace",
                          self.sndbx('run', 'claude', '-v', '.:/workspace', '-w', 'api'))

    def test_run_starts_in_a_directory_volume_outside_the_workspace_without_one_inside(self):
        self.write_claude_settings()
        sdk = self.mkdir('work/sdk')
        self.write_file(os.path.join(self.work, 'notes.txt'))

        self.sndbx('run', 'claude', '-v', 'notes.txt:/workspace/notes.txt', '-v', f'{sdk}:/opt/sdk')

        self.assertIn('--workdir=/opt/sdk', self.docker_calls()[-1])

    def test_run_needs_a_directory_volume(self):
        self.write_claude_settings()
        self.write_file(os.path.join(self.work, 'notes.txt'))

        self.assert_error('no directory volume to start in',
                          self.sndbx('run', 'claude', '-v', 'notes.txt:/workspace/notes.txt'))

    def test_volume_without_target_must_be_a_directory(self):
        self.write_claude_settings()
        self.write_file(os.path.join(self.work, 'notes.txt'))

        self.assert_error(f"{os.path.join(self.work, 'notes.txt')} is not a directory",
                          self.sndbx('run', 'claude', '-v', 'notes.txt'))

    def test_volume_must_exist(self):
        self.write_claude_settings()
        missing = os.path.join(self.root, 'missing')

        self.assert_error(f'{missing} does not exist', self.sndbx('run', 'claude', '-v', f'{missing}:/missing'))

    def test_volume_target_must_be_absolute(self):
        self.write_claude_settings()

        self.assert_error("invalid volume '.:workspace', DST must be an absolute path",
                          self.sndbx('run', 'claude', '-v', '.:workspace'))

    def test_invalid_volume(self):
        self.write_claude_settings()

        self.assert_error("invalid volume '.:/a:ro:b', expected SRC[:DST[:OPTS]]",
                          self.sndbx('run', 'claude', '-v', '.:/a:ro:b'))
        self.assert_error("invalid volume '.::ro', expected SRC[:DST[:OPTS]]", self.sndbx('run', 'claude', '-v', '.::ro'))

    def test_volume_targets_must_be_unique(self):
        self.write_claude_settings()
        first = self.mkdir('a/project')
        second = self.mkdir('b/project')

        self.assert_error('more than one volume is mounted at /workspace/project',
                          self.sndbx('run', 'claude', '-v', first, '-v', second))

    def test_refuses_to_mount_home(self):
        self.write_claude_settings()

        self.assert_error(f'refusing to mount {self.home}', self.sndbx('run', 'claude', '-v', self.home))

    def test_refuses_to_mount_home_with_a_target(self):
        self.write_claude_settings()

        self.assert_error(f'refusing to mount {self.home}', self.sndbx('run', 'claude', '-v', '~:/home/ubuntu/host'))

    def test_refuses_to_mount_a_link_to_home(self):
        self.write_claude_settings()
        link = os.path.join(self.root, 'link')
        try:
            os.symlink(self.home, link, target_is_directory=True)
        except OSError:
            self.skipTest('creating symlinks needs developer mode or admin rights')

        self.assert_error(f'refusing to mount {link}', self.sndbx('run', 'claude', '-v', link))

    def test_missing_home(self):
        missing = os.path.join(self.root, 'missing')

        self.assertTrue(self.sndbx('-h', home=missing).success)
        self.assertTrue(self.sndbx('run', '--list', home=missing).success)

    def test_refuses_to_mount_root(self):
        self.write_claude_settings()
        root = os.path.abspath(os.path.join(self.work, '/'))

        self.assert_error(f'refusing to mount {root}', self.sndbx('run', 'claude', '-v', '/'))

    @unittest.skipUnless(WINDOWS, 'drive letters are Windows only')
    def test_refuses_to_mount_a_drive_root(self):
        self.write_claude_settings()
        drive = os.path.splitdrive(self.work)[0]

        self.assert_error(f'refusing to mount {drive}\\', self.sndbx('run', 'claude', '-v', f'{drive}\\:/drive'))

    @unittest.skipUnless(WINDOWS, 'drive letters are Windows only')
    def test_volume_with_a_drive_letter_and_backslashes(self):
        self.write_claude_settings()
        sdk = self.mkdir('work/sdk')
        drive, path = os.path.splitdrive(sdk)

        self.sndbx('run', 'claude', '-v', f'{drive.lower()}{path}:/opt/sdk:ro')

        self.assertIn(f'{drive.lower()}{path}:/opt/sdk:ro', self.docker_calls()[-1])

    @unittest.skipIf(WINDOWS, 'on Windows c: is a drive')
    def test_single_letter_source_is_not_a_drive(self):
        self.write_claude_settings()
        c = self.mkdir('work/project/c')

        self.sndbx('run', 'claude', '-v', 'c:/opt/c')

        self.assertIn(f'{c}:/opt/c', self.docker_calls()[-1])

    def test_run_publishes_ports(self):
        self.write_settings(images=[{'name': 'claude', 'user': 'ubuntu', 'ports': ['127.0.0.1:3080:3080', '3000']}])
        self.add_docker_image('sndbx:claude')

        self.sndbx('run', 'claude', '-p', '3000', '-p', '8080:80', '-p', '53/udp')

        self.assertEqual([*self.run_options('project'), *self.volume('project'), *self.config_volume(),
                          '-p', '127.0.0.1:3080:3080', '-p', '3000:3000', '-p', '8080:80', '-p', '53:53/udp',
                          'sndbx:claude'],
                         self.docker_calls()[-1])

    def test_run_keeps_the_container(self):
        self.write_claude_settings()

        self.sndbx('run', 'claude', '--keep')

        self.assertEqual(['run', '-it', '--label=sndbx.image=claude', '--workdir=/workspace/project',
                          *self.volume('project'), *self.config_volume(), 'sndbx:claude'],
                         self.docker_calls()[-1])

    def test_invalid_port(self):
        self.write_claude_settings()

        self.assert_error("invalid port 'http', expected PORT or HOST:CONTAINER", self.sndbx('run', 'claude', '-p', 'http'))

    def test_port_out_of_range(self):
        self.write_claude_settings()

        self.assert_error("invalid port '8080:70000', ports go up to 65535",
                          self.sndbx('run', 'claude', '-p', '8080:70000'))

    def test_run_uses_image_settings(self):
        config_dir = os.path.join(self.root, 'claude-config')
        self.write_settings(tag_prefix='mine', images=[{
            'name': 'claude',
            'user': 'dev',
            'config_dir': config_dir,
            'config_target': '.config/claude',
            'docker_args': ['--memory=8g', '--init'],
        }])
        self.add_docker_image('mine:claude')

        self.sndbx('run', 'claude')

        self.assertEqual([*self.run_options('project'), *self.volume('project'),
                          '-v', f'{config_dir}:/home/dev/.config/claude', '--memory=8g', '--init', 'mine:claude'],
                         self.docker_calls()[-1])

    def test_relative_config_dir_resolves_against_the_settings_dir(self):
        self.write_settings(images=[{'name': 'claude', 'user': 'ubuntu', 'config_dir': 'claude-docker'}])
        self.add_docker_image('sndbx:claude')

        self.sndbx('run', 'claude')

        config_dir = os.path.join(self.home, '.config', 'sndbx', 'claude-docker')
        self.assertTrue(os.path.isdir(config_dir))
        self.assertEqual([*self.run_options('project'), *self.volume('project'),
                          '-v', f'{config_dir}:/home/ubuntu/.claude', 'sndbx:claude'],
                         self.docker_calls()[-1])

    def test_home_config_dir_resolves_against_home(self):
        self.write_settings(images=[{'name': 'claude', 'user': 'ubuntu', 'config_dir': '~/.claude_docker'}])
        self.add_docker_image('sndbx:claude')

        self.sndbx('run', 'claude')

        config_dir = os.path.join(self.home, '.claude_docker')
        self.assertTrue(os.path.isdir(config_dir))
        self.assertEqual([*self.run_options('project'), *self.volume('project'),
                          '-v', f'{config_dir}:/home/ubuntu/.claude', 'sndbx:claude'],
                         self.docker_calls()[-1])

    def test_config_dir_must_be_a_path(self):
        self.write_settings(images=[{'name': 'claude', 'user': 'ubuntu', 'config_dir': 42}])

        self.assert_error(f"image 'claude' has a config_dir that isn't a path in {self.settings_path()}",
                          self.sndbx('run', 'claude'))

    def test_config_dir_must_not_be_empty(self):
        self.write_settings(images=[{'name': 'claude', 'user': 'ubuntu', 'config_dir': ''}])

        self.assert_error(f"image 'claude' has a config_dir that isn't a path in {self.settings_path()}",
                          self.sndbx('run', 'claude'))

    def test_run_passes_its_own_options_after_the_separator_to_docker(self):
        self.write_claude_settings()

        self.sndbx('run', 'claude', '--', '-v', '/tmp:/tmp', '-p', '3000', '-w', '/tmp')

        self.assertEqual([*self.run_options('project'), *self.volume('project'), *self.config_volume(),
                          '-v', '/tmp:/tmp', '-p', '3000', '-w', '/tmp', 'sndbx:claude'],
                         self.docker_calls()[-1])

    def test_run_passes_docker_args_after_the_image_ones(self):
        self.write_settings(images=[{'name': 'claude', 'user': 'ubuntu', 'docker_args': ['--memory=8g']}])
        self.add_docker_image('sndbx:claude')

        self.sndbx('run', 'claude', '-v', '.', '--', '--memory=16g', '-e', 'FOO=bar')

        self.assertEqual([*self.run_options('project'), *self.volume('project'), *self.config_volume(),
                          '--memory=8g', '--memory=16g', '-e', 'FOO=bar', 'sndbx:claude'],
                         self.docker_calls()[-1])

    def test_run_takes_the_image_before_docker_args(self):
        self.write_claude_settings()

        self.assert_error('expected exactly one image', self.sndbx('run', '--', 'claude'))

    def test_run_uses_image_tag(self):
        self.write_settings(images=[{'name': 'claude', 'user': 'ubuntu', 'tag': 'my-claude:latest'}])
        self.add_docker_image('my-claude:latest')

        self.sndbx('run', 'claude')

        self.assertEqual('my-claude:latest', self.docker_calls()[-1][-1])

    def test_run_without_docker(self):
        self.write_claude_settings()

        self.assert_error('docker is not installed', self.sndbx('run', 'claude', docker=False))

    def test_run_with_docker_stopped(self):
        self.write_claude_settings()

        self.assert_error('docker is not running', self.sndbx('run', 'claude', DOCKER_STOPPED='1'))

    def test_run_with_missing_image(self):
        self.write_settings(images=[{'name': 'claude', 'user': 'ubuntu'}])

        self.assert_error("docker image 'sndbx:claude' does not exist", self.sndbx('run', 'claude'))

    def test_run_needs_one_image(self):
        self.assert_error('expected exactly one image', self.sndbx('run'))
        self.assert_error('expected exactly one image', self.sndbx('run', 'claude', 'codex'))

    def test_run_list(self):
        self.write_settings(images=[{'name': 'claude', 'user': 'ubuntu'}, {'name': 'codex', 'user': 'ubuntu'}])

        self.assertEqual('claude\ncodex\n', self.sndbx('run', '--list').out)

    def test_run_list_without_settings_does_not_create_them(self):
        result = self.sndbx('run', '--list')

        self.assertTrue(result.success)
        self.assertEqual('', result.out)
        self.assertFalse(os.path.exists(self.settings_path()))

    def test_build_list(self):
        self.write_build_settings()
        self.mkdir('images/not-an-image')

        self.assertEqual('base\nclaude\nplain\n', self.sndbx('build', '--list').out)

    def test_build_list_defaults_to_the_repo_images(self):
        result = self.sndbx('build', '--list')

        expected = sorted(name for name in os.listdir(REPO_IMAGES_DIR)
                          if os.path.isfile(os.path.join(REPO_IMAGES_DIR, name, 'Dockerfile')))
        self.assertEqual(expected, result.out.splitlines())
        self.assertFalse(os.path.exists(self.settings_path()))

    def test_build_with_relative_images_dir(self):
        self.write_build_settings(images_dir='../../images', home=self.root)

        self.assertEqual('base\nclaude\nplain\n', self.sndbx('build', '--list', home=self.root).out)

    def test_build_builds_missing_base_first(self):
        self.write_build_settings()

        result = self.sndbx('build', 'claude')

        self.assertTrue(result.success, result.err)
        self.assertEqual([self.build_call('base'), self.build_call('claude', base=True)], self.docker_builds())

    def test_build_keeps_existing_base(self):
        self.write_build_settings()
        self.add_docker_image('sndbx:base')

        self.sndbx('build', 'claude')

        self.assertEqual([self.build_call('claude', base=True)], self.docker_builds())

    def test_build_image_without_base(self):
        self.write_build_settings()

        self.sndbx('build', 'plain')

        self.assertEqual([self.build_call('plain')], self.docker_builds())

    def test_build_base(self):
        self.write_build_settings()
        self.add_docker_image('sndbx:base')

        self.sndbx('build', 'base')

        self.assertEqual([self.build_call('base')], self.docker_builds())

    def test_build_all_builds_base_first(self):
        self.write_build_settings()
        self.write_dockerfile('alpine', 'FROM alpine\n')
        self.add_docker_image('sndbx:base')

        self.sndbx('build', '--all')

        self.assertEqual([self.build_call('base'), self.build_call('alpine'), self.build_call('claude', base=True),
                          self.build_call('plain')],
                         self.docker_builds())

    def test_build_uses_tag_prefix(self):
        self.write_build_settings(tag_prefix='mine')

        self.sndbx('build', 'claude')

        self.assertEqual([self.build_call('base', prefix='mine'), self.build_call('claude', base=True, prefix='mine')],
                         self.docker_builds())

    def test_build_unknown_image(self):
        self.write_build_settings()

        self.assert_error("unknown image 'nope', expected one of: base, claude, plain", self.sndbx('build', 'nope'))

    def test_build_failure(self):
        self.write_build_settings()

        result = self.sndbx('build', 'claude', DOCKER_BROKEN='sndbx:base')

        self.assert_error('failed to build sndbx:base', result)
        self.assertEqual([self.build_call('base')], self.docker_builds())

    def test_build_without_docker(self):
        self.write_build_settings()

        self.assert_error('docker is not installed', self.sndbx('build', 'base', docker=False))

    def test_build_with_missing_images_dir(self):
        missing = os.path.join(self.root, 'missing')
        self.write_settings(images_dir=missing, images=[])

        self.assert_error(f'images directory {missing} does not exist, set images_dir in {self.settings_path()}',
                          self.sndbx('build', 'base'))

    def test_build_needs_one_image_or_all(self):
        self.write_build_settings()

        self.assert_error('expected exactly one image, or --all', self.sndbx('build'))
        self.assert_error('expected exactly one image, or --all', self.sndbx('build', 'base', 'plain'))
        self.assert_error('expected exactly one image, or --all', self.sndbx('build', '--all', 'base'))

    def test_exec(self):
        self.write_exec_settings()

        self.sndbx('exec', 'claude', 'gifted_mcnulty', 'bash')

        self.assertEqual([['info'], ['ps', '--filter', 'label=sndbx.image=claude', '--format', '{{.Names}}'],
                          ['exec', '-i', 'gifted_mcnulty', 'bash']],
                         self.docker_calls())

    def test_exec_as_user(self):
        self.write_exec_settings()

        self.sndbx('exec', '-u', 'root', 'claude', 'gifted_mcnulty', 'bash')
        self.sndbx('exec', 'claude', '--user=root', 'gifted_mcnulty', 'bash')
        self.sndbx('exec', 'claude', 'gifted_mcnulty', '-u', 'root', 'bash')

        self.assertEqual([['exec', '-i', '--user=root', 'gifted_mcnulty', 'bash']] * 3, self.docker_execs())

    def test_exec_passes_options_after_the_command_to_it(self):
        self.write_exec_settings()

        self.sndbx('exec', 'claude', 'gifted_mcnulty', 'ls', '-la', '-u', 'x', '--help', '--')

        self.assertEqual([['exec', '-i', 'gifted_mcnulty', 'ls', '-la', '-u', 'x', '--help', '--']],
                         self.docker_execs())

    @unittest.skipIf(WINDOWS, 'needs a pty')
    def test_exec_with_a_terminal(self):
        self.write_exec_settings()
        primary, secondary = os.openpty()
        self.addCleanup(os.close, primary)

        try:
            self.sndbx('exec', 'claude', 'gifted_mcnulty', 'bash', stdin=secondary)
        finally:
            os.close(secondary)

        self.assertEqual([['exec', '-it', 'gifted_mcnulty', 'bash']], self.docker_execs())

    def test_exec_needs_a_nonempty_user(self):
        self.write_exec_settings()

        self.assert_error('expected a user', self.sndbx('exec', '-u', '', 'claude', 'gifted_mcnulty', 'bash'))
        self.assert_error('expected a user', self.sndbx('exec', '--user=', 'claude', 'gifted_mcnulty', 'bash'))
        self.assertFalse(os.path.exists(self.docker_log))

    def test_exec_after_double_dash(self):
        self.write_exec_settings()

        self.sndbx('exec', 'claude', 'gifted_mcnulty', '--', '-weird')
        self.sndbx('exec', '--', 'claude', 'gifted_mcnulty', 'bash')

        self.assertEqual([['exec', '-i', 'gifted_mcnulty', '-weird'], ['exec', '-i', 'gifted_mcnulty', 'bash']],
                         self.docker_execs())

    def test_exec_needs_an_image_a_container_and_a_command(self):
        self.write_exec_settings()

        self.assert_error('expected an image, a container and a command', self.sndbx('exec'))
        self.assert_error('expected an image, a container and a command', self.sndbx('exec', 'claude'))
        self.assert_error('expected an image, a container and a command',
                          self.sndbx('exec', 'claude', 'gifted_mcnulty'))

    def test_exec_unknown_image(self):
        self.write_exec_settings()

        self.assert_error("unknown image 'nope', expected one of: claude, codex",
                          self.sndbx('exec', 'nope', 'gifted_mcnulty', 'bash'))

    def test_exec_container_of_another_image(self):
        self.write_exec_settings()

        self.assert_error("container 'eager_turing' is not a running claude sandbox, "
                          'expected one of: gifted_mcnulty, quirky_hopper',
                          self.sndbx('exec', 'claude', 'eager_turing', 'bash'))
        self.assertEqual([], self.docker_execs())

    def test_exec_without_running_containers(self):
        self.write_settings(images=[{'name': 'claude', 'user': 'ubuntu'}])

        self.assert_error('no running claude sandbox', self.sndbx('exec', 'claude', 'gifted_mcnulty', 'bash'))

    def test_exec_without_docker(self):
        self.write_exec_settings()

        self.assert_error('docker is not installed',
                          self.sndbx('exec', 'claude', 'gifted_mcnulty', 'bash', docker=False))

    def test_exec_list(self):
        self.write_exec_settings()

        self.assertEqual('gifted_mcnulty\nquirky_hopper\n', self.sndbx('exec', 'claude', '--list').out)
        self.assertEqual('eager_turing\n', self.sndbx('exec', '-l', 'codex').out)
        self.assertEqual('', self.sndbx('exec', 'opencode', '--list').out)

    def test_exec_list_without_settings_does_not_create_them(self):
        self.add_docker_container('claude', 'gifted_mcnulty')

        self.assertEqual('gifted_mcnulty\n', self.sndbx('exec', 'claude', '--list').out)
        self.assertFalse(os.path.exists(self.settings_path()))

    def test_exec_list_needs_one_image(self):
        self.assert_error('expected exactly one image', self.sndbx('exec', '--list'))
        self.assert_error('expected exactly one image', self.sndbx('exec', 'claude', 'gifted_mcnulty', '--list'))

    def test_resume(self):
        self.write_resume_settings()

        self.sndbx('resume', 'claude', 'sleepy_babbage')

        self.assertEqual([['info'],
                          ['ps', '--all', '--filter', 'status=exited', '--filter', 'label=sndbx.image=claude',
                           '--format', '{{.Names}}'],
                          ['start', '-ai', 'sleepy_babbage']],
                         self.docker_calls())

    def test_resume_running_container(self):
        self.write_resume_settings()

        self.assert_error("container 'gifted_mcnulty' is not a stopped claude sandbox, expected one of: sleepy_babbage",
                          self.sndbx('resume', 'claude', 'gifted_mcnulty'))
        self.assertEqual([], self.docker_starts())

    def test_resume_without_stopped_containers(self):
        self.write_exec_settings()

        self.assert_error('no stopped claude sandbox', self.sndbx('resume', 'claude', 'gifted_mcnulty'))

    def test_resume_unknown_image(self):
        self.write_resume_settings()

        self.assert_error("unknown image 'nope', expected one of: claude, codex",
                          self.sndbx('resume', 'nope', 'sleepy_babbage'))

    def test_resume_needs_an_image_and_a_container(self):
        self.write_resume_settings()

        self.assert_error('expected an image and a container', self.sndbx('resume'))
        self.assert_error('expected an image and a container', self.sndbx('resume', 'claude'))
        self.assert_error('expected an image and a container',
                          self.sndbx('resume', 'claude', 'sleepy_babbage', 'bash'))

    def test_resume_without_docker(self):
        self.write_resume_settings()

        self.assert_error('docker is not installed', self.sndbx('resume', 'claude', 'sleepy_babbage', docker=False))

    def test_resume_list(self):
        self.write_resume_settings()

        self.assertEqual('sleepy_babbage\n', self.sndbx('resume', 'claude', '--list').out)
        self.assertEqual('', self.sndbx('resume', '-l', 'codex').out)

    def test_resume_list_needs_one_image(self):
        self.assert_error('expected exactly one image', self.sndbx('resume', '--list'))
        self.assert_error('expected exactly one image', self.sndbx('resume', 'claude', 'sleepy_babbage', '--list'))

    def test_logs_docker_commands(self):
        self.write_resume_settings()
        self.add_docker_image('sndbx:claude')
        directory = self.mkdir('work/project/my dir')

        self.sndbx('run', 'claude', '-v', directory)
        self.sndbx('exec', 'claude', 'gifted_mcnulty', 'bash')
        self.sndbx('resume', 'claude', 'sleepy_babbage')

        self.assertEqual([['docker', *self.run_options('my dir'), '-v', f'{directory}:/workspace/my dir',
                           *self.config_volume(), 'sndbx:claude'],
                          ['docker', 'exec', '-i', 'gifted_mcnulty', 'bash'],
                          ['docker', 'start', '-ai', 'sleepy_babbage']],
                         self.logged_commands())
        for line in self.log_lines():
            self.assertRegex(line, r'\A\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d docker ')

    def test_logs_builds(self):
        self.write_build_settings()

        self.sndbx('build', 'plain')

        self.assertEqual([['docker', 'build', '--no-cache', '-t', 'sndbx:plain', os.path.join(self.images_dir, 'plain')]],
                         self.logged_commands())

    def test_does_not_log_lists(self):
        self.write_resume_settings()

        self.sndbx('run', '--list')
        self.sndbx('exec', 'claude', '--list')
        self.sndbx('resume', 'claude', '--list')

        self.assertFalse(os.path.exists(self.log_path()))

    def test_runs_when_the_log_cannot_be_written(self):
        self.write_claude_settings()
        self.write_file(os.path.join(self.mkdir('home/.local'), 'state'))

        result = self.sndbx('run', 'claude')

        self.assertTrue(result.success, result.err)
        self.assertRegex(result.err, rf"\AWarning: can't write {re.escape(self.log_path())}: ")
        self.assertEqual(self.run_options('project'), self.docker_calls()[-1][:5])

    def test_logs_follows_the_log(self):
        self.write_log(*(f'line {number}' for number in range(1, 13)))

        with self.follow_log() as logs:
            self.assertEqual([f'line {number}' for number in range(3, 13)], self.read_lines(logs, 10))
            self.append_log('line 13')
            self.assertEqual(['line 13'], self.read_lines(logs, 1))

    def test_logs_with_lines(self):
        self.write_log('line 1', 'line 2', 'line 3')

        with self.follow_log('-n', '2') as logs:
            self.assertEqual(['line 2', 'line 3'], self.read_lines(logs, 2))

        # Lines appended before it reaches the end are skipped too, so append until one shows up
        with self.follow_log('--lines=0') as logs:
            self.assertEqual(['line 4'], self.read_lines(logs, 1, while_waiting=lambda: self.append_log('line 4')))

    def test_logs_without_a_log(self):
        self.assert_error(f'no log yet at {self.log_path()}', self.sndbx('logs'))

    def test_logs_needs_a_line_count(self):
        self.assert_error('invalid argument: -n x', self.sndbx('logs', '-n', 'x'))
        self.assert_error('invalid argument: --lines=x', self.sndbx('logs', '--lines=x'))
        self.assert_error('expected a line count of 0 or more', self.sndbx('logs', '-n', '-1'))

    def test_logs_takes_no_arguments(self):
        self.assert_error('expected no arguments', self.sndbx('logs', 'claude'))

    def assert_error(self, message, result):
        self.assertFalse(result.success)
        self.assertEqual(f'Error: {message}.\n', result.err)

    def assert_help(self, usage, result):
        self.assertTrue(result.success, result.err)
        self.assertEqual(usage, result.out.splitlines()[0])
        self.assertFalse(os.path.exists(self.settings_path()))
        self.assertFalse(os.path.exists(self.docker_log))

    def write_claude_settings(self):
        self.write_settings(images=[{'name': 'claude', 'user': 'ubuntu'}])
        self.add_docker_image('sndbx:claude')

    def write_build_settings(self, images_dir=None, **settings):
        self.write_dockerfile('base', 'FROM ubuntu\n')
        self.write_dockerfile('claude', 'ARG TAG_PREFIX=sndbx\nFROM ${TAG_PREFIX}:base\n')
        self.write_dockerfile('plain', 'FROM ubuntu\n')
        self.write_settings(images_dir=images_dir or self.images_dir, images=[], **settings)

    def write_exec_settings(self):
        self.write_settings(images=[{'name': 'claude', 'user': 'ubuntu'}, {'name': 'codex', 'user': 'ubuntu'}])
        self.add_docker_container('claude', 'gifted_mcnulty')
        self.add_docker_container('codex', 'eager_turing')
        self.add_docker_container('claude', 'quirky_hopper')

    def write_resume_settings(self):
        self.write_exec_settings()
        self.add_docker_container('claude', 'sleepy_babbage', 'exited')

    def log_path(self):
        return os.path.join(self.home, '.local', 'state', 'sndbx', 'sndbx.log')

    def log_lines(self):
        with open(self.log_path(), encoding='utf-8') as file:
            return file.read().splitlines()

    def logged_commands(self):
        return [shlex.split(line.split(' ', 1)[1]) for line in self.log_lines()]

    def write_log(self, *lines):
        os.makedirs(os.path.dirname(self.log_path()), exist_ok=True)
        self.write_file(self.log_path(), ''.join(f'{line}\n' for line in lines))

    def append_log(self, line):
        with open(self.log_path(), 'a', encoding='utf-8') as file:
            file.write(f'{line}\n')

    @contextlib.contextmanager
    def follow_log(self, *args):
        """Starts sndbx logs, which only stops when killed."""
        process = subprocess.Popen([sys.executable, BIN, 'logs', *args], cwd=self.work, env=self.env(),
                                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        try:
            yield process
        finally:
            process.kill()
            process.wait()
            process.stdout.close()

    def read_lines(self, process, count, while_waiting=lambda: None):
        """Reads COUNT lines from PROCESS, calling WHILE_WAITING every so often, and fails instead of hanging
        when they don't come."""
        lines = []
        reader = threading.Thread(target=lambda: lines.extend(process.stdout.readline().decode().rstrip('\r\n')
                                                               for _ in range(count)), daemon=True)
        reader.start()
        deadline = time.monotonic() + 10
        while reader.is_alive() and time.monotonic() < deadline:
            while_waiting()
            reader.join(0.2)
        self.assertFalse(reader.is_alive(), f'expected {count} lines, got {lines}')
        return lines

    def docker_execs(self):
        return [call for call in self.docker_calls() if call[0] == 'exec']

    def docker_starts(self):
        return [call for call in self.docker_calls() if call[0] == 'start']

    def docker_builds(self):
        return [call for call in self.docker_calls() if call[0] == 'build']

    @staticmethod
    def run_options(workdir):
        return ['run', '--rm', '-it', '--label=sndbx.image=claude', f'--workdir=/workspace/{workdir}']

    def volume(self, name, path=None):
        return ['-v', f'{path or self.work}:/workspace/{name}']

    def config_volume(self):
        return ['-v', f'{self.default_config_dir()}:/home/ubuntu/.claude']

    def default_config_dir(self):
        return os.path.join(self.home, '.config', 'sndbx', 'claude')

    def build_call(self, name, base=False, prefix='sndbx'):
        args = ['--build-arg', f'TAG_PREFIX={prefix}'] if base else []
        return ['build', '--no-cache', *args, '-t', f'{prefix}:{name}', os.path.join(self.images_dir, name)]


if __name__ == '__main__':
    unittest.main()
