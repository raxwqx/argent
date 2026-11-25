"""Build the interactive pipeline page in ``docs/``.

    python tools/make_site.py

Code shown in the page is pulled from the package with ``inspect``: the site
cannot drift from the engine without this script being re-run.
"""

import inspect
import json
from pathlib import Path
from textwrap import dedent

from argent import asm, engine, machine, solver

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "index.html"


def excerpt(*objects):
    """Source of the given functions, dedented and trimmed."""
    blocks = []
    for obj in objects:
        source = dedent(inspect.getsource(obj)).strip("\n")
        blocks.append(source)
    return "\n\n\n".join(blocks)


STAGES = [
    {
        "name": "ASSEMBLER",
        "module": "argent/asm.py",
        "title": "Labels become instruction indices",
        "blurb": (
            "Labels are collected before any operand is parsed, so a forward "
            "jump costs nothing. Every operand is then written into its own "
            "byte field; there is no ambiguity to resolve later."
        ),
        "code": excerpt(asm.assemble),
    },
    {
        "name": "INTERPRETER",
        "module": "argent/machine.py",
        "title": "One step function, two modes",
        "blurb": (
            "Concrete words are BitVecVal, symbolic words are BitVec. The same "
            "execute_step therefore runs a normal program and a symbolic path; "
            "branches are returned undecided so the explorer can own the fork."
        ),
        "code": excerpt(machine.execute_step),
    },
    {
        "name": "EXPLORER",
        "module": "argent/engine.py",
        "title": "Depth-first, pruned before queueing",
        "blurb": (
            "At a symbolic branch the guard is simplified: known true or false "
            "continues in place, anything else forks. Each child is checked "
            "with z3 before it enters the stack, and every candidate is "
            "replayed concretely before it is reported."
        ),
        "code": excerpt(engine.Explorer.run),
    },
    {
        "name": "SOLVER",
        "module": "argent/solver.py",
        "title": "A thin bridge to z3",
        "blurb": (
            "No incremental solver, no cached context: a fresh Solver per "
            "check, a timeout in milliseconds, and model bytes read back in "
            "declaration order. Small enough to audit in a minute."
        ),
        "code": excerpt(solver.check, solver.model_bytes),
    },
    {
        "name": "REPLAY",
        "module": "argent/engine.py",
        "title": "The part that makes it honest",
        "blurb": (
            "A model is not an answer. The candidate is executed concretely, "
            "the trace must contain the goal index, and no avoided index may "
            "appear. If this fails, the result is unsolved."
        ),
        "code": excerpt(engine.verify),
    },
]


HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Argent — interactive pipeline</title>
<meta name="description" content="Click through the stages of a small symbolic execution engine.">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' fill='%230d1117'/%3E%3Cpath d='M16 6l10 10-10 10L6 16z' fill='%23c9d1d9'/%3E%3C/svg%3E">
<style>
  :root {
    --bg: #0d1117;
    --panel: #11161d;
    --panel-2: #161b22;
    --edge: #30363d;
    --edge-soft: #21262d;
    --fg: #c9d1d9;
    --bright: #e6edf3;
    --dim: #6e7681;
    --faint: #484f58;
    --mono: ui-monospace, SFMono-Regular, "Fira Code", "DejaVu Sans Mono", monospace;
    --sans: ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
  }

  * { box-sizing: border-box; }

  html, body { margin: 0; min-height: 100%; }

  body {
    background: var(--bg);
    color: var(--fg);
    font-family: var(--sans);
    line-height: 1.55;
    display: flex;
    flex-direction: column;
    min-height: 100vh;
  }

  body::before {
    content: "";
    position: fixed;
    inset: 0;
    pointer-events: none;
    background-image:
      linear-gradient(to right, #141a21 1px, transparent 1px),
      linear-gradient(to bottom, #141a21 1px, transparent 1px);
    background-size: 32px 32px;
    opacity: 0.55;
    z-index: 0;
  }

  header, main, footer { position: relative; z-index: 1; }

  header {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 24px;
    padding: 26px clamp(20px, 5vw, 56px) 18px;
    border-bottom: 1px solid var(--edge-soft);
    flex-wrap: wrap;
  }

  .brand { display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap; }

  .brand .mark { color: var(--dim); font-family: var(--mono); font-size: 12px; }

  .brand .name {
    font-family: var(--mono);
    font-size: 28px;
    font-weight: 700;
    letter-spacing: 8px;
    background: linear-gradient(180deg, #f7f9fb, #d3dae2 42%, #8b949e 52%, #c3ccd5 62%, #7d8792);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
  }

  .brand .tag {
    font-family: var(--mono);
    font-size: 12px;
    letter-spacing: 3px;
    color: var(--dim);
    text-transform: uppercase;
  }

  nav { font-family: var(--mono); font-size: 13px; color: var(--faint); }
  nav a { color: var(--dim); text-decoration: none; }
  nav a:hover, nav a:focus-visible { color: var(--bright); text-decoration: underline; }
  nav span { margin: 0 8px; }

  main {
    flex: 1;
    display: grid;
    grid-template-columns: minmax(240px, 340px) minmax(0, 1fr);
    gap: clamp(20px, 4vw, 48px);
    padding: clamp(24px, 4vw, 48px) clamp(20px, 5vw, 56px);
    align-items: start;
  }

  .rail {
    position: relative;
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding-left: 22px;
  }

  .rail::before {
    content: "";
    position: absolute;
    left: 9px;
    top: 14px;
    bottom: 14px;
    width: 1px;
    background: linear-gradient(#30363d, #8b949e 40%, #8b949e 60%, #30363d);
  }

  .stage {
    position: relative;
    appearance: none;
    width: 100%;
    text-align: left;
    font: inherit;
    color: inherit;
    background: var(--panel);
    border: 1px solid var(--edge);
    border-radius: 9px;
    padding: 12px 16px;
    cursor: pointer;
    transition: border-color 140ms ease, background 140ms ease, transform 140ms ease;
  }

  .stage::before {
    content: "";
    position: absolute;
    left: -18px;
    top: 50%;
    width: 7px;
    height: 7px;
    margin-top: -3.5px;
    transform: rotate(45deg);
    background: var(--faint);
    transition: background 140ms ease, box-shadow 140ms ease;
  }

  .stage:hover { border-color: var(--dim); background: var(--panel-2); }

  .stage:focus-visible { outline: 2px solid var(--dim); outline-offset: 2px; }

  .stage[aria-selected="true"] {
    border-color: var(--bright);
    background: var(--panel-2);
  }

  .stage[aria-selected="true"]::before {
    background: var(--bright);
    box-shadow: 0 0 10px rgba(230, 237, 243, 0.55);
  }

  .stage .row { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; }
  .stage .num { font-family: var(--mono); font-size: 11px; color: var(--faint); }
  .stage .label {
    font-family: var(--mono);
    font-size: 14px;
    font-weight: 700;
    letter-spacing: 2px;
    color: var(--fg);
  }
  .stage[aria-selected="true"] .label { color: var(--bright); }
  .stage .file { font-family: var(--mono); font-size: 11px; color: var(--dim); margin-top: 2px; }

  .panel {
    border: 1px solid var(--edge);
    border-radius: 10px;
    background: var(--panel);
    overflow: hidden;
    min-width: 0;
  }

  .panel-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    padding: 10px 16px;
    border-bottom: 1px solid var(--edge-soft);
    font-family: var(--mono);
    font-size: 12px;
    color: var(--dim);
    background: #0f141a;
  }

  .panel-head .path { color: var(--fg); }
  .panel-head .lines { color: var(--faint); }

  .panel-body { padding: 18px 16px 8px; }

  .panel h2 {
    margin: 0 0 6px;
    font-family: var(--mono);
    font-weight: 600;
    font-size: 15px;
    letter-spacing: 0.4px;
    color: var(--bright);
  }

  .panel p { margin: 0 0 16px; color: var(--dim); font-size: 14px; max-width: 70ch; }

  pre {
    margin: 0;
    padding: 14px 16px;
    max-height: min(58vh, 620px);
    overflow: auto;
    border-top: 1px solid var(--edge-soft);
    background: #0b0f14;
    font-family: var(--mono);
    font-size: 12.5px;
    line-height: 1.6;
    tab-size: 4;
  }

  code { font-family: inherit; white-space: pre; }

  .tok-key { color: #e6edf3; }
  .tok-str { color: #a8b3bf; }
  .tok-com { color: #6e7681; font-style: italic; }
  .tok-num { color: #d8dee4; }
  .tok-def { color: #f0f6fc; font-weight: 600; }

  footer {
    display: flex;
    gap: 12px;
    align-items: baseline;
    flex-wrap: wrap;
    padding: 16px clamp(20px, 5vw, 56px) 26px;
    border-top: 1px solid var(--edge-soft);
    font-family: var(--mono);
    font-size: 12px;
    color: var(--dim);
  }

  footer .rule { color: var(--bright); }

  @media (max-width: 760px) {
    main { grid-template-columns: 1fr; }
    .rail { flex-direction: row; overflow-x: auto; padding: 0 0 12px; gap: 8px; }
    .rail::before, .stage::before { display: none; }
    .stage { min-width: 168px; }
    .stage .file { display: none; }
    pre { font-size: 11.5px; max-height: 46vh; }
  }

  @media (prefers-reduced-motion: reduce) {
    * { transition: none !important; }
  }
</style>
</head>
<body>
<header>
  <div class="brand">
    <span class="mark">&#9670;</span>
    <span class="name">ARGENT</span>
    <span class="tag">interactive pipeline</span>
  </div>
  <nav>
    <a href="https://github.com/raxwqx/argent">repository</a><span>/</span><a href="https://github.com/raxwqx/argent/blob/master/docs/DESIGN.md">design notes</a>
  </nav>
</header>

<main>
  <section class="rail" id="rail" role="tablist" aria-label="Pipeline stages"></section>

  <section class="panel" role="tabpanel" aria-live="polite">
    <div class="panel-head">
      <span class="path" id="path"></span>
      <span class="lines" id="lines"></span>
    </div>
    <div class="panel-body">
      <h2 id="title"></h2>
      <p id="blurb"></p>
    </div>
    <pre><code id="code"></code></pre>
  </section>
</main>

<footer>
  <span>acceptance rule</span>
  <span class="rule">an input is reported only if concrete replay reaches the goal</span>
</footer>

<script id="stage-data" type="application/json">__DATA__</script>
<script>
  const stages = JSON.parse(document.getElementById("stage-data").textContent);
  const rail = document.getElementById("rail");
  const path = document.getElementById("path");
  const lines = document.getElementById("lines");
  const title = document.getElementById("title");
  const blurb = document.getElementById("blurb");
  const code = document.getElementById("code");

  const KEYWORDS = new Set([
    "def", "class", "return", "if", "elif", "else", "for", "while", "in",
    "not", "and", "or", "None", "True", "False", "raise", "import", "from",
    "yield", "continue", "break", "try", "except", "with", "as", "lambda",
    "is", "pass", "global", "nonlocal", "assert", "del"
  ]);

  const escape = (text) => text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");

  // Small, dependency-free highlighter. Comments and strings first, then
  // keywords and numbers, so a word inside a string is never recoloured.
  function highlight(source) {
    const pattern = /(#[^\\n]*)|(\\"\\"\\"[\\s\\S]*?\\"\\"\\"|'''[\\s\\S]*?'''|"[^"\\n]*"|'[^'\\n]*')|\\b([A-Za-z_]\\w*)\\b|\\b(\\d+)\\b/g;
    let out = "";
    let last = 0;
    let match;

    while ((match = pattern.exec(source)) !== null) {
      out += escape(source.slice(last, match.index));
      const [text, comment, string, word, number] = match;

      if (comment) {
        out += '<span class="tok-com">' + escape(text) + "</span>";
      } else if (string) {
        out += '<span class="tok-str">' + escape(text) + "</span>";
      } else if (word) {
        const before = source.slice(Math.max(0, match.index - 4), match.index);
        if (KEYWORDS.has(word)) {
          const cls = before === "def " || before === "class " ? "tok-def" : "tok-key";
          out += '<span class="' + cls + '">' + word + "</span>";
        } else {
          out += word;
        }
      } else if (number) {
        out += '<span class="tok-num">' + number + "</span>";
      }

      last = match.index + text.length;
    }

    return out + escape(source.slice(last));
  }

  const buttons = stages.map((stage, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "stage";
    button.setAttribute("role", "tab");
    button.setAttribute("aria-selected", "false");
    button.setAttribute("aria-controls", "code");
    button.innerHTML =
      '<div class="row"><span class="num">' + String(index + 1).padStart(2, "0") +
      '</span><span class="label">' + stage.name + "</span></div>" +
      '<div class="file">' + stage.module + "</div>";
    button.addEventListener("click", () => select(index));
    button.addEventListener("keydown", (event) => {
      if (event.key === "ArrowDown" || event.key === "ArrowRight") {
        event.preventDefault();
        const next = (index + 1) % stages.length;
        select(next);
        buttons[next].focus();
      } else if (event.key === "ArrowUp" || event.key === "ArrowLeft") {
        event.preventDefault();
        const next = (index - 1 + stages.length) % stages.length;
        select(next);
        buttons[next].focus();
      }
    });
    rail.appendChild(button);
    return button;
  });

  function select(index) {
    const stage = stages[index];
    buttons.forEach((button, i) => {
      button.setAttribute("aria-selected", i === index ? "true" : "false");
    });
    path.textContent = stage.module;
    lines.textContent = stage.code.split("\\n").length + " lines";
    title.textContent = stage.title;
    blurb.textContent = stage.blurb;
    code.innerHTML = highlight(stage.code);
    history.replaceState(null, "", "#" + stage.name.toLowerCase());
  }

  const wanted = stages.findIndex(
    (stage) => stage.name.toLowerCase() === location.hash.slice(1).toLowerCase()
  );
  select(wanted === -1 ? 0 : wanted);

  window.addEventListener("hashchange", () => {
    const index = stages.findIndex(
      (stage) => stage.name.toLowerCase() === location.hash.slice(1).toLowerCase()
    );
    if (index !== -1) select(index);
  });
</script>
</body>
</html>
"""


def main():
    payload = [
        {
            "name": stage["name"],
            "module": stage["module"],
            "title": stage["title"],
            "blurb": stage["blurb"],
            "code": stage["code"],
        }
        for stage in STAGES
    ]

    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    page = HTML.replace("__DATA__", data)
    OUT.write_text(page, encoding="utf-8")

    (OUT.parent / ".nojekyll").write_text("", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(page) / 1024:.1f} KiB)")
    for stage in payload:
        print(f"  {stage['name']:<12} {stage['module']:<22} {len(stage['code'].splitlines()):>3} lines")


if __name__ == "__main__":
    main()
