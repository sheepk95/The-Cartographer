"""Offline tests: no model is called. Run with  python -m unittest discover -s tests"""
import io, json, os, shutil, subprocess, sys, tempfile, textwrap, time, types, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from the_cartographer import answer, backends, catalogue, cli, frontmatter, mcp_server  # noqa: E402
from the_cartographer.prompt import END_MARKER  # noqa: E402


def setUpModule():
    # every temporary folder this module makes lands in one, removed when the module ends
    global _old_tempdir, _tmp_root
    _old_tempdir, _tmp_root = tempfile.tempdir, tempfile.mkdtemp(prefix="cartographer-tests-")
    tempfile.tempdir = _tmp_root


def tearDownModule():
    tempfile.tempdir = _old_tempdir
    shutil.rmtree(_tmp_root, ignore_errors=True)


def make_skill(root, name, description, body="Body text.\n", pad=0):
    d = os.path.join(root, name)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "SKILL.md"), "w", encoding="utf-8") as f:
        f.write("---\nname: %s\ndescription: %s\n---\n\n%s%s" % (name, description, body, "x" * pad))
    return os.path.join(d, "SKILL.md")


class FrontmatterTests(unittest.TestCase):
    def test_shapes(self):
        cases = {
            "---\nname: a\ndescription: plain words\n---\n": "plain words",
            "---\nname: a\ndescription: 'it''s quoted'\n---\n": "it's quoted",
            '---\nname: a\ndescription: "say \\"hi\\""\n---\n': 'say "hi"',
            "---\nname: a\ndescription: >\n  folded\n  lines\n---\n": "folded lines",
            "---\nname: a\ndescription: |\n  line one\n  line two\n---\n": "line one\nline two",
            "---\nname: a\ndescription: starts here\n  and goes on\nother: x\n---\n": "starts here and goes on",
            "---\nname: a\nmetadata:\n  k: v\ndescription: after a map\n---\n": "after a map",
        }
        for text, want in cases.items():
            self.assertEqual(frontmatter.parse(text)["description"], want, text)

    def test_no_front_matter(self):
        self.assertEqual(frontmatter.parse("# Title\nno front matter"), {})


class CatalogueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.a = make_skill(self.tmp, "alpha", "Write alpha reports.")
        self.b = make_skill(self.tmp, "beta", "Tune beta engines.", pad=catalogue.LARGE_BYTES + 10)
        os.makedirs(os.path.join(self.tmp, ".hidden", "x"))

    def build(self, **kw):
        return catalogue.build(extra_dirs=[self.tmp], user_skills=False, bundled=False, **kw)

    def test_scan_and_render_is_stable(self):
        skills = self.build()
        self.assertEqual([s.name for s in skills], ["alpha", "beta"])
        self.assertTrue(skills[1].large and not skills[0].large)
        text = catalogue.render(skills)
        beta_line = next(l for l in text.splitlines() if l.startswith("- **beta**"))
        self.assertIn("(LARGE - read in parts", beta_line)
        self.assertEqual(text, catalogue.render(self.build()))  # same skills, same bytes: the cache keeps hitting

    def test_duplicates(self):
        other = tempfile.mkdtemp()
        make_skill(other, "alpha", "A second alpha.")
        skills = catalogue.build(extra_dirs=[self.tmp, other, self.tmp], user_skills=False, bundled=False)
        self.assertEqual(sorted(s.name for s in skills), ["alpha", "alpha#2", "beta"])

    def test_search(self):
        hits = catalogue.search(self.build(), ["beta", "engines"])
        self.assertEqual(hits[0].name, "beta")


class AnswerTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.mkdtemp()
        make_skill(tmp, "alpha", "Write alpha reports.")
        make_skill(tmp, "beta", "Tune beta engines.", pad=catalogue.LARGE_BYTES + 10)
        self.skills = catalogue.build(extra_dirs=[tmp], user_skills=False, bundled=False)

    def test_fix_paths_and_drop_unknown(self):
        raw = textwrap.dedent("""\
            PICKS:
            - alpha | wrong/path/SKILL.md | reports | read: whole
            - ghost | /nowhere/SKILL.md | invented | read: whole
            MAYBE:
            - beta | x | maybe engines | read: whole
            ALSO GREP: alpha reports
            NOTE: one note
            """) + END_MARKER
        a = answer.check(answer.parse(raw), self.skills)
        self.assertEqual([e["name"] for e in a["picks"]], ["alpha"])
        self.assertTrue(a["picks"][0]["path"].endswith("alpha/SKILL.md"))
        self.assertEqual(a["maybe"][0]["read"], "read: LARGE read in parts")
        self.assertTrue(any("ghost" in n for n in a["notes"]))
        self.assertTrue(answer.render(a).endswith(END_MARKER))

    def test_none_and_missing_marker(self):
        a = answer.check(answer.parse("PICKS: none\n" + END_MARKER), self.skills)
        self.assertEqual(answer.render(a).splitlines()[0], "PICKS: none")
        with self.assertRaises(answer.AnswerError):
            answer.parse("PICKS: none\n")

    def test_a_malformed_answer_is_an_error_not_none(self):
        # prose, an empty or unreadable PICKS section: each must fail (exit 3, fallback), never render "PICKS: none"
        for raw in ("I think you should read the testing skills.\n",
                    "MAYBE:\n- beta | b/SKILL.md | might fit | read: whole\n",
                    "PICKS:\nalpha would fit, and so would beta.\n",
                    "PICKS:\n- alpha, because it fits\n",
                    "PICKS: alpha and beta\n",
                    "PICKS:\n"):
            with self.subTest(raw=raw), self.assertRaises(answer.AnswerError):
                answer.parse(raw + END_MARKER)
        for raw in ("PICKS: none\n", "**PICKS:** None.\n",
                    "PICKS:\n- alpha | a/SKILL.md | fits | read: whole\nprose\n"):
            with self.subTest(raw=raw):
                answer.parse(raw + END_MARKER)  # an explicit none, or readable picks with a stray line, still parse

    def test_an_explicit_none_with_a_reason_is_still_none(self):
        # the prompt asks for "PICKS: none"; a model that adds a reason, brackets it or puts it on the next line has
        # still said none, and must not be sent to the fallback as if its answer were unreadable
        for raw in ("PICKS: none (the task is mechanical)\n", "PICKS: None \u2014 copying files needs no skill.\n",
                    "PICKS: (none)\n", "PICKS:\nnone\n", "PICKS:\n- none\n"):
            with self.subTest(raw=raw):
                self.assertEqual(answer.parse(raw + END_MARKER)["picks"], [])
        for raw in ("PICKS: none-such\n", "PICKS: nonexistent\n", "PICKS:\n- none-such\n"):
            with self.subTest(raw=raw), self.assertRaises(answer.AnswerError):
                answer.parse(raw + END_MARKER)  # a word that only starts with "none" is not a none

    def test_a_path_that_starts_with_none_is_not_none(self):
        # "none/testing" is a path or a name, not "no skill fits": it must fail like any unreadable PICKS section
        for raw in ("PICKS: none/testing\n", "PICKS:\n- none/testing\n", "PICKS: none\\testing\n",
                    "PICKS: none|x\n", "PICKS: none_x\n", "PICKS: none2\n", "PICKS: none.md\n"):
            with self.subTest(raw=raw), self.assertRaises(answer.AnswerError):
                answer.parse(raw + END_MARKER)
        for raw in ("PICKS: none, nothing fits\n", "PICKS: none; mechanical\n", "PICKS: none: mechanical\n",
                    "PICKS: none - mechanical\n", "PICKS: none- mechanical\n", "PICKS: none\u2014 mechanical\n",
                    "PICKS: none(mechanical)\n", "PICKS: none.\n"):
            with self.subTest(raw=raw):
                self.assertEqual(answer.parse(raw + END_MARKER)["picks"], [])

    def test_an_unreadable_line_beside_readable_picks_is_noted(self):
        p = answer.parse("PICKS:\n- alpha | a/SKILL.md | fits | read: whole\n- beta, because it fits\n" + END_MARKER)
        self.assertEqual([e["name"] for e in p["picks"]], ["alpha"])
        self.assertTrue(any("beta, because it fits" in n for n in p["notes"]), p["notes"])

    def test_stray_characters_around_none_are_not_none(self):
        # only paired markdown wrappers, brackets and one trailing period come off a none: ".none" and "none_" are
        # names or paths, and "no**ne" is not a word the model wrote
        for raw in ("PICKS: .none\n", "PICKS: none_\n", "PICKS:\n- .none\n", "PICKS:\n- none_\n", "PICKS: _none\n",
                    "PICKS: no**ne\n", "PICKS: no__ne\n", "PICKS: (none\n", "PICKS: none)\n", "PICKS: none..\n"):
            with self.subTest(raw=raw), self.assertRaises(answer.AnswerError):
                answer.parse(raw + END_MARKER)
        for raw in ("PICKS: (none)\n", "PICKS: None.\n", "PICKS: **none**\n", "PICKS: `none`\n", "PICKS: [none]\n",
                    "**PICKS: none**\n", "**PICKS:** None.\n", "PICKS: (none).\n", "PICKS:\n- **none**\n",
                    "PICKS: *none*\n", "PICKS: _none_\n", "## PICKS: none\n"):
            with self.subTest(raw=raw):
                self.assertEqual(answer.parse(raw + END_MARKER)["picks"], [])

    def test_the_whole_none_expression_is_checked(self):
        # "none(" then a path, an unclosed bracket or a pick field is not an explicit none
        for raw in ("PICKS: none(foo)/SKILL.md\n", "PICKS: none(/testing\n", "PICKS: none (foo) /x\n",
                    "PICKS: none(foo)bar\n", "PICKS: none: a | b\n", "PICKS: none (a) | b\n", "PICKS: none((x)\n",
                    "PICKS: none - copy to a/b\n", "PICKS:\n- none(foo)/SKILL.md\n", "PICKS: none\u2014such\n"):
            with self.subTest(raw=raw), self.assertRaises(answer.AnswerError):
                answer.parse(raw + END_MARKER)
        for raw in ("PICKS: none(mechanical)\n", "PICKS: none: mechanical\n", "PICKS: none.\n",
                    "PICKS: none - mechanical\n", "PICKS: none \u2013 mechanical\n", "PICKS: none \u2014 mechanical\n",
                    "PICKS: none (see a/b for why)\n", "PICKS: none the task is mechanical\n",
                    "PICKS: None. Copying files needs no skill.\n", "PICKS: none (mechanical), nothing fits\n",
                    "PICKS: none:\n"):
            with self.subTest(raw=raw):
                self.assertEqual(answer.parse(raw + END_MARKER)["picks"], [])

    def test_a_pick_row_needs_four_full_fields(self):
        # the prompt asks for exactly four " | " fields; a row with an empty field or the wrong count is not a pick,
        # and a PICKS section of only such rows is malformed, not "none"
        for row in ("- ghost |  | why | read: whole", "- ghost | g/SKILL.md | why",
                    "-  | g/SKILL.md | why | read: whole", "- ghost | g/SKILL.md |  | read: whole",
                    "- ghost | g/SKILL.md | why | read: whole | extra", "- ghost | g/SKILL.md | why | whole",
                    "- ghost | g/SKILL.md | why |", "- `` | g/SKILL.md | w | read: whole"):
            with self.subTest(row=row), self.assertRaises(answer.AnswerError):
                answer.parse("PICKS:\n" + row + "\n" + END_MARKER)
        p = answer.parse("PICKS:\n- alpha | a/SKILL.md | fits | read: whole\n"
                         "- beta | b/SKILL.md | engines | read: LARGE read in parts\n- ghost |  | why | read: whole\n"
                         "MAYBE:\n- gamma | c/SKILL.md | might fit | read: whole\n" + END_MARKER)
        self.assertEqual([e["name"] for e in p["picks"]], ["alpha", "beta"])
        self.assertEqual([e["name"] for e in p["maybe"]], ["gamma"])
        self.assertTrue(any("ghost" in n for n in p["notes"]), p["notes"])  # the bad row is noted, not dropped silently

    def test_third_review_cases(self):
        # a bare "|" inside a field is text, markdown may wrap the header and the none separately, "read:" needs a
        # mode, and a bracketed reason must close with its own bracket and hold no pick row
        p = answer.parse("PICKS:\n- alpha | a/SKILL.md | covers str|None unions | read: whole\n"
                         "- beta|b/SKILL.md|fits|read: whole\n" + END_MARKER)
        self.assertEqual([e["name"] for e in p["picks"]], ["alpha", "beta"])
        self.assertEqual(p["picks"][0]["why"], "covers str|None unions")
        for raw in ("**PICKS**: **none**\n", "__PICKS__: __none__\n", "PICKS: **none** (mechanical task)\n",
                    "PICKS: `none` - mechanical\n", "**PICKS:** **none**.\n"):
            with self.subTest(raw=raw):
                self.assertEqual(answer.parse(raw + END_MARKER)["picks"], [])
        for raw in ("PICKS:\n- alpha | a/SKILL.md | fits | read:\n", "PICKS:\n- alpha | a/SKILL.md | fits | read:  \n",
                    "PICKS: none (x]\n", "PICKS: none [x)\n", "PICKS: none (a | b | why | read: whole)\n",
                    "PICKS: **none\n", "PICKS: none**\n"):
            with self.subTest(raw=raw), self.assertRaises(answer.AnswerError):
                answer.parse(raw + END_MARKER)


