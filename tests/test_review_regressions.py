"""Offline regression cases from the 2026-10-29 release review."""
import io
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from the_cartographer import backends, catalogue, cli, install, licences, mcp_server, web
from the_cartographer.prompt import END_MARKER
import test_finder as fixtures


class ReviewRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.add_skill("alpha")

    def add_skill(self, name):
        folder = self.root / name
        folder.mkdir(exist_ok=True)
        (folder / "SKILL.md").write_text("---\nname: %s\ndescription: %s testing.\n---\nRead me.\n" % (name, name),
                                        encoding="utf-8")
        return folder

    def server(self, *options):
        args = cli.build_parser().parse_args(["mcp", "--no-user-skills", "--no-bundled", "--skills-dir",
                                               str(self.root)] + list(options))
        return mcp_server.Server(args, out=io.BytesIO())

    def tool_response(self, server, name, arguments):
        server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": name, "arguments": arguments}})
        return json.loads(server.out.getvalue().splitlines()[-1])

    def test_codex_nonzero_exit_rejects_an_identical_valid_answer_file(self):
        skills = catalogue.scan_dir(str(self.root))
        for status in (0, 1):
            def run(args, stdin, timeout, cwd=None, env=None):
                Path(args[args.index("-o") + 1]).write_text("PICKS: none\n" + END_MARKER, encoding="utf-8")
                return status, "", "ERROR: synthetic failure" if status else ""
            with self.subTest(status=status), mock.patch.object(backends, "find_codex", return_value="codex"), \
                    mock.patch.object(backends, "_run", side_effect=run):
                code, text, _ = cli.ask(skills, "alpha", backend="codex")
                response = self.tool_response(self.server("--backend", "codex"), "ask_cartographer", {"brief": "alpha"})
                self.assertEqual(code, 3 if status else 0)
                self.assertEqual(response["result"]["isError"], bool(status))
                if status:
                    self.assertIn("codex exited 1", text)
                    self.assertIn("CARTOGRAPHER_UNAVAILABLE", response["result"]["content"][0]["text"])

    def test_malformed_commands_use_cli_and_mcp_fallback(self):
        skills = catalogue.scan_dir(str(self.root))
        for command in ("   ", '"unterminated'):
            with self.subTest(command=command):
                code, text, _ = cli.ask(skills, "alpha", backend="command", command=command)
                self.assertEqual(code, 3)
                self.assertIn("CARTOGRAPHER_UNAVAILABLE", text)
                response = self.tool_response(self.server("--backend", "command", "--command", command),
                                              "ask_cartographer", {"brief": "alpha"})
                self.assertNotIn("error", response)
                self.assertTrue(response["result"]["isError"])
                self.assertIn("CARTOGRAPHER_UNAVAILABLE", response["result"]["content"][0]["text"])

    def test_codex_failed_exit_does_not_inspect_output_artifacts(self):
        skills = catalogue.scan_dir(str(self.root))
        for artifact in ("directory", "invalid-bytes", "missing"):
            def run(args, stdin, timeout, cwd=None, env=None):
                path = Path(args[args.index("-o") + 1])
                if artifact == "directory":
                    path.mkdir()  # opening a directory as the answer raises before the process failure is handled
                elif artifact == "invalid-bytes":
                    path.write_bytes(b"\xff\xfe\x00unfinished")
                return 1, "", "ERROR: synthetic process failure"

            with self.subTest(artifact=artifact), mock.patch.object(backends, "find_codex", return_value="codex"), \
                    mock.patch.object(backends, "_run", side_effect=run):
                code, text, _ = cli.ask(skills, "alpha", backend="codex")
                response = self.tool_response(self.server("--backend", "codex"), "ask_cartographer", {"brief": "alpha"})
                self.assertEqual(code, 3)
                self.assertIn("CARTOGRAPHER_UNAVAILABLE", text)
                self.assertIn("synthetic process failure", text)
                self.assertNotIn("error", response)
                self.assertTrue(response["result"]["isError"])
                self.assertIn("CARTOGRAPHER_UNAVAILABLE", response["result"]["content"][0]["text"])

    def test_codex_unreadable_success_artifact_falls_back_and_stdout_only_still_succeeds(self):
        skills = catalogue.scan_dir(str(self.root))
        for artifact in ("directory", "stdout-only"):
            def run(args, stdin, timeout, cwd=None, env=None):
                if artifact == "directory":
                    Path(args[args.index("-o") + 1]).mkdir()
                    return 0, "", ""
                return 0, "PICKS: none\n" + END_MARKER, ""

            with self.subTest(artifact=artifact), mock.patch.object(backends, "find_codex", return_value="codex"), \
                    mock.patch.object(backends, "_run", side_effect=run):
                code, text, _ = cli.ask(skills, "alpha", backend="codex")
                response = self.tool_response(self.server("--backend", "codex"), "ask_cartographer", {"brief": "alpha"})
                self.assertEqual(code, 3 if artifact == "directory" else 0)
                self.assertNotIn("error", response)
                self.assertEqual(response["result"]["isError"], artifact == "directory")
                if artifact == "directory":
                    self.assertIn("CARTOGRAPHER_UNAVAILABLE", text)
                    self.assertIn("cannot read codex answer file", text)
                else:
                    self.assertIn("PICKS: none", text)

    def test_mcp_search_and_read_refresh_after_add_remove_and_rename(self):
        server = self.server()
        self.assertIn("alpha |", server.call_tool("search_skills", {"query": "alpha"})["content"][0]["text"])
        beta = self.add_skill("beta")
        self.assertIn("beta |", server.call_tool("search_skills", {"query": "beta"})["content"][0]["text"])
        self.assertFalse(server.call_tool("read_skill", {"name": "beta"})["isError"])
        (beta / "SKILL.md").write_text("---\nname: gamma\ndescription: gamma testing.\n---\nRenamed.\n", encoding="utf-8")
        self.assertTrue(server.call_tool("read_skill", {"name": "beta"})["isError"])
        self.assertFalse(server.call_tool("read_skill", {"name": "gamma"})["isError"])
        shutil.rmtree(beta)
        self.assertEqual(server.call_tool("search_skills", {"query": "gamma"})["content"][0]["text"], "no match")
        self.assertTrue(server.call_tool("read_skill", {"name": "gamma"})["isError"])

    def test_unknown_with_exceptions_fail_closed_without_losing_supported_case(self):
        self.assertEqual(licences.from_field("Apache-2.0 WITH LLVM-exception"), "Apache-2.0")
        self.assertTrue(licences.policy(licences.from_field("MIT"))[0])
        for expression in ("MIT WITH Noncommercial-use-only", "MIT WITH Made-up-exception", "MIT WITH LLVM-exception",
                           "Apache-2.0 WITH LLVM-exception WITH Made-up-exception", "MIT WITH"):
            with self.subTest(expression=expression):
                self.assertEqual(licences.from_field(expression), "UNKNOWN")
                self.assertFalse(licences.policy(licences.from_field(expression))[0])

    def test_install_unknown_with_exception_requires_explicit_override(self):
        files = {"skills/pbt/SKILL.md": fixtures.SKILL_MD % ("pbt", "license: MIT WITH Noncommercial-use-only\n")}
        for override in (False, True):
            routes = fixtures.gh_routes(files)
            routes["https://www.skills.sh/robots.txt"] = fixtures.ROBOTS
            routes["https://www.skills.sh/acme/tools/pbt"] = fixtures.skill_page("acme/tools/pbt", "Property tests.")
            fetch, _, _ = fixtures.fetcher(routes)
            dest = self.root / ("override" if override else "refused")
            code = install.run("acme/tools/pbt", dest=str(dest), yes=True, allow_any_licence=override,
                               fetcher=fetch, cache=str(self.root / "cache"), out=lambda _: None)
            self.assertEqual(code, 0 if override else 1)
            if override:
                record = install.read_record(str(dest / "pbt"))
                self.assertEqual(record["licence"], "UNKNOWN")
                self.assertTrue(record["licence_override"])
            else:
                self.assertFalse((dest / "pbt").exists())

    def test_spdx_operators_cannot_be_mistaken_for_licence_file_pointers(self):
        cases = {"MIT WITH See-LICENSE": "UNKNOWN", "MIT WITH LicenseRef-in-LICENSE": "UNKNOWN",
                 "MIT WITH complete terms in LICENSE": "UNKNOWN", "MIT AND See-LICENSE": "MIT AND UNKNOWN",
                 "MIT WITH(See-LICENSE)": "UNKNOWN", "MIT WITH: See-LICENSE": "UNKNOWN",
                 "MIT WITH/See-LICENSE": "UNKNOWN", "(MIT WITH See-LICENSE)": "UNKNOWN",
                 "MIT WITH (See-LICENSE)": "UNKNOWN", "LicenseRef-in-LICENSE": "UNKNOWN"}
        for expression, expected in cases.items():
            with self.subTest(expression=expression):
                self.assertEqual(licences.from_field(expression), expected)
                self.assertFalse(licences.policy(licences.from_field(expression))[0])
        for pointer in ("see LICENSE", "see LICENSE.txt", "in LICENSE", "Complete terms in LICENSE.txt", "LICENSE.txt",
                        "LICENSE-WITH-notes.txt", "see LICENSE-WITH-notes.txt", "see LICENSE.WITH.notes.txt"):
            with self.subTest(pointer=pointer):
                self.assertIsNone(licences.from_field(pointer))
        self.assertEqual(licences.from_field("Apache-2.0 WITH LLVM-exception"), "Apache-2.0")

    def test_install_pointer_looking_exception_with_permissive_root_requires_override(self):
        cases = (("MIT WITH See-LICENSE", "UNKNOWN", False), ("MIT WITH LicenseRef-in-LICENSE", "UNKNOWN", False),
                 ("MIT WITH complete terms in LICENSE", "UNKNOWN", False),
                 ("MIT AND See-LICENSE", "MIT AND UNKNOWN", False),
                 ("MIT WITH(See-LICENSE)", "UNKNOWN", False), ("MIT WITH: See-LICENSE", "UNKNOWN", False),
                 ("MIT WITH/See-LICENSE", "UNKNOWN", False), ("LicenseRef-in-LICENSE", "UNKNOWN", False),
                 ("see LICENSE", "MIT", True), ("Apache-2.0 WITH LLVM-exception", "Apache-2.0 AND MIT", True))
        for index, (expression, expected, allowed) in enumerate(cases):
            for override in (False, True):
                with self.subTest(expression=expression, override=override):
                    files = {"skills/pbt/SKILL.md": fixtures.SKILL_MD % ("pbt", "license: " + expression + "\n"),
                             "LICENSE": fixtures.MIT_FULL}
                    routes = fixtures.gh_routes(files)
                    routes["https://www.skills.sh/robots.txt"] = fixtures.ROBOTS
                    routes["https://www.skills.sh/acme/tools/pbt"] = fixtures.skill_page("acme/tools/pbt", "Tests.")
                    fetch, _, _ = fixtures.fetcher(routes)
                    dest = self.root / ("pointer-%d-%s" % (index, override))
                    output = []
                    code = install.run("acme/tools/pbt", dest=str(dest), yes=True, allow_any_licence=override,
                                       fetcher=fetch, cache=str(self.root / ("cache-%d-%s" % (index, override))),
                                       out=output.append)
                    self.assertEqual(code, 0 if allowed or override else 1, "\n".join(output))
                    if allowed or override:
                        record = install.read_record(str(dest / "pbt"))
                        self.assertEqual(record["licence"], expected)
                        self.assertEqual(record["licence_override"], not allowed)
                        self.assertEqual(record["licence_text"], ["LICENSE"])
                        self.assertEqual((dest / "pbt" / "LICENSE").read_text(encoding="utf-8"), fixtures.MIT_FULL)
                    else:
                        self.assertFalse((dest / "pbt").exists())
                        self.assertTrue(any("--allow-any-licence" in line for line in output))

    def test_mcp_example_timeout_provides_default_attempt_headroom(self):
        config = (ROOT / "integrations/codex/config.toml").read_text(encoding="utf-8")
        timeout = int(re.search(r"tool_timeout_sec\s*=\s*(\d+)", config).group(1))
        # Independent client deadline: include older Claude CLI's second attempt and process cleanup.
        self.assertGreater(timeout, backends.CodexCliBackend().timeout + 40)
        self.assertGreater(timeout, 2 * backends.ClaudeCliBackend().timeout + 40)
        # Nominal API attempt headroom only: SDK backoff/Retry-After waits have no total bound here.
        self.assertGreater(timeout, 3 * backends.AnthropicBackend().timeout)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("tool_timeout_sec = %d" % timeout, readme)

    def test_bundled_playwright_relocation_is_present_for_show_read_and_ask(self):
        folder = self.root / "bundle with spaces"
        scripts = folder / "scripts"
        scripts.mkdir(parents=True)
        wrapper = scripts / "playwright_cli.sh"
        wrapper.write_text("# fixture; never executed\n", encoding="utf-8")
        path = folder / "SKILL.md"
        path.write_text('export PWCLI="$CODEX_HOME/skills/playwright/scripts/playwright_cli.sh"\n', encoding="utf-8")
        skill = catalogue.Skill("openai/playwright", str(path), "Browser automation", path.stat().st_size, "bundled")
        with mock.patch.object(mcp_server, "load_skills", return_value=[skill]), \
                mock.patch.object(cli, "load_skills", return_value=[skill]):
            served = self.server().call_tool("read_skill", {"name": "openai/playwright"})["content"][0]["text"]
            out = io.StringIO()
            with redirect_stdout(out):
                cli.cmd_show(type("Args", (), {"name": "openai/playwright"})())
        model = mock.Mock()
        model.ask.return_value = ("PICKS:\n- openai/playwright | ignored | fits | read: whole\n" + END_MARKER, {})
        with mock.patch.object(backends, "make", return_value=model):
            code, answer, info = cli.ask([skill], "browser task", backend="command")
        self.assertEqual(code, 0)
        expected = "export PWCLI=" + shlex.quote(str(wrapper).replace("\\", "/"))
        for text in (served, out.getvalue(), answer, "\n".join(info["answer"]["notes"])):
            self.assertIn(expected, text)
            self.assertIn('bash "$PWCLI"', text)
        assignment = expected.removeprefix("export ")
        self.assertEqual(shlex.split(assignment)[0].split("=", 1)[1], str(wrapper).replace("\\", "/"))

    @unittest.skipUnless(os.name == "posix", "requires POSIX file execute permissions")
    def test_playwright_guidance_runs_a_non_executable_bash_fixture(self):
        bash = shutil.which("bash")
        if not bash:
            self.skipTest("Bash is required by the Playwright wrapper")
        folder = self.root / "non executable fixture"
        scripts = folder / "scripts"
        scripts.mkdir(parents=True)
        wrapper = scripts / "playwright_cli.sh"
        wrapper.write_text('#!/usr/bin/env bash\nprintf "fixture:%s\\n" "$1"\n', encoding="utf-8")
        wrapper.chmod(0o644)
        self.assertFalse(os.access(wrapper, os.X_OK))
        with self.assertRaises(PermissionError):
            subprocess.run([str(wrapper), "--help"], check=True, capture_output=True, text=True, timeout=5)
        path = folder / "SKILL.md"
        path.write_text("Local inert fixture only.\n", encoding="utf-8")
        skill = catalogue.Skill("openai/playwright", str(path), "Fixture", path.stat().st_size, "bundled")
        note = catalogue.skill_read_note(skill)
        self.assertIn('bash "$PWCLI"', note)
        self.assertNotIn("wslpath", re.search(r"`(export PWCLI=[^`]+)`", note).group(1))
        assignment = re.search(r"`(export PWCLI=[^`]+)`", note).group(1)
        result = subprocess.run([bash, "-c", assignment + '; bash "$PWCLI" --help'],
                                check=True, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.stdout, "fixture:--help\n")

    @unittest.skipUnless(os.name == "nt" and shutil.which("wsl"), "requires Windows with WSL")
    def test_shared_windows_wsl_cache_refuses_incompatible_locks(self):
        distro = os.environ.get("CARTOGRAPHER_TEST_WSL_DISTRO", "Ubuntu-24.04")
        prefix = ["wsl", "--distribution", distro, "--exec"]
        probe = subprocess.run(prefix + ["wslpath", "-u", str(ROOT)],
                               capture_output=True, text=True, timeout=20)
        if probe.returncode:
            self.skipTest("WSL distribution with wslpath is unavailable: " + distro)
        source = probe.stdout.strip()

        def wsl_path(path):
            result = subprocess.run(prefix + ["wslpath", "-u", str(path)],
                                    capture_output=True, text=True, check=True, timeout=20)
            return result.stdout.strip()

        code = ("import sys, time\nfrom pathlib import Path\n"
                "sys.path.insert(0, sys.argv[1])\nfrom the_cartographer.web import NetState, WebError\n"
                "state = NetState(sys.argv[2])\n"
                "if sys.argv[3] == 'hold':\n"
                " state.lock(wait=1)\n Path(sys.argv[4]).write_text('held')\n"
                " deadline = time.monotonic() + 15\n"
                " while not Path(sys.argv[5]).exists() and time.monotonic() < deadline: time.sleep(0.01)\n"
                " state.unlock()\n"
                "else:\n"
                " try: state.lock(wait=0.05)\n"
                " except (WebError, OSError): print('REFUSED')\n"
                " else:\n  state.unlock()\n  print('ACQUIRED')\n  sys.exit(1)\n")
        linux_cache = self.root / "linux-cache"
        ready, release = self.root / "wsl-held", self.root / "wsl-release"
        args = prefix + ["python3", "-B", "-c", code, source, wsl_path(linux_cache)]
        child = subprocess.Popen(args + ["hold", wsl_path(ready), wsl_path(release)],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        state = web.NetState(str(linux_cache))
        try:
            deadline = time.monotonic() + 10
            while not ready.exists() and child.poll() is None and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(ready.exists(), "WSL holder did not acquire the shared cache")
            # A second WSL process must be excluded too: the first really holds its native lock.
            control = subprocess.run(args + ["try"], capture_output=True, text=True, timeout=10)
            self.assertEqual(control.returncode, 0, control.stderr)
            self.assertEqual(control.stdout.strip(), "REFUSED")
            self.assertIsNone(child.poll())
            with self.assertRaises(web.WebError):
                state.lock(wait=0.05)
            self.assertFalse(state._held)
            self.assertIsNone(child.poll())
        finally:
            state.unlock()
            release.touch()
            child.communicate(timeout=10)
        self.assertEqual(child.returncode, 0)
        original_marker = (linux_cache / "fetch.lock").read_bytes()
        with self.assertRaises(web.WebError):
            state.lock(wait=0)  # a stopped foreign holder still requires a different cache or manual migration
        self.assertEqual((linux_cache / "fetch.lock").read_bytes(), original_marker)

        windows_cache = self.root / "windows-cache"
        state = web.NetState(str(windows_cache))
        state.lock(wait=0)
        try:
            result = subprocess.run(prefix + ["python3", "-B", "-c", code, source,
                                             wsl_path(windows_cache), "try"],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "REFUSED")
            self.assertTrue(state._held)
        finally:
            state.unlock()

    @unittest.skipUnless(os.name == "nt" and shutil.which("wsl"), "requires Windows with WSL")
    def test_windows_playwright_guidance_converts_spaced_path_in_real_wsl(self):
        # Optional integration control: no bundled wrapper, downloads or external command packages run here.
        distro = os.environ.get("CARTOGRAPHER_TEST_WSL_DISTRO", "Ubuntu-24.04")
        probe = subprocess.run(["wsl", "--distribution", distro, "--exec", "bash", "-c", "command -v wslpath"],
                               capture_output=True, text=True, timeout=20)
        if probe.returncode:
            self.skipTest("WSL distribution with wslpath is unavailable: " + distro)
        folder = self.root / "Windows fixture's spaced path"
        scripts = folder / "scripts"
        scripts.mkdir(parents=True)
        wrapper = scripts / "playwright_cli.sh"
        wrapper.write_text('#!/usr/bin/env bash\nprintf "fixture:%s\\n" "$1"\n', encoding="utf-8")
        path = folder / "SKILL.md"
        skill = catalogue.Skill("openai/playwright", str(path), "Inert fixture", 0, "bundled")
        note = catalogue.skill_read_note(skill)
        # Execute the Cartographer-owned assignment exactly as delivered, then its explicit Bash invocation.
        assignment = re.search(r"`(export PWCLI=[^`]+)`", note).group(1)
        result = subprocess.run(["wsl", "--distribution", distro, "--exec", "bash", "-c",
                                 assignment + '; bash "$PWCLI" --help'],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "fixture:--help\n")
        # Simulate Git Bash's lack of WSL environment flags: preserve its usable C:/... assignment verbatim.
        result = subprocess.run(["wsl", "--distribution", distro, "--exec", "env", "-u", "WSL_DISTRO_NAME",
                                 "-u", "WSL_INTEROP", "bash", "-c", assignment + '; printf "%s" "$PWCLI"'],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, str(wrapper).replace("\\", "/"))


if __name__ == "__main__":
    unittest.main()
