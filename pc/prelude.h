#ifndef PC_PRELUDE_H
#define PC_PRELUDE_H
/* Tipos de 128 bits para PC (clang x86 de 32 bits no tiene __int128). */
typedef struct { unsigned long long lo, hi; } __attribute__((aligned(16))) pc_u128;
typedef struct { unsigned long long lo, hi; } __attribute__((aligned(16))) pc_s128;
#include "gen/include/effect_vu0_internal.h"
#include "gen/include/particle_spawn_internal.h"
#endif
