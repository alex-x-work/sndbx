require_relative 'test_helper'

class CompletionTest < Minitest::Test
  include SndbxTestHelper

  COMPLETION = File.expand_path('../completions/_sndbx', __dir__)

  COMPLETE = <<~BASH.freeze
    source "$COMPLETION"
    COMP_WORDS=(sndbx "$@")
    COMP_CWORD=$#
    _sndbx 2>/dev/null
    (( ${#COMPREPLY[@]} )) && printf '%s\\n' "${COMPREPLY[@]}"
    exit 0
  BASH

  def setup
    super
    write_executable(File.join(@bin, 'sndbx'), "#!/bin/sh\nexec '#{RbConfig.ruby}' '#{BIN}' \"$@\"\n")
  end

  def test_options_match_help
    [[], ['run'], ['build']].each do |command|
      assert_equal help_options(*command), complete(*command, '-'), "options of sndbx #{command.join(' ')}"
    end
  end

  def test_commands
    assert_equal %w[build run], complete('')
    assert_equal %w[run], complete('r')
  end

  def test_unknown_command
    assert_empty complete('foo', '')
  end

  def test_run_images
    write_images_settings

    assert_equal %w[claude codex], complete('run', '')
    assert_equal %w[codex], complete('run', 'co')
  end

  def test_run_images_after_option_values
    write_images_settings
    api = mkdir('work/api')

    assert_equal %w[claude codex], complete('run', '-v', api, '-w', 'api', '-p', '3000', '')
    assert_equal %w[claude codex], complete('run', '--volume', '=', api, '--publish', '=', '3000', '')
  end

  def test_run_no_image_after_image
    write_images_settings

    assert_empty complete('run', 'claude', '')
  end

  def test_run_images_without_settings_do_not_create_them
    assert_empty complete('run', '')
    refute File.exist?(settings_path)
  end

  def test_build_images
    write_dockerfile('base', "FROM ubuntu\n")
    write_dockerfile('claude', "FROM ubuntu\n")
    write_settings(images_dir: @images_dir, images: [])

    assert_equal %w[base claude], complete('build', '')
    assert_empty complete('build', 'base', '')
    assert_empty complete('build', '--all', '')
  end

  def test_volume_completes_directories
    mkdir('work/project/src')
    File.write(File.join(@work, 'README.md'), '')

    assert_equal %w[src], complete('run', '-v', '')
  end

  def test_publish_completes_nothing
    assert_empty complete('run', '-p', '')
  end

  def test_workdir_defaults_to_the_current_directory
    assert_equal %w[project], complete('run', 'claude', '-w', '')
  end

  def test_workdir_completes_volumes
    api = mkdir('work/api')
    mkdir('work/web')
    mkdir('home/notes')

    assert_equal %w[api notes web], complete('run', '-v', api, '-v', '../web', '-v', '~/notes', '-w', '')
  end

  def test_workdir_skips_missing_volumes
    api = mkdir('work/api')

    assert_equal %w[api], complete('run', '-v', api, '-v', File.join(@root, 'missing'), '-w', '')
  end

  def test_workdir_with_equals_sign
    api = mkdir('work/api')

    assert_equal %w[api], complete('run', '--volume', '=', api, '--workdir', '=', '')
    assert_equal %w[api], complete('run', '--volume', '=', api, '--workdir', '=')
  end

  private

  def complete(*words)
    env = { 'HOME' => @home, 'PATH' => "#{@bin}:#{ENV.fetch('PATH')}", 'COMPLETION' => COMPLETION }
    out, status = Open3.capture2(env, 'bash', '-c', COMPLETE, 'bash', *words, chdir: @work)
    assert_predicate status, :success?

    out.lines(chomp: true).sort
  end

  def help_options(*command)
    sndbx(*command, '-h').out.lines
                         .map(&:strip)
                         .select { |line| line.start_with?('-') }
                         .flat_map { |line| line.split(/\s{2,}/).first.scan(/-[-\w]+/) }
                         .sort
  end

  def write_images_settings
    write_settings(images: [{ name: 'claude', user: 'ubuntu' }, { name: 'codex', user: 'ubuntu' }])
  end
end
