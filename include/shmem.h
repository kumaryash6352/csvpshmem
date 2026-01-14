#ifndef _SHMEM_H
#define _SHMEM_H

#include "pshmem.h"
#include <execinfo.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>

#if defined(SHMEM_PERF_SETUP) && !defined(_SHMEM_INSTANTIATED)
FILE *_osh_profile_log = NULL;
int _osh_pe_id = -1;
#define _SHMEM_INSTANTIATED
#else
extern FILE *_osh_profile_log;
extern int _osh_pe_id;
#endif

#define UNLIKELY(x) __builtin_expect(!!(x), 0)

static inline double _osh_get_time(void) {
  struct timespec ts;
  clock_gettime(CLOCK_MONOTONIC, &ts);
  return (double)ts.tv_sec + (double)ts.tv_nsec / 1e9;
}

static inline void _osh_log_call(const char *func_name, double duration,
                                 double start, int target_pe, size_t size) {
  if (UNLIKELY(_osh_profile_log == NULL)) {
    if (_osh_pe_id == -1) {
      return;
    }

    char filename[32];
    snprintf(filename, sizeof(filename), "pperf.%03d.csv", _osh_pe_id);

    _osh_profile_log = fopen(filename, "a");
    if (!_osh_profile_log) {
      perror("failed to open log file");
      return;
    }
  }

  void *buffer[10];
  int nptrs = backtrace(buffer, 10);
  char bt_str[256] = "";
  int offset = 0;
  for (int i = 0; i < nptrs && offset < 250; i++) {
    offset += snprintf(bt_str + offset, 256 - offset, "%p|", buffer[i]);
  }

  fprintf(_osh_profile_log, "%.9f,%s,%.9f,%d,%zu,%s\n", start, func_name,
          duration, target_pe, size, bt_str);
}

// beware
#ifndef SYM_QUAL_INNER2
#define SYM_QUAL_INNER2(p, n) #p #n
#ifndef SYM_QUAL_INNER
#define SYM_QUAL_INNER(p, n) SYM_QUAL_INNER2(p, n)
#endif
#endif
#define WRAP_SYM(n) SYM_QUAL_INNER(__USER_LABEL_PREFIX__, _osh_wrap_##n)