FAKE_MODEL = textwrap.dedent("""\
    import sys
    prompt = sys.stdin.read()
    assert "<brief>" in prompt and "# Skill catalogue" in prompt
    print("PICKS:\\n- alpha | ? | fits | read: whole\\n%s")
    """) % END_MARKER


class CommandBackendTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        make_skill(self.tmp, "alpha", "Write alpha reports.")
        self.fake = os.path.join(self.tmp, "fake_model.py")
        with open(self.fake, "w", encoding="utf-8") as f:
            f.write(FAKE_MODEL)
        self.command = '"%s" "%s"' % (sys.executable, self.fake)

    def test_cli_ask_with_command_backend(self):
        skills = catalogue.build(extra_dirs=[self.tmp], user_skills=False, bundled=False)
        code, text, info = cli.ask(skills, "Write the alpha report", backend="command", command=self.command)
        self.assertEqual(code, 0, text)
        self.assertIn("- alpha | ", text)
        self.assertEqual(info["answer"]["picks"][0]["name"], "alpha")

    def test_unavailable_paths(self):
        skills = catalogue.build(extra_dirs=[self.tmp], user_skills=False, bundled=False)
        self.assertEqual(cli.ask(skills, "  ", backend="command", command=self.command)[0], 2)
        code, text, _ = cli.ask(skills, "task", backend="command", command='"%s" -c "import sys; sys.exit(4)"'
                                % sys.executable)
        self.assertEqual(code, 3)
        self.assertTrue(text.startswith("CARTOGRAPHER_UNAVAILABLE"))

    def test_a_malformed_answer_exits_3_not_none(self):
        # the whole path, not only the parser: prose with the end marker comes back as exit 3, never "PICKS: none"
        prose = os.path.join(self.tmp, "prose_model.py")
        with open(prose, "w", encoding="utf-8") as f:
            f.write("import sys\nsys.stdin.read()\nprint(%r)\n" % ("I would read alpha.\n" + END_MARKER))
        skills = catalogue.build(extra_dirs=[self.tmp], user_skills=False, bundled=False)
        code, text, _ = cli.ask(skills, "Write the alpha report", backend="command",
                                command='"%s" "%s"' % (sys.executable, prose))
        self.assertEqual(code, 3, text)
        self.assertTrue(text.startswith("CARTOGRAPHER_UNAVAILABLE") and "malformed" in text, text)
        self.assertNotIn("PICKS: none", text)

    def test_a_none_path_exits_3_not_none(self):
        # "none/testing" under PICKS is unreadable, not an explicit none: the CLI must exit 3, never print "PICKS: none"
        skills = catalogue.build(extra_dirs=[self.tmp], user_skills=False, bundled=False)
        for i, body in enumerate(("PICKS: none/testing\n", "PICKS:\n- none/testing\n")):
            model = os.path.join(self.tmp, "none_path_model_%d.py" % i)
            with open(model, "w", encoding="utf-8") as f:
                f.write("import sys\nsys.stdin.read()\nprint(%r)\n" % (body + END_MARKER))
            with self.subTest(body=body):
                code, text, _ = cli.ask(skills, "Write the alpha report", backend="command",
                                        command='"%s" "%s"' % (sys.executable, model))
                self.assertEqual(code, 3, text)
                self.assertTrue(text.startswith("CARTOGRAPHER_UNAVAILABLE") and "malformed" in text, text)
                self.assertNotIn("PICKS: none", text.splitlines())  # the error quotes the line; no answer is printed
                self.assertNotIn(END_MARKER, text)

    def ask_with(self, body, tag):
        model = os.path.join(self.tmp, "model_%s.py" % tag)
        with open(model, "w", encoding="utf-8") as f:
            f.write("import sys\nsys.stdin.read()\nprint(%r)\n" % (body + END_MARKER))
        skills = catalogue.build(extra_dirs=[self.tmp], user_skills=False, bundled=False)
        return cli.ask(skills, "Write the alpha report", backend="command",
                       command='"%s" "%s"' % (sys.executable, model))

    def test_bad_nones_and_bad_rows_exit_3_not_none(self):
        for i, body in enumerate(("PICKS: .none\n", "PICKS: none_\n", "PICKS: none(foo)/SKILL.md\n",
                                  "PICKS: none(/testing\n", "PICKS:\n- ghost |  | why | read: whole\n",
                                  "PICKS:\n- alpha | a/SKILL.md | fits\n",
                                  "PICKS:\n- alpha | a/SKILL.md | fits | read: whole | extra\n",
                                  "PICKS:\n- alpha | a/SKILL.md | fits | read:\n", "PICKS: none (x]\n",
                                  "PICKS: none (a | b | why | read: whole)\n")):
            with self.subTest(body=body):
                code, text, _ = self.ask_with(body, "bad_%d" % i)
                self.assertEqual(code, 3, text)
                self.assertTrue(text.startswith("CARTOGRAPHER_UNAVAILABLE") and "malformed" in text, text)
                self.assertNotIn("PICKS: none", text.splitlines())
                self.assertNotIn(END_MARKER, text)

    def test_every_pick_unknown_exits_3_some_unknown_is_a_note(self):
        # a model that named only skills the catalogue lacks did not say "none": that must not print "PICKS: none"
        code, text, info = self.ask_with("PICKS:\n- ghost | g/SKILL.md | why | read: whole\n"
                                         "- spook | s/SKILL.md | why | read: whole\n", "all_unknown")
        self.assertEqual(code, 3, text)
        self.assertTrue(text.startswith("CARTOGRAPHER_UNAVAILABLE") and "every pick was unknown" in text, text)
        self.assertIn("ghost", text)
        self.assertNotIn("PICKS: none", text.splitlines())
        self.assertIn("raw", info)
        code, text, _ = self.ask_with("PICKS:\n- alpha | ? | fits | read: whole\n"
                                      "- ghost | g/SKILL.md | why | read: whole\n", "some_unknown")
        self.assertEqual(code, 0, text)
        self.assertIn("- alpha | ", text)
        self.assertIn("NOTE: dropped names not in the catalogue: ghost", text)
        code, text, _ = self.ask_with("PICKS: none\n", "said_none")
        self.assertEqual((code, text.splitlines()[0]), (0, "PICKS: none"))


