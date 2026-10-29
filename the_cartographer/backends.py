"""Model backends. Each takes the catalogue text and a brief and returns (answer_text, info). complete(system, message)
is the same call with any system text (the finder's judge uses it); ask() goes through it with the cartographer's own.

anthropic  Claude API through the official SDK. The catalogue is a cached system block (1 hour TTL), so repeat asks
           read it from cache instead of paying for it again.
claude     Claude Code CLI in print mode (`claude -p`), using whatever login the user already has. Customisations,
           tools and session saving are switched off so the cartographer sees only its own prompt.
codex      Codex CLI (`codex exec`), read-only sandbox, shell tool off, ephemeral session.
command    Any command that reads the full prompt on stdin and prints the answer (local models, other CLIs).
"""
import glob, os, shlex, shutil, signal, subprocess, tempfile

from .prompt import RULES, single_prompt, user_message

DEFAULT_API_MODEL = "claude-opus-5-5"
FALLBACK_MODELS = {"claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"}


class BackendError(RuntimeError):
    pass


def _cmd_arg(a):
    """Quote one argument for a Windows .cmd/.bat shim: cmd.exe splits on & | < > ^ ( ) unless they are in quotes."""
    q = subprocess.list2cmdline([a])
    if not q.startswith('"') and any(c in a for c in "&|<>^()"):
        q = '"%s"' % q
    return q


def _kill_tree(p):
    """Kill the child and everything it started. A shim (claude.cmd, a shell wrapper) leaves its real program
    holding the output pipes, so killing only the shim would leave the read waiting for that program to finish."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True, timeout=30)
        else:
            os.killpg(p.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        p.kill()
    except OSError:
        pass


def _run(args, stdin_text, timeout, cwd=None, env=None):
    exe = shutil.which(args[0]) or args[0]  # PATHEXT on Windows: `mymodel` finds mymodel.cmd
    args = [exe] + list(args[1:])
    env = dict(os.environ if env is None else env)
    env.setdefault("PYTHONIOENCODING", "utf-8")  # a Python wrapper reads and prints UTF-8, not the console code page
    if os.name == "nt" and exe.lower().endswith((".cmd", ".bat")):
        # Windows runs a batch file through cmd.exe by itself. Wrapping it in `cmd /c` again double-quotes the line:
        # a path with a space then fails and an empty argument ("") arrives as two quote characters.
        popen_args, extra = " ".join(_cmd_arg(a) for a in args), {}
    else:
        popen_args, extra = args, ({} if os.name == "nt" else {"start_new_session": True})
    try:
        p = subprocess.Popen(popen_args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             cwd=cwd, env=env, **extra)
    except FileNotFoundError:
        raise BackendError("not found: %s" % exe)
    except OSError as e:
        raise BackendError("cannot run %s: %s" % (exe, e))
    try:
        out, err = p.communicate(stdin_text.encode("utf-8"), timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(p)
        try:
            p.communicate(timeout=10)
        except (subprocess.TimeoutExpired, OSError, ValueError):
            pass
        raise BackendError("no answer in %ds" % timeout)
    except BaseException:  # Ctrl-C and the like: do not leave the model running
        _kill_tree(p)
        raise
    return p.returncode, out.decode("utf-8", errors="replace"), err.decode("utf-8", errors="replace")


def _tail(out, err, n=300):
    """The end of the error output: a traceback or a CLI error says what went wrong in its last lines."""
    return (err or out).strip()[-n:]


class AnthropicBackend:
    name = "anthropic"

    def __init__(self, model=None, effort="medium", timeout=120, fallbacks=True):
        self.model = model or DEFAULT_API_MODEL
        self.effort = effort
        self.timeout = timeout
        self.fallbacks = fallbacks

    @staticmethod
    def available():
        try:
            import anthropic  # noqa: F401
        except ImportError:
            return False, "pip install anthropic"
        if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
            return False, "set ANTHROPIC_API_KEY"
        return True, ""

    def ask(self, catalogue_text, brief, requester="unknown"):
        system = [{"type": "text", "text": RULES},
                  {"type": "text", "text": catalogue_text, "cache_control": {"type": "ephemeral", "ttl": "1h"}}]
        return self._call(system, user_message(brief, requester))

    def complete(self, system_text, message):
        """One plain call: a system text and a user message, no tools (the finder's judge)."""
        return self._call([{"type": "text", "text": system_text}], message)

    def _call(self, system, message):
        try:
            import anthropic
        except ImportError:
            raise BackendError("the anthropic package is not installed (pip install anthropic)")
        client = anthropic.Anthropic(timeout=self.timeout, max_retries=2)
        kwargs = {"model": self.model, "max_tokens": 16000, "system": system,
                  "messages": [{"role": "user", "content": message}]}
        if self.effort and self.effort != "none":
            kwargs["output_config"] = {"effort": self.effort}
        try:
            if self.fallbacks and self.model in FALLBACK_MODELS:
                # On a policy decline the API re-runs the request on a fallback model inside the same call.
                try:
                    resp = client.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default",
                                                       **kwargs)
                except TypeError:  # an SDK release that does not know the parameter yet
                    resp = client.beta.messages.create(betas=["server-side-fallback-2026-07-01"],
                                                       extra_body={"fallbacks": "default"}, **kwargs)
            else:
                resp = client.messages.create(**kwargs)
        except anthropic.AuthenticationError:
            raise BackendError("the API key was refused")
        except anthropic.RateLimitError:
            raise BackendError("rate limited")
        except anthropic.APIStatusError as e:
            raise BackendError("API error %s: %s" % (e.status_code, getattr(e, "message", e)))
        except anthropic.APIConnectionError:
            raise BackendError("cannot reach the API")
        if resp.stop_reason == "refusal":
            raise BackendError("the model declined the brief")
        text = "".join(getattr(b, "text", "") for b in resp.content if b.type == "text")
        u = resp.usage
        info = {"backend": self.name, "model": resp.model, "input_tokens": u.input_tokens,
                "cache_read_tokens": getattr(u, "cache_read_input_tokens", 0) or 0,
                "cache_write_tokens": getattr(u, "cache_creation_input_tokens", 0) or 0,
                "output_tokens": u.output_tokens}
        return text, info


