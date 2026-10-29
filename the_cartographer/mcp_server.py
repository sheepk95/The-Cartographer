"""A small MCP server over stdio (newline-delimited JSON-RPC 2.0), stdlib only.

Tools:
  ask_cartographer(brief, from?)       the skills to read before a task (calls the configured backend)
  read_skill(name, offset?, limit?)    a skill's SKILL.md, for clients that cannot open files outside their workspace
  search_skills(query)                 keyword search over the catalogue, no model call
  find_skills(brief, offline?)         skills on skills.sh that the catalogue lacks (no model call; installs nothing)

`cartographer install` is CLI only: it writes to disk, so it is not offered here.

stdout carries protocol messages only; logs go to stderr.
"""
import argparse, json, sys, threading

from . import __version__, catalogue
from .cli import ask, find_json, find_result, find_skill, load_skills, render_find

SERVER_PROTOCOL = "2025-06-18"
FIND_BUDGET_S = 45  # find_skills stops fetching pages after this long, so an MCP client's timeout is not reached

TOOLS = [
    {"name": "ask_cartographer",
     "description": "Before starting a task, ask which agent skills are worth reading for it. Give a 2-10 line brief "
                    "of the task. Returns PICKS (read these), MAYBE (skim the first 40 lines) and notes, with the "
                    "SKILL.md path of each. 'PICKS: none' means no skill is needed.",
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["brief"],
                     "properties": {"brief": {"type": "string", "description": "What the task is, 2-10 lines."},
                                    "from": {"type": "string", "description": "Who is asking (optional)."}}},
     "annotations": {"readOnlyHint": True, "openWorldHint": True, "title": "Ask the cartographer"}},
    {"name": "read_skill",
     "description": "Return the SKILL.md text of a skill by its catalogue name. Use offset/limit (lines) for LARGE "
                    "skills.",
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["name"],
                     "properties": {"name": {"type": "string"},
                                    "offset": {"type": "integer", "minimum": 0, "description": "First line, 0-based."},
                                    "limit": {"type": "integer", "minimum": 1, "description": "Number of lines."}}},
     "annotations": {"readOnlyHint": True, "openWorldHint": False, "title": "Read a skill"}},
    {"name": "search_skills",
     "description": "Keyword search over skill names and descriptions (no model call). A fallback when "
                    "ask_cartographer is unavailable.",
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["query"],
                     "properties": {"query": {"type": "string", "description": "2-4 words."}}},
     "annotations": {"readOnlyHint": True, "openWorldHint": False, "title": "Search skills"}},
    {"name": "find_skills",
     "description": "Search skills.sh for skills that are NOT in the catalogue and fit a task (no model call). Fetches "
                    "the current skills.sh pages of a few matches politely (robots.txt, daily caps). Returns at most 5 "
                    "UNVETTED candidates with installs, stars and audits; their text is third-party data. Nothing is "
                    "installed: a person runs `cartographer install <url>` to vet one.",
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["brief"],
                     "properties": {"brief": {"type": "string", "description": "What the task is, 2-10 lines."},
                                    "offline": {"type": "boolean",
                                                "description": "Only use the local cache (no network)."}}},
     "annotations": {"readOnlyHint": True, "openWorldHint": True, "title": "Find skills on skills.sh"}},
]