class AnthropicRequestShapeTests(unittest.TestCase):
    """Component test with a stand-in SDK: checks the request the API backend would send."""

    def test_request(self):
        sent = {}

        class Msgs:
            def create(self, **kw):
                sent.update(kw)
                usage = types.SimpleNamespace(input_tokens=10, cache_read_input_tokens=900,
                                              cache_creation_input_tokens=0, output_tokens=20)
                block = types.SimpleNamespace(type="text", text="PICKS: none\n" + END_MARKER)
                return types.SimpleNamespace(stop_reason="end_turn", content=[block], usage=usage, model=kw["model"])

        class Err(Exception):
            pass

        fake = types.SimpleNamespace(
            Anthropic=lambda **kw: types.SimpleNamespace(messages=Msgs(), beta=types.SimpleNamespace(messages=Msgs())),
            AuthenticationError=Err, RateLimitError=Err, APIStatusError=Err, APIConnectionError=Err)
        with mock.patch.dict(sys.modules, {"anthropic": fake}):
            text, info = backends.AnthropicBackend().ask("CATALOGUE", "a brief", "tester")
        self.assertEqual(sent["model"], "claude-opus-5-5")
        self.assertEqual(sent["system"][1]["cache_control"], {"type": "ephemeral", "ttl": "1h"})
        self.assertEqual(sent["system"][1]["text"], "CATALOGUE")
        self.assertEqual(sent["output_config"], {"effort": "medium"})
        self.assertEqual(sent["fallbacks"], "default")
        self.assertIn("a brief", sent["messages"][0]["content"])
        self.assertEqual(info["cache_read_tokens"], 900)