def find_claude():
    return os.environ.get("CARTOGRAPHER_CLAUDE_BIN") or shutil.which("claude")


class ClaudeCliBackend:
    name = "claude"

    def __init__(self, model=None, effort="medium", timeout=180, exe=None):
        self.model = model
        self.effort = effort
        self.timeout = timeout
        self.exe = exe

    @staticmethod
    def available():
        return (True, "") if find_claude() else (False, "install Claude Code (the `claude` command)")

    def ask(self, catalogue_text, brief, requester="unknown"):
        return self.complete(RULES + "\n\n" + catalogue_text, user_message(brief, requester))

    def complete(self, system_text, msg):
        exe = self.exe or find_claude()
        if not exe:
            raise BackendError("the claude command was not found (set CARTOGRAPHER_CLAUDE_BIN)")
        work = tempfile.mkdtemp(prefix="cartographer-")
        try:
            sp = os.path.join(work, "system-prompt.md")
            with open(sp, "w", encoding="utf-8", newline="\n") as f:
                f.write(system_text)
            tail = ["--no-session-persistence", "--output-format", "text", "--system-prompt-file", sp]
            if self.model:
                tail += ["--model", self.model]
            if self.effort and self.effort != "none":
                tail += ["--effort", self.effort]
            env = dict(os.environ, CLAUDE_CODE_DISABLE_CLAUDE_MDS="1")
            # --safe-mode turns off CLAUDE.md, skills, plugins, hooks and MCP servers; --tools "" removes every tool.
            code, out, err = _run([exe, "-p", "--safe-mode", "--tools", ""] + tail, msg, self.timeout, work, env)
            if code != 0 and "safe-mode" in err.lower():  # an older Claude Code without --safe-mode
                code, out, err = _run([exe, "-p", "--tools", "", "--strict-mcp-config", "--setting-sources", "",
                                       "--disable-slash-commands"] + tail, msg, self.timeout, work, env)
            if code != 0:
                raise BackendError("claude exited %d: %s" % (code, _tail(out, err)))
            return out, {"backend": self.name, "model": self.model or "(claude default)"}
        finally:
            shutil.rmtree(work, ignore_errors=True)


def find_codex():
    exe = os.environ.get("CARTOGRAPHER_CODEX_BIN") or shutil.which("codex")
    if exe:
        return exe
    if os.name == "nt":  # the Codex desktop app keeps its CLI under %LOCALAPPDATA%\OpenAI\Codex\bin\<build>\
        base = os.path.join(os.environ.get("LOCALAPPDATA", ""), "OpenAI", "Codex", "bin")
        found = sorted(glob.glob(os.path.join(base, "*", "codex.exe")), key=os.path.getmtime)
        if found:
            return found[-1]
    return None


