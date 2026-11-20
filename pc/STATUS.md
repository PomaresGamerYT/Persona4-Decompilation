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
