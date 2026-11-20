#!/usr/bin/env python3
"""Mide cuanto del codigo propio compila en PC (clang, x86 de 32 bits) y aplica
arreglos mecanicos en COPIAS bajo pc/gen/. No modifica src/ ni include/."""
import collections
import concurrent.futures as cf
import os
import pathlib
import re
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
GEN = ROOT / "pc" / "gen"
OUT = pathlib.Path(os.environ.get("OUT", str(pathlib.Path.home() / "p4work")))
THIRD = re.compile(r"^src/(renderware|rw|cri|sce|middleware)/")
LOC = re.compile(r"^(.*?):(\d+):(\d+): (?:fatal )?error: (.*)$")

PRELUDE = """#ifndef PC_PRELUDE_H
#define PC_PRELUDE_H
/* Tipos de 128 bits para PC (clang x86 de 32 bits no tiene __int128). */
typedef struct { unsigned long long lo, hi; } __attribute__((aligned(16))) pc_u128;
typedef struct { unsigned long long lo, hi; } __attribute__((aligned(16))) pc_s128;
#include "gen/include/effect_vu0_internal.h"
#include "gen/include/particle_spawn_internal.h"
#endif
"""

EFFECT_STUB = """#ifndef EFFECT_VU0_INTERNAL_H
#define EFFECT_VU0_INTERNAL_H
#include "type.h"
/* Sustituto de PC (generado por pc/tools/check.py): efectos del VU0 desactivados hasta el hito M6. */
typedef struct EffectVuVector {
    f32 lane[4];
} __attribute__((aligned(16))) EffectVuVector;
static inline void effectVuUnpackColor10(const u32 *word, f32 scale) { (void)word; (void)scale; }
static inline void effectVuUnpackColor10V0(const u32 *word, f32 scale) { (void)word; (void)scale; }
static inline void effectVuLoad10(const EffectVuVector *value) { (void)value; }
static inline void effectVuLoad11(const EffectVuVector *value) { (void)value; }
static inline void effectVuStore10(EffectVuVector *value) { (void)value; }
static inline void effectVuStore11(EffectVuVector *value) { (void)value; }
static inline void effectVuScale10(f32 scale) { (void)scale; }
static inline void effectVuScale11(f32 scale) { (void)scale; }
static inline f32 effectVuGetX10(void) { return 0.0f; }
static inline f32 effectVuGetZ10(void) { return 0.0f; }
static inline void effectVuSetX10(f32 value) { (void)value; }
static inline void effectVuSetZ10(f32 value) { (void)value; }
#endif
"""

PARTICLE_TAIL = """/* Sustitutos de PC (generado por pc/tools/check.py): operaciones del VU0 desactivadas hasta el hito M6. */
static inline void spawnVuTransform10(void) {}
static inline void spawnVuNormalize10(void) {}
static inline void spawnVuMultiply10(void) {}
static inline void spawnVuAdd10(void) {}
#endif
"""


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def gen_headers():
    inc = ROOT / "include"
    out = GEN / "include"
    write(ROOT / "pc" / "prelude.h", PRELUDE)
    write(out / "effect_vu0_internal.h", EFFECT_STUB)
    t = (inc / "particle_spawn_internal.h").read_text(errors="replace")
    k = t.find("/* VF28..30")
    if k < 0:
        sys.exit("No encontre el marcador '/* VF28..30' en particle_spawn_internal.h")
    write(out / "particle_spawn_internal.h", t[:k] + PARTICLE_TAIL)
    for h in sorted(inc.rglob("*.h")):
        rel = h.relative_to(inc)
        if str(rel) in ("effect_vu0_internal.h", "particle_spawn_internal.h"):
            continue
        t = h.read_text(errors="replace")
        if "__int128" in t:
            t = re.sub(r"unsigned\s+__int128", "pc_u128", t).replace("__int128", "pc_s128")
            write(out / rel, t)


def load_flags():
    raw = (ROOT / "compile_flags.txt").read_text().replace("\r", "").split("\n")
    return [l for l in raw if l.strip() and not l.startswith("--target")]


FLAGS = load_flags()
BASE = ["clang", "-fsyntax-only", "-m32", "-malign-double", "-fms-extensions", "-w",
        "-Ipc/gen/include", "-include", "pc/prelude.h"]


def run_clang(path, orig_dir):
    cmd = BASE + ["-I" + orig_dir] + FLAGS + [path]
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    return [l for l in (p.stdout + p.stderr).splitlines() if " error: " in l]


def norm(path):
    return path[len("pc/gen/"):] if path.startswith("pc/gen/") else path


def comment_decl(lines, idx):
    """Comenta con // una declaracion extern que empieza en lines[idx]."""
    if not lines[idx].lstrip().startswith("extern"):
        return False
    end = idx
    while end < len(lines) - 1 and ";" not in lines[end] and end - idx < 4:
        end += 1
    if ";" not in lines[end]:
        return False
    for k in range(idx, end + 1):
        if not lines[k].lstrip().startswith("//"):
            lines[k] = "//PCFIX " + lines[k]
    return True


def unprototype(lines, idx):
    """Convierte 'extern T f(args);' en 'extern T f();' (compatible con cualquier prototipo)."""
    s = lines[idx]
    if not s.lstrip().startswith("extern"):
        return False
    p = s.find("(")
    if p < 0 or not re.search(r"[A-Za-z0-9_]\s*$", s[:p]):
        return False
    depth, q = 0, -1
    for i in range(p, len(s)):
        if s[i] == "(":
            depth += 1
        elif s[i] == ")":
            depth -= 1
            if depth == 0:
                q = i
                break
    if q < 0 or not s[q + 1:].lstrip().startswith(";"):
        return False
    lines[idx] = s[:p].rstrip() + "()" + s[q + 1:]
    return True


