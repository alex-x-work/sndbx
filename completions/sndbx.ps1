# PowerShell completions for sndbx: dot-source this file, e.g. from $PROFILE.
# sndbx __complete does the work, it reads the words from SNDBX_COMPLETE because
# PowerShell 5.1 drops empty arguments and mangles quotes in arguments to native commands.

# sndbx.cmd starts sndbx.py through uv, which takes longer than a completion should. The first
# completion asks which python and script that ends up running, the others run them directly.
$global:SndbxCompletionPython = @()

Register-ArgumentCompleter -Native -CommandName sndbx, sndbx.cmd -ScriptBlock {
  param($wordToComplete, $commandAst, $cursorPosition)

  # The words before the one being completed, without the command, unquoted
  $words = @($commandAst.CommandElements |
    Select-Object -Skip 1 |
    Where-Object { $_.Extent.EndOffset -lt $cursorPosition } |
    ForEach-Object {
      if ($_ -is [System.Management.Automation.Language.StringConstantExpressionAst]) { $_.Value } else { $_.Extent.Text }
    })
  $current = $wordToComplete -replace "^['""]", ''

  $command = $commandAst.CommandElements[0].Extent.Text
  $python = $global:SndbxCompletionPython
  if ($python.Count -ne 2 -or -not (Test-Path -LiteralPath $python[0])) {
    $python = $global:SndbxCompletionPython = @(& $command __complete --python 2>$null)
  }

  $previousEncoding = [Console]::OutputEncoding
  try {
    $env:SNDBX_COMPLETE = ConvertTo-Json -Compress -InputObject @($words + $current)
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $candidates = if ($python.Count -eq 2) {
      @(& $python[0] $python[1] __complete 2>$null)
    } else {
      @(& $command __complete 2>$null)
    }
  } finally {
    [Console]::OutputEncoding = $previousEncoding
    Remove-Item Env:SNDBX_COMPLETE -ErrorAction SilentlyContinue
  }

  foreach ($candidate in $candidates) {
    # Quote what PowerShell would otherwise parse, like spaces in paths
    $text = if ($candidate -match '[\s''"`$&|;,(){}@#<>]') { "'" + ($candidate -replace "'", "''") + "'" } else { $candidate }
    [System.Management.Automation.CompletionResult]::new($text, $candidate, 'ParameterValue', $candidate)
  }
}
