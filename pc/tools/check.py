#!/usr/bin/env python3
"""Mide cuanto del codigo propio compila en PC (clang, x86 de 32 bits) y aplica
arreglos mecanicos en COPIAS bajo pc/gen/. No modifica src/ ni include/.
Uso: python3 pc/tools/check.py [--objects]"""
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
OBJECTS = "--objects" in sys.argv
THIRD = re.compile(r"^src/(renderware|rw|cri|sce|middleware)/")
LOC = re.compile(r"^(.*?):(\d+):(\d+): (?:fatal )?error: (.*)$")
NOTE = re.compile(r"^(.*?):(\d+):(\d+): note: previous (?:declaration|definition) is here")
CONFLICT = re.compile(r"(conflicting types for|redeclaration of)")
NAMEPAT = re.compile(r"\b(D_[0-9A-Fa-f]{6,8}|[a-z]?Gpffff[0-9a-fA-F]{4}|jtbl_[0-9A-Fa-f]{6,8})\b")
LIBC = re.compile(r"^(mem|str)[a-z]+$|^(sin|cos|tan|atan2?|sqrt|fabs|floor|ceil|pow|exp|log)f?$|^[sv]?n?printf$")
INDEX = {}

PRELUDE = """#ifndef PC_PRELUDE_H
#define PC_PRELUDE_H
/* Tipos de 128 bits para PC (clang x86 de 32 bits no tiene __int128). */
typedef struct { unsigned long long lo, hi; } __attribute__((aligned(16))) pc_u128;
typedef struct { unsigned long long lo, hi; } __attribute__((aligned(16))) pc_s128;
/* va_start al estilo GCC 2.x (ee-gcc). En x86 los argumentos variables van en la pila. DEUDA: verificar. */
#define __builtin_next_arg(last) ((char *)&(last) + ((sizeof(last) + 3) & ~3))
#define __builtin_args_info(n) 0
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

# Simbolos que el original declara fuera de C (tablas de RenderWare y una variable del gp).
# Tipos DEDUCIDOS del uso; se inyectan solo en archivos donde el identificador no esta declarado.
KNOWN = {
    "D_00887300": "extern int (*D_00887300[1])(int, void *);",
    "D_00887310": "extern int (*D_00887310[1])(int, void *, int);",
    "iGpffffa748": "extern int iGpffffa748;",
}

# Parches puntuales (DEUDA: cambian comportamiento, hay que verificarlos).
PATCHES = {
    "src/cmmMisc.c": [("cmmCommunityHasRecord() == 0",
                       "cmmCommunityHasRecord(0 /* PCFIX: argumento no recuperado */) == 0")],
}


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def has128(t):
    return re.search(r"__u?int128", t) is not None


def fix128(t):
    t = re.sub(r"unsigned\s+__int128(_t)?", "pc_u128", t)
    t = re.sub(r"signed\s+__int128(_t)?", "pc_s128", t)
    t = re.sub(r"__uint128_t", "pc_u128", t)
    t = re.sub(r"__int128(_t)?", "pc_s128", t)
    return t


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
        if has128(t):
            write(out / rel, fix128(t))


def load_flags():
    raw = (ROOT / "compile_flags.txt").read_text().replace("\r", "").split("\n")
    return [l for l in raw if l.strip() and not l.startswith("--target")]


FLAGS = load_flags()
BASE = ["-m32", "-malign-double", "-fms-extensions", "-w",
        "-Wno-error=int-conversion", "-Wno-error=incompatible-function-pointer-types",
        "-Wno-error=return-type", "-fno-pic", "-fno-pie",
        "-Ipc/gen/include", "-include", "pc/prelude.h"]


def run_clang(path, orig_dir, obj=None):
    mode = ["-fsyntax-only"] if obj is None else ["-c", "-o", obj]
    cmd = ["clang"] + mode + BASE + ["-I" + orig_dir] + FLAGS + [path]
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    return [l for l in (p.stdout + p.stderr).splitlines()
            if " error: " in l or ": note: previous " in l]


def norm(path):
    return path[len("pc/gen/"):] if path.startswith("pc/gen/") else path


def looks_like_proto(lines, idx):
    t = lines[idx].strip()
    if t.startswith("extern"):
        return True
    if t.startswith(("//", "/*", "#", "typedef", "return", "if", "for", "while", "else")):
        return False
    return bool(re.match(r"^[A-Za-z_][A-Za-z0-9_ \t\*]*\([^{}]*\)\s*;\s*(/\*.*\*/)?\s*$", t))


def comment_decl(lines, idx):
    if not looks_like_proto(lines, idx):
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


def build_index():
    idx = collections.defaultdict(collections.Counter)
    paths = list((ROOT / "src").rglob("*.c")) + list((ROOT / "include").rglob("*.h"))
    for f in paths:
        for ln in f.read_text(errors="replace").split("\n"):
            t = ln.strip()
            if not t.startswith("extern") or not t.endswith(";") or "=" in t:
                continue
            names = set(m.group(1) for m in NAMEPAT.finditer(t))
            if len(names) == 1:
                idx[next(iter(names))][t] += 1
    return idx


def pick_decl(name, lines):
    pat = re.compile(r"\b%s\b" % re.escape(name))
    for x in lines:
        t = x.strip()
        if t.startswith("extern") and t.endswith(";") and "=" not in t and pat.search(t):
            return t
    c = INDEX.get(name)
    if c:
        return c.most_common(1)[0][0]
    return KNOWN.get(name)


def process(rel):
    orig = ROOT / rel
    text = orig.read_text(errors="replace")
    modified = False
    if has128(text):
        text, modified = fix128(text), True
    if re.search(r"\(\s*\.\.\.\s*\)", text):
        text, modified = re.sub(r"\(\s*\.\.\.\s*\)", "()", text), True
    for old, new in PATCHES.get(rel, []):
        if old in text:
            text, modified = text.replace(old, new), True
    lines = text.split("\n")
    gen_path = GEN / rel
    orig_dir = str(orig.parent.relative_to(ROOT))
    obj = str(OUT / "obj" / (rel.replace("/", "__") + ".o")) if OBJECTS else None
    st = {"fixes": 0, "modified": modified, "scalar": False}
    state, injected = {}, set()

    def compile_now():
        work = rel
        if st["modified"]:
            gen_path.parent.mkdir(parents=True, exist_ok=True)
            gen_path.write_text("\n".join(lines))
            work = "pc/gen/" + rel
        return run_clang(work, orig_dir, obj)

    def fix_decl(idx):
        if idx is None or idx < 0 or idx >= len(lines) or (idx == 0 and injected):
            return False
        if lines[idx].lstrip().startswith("extern") and state.get(idx) != 1 and unprototype(lines, idx):
            state[idx] = 1
            return True
        if comment_decl(lines, idx):
            state[idx] = 2
            return True
        return False

    raw = []
    for _ in range(8):
        raw = compile_now()
        todo, inject, scalar, later = [], set(), False, None
        for l in raw:
            m = LOC.match(l)
            if m:
                f, ln, msg = norm(m.group(1)), int(m.group(2)), m.group(4)
                later = None
                if f == rel and CONFLICT.match(msg):
                    later = ln - 1
                    todo.append([later, None])
                mm = re.match(r"use of undeclared identifier '([^']*)'", msg)
                if f == rel and mm and (mm.group(1) in KNOWN or NAMEPAT.fullmatch(mm.group(1))) and mm.group(1) not in injected:
                    inject.add(mm.group(1))
                if f == rel and re.match(r"(assigning to|operand of type) '(s128|u128)'", msg):
                    scalar = True
                continue
            mn = NOTE.match(l)
            if mn and todo and later is not None and todo[-1][1] is None and norm(mn.group(1)) == rel:
                todo[-1][1] = int(mn.group(2)) - 1
        n = 0
        if inject:
            decls = [d for d in (pick_decl(k, lines) for k in sorted(inject)) if d]
            if decls:
                lines[0] = " ".join(decls) + " " + lines[0]
            injected |= inject
            state.clear()
            n = 1
        elif scalar and not st["scalar"]:
            joined = re.sub(r"\bs128\b", "s64", "\n".join(lines))
            joined = re.sub(r"\bu128\b", "u64", joined)
            lines[:] = joined.split("\n")
            st["scalar"] = True
            state.clear()
            n = 1
        else:
            for later_idx, prev_idx in todo:
                if fix_decl(later_idx) or fix_decl(prev_idx):
                    n += 1
        if n == 0:
            break
        st["modified"] = True
        st["fixes"] += n
    else:
        raw = compile_now()
    errs = [l for l in raw if " error: " in l]
    return rel, errs, st["fixes"], st["modified"]


def srcline(path, ln):
    for base in (GEN, ROOT):
        f = base / path
        if f.exists():
            try:
                return f.read_text(errors="replace").split("\n")[ln - 1].strip()[:100]
            except Exception:
                return ""
    return ""


def link_report(out):
    nm = shutil.which("nm") or shutil.which("llvm-nm")
    if not nm:
        out.append("--- M2: falta 'nm'. Instala con: sudo apt install -y binutils")
        return
    objs = sorted((OUT / "obj").glob("*.o"))
    defined, undef = set(), collections.Counter()
    for o in objs:
        r = subprocess.run([nm, "-g", str(o)], capture_output=True, text=True)
        for ln in r.stdout.splitlines():
            parts = ln.split()
            if len(parts) == 3:
                defined.add(parts[2])
            elif len(parts) == 2 and parts[0] in ("U", "w", "v"):
                undef[parts[1]] += 1
    missing = {k: v for k, v in undef.items() if k not in defined}
    groups = collections.Counter()
    for k in missing:
        if k.startswith("func_"):
            g = "func_XXXXXXXX (sin nombre)"
        elif re.match(r"^(Rw|Rp|Rt|Rs)[A-Z]", k):
            g = "RenderWare con nombre"
        elif k.startswith("D_") or re.match(r"^[a-z]Gpffff", k):
            g = "datos (D_ y gp)"
        elif k.startswith("sce"):
            g = "SDK de Sony (sce)"
        elif k == "_GLOBAL_OFFSET_TABLE_":
            g = "artefacto PIC (se quita con -fno-pic)"
        elif LIBC.match(k):
            g = "libc del sistema (se resuelve al enlazar)"
        else:
            g = "otros"
        groups[g] += 1
    out.append("--- M2: objetos compilados: %d | simbolos sin definir: %d" % (len(objs), len(missing)))
    for g, n in groups.most_common():
        out.append("%6d %s" % (n, g))
    out.append("--- los 15 mas referenciados")
    for k, n in sorted(missing.items(), key=lambda x: -undef[x[0]])[:15]:
        out.append("%6d %s" % (undef[k], k))
    (OUT / "undefined.txt").write_text("\n".join(
        "%d %s" % (undef[k], k) for k in sorted(missing, key=lambda x: -undef[x])) + "\n")


def main():
    shutil.rmtree(GEN, ignore_errors=True)
    OUT.mkdir(parents=True, exist_ok=True)
    if OBJECTS:
        shutil.rmtree(OUT / "obj", ignore_errors=True)
        (OUT / "obj").mkdir(parents=True, exist_ok=True)
    gen_headers()
    INDEX.update(build_index())
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
    full = [e for _, errs, _, _ in results for e in errs]
    (OUT / "report_full.txt").write_text("\n".join(full) + "\n")
    cat, perfile = collections.Counter(), collections.Counter()
    for rel, errs, _, _ in results:
        for e in errs:
            m = LOC.match(e)
            if m:
                cat[re.sub(r"'[^']*'", "'X'", m.group(4))] += 1
                perfile[rel] += 1
            else:
                cat["(sin ubicacion) " + e[:70]] += 1

    s = []
    s.append("Archivos comprobados: %d (excluidos: %d)" % (len(files), len(allc) - len(files)))
    s.append("Sin errores: %d   Con errores: %d" % (ok, len(files) - ok))
    s.append("Arreglos mecanicos aplicados: %d (copias generadas: %d)" % (fixes, copies))
    s.append("Errores en total: %d" % len(full))
    s.append("--- errores por tipo (top 8)")
    s += ["%5d %s" % (n, k[:110]) for k, n in cat.most_common(8)]
    s.append("--- errores restantes (con su linea de codigo)")
    seen, cnt = set(), 0
    for e in full:
        m = LOC.match(e)
        if not m:
            s.append(e[:140])
            continue
        p_, l_ = norm(m.group(1)), int(m.group(2))
        key = (p_, l_, m.group(4)[:40])
        if key in seen:
            continue
        seen.add(key)
        cnt += 1
        if cnt > 40:
            break
        s.append("%s:%d %s" % (p_, l_, m.group(4)[:80]))
        s.append("    > " + srcline(p_, l_))
    if OBJECTS:
        link_report(s)
    text = "\n".join(s)
    (OUT / "summary.txt").write_text(text + "\n")
    print(text)
    print("\nDetalle completo en", OUT / "report_full.txt")


if __name__ == "__main__":
    main()
