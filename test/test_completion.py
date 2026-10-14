"""Tests of sndbx.py __complete, ported from test/completion_test.rb, and of completions/sndbx.ps1.

PowerShell doesn't split words at = and : like bash, so the words here are whole."""

import json
import os
import re
import shutil
import subprocess
import sys
import unittest

from helper import BIN, WINDOWS, SndbxTestCase

COMPLETION_PS = os.path.join(os.path.dirname(os.path.dirname(BIN)), 'completions', 'sndbx.ps1')
PWSH = shutil.which('pwsh') or shutil.which('powershell')


class CompletionTest(SndbxTestCase):
    def env(self, docker=True, **env):
        return {**super().env(docker, **env), 'PATH': os.pathsep.join([self.bin, os.environ['PATH']])}

    def test_options_match_help(self):
        for command in [[], ['run'], ['build'], ['exec']]:
            self.assertEqual(self.help_options(*command), self.complete(*command, '-'), f'options of {command}')

    def test_commands(self):
        self.assertEqual(['build', 'exec', 'run'], self.complete(''))
        self.assertEqual(['run'], self.complete('r'))

    def test_hidden_command_needs_words(self):
        result = self.sndbx('__complete')

        self.assertEqual('Error: expected a JSON list of words in SNDBX_COMPLETE.\n', result.err)

    def test_python_prints_the_interpreter_and_script(self):
        result = self.sndbx('__complete', '--python')

        self.assertEqual([sys.executable, os.path.realpath(BIN)], result.out.splitlines())

    def test_unknown_command(self):
        self.assertEqual([], self.complete('foo', ''))

    def test_run_images(self):
        self.write_images_settings()

        self.assertEqual(['claude', 'codex'], self.complete('run', ''))
        self.assertEqual(['codex'], self.complete('run', 'co'))

    def test_run_images_after_option_values(self):
        self.write_images_settings()
        api = self.mkdir('work/api')

        self.assertEqual(['claude', 'codex'], self.complete('run', '-v', api, '-w', 'api', '-p', '3000', ''))
        self.assertEqual(['claude', 'codex'], self.complete('run', f'--volume={api}', '--publish=3000', ''))
        self.assertEqual(['claude', 'codex'], self.complete('run', '-v', f'{api}:/opt/api:ro', '-p', '8080:80', ''))

    def test_volume_target_completes_nothing(self):
        self.mkdir('work/project/src')

        self.assertEqual([], self.complete('run', '-v', 'src:'))
        self.assertEqual([], self.complete('run', '-v', 'src:/opt:'))
        self.assertEqual([], self.complete('run', '--volume=src:'))

    def test_docker_args_complete_with_docker(self):
        self.write_docker_completions('--memory\tMemory limit\n--memory-swap\n:4\n')

        self.assertEqual(['--memory', '--memory-swap'], self.complete('run', 'claude', '-v', '.', '--', '--init', '--mem'))
        self.assertEqual([['__complete', 'run', '--init', '--mem']], self.docker_calls())

    def test_docker_args_filter_candidates(self):
        self.write_docker_completions('bridge\nhost\nnone\n:4\n')

        self.assertEqual(['host'], self.complete('run', 'claude', '--', '--network', 'h'))

    def test_docker_args_complete_values_after_equals_signs(self):
        self.write_docker_completions('src:/opt\nsrc:/srv\nother:/opt\n:0\n')

        self.assertEqual(['--volume=src:/opt', '--volume=src:/srv'],
                         self.complete('run', 'claude', '--', '--volume=src:/'))
        self.assertEqual(['src:/opt', 'src:/srv'], self.complete('run', 'claude', '--', '-v', 'src:'))
        self.assertEqual([['__complete', 'run', '--volume=src:/'], ['__complete', 'run', '-v', 'src:']],
                         self.docker_calls())

    def test_docker_args_without_candidates_complete_files(self):
        self.write_docker_completions(':0\n')
        self.write_file(os.path.join(self.work, 'env'))
        self.mkdir('work/project/src')

        self.assertEqual(['--env-file=env', '--env-file=src'], self.complete('run', 'claude', '--', '--env-file='))

    def test_docker_args_complete_directories_when_docker_says_so(self):
        self.write_docker_completions(':16\n')
        self.write_file(os.path.join(self.work, 'env'))
        self.mkdir('work/project/src')

        self.assertEqual(['src'], self.complete('run', 'claude', '--', '--workdir', ''))

    def test_docker_args_without_file_completion(self):
        self.write_docker_completions(':4\n')
        self.write_file(os.path.join(self.work, 'env'))

        self.assertEqual([], self.complete('run', 'claude', '--', '-e', ''))

    def test_docker_args_after_a_docker_error(self):
        self.write_docker_completions('--memory\n:1\n')

        self.assertEqual([], self.complete('run', 'claude', '--', '-'))

    def test_docker_args_complete_files_with_old_docker(self):
        self.write_file(os.path.join(self.work, 'env'))

        self.assertEqual(['env'], self.complete('run', 'claude', '--', '--env-file', ''))

    def test_run_no_image_after_image(self):
        self.write_images_settings()

        self.assertEqual([], self.complete('run', 'claude', ''))

    def test_run_images_without_settings_do_not_create_them(self):
        self.assertEqual([], self.complete('run', ''))
        self.assertFalse(os.path.exists(self.settings_path()))

    def test_build_images(self):
        self.write_dockerfile('base', 'FROM ubuntu\n')
        self.write_dockerfile('claude', 'FROM ubuntu\n')
        self.write_settings(images_dir=self.images_dir, images=[])

        self.assertEqual(['base', 'claude'], self.complete('build', ''))
        self.assertEqual([], self.complete('build', 'base', ''))
        self.assertEqual([], self.complete('build', '--all', ''))

    def test_exec_images(self):
        self.write_images_settings()

        self.assertEqual(['claude', 'codex'], self.complete('exec', ''))
        self.assertEqual(['claude', 'codex'], self.complete('exec', '-u', 'root', ''))
        self.assertEqual(['claude', 'codex'], self.complete('exec', '--user=root', ''))

    def test_exec_containers(self):
        self.write_images_settings()
        self.add_docker_container('claude', 'gifted_mcnulty')
        self.add_docker_container('claude', 'quirky_hopper')

        self.assertEqual(['gifted_mcnulty', 'quirky_hopper'], self.complete('exec', 'claude', ''))
        self.assertEqual(['quirky_hopper'], self.complete('exec', '-u', 'root', 'claude', 'q'))
        self.assertEqual([['info'], ['ps', '--filter', 'label=sndbx.image=claude', '--format', '{{.Names}}']],
                         self.docker_calls()[-2:])

    def test_exec_options_before_the_command(self):
        self.assertEqual(['--user'], self.complete('exec', 'claude', 'gifted_mcnulty', '--u'))

    def test_exec_completes_nothing_from_the_command_on(self):
        self.write_file(os.path.join(self.work, 'README.md'))

        self.assertEqual([], self.complete('exec', 'claude', 'gifted_mcnulty', ''))
        self.assertEqual([], self.complete('exec', 'claude', 'gifted_mcnulty', 'ls', ''))
        self.assertEqual([], self.complete('exec', 'claude', 'gifted_mcnulty', 'ls', '-'))
        self.assertEqual([], self.complete('exec', 'claude', 'gifted_mcnulty', '--', '-'))
        self.assertEqual([], self.complete('exec', '-u', ''))
        self.assertEqual([], self.complete('exec', '--user='))

    def test_exec_list_completes_nothing_after_the_image(self):
        self.write_images_settings()

        self.assertEqual([], self.complete('exec', 'claude', '--list', ''))
        self.assertEqual([], self.complete('exec', '-l', 'claude', ''))
        self.assertEqual(['claude', 'codex'], self.complete('exec', '--list', ''))

    def test_volume_completes_directories(self):
        self.mkdir('work/project/src')
        self.write_file(os.path.join(self.work, 'README.md'))

        self.assertEqual(['src'], self.complete('run', '-v', ''))
        self.assertEqual(['--volume=src'], self.complete('run', '--volume='))

    def test_volume_completes_nested_directories(self):
        self.mkdir('work/project/src/lib')
        self.mkdir('work/api')

        self.assertEqual([os.path.join('src', 'lib')], self.complete('run', '-v', f'src{os.sep}'))
        self.assertEqual(['../api', '../project'], self.complete('run', '-v', '../'))

    def test_volume_completes_home(self):
        self.mkdir('home/notes')

        self.assertEqual(['~/notes'], self.complete('run', '-v', '~/n'))

    @unittest.skipUnless(WINDOWS, 'drive letters are Windows only')
    def test_volume_completes_absolute_windows_paths(self):
        self.mkdir('work/api')
        parent = os.path.dirname(self.work)

        self.assertEqual([os.path.join(parent, 'api')], self.complete('run', '-v', os.path.join(parent, 'a')))
        self.assertEqual([os.path.join(parent, 'api')], self.complete('run', '-v', os.path.join(parent, 'A')))

    def test_publish_completes_nothing(self):
        self.assertEqual([], self.complete('run', '-p', ''))

    def test_workdir_defaults_to_the_current_directory(self):
        self.assertEqual(['project'], self.complete('run', 'claude', '-w', ''))

    def test_workdir_completes_volumes(self):
        api = self.mkdir('work/api')
        self.mkdir('work/web')
        self.mkdir('home/notes')

        self.assertEqual(['api', 'notes', 'web'], self.complete('run', '-v', api, '-v', '../web', '-v', '~/notes', '-w', ''))

    def test_workdir_completes_volume_targets(self):
        api = self.mkdir('work/api')
        self.mkdir('work/sdk')
        self.write_file(os.path.join(self.work, 'notes.txt'))

        self.assertEqual(['/opt/sdk', 'project'],
                         self.complete('run', '-v', '../sdk:/opt/sdk:ro', '-v', 'notes.txt:/notes.txt', '-w', ''))
        self.assertEqual(['/opt/sdk', 'backend'],
                         self.complete('run', '-v', '"../sdk:/opt/sdk"', '-v', f'{api}:/workspace/backend', '-w', ''))

    def test_workdir_completes_the_workspace_root(self):
        api = self.mkdir('work/api')

        self.assertEqual(['/workspace'], self.complete('run', '-v', f'{api}:/workspace', '-w', ''))

    def test_workdir_skips_missing_volumes(self):
        api = self.mkdir('work/api')

        self.assertEqual(['api'], self.complete('run', '-v', api, '-v', os.path.join(self.root, 'missing'), '-w', ''))

    def test_workdir_with_equals_sign(self):
        api = self.mkdir('work/api')

        self.assertEqual(['--workdir=api'], self.complete('run', f'--volume={api}', '--workdir='))

    @unittest.skipUnless(PWSH, 'needs PowerShell')
    def test_powershell_completes_images(self):
        self.write_images_settings()

        self.assertEqual(['claude', 'codex'], self.tab_complete('sndbx run '))
        self.assertEqual(['codex'], self.tab_complete('sndbx run co'))
        self.assertEqual(['claude', 'codex'], self.tab_complete('sndbx exec -u root '))

    @unittest.skipUnless(PWSH, 'needs PowerShell')
    def test_powershell_completes_empty_words(self):
        self.assertEqual(['project'], self.tab_complete('sndbx run claude -w '))

    @unittest.skipUnless(PWSH, 'needs PowerShell')
    def test_powershell_quotes_paths_with_spaces(self):
        self.mkdir('work/project/my dir')

        self.assertEqual(["'my dir'"], self.tab_complete('sndbx run -v my'))

    @unittest.skipUnless(PWSH, 'needs PowerShell')
    def test_powershell_passes_docker_args(self):
        self.write_docker_completions('bridge\nhost\nnone\n:4\n')

        self.assertEqual(['host'], self.tab_complete('sndbx run claude -- --network h'))

    def complete(self, *words):
        result = self.sndbx('__complete', SNDBX_COMPLETE=json.dumps(words))
        self.assertTrue(result.success, result.err)

        return sorted(result.out.splitlines())

    def tab_complete(self, line):
        """Completes LINE with completions/sndbx.ps1 in PowerShell, through a sndbx on PATH."""
        if WINDOWS:
            self.write_file(os.path.join(self.bin, 'sndbx.cmd'), f'@"{sys.executable}" "{BIN}" %*\n')
        else:
            sndbx = os.path.join(self.bin, 'sndbx')
            self.write_file(sndbx, f'#!/bin/sh\nexec "{sys.executable}" "{BIN}" "$@"\n')
            os.chmod(sndbx, 0o755)

        script = (f". '{COMPLETION_PS}'; "
                  f"(TabExpansion2 -inputScript '{line}' -cursorColumn {len(line)}).CompletionMatches | "
                  'ForEach-Object CompletionText')
        result = subprocess.run([PWSH, '-NoProfile', '-NonInteractive', '-Command', script], cwd=self.work,
                                env=self.env(), capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(0, result.returncode, result.stderr)

        return sorted(result.stdout.splitlines())

    def help_options(self, *command):
        lines = [line.strip() for line in self.sndbx(*command, '-h').out.splitlines()]
        return sorted(option for line in lines if line.startswith('-')
                      for option in re.findall(r'-[-\w]+', re.split(r'\s{2,}', line)[0]))

    def write_docker_completions(self, output):
        self.write_file(self.docker_completions, output)

    def write_images_settings(self):
        self.write_settings(images=[{'name': 'claude', 'user': 'ubuntu'}, {'name': 'codex', 'user': 'ubuntu'}])


if __name__ == '__main__':
    unittest.main()