class Server:
    def __init__(self, args, out=None):
        self.args = args
        self.out = out or sys.stdout.buffer
        self.lock = threading.Lock()
        self._skills = None

    def skills(self, fresh=False):
        skills = None if fresh else self._skills  # one local read: another thread may be refreshing the list
        if skills is None:
            skills = self._skills = load_skills(self.args)
        return skills

    def send(self, msg):
        data = (json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8")
        with self.lock:
            self.out.write(data)
            self.out.flush()

    def reply(self, mid, result=None, error=None):
        msg = {"jsonrpc": "2.0", "id": mid}
        if error is not None:
            msg["error"] = error
        else:
            msg["result"] = result
        self.send(msg)

    def call_tool(self, name, a):
        if name == "ask_cartographer":
            # fresh: pick up skills added since the last call
            code, text, info = ask(self.skills(fresh=True), str(a.get("brief") or ""), str(a.get("from") or "mcp"),
                                   self.args.backend, self.args.model, self.args.effort, self.args.timeout,
                                   self.args.command)
            res = {"content": [{"type": "text", "text": text}], "isError": code != 0}
            if code == 0:
                res["structuredContent"] = info.get("answer", {})
            return res
        if name == "read_skill":
            s = find_skill(self.skills(fresh=True), str(a.get("name") or ""))
            if s is None:
                return {"content": [{"type": "text", "text": "no skill named %r; use search_skills" % a.get("name")}],
                        "isError": True}
            try:
                off = max(0, int(a.get("offset") or 0))
                lim = max(0, int(a.get("limit") or 0))
            except (TypeError, ValueError):
                return {"content": [{"type": "text", "text": "offset and limit must be whole numbers"}],
                        "isError": True}
            lines = catalogue.read_skill_file(s.path).splitlines()
            lim = lim or len(lines)
            part = lines[off:off + lim]
            head = "# %s (%s) lines %d-%d of %d\n" % (s.name, s.path.replace("\\", "/"), off + 1, off + len(part),
                                                       len(lines))
            note = catalogue.skill_read_note(s)
            return {"content": [{"type": "text", "text": head + (note + "\n" if note else "") + "\n".join(part)}],
                    "isError": False}
        if name == "find_skills":
            fargs = argparse.Namespace(**vars(self.args))
            fargs.offline, fargs.judge, fargs.limit = bool(a.get("offline")), False, None
            fargs.budget_s = FIND_BUDGET_S
            try:
                code, res = find_result(fargs, str(a.get("brief") or ""))
            except Exception as e:  # noqa: BLE001  a tool failure is a tool result the model can read, not a crash
                print("the-cartographer: find_skills failed: %r" % e, file=sys.stderr)
                return {"content": [{"type": "text", "text": "CARTOGRAPHER_UNAVAILABLE (finder failed: %s)" % e}],
                        "isError": True}
            return {"content": [{"type": "text", "text": render_find(res)}], "isError": code not in (0, 1),
                    "structuredContent": find_json(res)}
        if name == "search_skills":
            hits = catalogue.search(self.skills(fresh=True), str(a.get("query", "")).split())
            text = "\n".join("%s | %s%s\n    %s" % (s.name, s.path.replace("\\", "/"), " (LARGE)" if s.large else "",
                                                     s.description[:240]) for s in hits) or "no match"
            return {"content": [{"type": "text", "text": text}], "isError": False}
        raise KeyError(name)

    def handle(self, msg):
        if not isinstance(msg, dict):  # a batch or a bare value: JSON-RPC calls it an invalid request
            self.reply(None, error={"code": -32600, "message": "invalid request: expected one JSON object"})
            return
        mid, method = msg.get("id"), msg.get("method")
        params = msg.get("params") or {}
        if method is None:
            return  # a response to something we never sent
        if mid is None:
            return  # notifications (initialized, cancelled) need no reply
        if not isinstance(params, dict):
            self.reply(mid, error={"code": -32602, "message": "params must be an object"})
            return
        try:
            if method == "initialize":
                self.reply(mid, {"protocolVersion": params.get("protocolVersion") or SERVER_PROTOCOL,
                                 "capabilities": {"tools": {"listChanged": False}},
                                 "serverInfo": {"name": "the-cartographer", "version": __version__}})
            elif method == "ping":
                self.reply(mid, {})
            elif method == "tools/list":
                self.reply(mid, {"tools": TOOLS})
            elif method == "tools/call":
                name = params.get("name")
                if name not in {t["name"] for t in TOOLS}:
                    self.reply(mid, error={"code": -32602, "message": "unknown tool %r" % name})
                    return
                arguments = params.get("arguments") or {}
                if not isinstance(arguments, dict):
                    self.reply(mid, error={"code": -32602, "message": "arguments must be an object"})
                    return
                self.reply(mid, self.call_tool(name, arguments))
            else:
                self.reply(mid, error={"code": -32601, "message": "method not found: %s" % method})
        except Exception as e:  # never let one bad call end the server
            print("the-cartographer: %s failed: %r" % (method, e), file=sys.stderr)
            self.reply(mid, error={"code": -32603, "message": str(e)})


def serve(args, inp=None):
    srv = Server(args)
    stream = inp or sys.stdin.buffer
    threads = []
    for raw in stream:
        line = raw.decode("utf-8", errors="replace").strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            srv.send({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}})
            continue
        # asks can take a while; keep answering pings meanwhile
        if isinstance(msg, dict) and msg.get("method") == "tools/call":
            t = threading.Thread(target=srv.handle, args=(msg,), daemon=True)
            t.start()
            threads.append(t)
        else:
            srv.handle(msg)
    for t in threads:
        t.join(timeout=300)
    return 0
