"""What a shell command does, and what its output says about how it went.

These are the only places the checker knows anything about the outside world:
which commands run tests, which build, which write files, which commit. Each is
a regex over the command line, kept here so the list is one diff to extend.
"""

import os
import re

TEST = re.compile(
    r"\b(?:pytest|py\.test|unittest|nosetests|tox|nox|vitest|jest|mocha|ava|playwright test|"
    r"cypress run|rspec|phpunit|ctest|bats|"
    r"(?:npm|pnpm|yarn|bun|deno)\s+(?:run\s+)?test(?::\S+)?|"
    r"(?:cargo|go|swift|dotnet|mix|zig|gradle|gradlew|mvn|sbt|stack|cabal)\s+test|"
    r"xcodebuild\b[^|;&]*\btest\b|make\s+(?:test|check)\w*|"
    r"(?:Rscript|R\s+-e|python3?|node|bash|sh|uv run|poetry run)\s+[^|;&]*\btests?[\w./-]*|"
    r"\btest_[\w./-]*\.py|[\w./-]*_test\.\w+|run_tests?\b|\bverify(?:\.sh|\.py)?\b)", re.I)

BUILD = re.compile(
    r"\b(?:(?:npm|pnpm|yarn|bun)\s+(?:run\s+)?(?:build|compile)\b|"
    r"(?:cargo|go|swift|dotnet|zig|stack|cabal)\s+build|cargo\s+check|xcodebuild|"
    r"tsc\b|vite\s+build|next\s+build|webpack|esbuild|rollup|"
    r"gradle\w*\s+\w*(?:build|assemble)|mvn\s+\w*(?:package|compile|install)|"
    r"make\b(?!\s+(?:test|check|clean))|cmake\s+--build|ninja\b|bazel\s+build|"
    r"python3?\s+-m\s+(?:py_compile|compileall|build)|pip\s+install\s+-e|"
    r"tectonic|latexmk|pdflatex|xelatex|hugo\b|jekyll\s+build|astro\s+build)", re.I)

LINT = re.compile(
    r"\b(?:eslint|ruff|flake8|pylint|black\s+--check|prettier\s+--check|clippy|golangci-lint|"
    r"swiftlint|shellcheck|(?:npm|pnpm|yarn|bun)\s+(?:run\s+)?lint|biome\s+(?:check|lint)|stylelint)\b", re.I)

TYPECHECK = re.compile(
    r"\b(?:tsc\b|mypy|pyright|basedpyright|(?:npm|pnpm|yarn|bun)\s+(?:run\s+)?(?:typecheck|type-check|check-types|tsc)|"
    r"cargo\s+check|flow\s+check|vue-tsc|svelte-check)\b", re.I)

COMMIT = re.compile(r"\bgit\b[^|;&]*?\bcommit\b")
PUSH = re.compile(r"\bgit\b[^|;&]*?\bpush\b")
PR = re.compile(r"\bgh\s+pr\s+(?:create|merge)\b")
DEPLOY = re.compile(
    r"\b(?:vercel|netlify|wrangler|fly\s+deploy|flyctl|firebase\s+deploy|heroku|railway\s+up|"
    r"npm\s+publish|twine\s+upload|gh\s+release|kubectl\s+apply|terraform\s+apply|"
    r"docker\s+push|gh-pages|deploy\S*)\b", re.I)
INSTALL = re.compile(
    r"\b(?:(?:pip3?|uv\s+pip|pipx|npm|pnpm|yarn|bun|brew|cargo|go|gem|apt(?:-get)?)\s+"
    r"(?:install|add|i)\b|uv\s+(?:add|sync|tool\s+install))", re.I)

# Putting a built thing in place: copying a binary, loading a launch agent, linking a script.
PLACE = re.compile(
    r"\b(?:cp|mv|rsync|ln\s+-\w*s\w*|install\s+-|launchctl\s+(?:load|bootstrap|kickstart|enable)|"
    r"chmod\s+\+x|brew\s+services|systemctl\s+(?:enable|restart|start))\b")

# Commands that only look: a passing `ls` proves nothing ran.
READ_ONLY = re.compile(
    r"^\s*(?:cd\s+\S+\s*&&\s*)?(?:ls|cat|head|tail|less|wc|grep|rg|find|fd|pwd|echo|which|"
    r"git\s+(?:status|log|diff|show|branch)|sed\s+-n|stat|file|tree|du|df|date|whoami|printf)\b")