class McpTests(unittest.TestCase):
    def test_stdio_session(self):
        tmp = tempfile.mkdtemp()
        make_skill(tmp, "alpha", "Write alpha reports.", body="line1\nline2\nline3\n")
        fake = os.path.join(tmp, "fake_model.py")
        with open(fake, "w", encoding="utf-8") as f:
            f.write(FAKE_MODEL)
        msgs = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "search_skills",
                                                                           "arguments": {"query": "alpha"}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "read_skill",
                                                                           "arguments": {"name": "alpha", "limit": 3}}},
            {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "ask_cartographer",
                                                                           "arguments": {"brief": "alpha report"}}},
            {"jsonrpc": "2.0", "id": 6, "method": "nope"},
        ]
        inp = "".join(json.dumps(m) + "\n" for m in msgs).encode("utf-8")
        cmd = [sys.executable, "-m", "the_cartographer", "mcp", "--no-user-skills", "--no-bundled", "--skills-dir", tmp,
               "--backend", "command", "--command", '"%s" "%s"' % (sys.executable, fake)]
        r = subprocess.run(cmd, input=inp, capture_output=True, cwd=ROOT, timeout=60)
        out = {m["id"]: m for m in (json.loads(l) for l in r.stdout.decode("utf-8").splitlines() if l.strip())}
        self.assertEqual(out[1]["result"]["serverInfo"]["name"], "the-cartographer")
        self.assertEqual({t["name"] for t in out[2]["result"]["tools"]},
                         {"ask_cartographer", "read_skill", "search_skills", "find_skills"})
        self.assertIn("alpha", out[3]["result"]["content"][0]["text"])
        self.assertIn("lines 1-3", out[4]["result"]["content"][0]["text"])
        self.assertFalse(out[5]["result"]["isError"], out[5])
        self.assertEqual(out[5]["result"]["structuredContent"]["picks"][0]["name"], "alpha")
        self.assertEqual(out[6]["error"]["code"], -32601)


