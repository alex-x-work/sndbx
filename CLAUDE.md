# sndbx

- Bump `VERSION` in `bin/sndbx` on every code change to sndbx (`bin/sndbx`, `completions/_sndbx`): patch for fixes, minor for new features or options.
- Run `rake` after changing `bin/sndbx` or `completions/_sndbx`.
- `bin/sndbx.py` is a Python port of `bin/sndbx` that also runs on Windows; keep both behaving the same.
- Bump `VERSION` in `bin/sndbx.py` on every change to it, `bin/sndbx.cmd` or `completions/sndbx.ps1`, the same way.
- Run `uv run --with pyyaml python -m unittest discover -s test -p "test_*.py"` after changing them.