# Output that says something failed, whatever the exit code (`| tail` swallows it).
FAILED = re.compile(
    r"(?<![\w.])(?:[1-9]\d*\s+(?:failed|failures?|failing|errors?)\b|FAILED\b|FAIL\b|"
    r"Tests?:\s+\d+ failed|failures=\d*[1-9]|errors=\d*[1-9]|"
    r"Traceback \(most recent call last\)|AssertionError|panicked at|"
    r"npm ERR!|error\[E\d+\]|error TS\d+|BUILD FAILED|\*\* BUILD FAILED|"
    r"Compilation failed|SyntaxError|ModuleNotFoundError|command not found|"
    r"No such file or directory|fatal:|rejected\]|error: failed to push)")
PASSED = re.compile(
    r"(?:\b\d+\s+(?:passed|passing|tests? passed|tests? OK)|\bOK\b|\ball (?:\d+ )?tests? passed|"
    r"\bPASS\b|\bpassed\b|Build succeeded|BUILD SUCCEEDED|Compiled successfully|"
    r"\bFinished\b|\bSuccess|0 errors|no errors|All checks passed|✓)", re.I)
BACKGROUNDED = re.compile(r"running in background|background (?:task|shell)|backgroundTaskId", re.I)

CODE_EXT = {
    ".py", ".pyi", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".rs", ".go", ".swift", ".java",
    ".kt", ".kts", ".rb", ".php", ".c", ".h", ".cc", ".cpp", ".hpp", ".m", ".mm", ".cs", ".r",
    ".sql", ".sh", ".zsh", ".css", ".scss", ".html", ".vue", ".svelte", ".astro", ".json",
    ".toml", ".yaml", ".yml", ".lock", ".gradle", ".xml", ".proto", ".tex", ".ex", ".exs",
    ".scala", ".dart", ".lua", ".zig", ".hs", ".ml", ".jl", ".glsl", ".wgsl", ".ipynb",
}
_SCRATCH = re.compile(r"^(?:/private)?/tmp/|^/var/folders/|/scratchpad/|/\.cache/")

# Targets of a shell write. Conservative: a path we cannot name is not a write.
_REDIRECT = re.compile(r"(?<![0-9&<>])>>?\s*([^\s|;&<>()]+)")
_INPLACE = re.compile(r"\b(?:sed\s+-i(?:\s*''|\s*\"\")?|perl\s+-pi(?:\.bak)?(?:\s+-e)?)\s+.*?([\w./~-]+\.\w+)\s*(?:$|[;&|])")
_TEE = re.compile(r"\btee\s+(?:-a\s+)?([^\s|;&]+)")
_MOVE = re.compile(r"\b(?:mv|cp|rm|touch|git\s+mv|git\s+rm|git\s+checkout\s+--)\s+(?:-\w+\s+)*([^|;&]+)")


_HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n.*?\n\s*\2\s*(?:\n|$)", re.S)
_QUOTED = re.compile(r"'[^'\n]*'|\"(?:[^\"\\\n]|\\.)*\"")


def shape(cmd):
    """The command with heredoc bodies and quoted strings blanked out.

    `cat >> RUNLOG.md <<EOF ... ran the tests ... EOF` is a write, not a test run, and
    `git commit -m "fix build"` is a commit, not a build. Classify on what is left.
    """
    cmd = _HEREDOC.sub(lambda m: m.group(0).split("\n", 1)[0] + "\n", cmd or "")
    return _QUOTED.sub("''", cmd)


def shell_writes(cmd):
    """File paths a shell command plausibly writes."""
    cmd = shape(cmd)
    if not cmd:
        return []
    out = []
    for rx in (_REDIRECT, _INPLACE, _TEE):
        out += rx.findall(cmd)
    for args in _MOVE.findall(cmd):
        out += [a for a in args.split() if not a.startswith("-")]
    return [p.strip("'\"") for p in out
            if p and not p.startswith(("/dev/", "&")) and p.strip("'\"") not in ("", "-")]


def is_code(path, cwd=""):
    """A source or config file, not a throwaway under a temp dir (unless the project lives there)."""
    if not path or (_SCRATCH.search(path) and not (cwd and path.startswith(cwd))):
        return False
    return os.path.splitext(path)[1].lower() in CODE_EXT


def outcome(call, outputs_after=()):
    """'pass', 'fail' or 'unknown' for a command that is supposed to succeed.

    A backgrounded command's verdict lives in whatever later receipt reported
    on it (a notification, a BashOutput poll), so those are passed in.
    """
    text = call.output
    if BACKGROUNDED.search(text[:300]):
        text = "\n".join(c.output for c in outputs_after)
        if not text:
            return "unknown"
        if FAILED.search(text):
            return "fail"
        return "pass" if PASSED.search(text) else "unknown"
    if call.is_error or (call.exit_code not in (None, 0)):
        return "fail"
    if FAILED.search(text):
        return "fail"
    return "pass"