class BundleTests(unittest.TestCase):
    def test_bundled_skills_verify_and_load(self):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "vendor.py"), "verify"], capture_output=True,
                           text=True)
        self.assertEqual(r.returncode, 0, r.stdout[-2000:])
        skills = catalogue.load_bundled(ROOT)
        with open(os.path.join(ROOT, "catalogue", "bundled.json"), encoding="utf-8") as f:
            meta = json.load(f)["skills"]
        self.assertEqual(len(skills), len(meta))
        for e in meta:
            folder = os.path.join(ROOT, "skills", *e["id"].split("/"))
            self.assertTrue(any(n.upper().startswith(("LICENSE", "LICENCE", "COPYING")) for n in os.listdir(folder)),
                            e["id"])


ARGDUMP = textwrap.dedent("""\
    import json, sys
    sys.stdin.read()
    with open(sys.argv[1], "w", encoding="utf-8") as f:
        json.dump(sys.argv[2:], f)
    print("ok")
    """)


class RunTests(unittest.TestCase):
    """backends._run: how a backend program is started, fed and stopped."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def script(self, name, text):
        p = os.path.join(self.tmp, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return p

    @unittest.skipUnless(os.name == "nt", "a .cmd shim is a Windows thing")
    def test_cmd_shim_in_a_folder_with_a_space_gets_exact_arguments(self):
        # claude.cmd from npm is how most Windows users run Claude Code; --tools "" must arrive as an empty argument
        dump = self.script("argdump.py", ARGDUMP)
        shim_dir = os.path.join(self.tmp, "shim dir")
        os.makedirs(shim_dir)
        shim = os.path.join(shim_dir, "fake.cmd")
        with open(shim, "w", encoding="utf-8") as f:
            f.write('@echo off\r\n"%s" "%s" %%*\r\n' % (sys.executable, dump))
        out_file = os.path.join(self.tmp, "args.json")
        want = ["--tools", "", "-c", 'policy="never"', "a b", "p&q"]
        code, out, err = backends._run([shim, out_file] + want, "prompt", 60)
        self.assertEqual(code, 0, err)
        with open(out_file, encoding="utf-8") as f:
            self.assertEqual(json.load(f), want)

    def test_timeout_stops_the_program_and_what_it_started(self):
        # a shim's real program keeps the output pipes open; killing only the shim left the read hanging (Windows)
        # or the program running after the cartographer gave up (POSIX)
        pid_file = os.path.join(self.tmp, "grandchild.pid")
        child = self.script("child.py", textwrap.dedent("""\
            import subprocess, sys, time
            g = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(20)"])
            with open(sys.argv[1], "w") as f:
                f.write(str(g.pid))
            time.sleep(20)
            """))
        t0 = time.time()
        with self.assertRaises(backends.BackendError) as cm:
            backends._run([sys.executable, child, pid_file], "", 3)
        self.assertIn("no answer in 3s", str(cm.exception))
        self.assertLess(time.time() - t0, 12)
        if os.name != "nt":
            with open(pid_file) as f:
                pid = int(f.read())
            deadline = time.time() + 5
            while time.time() < deadline:
                try:
                    os.kill(pid, 0)
                except OSError:
                    break
                time.sleep(0.1)
            else:
                os.kill(pid, 9)
                self.fail("the program the backend started was still running after the timeout")

    def test_python_backend_reads_and_prints_utf8(self):
        # a Python wrapper printing a non-ASCII answer used to crash on a Windows code page console
        p = self.script("u.py", "import os, sys\ns = sys.stdin.read()\n"
                                "print(os.environ.get('PYTHONIOENCODING'), s, '\\u2713')\n")
        code, out, err = backends._run([sys.executable, p], "caf\u00e9", 60)
        self.assertEqual(code, 0, err)
        self.assertEqual(out.split(), ["utf-8", "caf\u00e9", "\u2713"])


class ChoiceTests(unittest.TestCase):
    """Which backend and effort a call ends up with."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        make_skill(self.tmp, "alpha", "Write alpha reports.")
        self.used = {}

        class Fake:
            def ask(fake, catalogue_text, brief, requester="unknown"):
                return "PICKS: none\n" + END_MARKER, {"backend": self.used["name"]}

        def make(name, model=None, effort="medium", timeout=None, command=None):
            self.used.update(name=name, effort=effort)
            return Fake()

        self.patch = mock.patch.object(backends, "make", make)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def run_cli(self, argv, env):
        base = ["--no-user-skills", "--no-bundled", "--skills-dir", self.tmp]
        clean = {k: v for k, v in os.environ.items() if not k.startswith("CARTOGRAPHER_")}
        clean.update(env)
        with mock.patch.dict(os.environ, clean, clear=True), mock.patch("sys.stdout", io.StringIO()):
            return cli.main(["ask"] + base + argv + ["the task"])

    def test_effort_flag_beats_environment(self):
        self.run_cli(["--backend", "claude", "--effort", "high"], {"CARTOGRAPHER_EFFORT": "low"})
        self.assertEqual(self.used["effort"], "high")
        self.run_cli(["--backend", "claude"], {"CARTOGRAPHER_EFFORT": "low"})
        self.assertEqual(self.used["effort"], "low")
        self.run_cli(["--backend", "claude"], {})
        self.assertEqual(self.used["effort"], "medium")

    def test_command_flag_means_command_backend(self):
        self.assertEqual(self.run_cli(["--command", "my-model"], {"CARTOGRAPHER_BACKEND": "claude"}), 0)
        self.assertEqual(self.used["name"], "command")
        self.run_cli(["--command", "my-model", "--backend", "claude"], {})
        self.assertEqual(self.used["name"], "claude")  # an explicit --backend still wins