class CodexCliBackend:
    name = "codex"

    def __init__(self, model=None, effort="medium", timeout=240, exe=None, keep_user_config=False):
        self.model = model
        self.effort = effort
        self.timeout = timeout
        self.exe = exe
        self.keep_user_config = keep_user_config or bool(os.environ.get("CARTOGRAPHER_CODEX_KEEP_CONFIG"))

    @staticmethod
    def available():
        return (True, "") if find_codex() else (False, "install the Codex CLI (the `codex` command)")

    def ask(self, catalogue_text, brief, requester="unknown"):
        return self._run_prompt(single_prompt(catalogue_text, brief, requester))

    def complete(self, system_text, message):
        return self._run_prompt(system_text + "\n\n" + message + "\n")

    def _run_prompt(self, prompt):
        exe = self.exe or find_codex()
        if not exe:
            raise BackendError("the codex command was not found (set CARTOGRAPHER_CODEX_BIN)")
        work = tempfile.mkdtemp(prefix="cartographer-")
        try:
            last = os.path.join(work, "answer.md")
            args = [exe, "exec", "--ephemeral", "-s", "read-only", "--skip-git-repo-check", "--ignore-rules",
                    "-C", work, "-o", last, "-c", "features.shell_tool=false", "-c", 'approval_policy="never"']
            if not self.keep_user_config:
                args.append("--ignore-user-config")  # no MCP servers or hooks from the user's config
            if self.model:
                args += ["-m", self.model]
            if self.effort and self.effort != "none":
                args += ["-c", 'model_reasoning_effort="%s"' % self.effort]
            args.append("-")
            code, out, err = _run(args, prompt, self.timeout, work)
            text = ""
            if os.path.exists(last):
                with open(last, encoding="utf-8", errors="replace") as f:
                    text = f.read()
            if code != 0 and not text.strip():
                errors = [l.strip() for l in (err + "\n" + out).splitlines() if l.strip().startswith("ERROR")]
                detail = errors[-1] if errors else (err or out).strip()[-300:]
                raise BackendError("codex exited %d: %s" % (code, detail))
            return text or out, {"backend": self.name, "model": self.model or "(codex default)"}
        finally:
            shutil.rmtree(work, ignore_errors=True)


class CommandBackend:
    name = "command"

    def __init__(self, command=None, timeout=240):
        self.command = command or os.environ.get("CARTOGRAPHER_COMMAND")
        self.timeout = timeout

    @staticmethod
    def available():
        return (True, "") if os.environ.get("CARTOGRAPHER_COMMAND") else (False, "set CARTOGRAPHER_COMMAND")

    def ask(self, catalogue_text, brief, requester="unknown"):
        return self._run_prompt(single_prompt(catalogue_text, brief, requester))

    def complete(self, system_text, message):
        return self._run_prompt(system_text + "\n\n" + message + "\n")

    def _run_prompt(self, prompt):
        if not self.command:
            raise BackendError("no command given (--command or CARTOGRAPHER_COMMAND)")
        args = shlex.split(self.command, posix=(os.name != "nt"))
        args = [a[1:-1] if len(a) > 1 and a[0] == a[-1] == '"' else a for a in args]
        code, out, err = _run(args, prompt, self.timeout)
        if code != 0:
            raise BackendError("command exited %d: %s" % (code, _tail(out, err)))
        return out, {"backend": self.name}


BACKENDS = {"anthropic": AnthropicBackend, "claude": ClaudeCliBackend, "codex": CodexCliBackend,
            "command": CommandBackend}


def pick_default():
    """First backend that looks usable: an API key, then Claude Code, then Codex, then a configured command."""
    for name in ("anthropic", "claude", "codex", "command"):
        ok, _ = BACKENDS[name].available()
        if ok:
            return name
    return None


def make(name, model=None, effort="medium", timeout=None, command=None):
    if name == "command":
        return CommandBackend(command, timeout or 240)
    cls = BACKENDS.get(name)
    if cls is None:
        raise BackendError("unknown backend %r (anthropic, claude, codex, command)" % name)
    b = cls(model=model, effort=effort)
    if timeout:
        b.timeout = timeout
    return b