#define WRAP_CALL_VOID(FN_NAME, DECL_ARGS, CALL_ARGS, PE, SIZE)                \
  static inline void FN_NAME DECL_ARGS __asm__(WRAP_SYM(FN_NAME));             \
  static inline void FN_NAME DECL_ARGS {                                       \
    double start_t = _osh_get_time();                                          \
    p##FN_NAME CALL_ARGS;                                                      \
    double end_t = _osh_get_time();                                            \
    _osh_log_call(#FN_NAME, end_t - start_t, start_t, PE, SIZE);               \
  }

#define WRAP_CALL_RET(RET_TYPE, FN_NAME, DECL_ARGS, CALL_ARGS, PE, SIZE)       \
  static inline RET_TYPE FN_NAME DECL_ARGS __asm__(WRAP_SYM(FN_NAME));         \
  static inline RET_TYPE FN_NAME DECL_ARGS {                                   \
    double start_t = _osh_get_time();                                          \
    RET_TYPE ret = p##FN_NAME CALL_ARGS;                                       \
    double end_t = _osh_get_time();                                            \
    _osh_log_call(#FN_NAME, end_t - start_t, start_t, PE, SIZE);               \
    return ret;                                                                \
  }

// magic to make sure we call the right shmem finalize
static inline void shmem_init(void) __asm__(WRAP_SYM(shmem_init));
static inline void shmem_init(void) {
  double start_t = _osh_get_time();

  pshmem_init();

  double end_t = _osh_get_time();

  _osh_pe_id = pshmem_my_pe();

  char filename[32];
  if (_osh_pe_id != -1) {
    snprintf(filename, sizeof(filename), "pperf.%03d.csv", _osh_pe_id);
    _osh_profile_log = fopen(filename, "w");
  }

  if (_osh_profile_log) {
    fprintf(_osh_profile_log,
            "Time,Function,Duration_Sec,Target_PE,Size_Bytes,Stacktrace\n");
    _osh_log_call("shmem_init", end_t - start_t, start_t, -1, 0);
  }
}

// magic to make sure we call the right shmem finalize
static inline void shmem_finalize(void) __asm__(WRAP_SYM(shmem_finalize));
static inline void shmem_finalize(void) {
  double start_t = _osh_get_time();

  pshmem_finalize();

  double end_t = _osh_get_time();

  _osh_log_call("shmem_finalize", end_t - start_t, start_t, -1, 0);

  if (_osh_profile_log) {
    fclose(_osh_profile_log);
    _osh_profile_log = NULL;
  }
}

// from osss-ucx

#define SHMEM_STANDARD_RMA_TYPE_TABLE(X)                                       \
  X(float, float)                                                              \
  X(double, double)                                                            \
  X(long double, longdouble)                                                   \
  X(char, char)                                                                \
  X(signed char, schar)                                                        \
  X(short, short)                                                              \
  X(int, int)                                                                  \
  X(long, long)                                                                \
  X(long long, longlong)                                                       \
  X(unsigned char, uchar)                                                      \
  X(unsigned short, ushort)                                                    \
  X(unsigned int, uint)                                                        \
  X(unsigned long, ulong)                                                      \
  X(unsigned long long, ulonglong)                                             \
  X(int8_t, int8)                                                              \
  X(int16_t, int16)                                                            \
  X(int32_t, int32)                                                            \
  X(int64_t, int64)                                                            \
  X(uint8_t, uint8)                                                            \
  X(uint16_t, uint16)                                                          \
  X(uint32_t, uint32)                                                          \
  X(uint64_t, uint64)                                                          \
  X(size_t, size)                                                              \
  X(ptrdiff_t, ptrdiff)

#define SHMEM_STANDARD_AMO_TYPE_TABLE(X)                                       \
  X(int, int)                                                                  \
  X(long, long)                                                                \
  X(long long, longlong)                                                       \
  X(unsigned int, uint)                                                        \
  X(unsigned long, ulong)                                                      \
  X(unsigned long long, ulonglong)                                             \
  X(int32_t, int32)                                                            \
  X(int64_t, int64)                                                            \
  X(uint32_t, uint32)                                                          \
  X(uint64_t, uint64)                                                          \
  X(size_t, size)                                                              \
  X(ptrdiff_t, ptrdiff)

#define SHMEM_EXTENDED_AMO_TYPE_TABLE(X)                                       \
  X(float, float)                                                              \
  X(double, double)                                                            \
  X(int, int)                                                                  \
  X(long, long)                                                                \
  X(long long, longlong)                                                       \
  X(unsigned int, uint)                                                        \
  X(unsigned long, ulong)                                                      \
  X(unsigned long long, ulonglong)                                             \
  X(int32_t, int32)                                                            \
  X(int64_t, int64)                                                            \
  X(uint32_t, uint32)                                                          \
  X(uint64_t, uint64)                                                          \
  X(size_t, size)                                                              \
  X(ptrdiff_t, ptrdiff)

#define SHMEM_BITWISE_AMO_TYPE_TABLE(X)                                        \
  X(unsigned int, uint)                                                        \
  X(unsigned long, ulong)                                                      \
  X(unsigned long long, ulonglong)                                             \
  X(int32_t, int32)                                                            \
  X(int64_t, int64)                                                            \
  X(uint32_t, uint32)                                                          \
  X(uint64_t, uint64)

#define SHMEM_TO_ALL_BITWISE_TYPE_TABLE(X)                                     \
  X(short, short)                                                              \
  X(int, int)                                                                  \
  X(long, long)                                                                \
  X(long long, longlong)

#define SHMEM_TO_ALL_MINMAX_TYPE_TABLE(X)                                      \
  X(short, short)                                                              \
  X(int, int)                                                                  \
  X(long, long)                                                                \
  X(long long, longlong)                                                       \
  X(float, float)                                                              \
  X(double, double)                                                            \
  X(long double, longdouble)

#define SHMEM_TO_ALL_ARITH_TYPE_TABLE(X)                                       \
  X(short, short)                                                              \
  X(int, int)                                                                  \
  X(long, long)                                                                \
  X(long long, longlong)                                                       \
  X(float, float)                                                              \
  X(double, double)                                                            \
  X(long double, longdouble)                                                   \
  X(double _Complex, complexd)                                                 \
  X(float _Complex, complexf)

#define SHMEM_REDUCE_BITWISE_TYPE_TABLE(X)                                     \
  X(unsigned char, uchar)                                                      \
  X(unsigned short, ushort)                                                    \
  X(unsigned int, uint)                                                        \
  X(unsigned long, ulong)                                                      \
  X(unsigned long long, ulonglong)                                             \
  X(int8_t, int8)                                                              \
  X(int16_t, int16)                                                            \
  X(int32_t, int32)                                                            \
  X(int64_t, int64)                                                            \
  X(uint8_t, uint8)                                                            \
  X(uint16_t, uint16)                                                          \
  X(uint32_t, uint32)                                                          \
  X(uint64_t, uint64)                                                          \
  X(size_t, size)

#define SHMEM_REDUCE_MINMAX_TYPE_TABLE(X)                                      \
  X(char, char)                                                                \
  X(signed char, schar)                                                        \
  X(short, short)                                                              \
  X(int, int)                                                                  \
  X(long, long)                                                                \
  X(long long, longlong)                                                       \
  X(ptrdiff_t, ptrdiff)                                                        \
  X(unsigned char, uchar)                                                      \
  X(unsigned short, ushort)                                                    \
  X(unsigned int, uint)                                                        \
  X(unsigned long, ulong)                                                      \
  X(unsigned long long, ulonglong)                                             \
  X(int8_t, int8)                                                              \
  X(int16_t, int16)                                                            \
  X(int32_t, int32)                                                            \
  X(int64_t, int64)                                                            \
  X(uint8_t, uint8)                                                            \
  X(uint16_t, uint16)                                                          \
  X(uint32_t, uint32)                                                          \
  X(uint64_t, uint64)                                                          \
  X(size_t, size)                                                              \
  X(float, float)                                                              \
  X(double, double)                                                            \
  X(long double, longdouble)

#define SHMEM_REDUCE_ARITH_TYPE_TABLE(X)                                       \
  X(char, char)                                                                \
  X(signed char, schar)                                                        \
  X(short, short)                                                              \
  X(int, int)                                                                  \
  X(long, long)                                                                \
  X(long long, longlong)                                                       \
  X(ptrdiff_t, ptrdiff)                                                        \
  X(unsigned char, uchar)                                                      \
  X(unsigned short, ushort)                                                    \
  X(unsigned int, uint)                                                        \
  X(unsigned long, ulong)                                                      \
  X(unsigned long long, ulonglong)                                             \
  X(int8_t, int8)                                                              \
  X(int16_t, int16)                                                            \
  X(int32_t, int32)                                                            \
  X(int64_t, int64)                                                            \
  X(uint8_t, uint8)                                                            \
  X(uint16_t, uint16)                                                          \
  X(uint32_t, uint32)                                                          \
  X(uint64_t, uint64)                                                          \
  X(size_t, size)                                                              \
  X(float, float)                                                              \
  X(double, double)                                                            \
  X(long double, longdouble)                                                   \
  X(double _Complex, complexd)                                                 \
  X(float _Complex, complexf)

#define SHMEM_RMA_HELPER(CT, ST)                                               \
  WRAP_CALL_VOID(shmem_##ST##_put,                                             \
                 (CT * dest, const CT *src, size_t nelems, int pe),            \
                 (dest, src, nelems, pe), pe, nelems * sizeof(CT))             \
  WRAP_CALL_VOID(shmem_##ST##_get,                                             \
                 (CT * dest, const CT *src, size_t nelems, int pe),            \
                 (dest, src, nelems, pe), pe, nelems * sizeof(CT))             \
  WRAP_CALL_VOID(shmem_##ST##_put_nbi,                                         \
                 (CT * dest, const CT *src, size_t nelems, int pe),            \
                 (dest, src, nelems, pe), pe, nelems * sizeof(CT))             \
  WRAP_CALL_VOID(shmem_##ST##_get_nbi,                                         \
                 (CT * dest, const CT *src, size_t nelems, int pe),            \
                 (dest, src, nelems, pe), pe, nelems * sizeof(CT))             \
  WRAP_CALL_VOID(shmem_##ST##_p, (CT * dest, CT value, int pe),                \
                 (dest, value, pe), pe, sizeof(CT))                            \
  WRAP_CALL_RET(CT, shmem_##ST##_g, (const CT *dest, int pe), (dest, pe), pe,  \
                sizeof(CT))                                                    \
  WRAP_CALL_VOID(shmem_##ST##_iput,                                            \
                 (CT * dest, const CT *src, ptrdiff_t dst, ptrdiff_t sst,      \
                  size_t nelems, int pe),                                      \
                 (dest, src, dst, sst, nelems, pe), pe, nelems * sizeof(CT))   \
  WRAP_CALL_VOID(shmem_##ST##_iget,                                            \
                 (CT * dest, const CT *src, ptrdiff_t dst, ptrdiff_t sst,      \
                  size_t nelems, int pe),                                      \
                 (dest, src, dst, sst, nelems, pe), pe, nelems * sizeof(CT))

SHMEM_STANDARD_RMA_TYPE_TABLE(SHMEM_RMA_HELPER)

#define SHMEM_AMO_HELPER(CT, ST)                                               \
  WRAP_CALL_VOID(shmem_atomic_##ST##_fetch, (CT * dest, int pe), (dest, pe),   \
                 pe, sizeof(CT))                                               \
  WRAP_CALL_VOID(shmem_atomic_##ST##_fetch_nbi,                                \
                 (CT * fetch, CT * dest, int pe), (fetch, dest, pe), pe,       \
                 sizeof(CT))                                                   \
  WRAP_CALL_VOID(shmem_atomic_##ST##_set, (CT * dest, CT val, int pe),         \
                 (dest, val, pe), pe, sizeof(CT))                              \
  WRAP_CALL_VOID(shmem_atomic_##ST##_set_nbi, (CT * dest, CT val, int pe),     \
                 (dest, val, pe), pe, sizeof(CT))                              \
  WRAP_CALL_RET(CT, shmem_atomic_##ST##_compare_swap,                          \
                (CT * dest, CT cond, CT val, int pe), (dest, cond, val, pe),   \
                pe, sizeof(CT))                                                \
  WRAP_CALL_VOID(shmem_atomic_##ST##_compare_swap_nbi,                         \
                 (CT * fetch, CT * dest, CT cond, CT val, int pe),             \
                 (fetch, dest, cond, val, pe), pe, sizeof(CT))

SHMEM_EXTENDED_AMO_TYPE_TABLE(SHMEM_AMO_HELPER)

#define SHMEM_AMO_ARITH_HELPER(CT, ST)                                         \
  WRAP_CALL_RET(CT, shmem_atomic_##ST##_fetch_inc, (CT * dest, int pe),        \
                (dest, pe), pe, sizeof(CT))                                    \
  WRAP_CALL_VOID(shmem_atomic_##ST##_fetch_inc_nbi,                            \
                 (CT * fetch, CT * dest, int pe), (fetch, dest, pe), pe,       \
                 sizeof(CT))                                                   \
  WRAP_CALL_VOID(shmem_atomic_##ST##_inc, (CT * dest, int pe), (dest, pe), pe, \
                 sizeof(CT))                                                   \
  WRAP_CALL_RET(CT, shmem_atomic_##ST##_fetch_add,                             \
                (CT * dest, CT value, int pe), (dest, value, pe), pe,          \
                sizeof(CT))                                                    \
  WRAP_CALL_VOID(shmem_atomic_##ST##_fetch_add_nbi,                            \
                 (CT * fetch, CT * dest, CT value, int pe),                    \
                 (fetch, dest, value, pe), pe, sizeof(CT))                     \
  WRAP_CALL_VOID(shmem_atomic_##ST##_add, (CT * dest, CT value, int pe),       \
                 (dest, value, pe), pe, sizeof(CT))

SHMEM_STANDARD_AMO_TYPE_TABLE(SHMEM_AMO_ARITH_HELPER)

#define SHMEM_AMO_BITWISE_HELPER(CT, ST)                                       \
  WRAP_CALL_RET(CT, shmem_atomic_##ST##_fetch_and,                             \
                (CT * dest, CT value, int pe), (dest, value, pe), pe,          \
                sizeof(CT))                                                    \
  WRAP_CALL_VOID(shmem_atomic_##ST##_fetch_and_nbi,                            \
                 (CT * fetch, CT * dest, CT value, int pe),                    \
                 (fetch, dest, value, pe), pe, sizeof(CT))                     \
  WRAP_CALL_VOID(shmem_atomic_##ST##_and, (CT * dest, CT value, int pe),       \
                 (dest, value, pe), pe, sizeof(CT))                            \
  WRAP_CALL_RET(CT, shmem_atomic_##ST##_fetch_or,                              \
                (CT * dest, CT value, int pe), (dest, value, pe), pe,          \
                sizeof(CT))                                                    \
  WRAP_CALL_VOID(shmem_atomic_##ST##_fetch_or_nbi,                             \
                 (CT * fetch, CT * dest, CT value, int pe),                    \
                 (fetch, dest, value, pe), pe, sizeof(CT))                     \
  WRAP_CALL_VOID(shmem_atomic_##ST##_or, (CT * dest, CT value, int pe),        \
                 (dest, value, pe), pe, sizeof(CT))                            \
  WRAP_CALL_RET(CT, shmem_atomic_##ST##_fetch_xor,                             \
                (CT * dest, CT value, int pe), (dest, value, pe), pe,          \
                sizeof(CT))                                                    \
  WRAP_CALL_VOID(shmem_atomic_##ST##_fetch_xor_nbi,                            \
                 (CT * fetch, CT * dest, CT value, int pe),                    \
                 (fetch, dest, value, pe), pe, sizeof(CT))                     \
  WRAP_CALL_VOID(shmem_atomic_##ST##_xor, (CT * dest, CT value, int pe),       \
                 (dest, value, pe), pe, sizeof(CT))

SHMEM_BITWISE_AMO_TYPE_TABLE(SHMEM_AMO_BITWISE_HELPER)

#define SHMEM_TO_ALL_BITWISE_HELPER(CT, ST)                                    \
  WRAP_CALL_VOID(                                                              \
      shmem_##ST##_and_to_all,                                                 \
      (CT * dest, const CT *source, int nreduce, int PE_start,                 \
       int logPE_stride, int PE_size, CT *pWrk, long *pSync),                  \
      (dest, source, nreduce, PE_start, logPE_stride, PE_size, pWrk, pSync),   \
      -1, nreduce * sizeof(CT))                                                \
  WRAP_CALL_VOID(                                                              \
      shmem_##ST##_or_to_all,                                                  \
      (CT * dest, const CT *source, int nreduce, int PE_start,                 \
       int logPE_stride, int PE_size, CT *pWrk, long *pSync),                  \
      (dest, source, nreduce, PE_start, logPE_stride, PE_size, pWrk, pSync),   \
      -1, nreduce * sizeof(CT))                                                \
  WRAP_CALL_VOID(                                                              \
      shmem_##ST##_xor_to_all,                                                 \
      (CT * dest, const CT *source, int nreduce, int PE_start,                 \
       int logPE_stride, int PE_size, CT *pWrk, long *pSync),                  \
      (dest, source, nreduce, PE_start, logPE_stride, PE_size, pWrk, pSync),   \
      -1, nreduce * sizeof(CT))

SHMEM_TO_ALL_BITWISE_TYPE_TABLE(SHMEM_TO_ALL_BITWISE_HELPER)

#define SHMEM_TO_ALL_MINMAX_HELPER(CT, ST)                                     \
  WRAP_CALL_VOID(                                                              \
      shmem_##ST##_max_to_all,                                                 \
      (CT * dest, const CT *source, int nreduce, int PE_start,                 \
       int logPE_stride, int PE_size, CT *pWrk, long *pSync),                  \
      (dest, source, nreduce, PE_start, logPE_stride, PE_size, pWrk, pSync),   \
      -1, nreduce * sizeof(CT))                                                \
  WRAP_CALL_VOID(                                                              \
      shmem_##ST##_min_to_all,                                                 \
      (CT * dest, const CT *source, int nreduce, int PE_start,                 \
       int logPE_stride, int PE_size, CT *pWrk, long *pSync),                  \
      (dest, source, nreduce, PE_start, logPE_stride, PE_size, pWrk, pSync),   \
      -1, nreduce * sizeof(CT))

SHMEM_TO_ALL_MINMAX_TYPE_TABLE(SHMEM_TO_ALL_MINMAX_HELPER)

#define SHMEM_TO_ALL_ARITH_HELPER(CT, ST)                                      \
  WRAP_CALL_VOID(                                                              \
      shmem_##ST##_sum_to_all,                                                 \
      (CT * dest, const CT *source, int nreduce, int PE_start,                 \
       int logPE_stride, int PE_size, CT *pWrk, long *pSync),                  \
      (dest, source, nreduce, PE_start, logPE_stride, PE_size, pWrk, pSync),   \
      -1, nreduce * sizeof(CT))                                                \
  WRAP_CALL_VOID(                                                              \
      shmem_##ST##_prod_to_all,                                                \
      (CT * dest, const CT *source, int nreduce, int PE_start,                 \
       int logPE_stride, int PE_size, CT *pWrk, long *pSync),                  \
      (dest, source, nreduce, PE_start, logPE_stride, PE_size, pWrk, pSync),   \
      -1, nreduce * sizeof(CT))

SHMEM_TO_ALL_ARITH_TYPE_TABLE(SHMEM_TO_ALL_ARITH_HELPER)

#define SHMEM_REDUCE_BITWISE_HELPER(CT, ST)                                    \
  WRAP_CALL_RET(                                                               \
      int, shmem_##ST##_and_reduce,                                            \
      (shmem_team_t team, CT * dest, const CT *source, size_t nreduce),        \
      (team, dest, source, nreduce), -1, nreduce * sizeof(CT))                 \
  WRAP_CALL_RET(                                                               \
      int, shmem_##ST##_or_reduce,                                             \
      (shmem_team_t team, CT * dest, const CT *source, size_t nreduce),        \
      (team, dest, source, nreduce), -1, nreduce * sizeof(CT))                 \
  WRAP_CALL_RET(                                                               \
      int, shmem_##ST##_xor_reduce,                                            \
      (shmem_team_t team, CT * dest, const CT *source, size_t nreduce),        \
      (team, dest, source, nreduce), -1, nreduce * sizeof(CT))

SHMEM_REDUCE_BITWISE_TYPE_TABLE(SHMEM_REDUCE_BITWISE_HELPER)

#define SHMEM_REDUCE_MINMAX_HELPER(CT, ST)                                     \
  WRAP_CALL_RET(                                                               \
      int, shmem_##ST##_max_reduce,                                            \
      (shmem_team_t team, CT * dest, const CT *source, size_t nreduce),        \
      (team, dest, source, nreduce), -1, nreduce * sizeof(CT))                 \
  WRAP_CALL_RET(                                                               \
      int, shmem_##ST##_min_reduce,                                            \
      (shmem_team_t team, CT * dest, const CT *source, size_t nreduce),        \
      (team, dest, source, nreduce), -1, nreduce * sizeof(CT))

SHMEM_REDUCE_MINMAX_TYPE_TABLE(SHMEM_REDUCE_MINMAX_HELPER)

#define SHMEM_REDUCE_ARITH_HELPER(CT, ST)                                      \
  WRAP_CALL_RET(                                                               \
      int, shmem_##ST##_sum_reduce,                                            \
      (shmem_team_t team, CT * dest, const CT *source, size_t nreduce),        \
      (team, dest, source, nreduce), -1, nreduce * sizeof(CT))                 \
  WRAP_CALL_RET(                                                               \
      int, shmem_##ST##_prod_reduce,                                           \
      (shmem_team_t team, CT * dest, const CT *source, size_t nreduce),        \
      (team, dest, source, nreduce), -1, nreduce * sizeof(CT))

SHMEM_REDUCE_ARITH_TYPE_TABLE(SHMEM_REDUCE_ARITH_HELPER)

WRAP_CALL_VOID(shmem_barrier_all, (void), (), -1, 0)
WRAP_CALL_VOID(shmem_fence, (void), (), -1, 0)
WRAP_CALL_VOID(shmem_quiet, (void), (), -1, 0)
WRAP_CALL_RET(int, shmem_my_pe, (void), (), -1, 0)
WRAP_CALL_RET(int, shmem_n_pes, (void), (), -1, 0)

WRAP_CALL_RET(int, shmem_broadcast64,
              (void *dest, const void *source, size_t nelems, int PE_root,
               int PE_start, int logPE_stride, int PE_size, long *pSync),
              (dest, source, nelems, PE_root, PE_start, logPE_stride, PE_size,
               pSync),
              PE_root, nelems * 8)

WRAP_CALL_RET(void *, shmem_malloc, (size_t size), (size), -1, size)
WRAP_CALL_VOID(shmem_free, (void *ptr), (ptr), -1, 0)

#endif /* _SHMEM_H */