class MoreAnswerTests(unittest.TestCase):
    def test_picks_are_capped_at_six(self):
        tmp = tempfile.mkdtemp()
        names = ["s%d" % i for i in range(8)]
        for n in names:
            make_skill(tmp, n, "Skill %s." % n)
        skills = catalogue.build(extra_dirs=[tmp], user_skills=False, bundled=False)
        raw = "PICKS:\n" + "".join("- %s | x | fits | read: whole\n" % n for n in names) + END_MARKER
        a = answer.check(answer.parse(raw), skills)
        self.assertEqual([e["name"] for e in a["picks"]], names[:6])
        self.assertTrue(any("s6" in n and "s7" in n for n in a["notes"]), a["notes"])

    def test_markdown_dressed_headers_still_parse(self):
        raw = ("**PICKS:**\n- **alpha** | a/SKILL.md | fits | read: whole\n"
               "## MAYBE:\n- beta | b/SKILL.md | might fit | read: whole\n"
               "**ALSO GREP:** gamma delta\n__NOTE:__ one line\n" + END_MARKER)
        p = answer.parse(raw)
        self.assertEqual([e["name"] for e in p["picks"]], ["alpha"])
        self.assertEqual([e["name"] for e in p["maybe"]], ["beta"])
        self.assertEqual(p["also_grep"], "gamma delta")
        self.assertEqual(p["notes"], ["one line"])


