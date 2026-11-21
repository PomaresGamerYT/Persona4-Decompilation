#ifndef PC_PRELUDE_H
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