def process(rel):
    orig = ROOT / rel
    text = orig.read_text(errors="replace")
    modified = False
    if "__int128" in text:
        text = re.sub(r"unsigned\s+__int128", "pc_u128", text).replace("__int128", "pc_s128")
        modified = True
    lines = text.split("\n")
    gen_path = GEN / rel
    orig_dir = str(orig.parent.relative_to(ROOT))
    fixes = 0
    errs = []
    state = {}

    def compile_now():
        work = rel
        if modified:
            gen_path.parent.mkdir(parents=True, exist_ok=True)
            gen_path.write_text("\n".join(lines))
            work = "pc/gen/" + rel
        return run_clang(work, orig_dir)

    for _ in range(6):
        errs = compile_now()
        todo = set()
        for e in errs:
            m = LOC.match(e)
            if not m:
                continue
            if norm(m.group(1)) == rel and re.match(r"(conflicting types for|redeclaration of)", m.group(4)):
                todo.add(int(m.group(2)) - 1)
        n = 0
        for idx in sorted(todo):
            if idx >= len(lines):
                continue
            if state.get(idx) != 1 and unprototype(lines, idx):
                state[idx] = 1
                n += 1
            elif comment_decl(lines, idx):
                state[idx] = 2
                n += 1
        if n == 0:
            break
        fixes += n
        modified = True
    else:
        errs = compile_now()
    return rel, errs, fixes, modified


def main():
    shutil.rmtree(GEN, ignore_errors=True)
    OUT.mkdir(parents=True, exist_ok=True)
    gen_headers()
    allc = sorted(str(p.relative_to(ROOT)) for p in (ROOT / "src").rglob("*.c")
                  if not THIRD.match(str(p.relative_to(ROOT))))
    exc_file = ROOT / "pc" / "excluded.txt"
    if not exc_file.exists():
        ex = [f for f in allc if "__asm__" in (ROOT / f).read_text(errors="replace")]
        ex += ["src/promoted/code1_0042.c", "src/promoted/code1_0041.c",
               "src/Kernel/Kwln/kwln_inferred_00100218.c"]
        exc_file.write_text("\n".join(sorted(set(ex))) + "\n")
    excluded = set(l.strip() for l in exc_file.read_text().splitlines() if l.strip())
    files = [f for f in allc if f not in excluded]
    with cf.ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
        results = list(pool.map(process, files))

    ok = sum(1 for r in results if not r[1])
    fixes = sum(r[2] for r in results)
    copies = sum(1 for r in results if r[3])
    cat, origin, perfile = collections.Counter(), collections.Counter(), collections.Counter()
    full = []
    for rel, errs, _, _ in results:
        for e in errs:
            full.append(e)
            m = LOC.match(e)
            if not m:
                cat["(sin ubicacion) " + e[:70]] += 1
                continue
            cat[re.sub(r"'[^']*'", "'X'", m.group(4))] += 1
            origin["%s:%s" % (norm(m.group(1)), m.group(2))] += 1
            perfile[rel] += 1
    (OUT / "report_full.txt").write_text("\n".join(full) + "\n")

    s = []
    s.append("Archivos comprobados: %d (excluidos: %d)" % (len(files), len(allc) - len(files)))
    s.append("Sin errores: %d   Con errores: %d" % (ok, len(files) - ok))
    s.append("Declaraciones extern comentadas en copias: %d (copias generadas: %d)" % (fixes, copies))
    s.append("Errores en total: %d" % len(full))
    s.append("--- errores por tipo (top 10)")
    s += ["%5d %s" % (n, k[:110]) for k, n in cat.most_common(10)]
    names, types, samples = collections.Counter(), collections.Counter(), collections.defaultdict(list)
    for e in full:
        m = LOC.match(e)
        if not m:
            continue
        msg = m.group(4)
        mm = re.match(r"use of undeclared identifier '([^']*)'", msg)
        if mm:
            names[mm.group(1)] += 1
        mm = re.match(r"unknown type name '([^']*)'", msg)
        if mm:
            types[mm.group(1)] += 1
        for key in ("incompatible pointer to integer", "typedef redefinition"):
            if msg.startswith(key) and len(samples[key]) < 3:
                samples[key].append("%s:%s %s" % (norm(m.group(1)), m.group(2), msg[:90]))
    s.append("--- identificadores sin declarar (top 8)")
    s += ["%5d %s" % (n, k) for k, n in names.most_common(8)]
    s.append("--- tipos desconocidos (top 8)")
    s += ["%5d %s" % (n, k) for k, n in types.most_common(8)]
    s.append("--- ejemplos")
    for v in samples.values():
        s += v
    s.append("--- origen de los errores (top 12)")
    s += ["%5d %s" % (n, k) for k, n in origin.most_common(12)]
    s.append("--- archivos con mas errores (top 12)")
    s += ["%5d %s" % (n, k) for k, n in perfile.most_common(12)]
    text = "\n".join(s)
    (OUT / "summary.txt").write_text(text + "\n")
    print(text)
    print("\nDetalle completo en", OUT / "report_full.txt")


if __name__ == "__main__":
    main()