class MoreCatalogueTests(unittest.TestCase):
    def test_search_matches_word_starts_only(self):
        tmp = tempfile.mkdtemp()
        make_skill(tmp, "scene", "Scene setup: transforms, cameras and the render loop.")
        make_skill(tmp, "filler", "Fill PDF forms and form-filling flows.")
        skills = catalogue.build(extra_dirs=[tmp], user_skills=False, bundled=False)
        self.assertEqual([s.name for s in catalogue.search(skills, ["forms"])], ["filler"])
        self.assertEqual([s.name for s in catalogue.search(skills, ["form"])], ["filler"])
        self.assertEqual([s.name for s in catalogue.search(skills, ["transform"])], ["scene"])

    def test_regular_install_finds_the_packaged_bundle(self):
        empty, packaged = tempfile.mkdtemp(), tempfile.mkdtemp()
        os.makedirs(os.path.join(packaged, "catalogue"))
        with open(os.path.join(packaged, "catalogue", "bundled.json"), "w", encoding="utf-8") as f:
            f.write('{"skills": []}')
        env = {k: v for k, v in os.environ.items() if k != "CARTOGRAPHER_HOME"}
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(catalogue, "REPO_ROOT", empty), \
                mock.patch.object(catalogue, "PACKAGE_BUNDLE", packaged, create=True):
            self.assertEqual(catalogue.bundled_home(), packaged)

    def test_front_matter_variants(self):
        cases = {
            "---\r\nname: a\r\ndescription: crlf words\r\n---\r\nbody": "crlf words",
            "\ufeff---\nname: a\ndescription: bom words\n---\n": "bom words",
            "---\nname: a\ndescription: starts\n\tand a tab\n---\n": "starts and a tab",
            '---\nname: a\ndescription: "Use when: x"\n---\n': "Use when: x",
            "---\nname: a\n# comment\ndescription: >-\n  one\n  two\nlicense: MIT\n---\n": "one two",
        }
        for text, want in cases.items():
            self.assertEqual(frontmatter.parse(text)["description"], want, repr(text))


class McpRobustnessTests(unittest.TestCase):
    def test_bad_messages_get_errors_and_the_server_keeps_going(self):
        tmp = tempfile.mkdtemp()
        make_skill(tmp, "alpha", "Write alpha reports.", body="line1\nline2\n")
        lines = [
            "{not json",
            "[1, 2]",
            "5",
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": [1]}),
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                        "params": {"name": "read_skill", "arguments": [1]}}),
            json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                        "params": {"name": "read_skill", "arguments": {"name": "alpha", "offset": "abc"}}}),
            json.dumps({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                        "params": {"name": "read_skill", "arguments": {"name": 7}}}),
            json.dumps({"jsonrpc": "2.0", "id": 5, "method": "ping"}),
        ]
        cmd = [sys.executable, "-m", "the_cartographer", "mcp", "--no-user-skills", "--no-bundled", "--skills-dir", tmp]
        r = subprocess.run(cmd, input=("\n".join(lines) + "\n").encode("utf-8"), capture_output=True, cwd=ROOT,
                           timeout=60)
        msgs = [json.loads(l) for l in r.stdout.decode("utf-8").splitlines() if l.strip()]
        by_id = {m["id"]: m for m in msgs if m["id"] is not None}
        anon = sorted(m["error"]["code"] for m in msgs if m["id"] is None)
        self.assertEqual(anon, [-32700, -32600, -32600], r.stderr[-1000:])
        self.assertEqual(by_id[1]["error"]["code"], -32602)
        self.assertEqual(by_id[2]["error"]["code"], -32602)
        self.assertTrue(by_id[3]["result"]["isError"])
        self.assertTrue(by_id[4]["result"]["isError"])
        self.assertEqual(by_id[5]["result"], {})
        self.assertEqual(r.returncode, 0)

    def test_skills_list_is_read_once(self):
        # another thread can reset the cached list between the check and the return; simulate that interleaving
        class Flaky:
            reads = 0

            def __get__(self, obj, owner=None):
                Flaky.reads += 1
                return ["cached"] if Flaky.reads == 1 else None

            def __set__(self, obj, value):
                pass

        class Srv(mcp_server.Server):
            _skills = Flaky()

        srv = Srv(types.SimpleNamespace(), out=io.BytesIO())
        self.assertEqual(srv.skills(), ["cached"])


if __name__ == "__main__":
    unittest.main()
