# Port a PC de Persona 4 (rama pc-port)

## Entorno
- Windows 11, WSL2 Debian, Docker Desktop. Repo en ~/Persona4-Decompilation. Plan gratuito de Claude: sin Claude Code.
- Compiladores propietarios en ~/p4private (se montan como /opt/p4 en el contenedor p4-decomp).
- Build del decomp: dentro del contenedor, "env -u P4_EEGCC_AS make". Reproduce los dos hashes del README.
- Medicion para PC: python3 pc/tools/check.py (clang x86 de 32 bits, -malign-double, -fms-extensions).

## Decisiones
- Primero PC, despues Wii. No editar src/ ni include/ originales: los cambios van en pc/ (copias en pc/gen/, ignorado por Git).
- Efectos (archivos con __asm__ del VU0): fuera por ahora; cabeceras de efectos sustituidas por funciones vacias hasta el hito M6.
- Trabajo en el chat: pocos mensajes, scripts que hacen mas por ronda, un chat nuevo por fase con este archivo pegado.

## Medidas
- 773 archivos propios. Con las opciones anteriores compilaban 532 (69 %). Ver la medicion mas reciente en ~/p4work/summary.txt.
- RenderWare: unas 1000 funciones sin nombre llamadas desde el juego; varias ya en C, otras en ensamblador.

## Hitos
M0 decomp compila: HECHO | M1 todo el codigo propio compila en PC | M2 enlaza con piezas vacias
M3 capa de plataforma | M4 RenderWare y dibujo | M5 sonido y video | M6 efectos VU0 | M7 Wii.
Reevaluar la viabilidad al terminar M2.

## Medicion M1 (casi hecho)
- 725 archivos comprobados (48 excluidos por asm): 699 compilan; 26 con errores (56 errores). Antes 69 %.
- Arreglos mecanicos en copias pc/gen: tipos de 128 bits, declaraciones en conflicto, cabeceras de efectos vacias.
- Deuda anotada: conversiones puntero/entero degradadas a aviso (solo seguro en 32 bits); efectos = funciones vacias.
- Pendiente: builtins desconocidos, D_00887300/D_00887310/iGpffffa748 sin declarar, prototipos en conflicto.
- Siguiente (M2): compilar a objetos (-c), enlazar y generar stubs de los simbolos que falten.

## Deuda anotada (hay que verificar mas adelante)
- va_start/__builtin_args_info definidos en pc/prelude.h como macros para x86 de 32 bits; sdkDbprt_* puede comportarse mal.
- D_00887300, D_00887310 e iGpffffa748: tipos deducidos del uso (tablas de RenderWare y una variable del gp).
- src/cmmMisc.c: cmmCommunityHasRecord(0) es una suposicion (el original no pasaba argumento).
- s128 tratado como s64 donde se usa como numero (fclCombineMisc.c).
- Fuera por ahora: src/nmCmdList_inferred_002ba080.c (pasa un u32 donde se espera otro tipo) y los 48 archivos con asm.
- Prototipos extern en conflicto: unprototype (extern T f();) o comentados en copias pc/gen.
- Conversiones puntero/entero y return sin valor: degradados a aviso (solo seguro en 32 bits).

## Siguiente (M2)
- python3 pc/tools/check.py --objects genera objetos y ~/p4work/undefined.txt con los simbolos sin definir.
- Generar stubs para los simbolos que falten y enlazar.

## Estado tras M1 (medido con check.py --objects)
- 773 archivos propios: 724 comprobados + 49 excluidos (asm del VU0, asm de nivel superior y nmCmdList_inferred_002ba080.c).
- 717 compilan en sintaxis; 7 con errores (23): fclCombineMisc, fclMisc, h_malloc_inferred_001400f0, datCalc_inferred_0021a7b0, frFont, nmCmdList_inferred_00353b50, shdPersona.
- "Compila" = solo sintaxis, efectos vacios, con deudas. No significa que funcione.
- Errores del propio check.py hallados en la revision: la inyeccion de declaraciones desplazaba lineas y se comentaba a si misma; el tipo deducido de D_00887310 chocaba con la declaracion propia del archivo. Parche aplicado, resultado por confirmar.
- Riesgo de ABI pendiente: parametros s64 y structs por valor (ej. radarDrawSegment(s64 ...)) ocupan distinto en x86-32 que en MIPS; auditar antes de ejecutar.

## M2 (medido): 717 objetos, 4830 simbolos sin definir
- 3876 datos (D_ y gp), 491 func_XXXXXXXX, 429 otros (incluye libc y _GLOBAL_OFFSET_TABLE_), 28 RenderWare con nombre, 6 sce.
- Mas referenciados: jtbl_008873EC (154), memset, D_008873F4 (111), func_00440b68 (93), iGpffffb3ac (74), D_00887300 (73), RpSkyRenderStateSet (66), jtbl_008873E8 (54).
- Segun architecture.md: jtbl_008873E8/EC y D_008873F4 = alloc/free/calloc de RenderWare; func_00440b68 = printf de depuracion; D_00887300 = setter de estados de render.
- Decision pendiente: como dar existencia en PC a ~3900 datos que en PS2 viven en direcciones fijas del ejecutable.
