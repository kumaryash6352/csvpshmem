#!/usr/bin/env python3
import re
import os
import subprocess
import sys

shmem_h_path = "./include/shmem.h"
# derive real shmem dir from SHMEM_DIR or oshcc -showme
real_shmem_dir = os.environ.get("SHMEM_DIR")
if not real_shmem_dir:
    try:
        showme = subprocess.check_output(["oshcc", "-showme"], stderr=subprocess.STDOUT).decode()
        for part in showme.split():
            if part.startswith("-I"):
                inc = part[2:]
                if os.path.isfile(os.path.join(inc, "shmem.h")):
                    real_shmem_dir = inc
                    break
    except Exception as e:
        print(f"could not find shmem install. set SHMEM_DIR environment variable or ensure oshcc -showme works.\n{e}")
        sys.exit(1)

if not real_shmem_dir or not os.path.isdir(real_shmem_dir):
    print("could not find shmem install. set SHMEM_DIR environment variable or ensure oshcc -showme works.")
    sys.exit(1)

real_shmem_h = os.path.join(real_shmem_dir, "shmem.h")

with open(real_shmem_h, "r") as f:
    real_shmem_content = f.read()

# lifted from tables in shmem.h which were stolen from osss-ucx
rma_types = [
    ("float", "float"), ("double", "double"), ("long double", "longdouble"),
    ("char", "char"), ("signed char", "schar"), ("short", "short"),
    ("int", "int"), ("long", "long"), ("long long", "longlong"),
    ("unsigned char", "uchar"), ("unsigned short", "ushort"),
    ("unsigned int", "uint"), ("unsigned long", "ulong"),
    ("unsigned long long", "ulonglong"), ("int8_t", "int8"),
    ("int16_t", "int16"), ("int32_t", "int32"), ("int64_t", "int64"),
    ("uint8_t", "uint8"), ("uint16_t", "uint16"), ("uint32_t", "uint32"),
    ("uint64_t", "uint64"), ("size_t", "size"), ("ptrdiff_t", "ptrdiff")
]

amo_types = [
    ("int", "int"), ("long", "long"), ("long long", "longlong"),
    ("unsigned int", "uint"), ("unsigned long", "ulong"),
    ("unsigned long long", "ulonglong"), ("int32_t", "int32"),
    ("int64_t", "int64"), ("uint32_t", "uint32"), ("uint64_t", "uint64"),
    ("size_t", "size"), ("ptrdiff_t", "ptrdiff")
]

ext_amo_types = [
    ("float", "float"), ("double", "double"), ("int", "int"),
    ("long", "long"), ("long long", "longlong"), ("unsigned int", "uint"),
    ("unsigned long", "ulong"), ("unsigned long long", "ulonglong"),
    ("int32_t", "int32"), ("int64_t", "int64"), ("uint32_t", "uint32"),
    ("uint64_t", "uint64"), ("size_t", "size"), ("ptrdiff_t", "ptrdiff")
]

bitwise_amo_types = [
    ("unsigned int", "uint"), ("unsigned long", "ulong"),
    ("unsigned long long", "ulonglong"), ("int32_t", "int32"),
    ("int64_t", "int64"), ("uint32_t", "uint32"), ("uint64_t", "uint64")
]

functions = []
# (ret, name, decl_args, call_args)
functions.append(("void", "shmem_init", "()", "()"))
functions.append(("void", "shmem_finalize", "()", "()"))
functions.append(("void", "shmem_barrier_all", "()", "()"))
functions.append(("void", "shmem_fence", "()", "()"))
functions.append(("void", "shmem_quiet", "()", "()"))
functions.append(("int", "shmem_my_pe", "()", "()"))
functions.append(("int", "shmem_n_pes", "()", "()"))
functions.append(("void *", "shmem_malloc", "(size_t size)", "(size)"))
functions.append(("void", "shmem_free", "(void *ptr)", "(ptr)"))
functions.append(("int", "shmem_broadcast64", "(void *dest, const void *source, size_t nelems, int PE_root, int PE_start, int logPE_stride, int PE_size, long *pSync)", "(dest, source, nelems, PE_root, PE_start, logPE_stride, PE_size, pSync)"))

for ct, st in rma_types:
    functions.append(("void", f"shmem_{st}_put", f"({ct} *dest, const {ct} *src, size_t nelems, int pe)", "(dest, src, nelems, pe)"))
    functions.append(("void", f"shmem_{st}_get", f"({ct} *dest, const {ct} *src, size_t nelems, int pe)", "(dest, src, nelems, pe)"))

for ct, st in ext_amo_types:
    functions.append(("void", f"shmem_atomic_{st}_fetch", f"({ct} *dest, int pe)", "(dest, pe)"))
    functions.append(("void", f"shmem_atomic_{st}_fetch_nbi", f"({ct} *fetch, {ct} *dest, int pe)", "(fetch, dest, pe)"))
    functions.append(("void", f"shmem_atomic_{st}_set", f"({ct} *dest, {ct} val, int pe)", "(dest, val, pe)"))
    functions.append(("void", f"shmem_atomic_{st}_set_nbi", f"({ct} *dest, {ct} val, int pe)", "(dest, val, pe)"))
    functions.append((ct, f"shmem_atomic_{st}_compare_swap", f"({ct} *dest, {ct} cond, {ct} val, int pe)", "(dest, cond, val, pe)"))
    functions.append(("void", f"shmem_atomic_{st}_compare_swap_nbi", f"({ct} *fetch, {ct} *dest, {ct} cond, {ct} val, int pe)", "(fetch, dest, cond, val, pe)"))

for ct, st in amo_types:
    functions.append((ct, f"shmem_atomic_{st}_fetch_inc", f"({ct} *dest, int pe)", "(dest, pe)"))
    functions.append(("void", f"shmem_atomic_{st}_fetch_inc_nbi", f"({ct} *fetch, {ct} *dest, int pe)", "(fetch, dest, pe)"))
    functions.append(("void", f"shmem_atomic_{st}_inc", f"({ct} *dest, int pe)", "(dest, pe)"))
    functions.append((ct, f"shmem_atomic_{st}_fetch_add", f"({ct} *dest, {ct} value, int pe)", "(dest, value, pe)"))
    functions.append(("void", f"shmem_atomic_{st}_fetch_add_nbi", f"({ct} *fetch, {ct} *dest, {ct} value, int pe)", "(fetch, dest, value, pe)"))
    functions.append(("void", f"shmem_atomic_{st}_add", f"({ct} *dest, {ct} value, int pe)", "(dest, value, pe)"))

for ct, st in bitwise_amo_types:
    for op in ["and", "or", "xor"]:
        name = f"shmem_atomic_{st}_{op}"
        fetch_name = f"shmem_atomic_{st}_fetch_{op}"
        nbi_name = f"shmem_atomic_{st}_fetch_{op}_nbi"
        functions.append((ct, fetch_name, f"({ct} *dest, {ct} value, int pe)", "(dest, value, pe)"))
        functions.append(("void", nbi_name, f"({ct} *fetch, {ct} *dest, {ct} value, int pe)", "(fetch, dest, value, pe)"))
        functions.append(("void", name, f"({ct} *dest, {ct} value, int pe)", "(dest, value, pe)"))

def get_real_name(name):
    if name in real_shmem_content:
        return name
    if name.startswith("shmem_atomic_"):
        m = re.match(r"shmem_atomic_([a-z0-9]+)_(.*)", name)
        if m:
            st, op = m.groups()
            alt = f"shmem_{st}_atomic_{op}"
            if alt in real_shmem_content: return alt
            alt = f"shmem_{st}_{op}"
            if alt in real_shmem_content: return alt
        else:
            m = re.match(r"shmem_atomic_([a-z0-9]+)", name)
            if m:
                st = m.group(1)
                alt = f"shmem_{st}_atomic_fetch"
                if alt in real_shmem_content: return alt
    if "atomic" in name:
        alt = name.replace("_atomic", "")
        if alt in real_shmem_content: return alt
    return None

def get_real_ret(real_name):
    m = re.search(r"SHMEM_FUNCTION_ATTRIBUTES\s+([a-zA-Z0-9_\s\*]+?)\s+" + re.escape(real_name) + r"\s*\(", real_shmem_content)
    if m:
        return m.group(1).strip()
    return None

all_shmem_names = sorted(list(set(re.findall(r"shmem_[a-zA-Z0-9_]+", real_shmem_content))))
rename_list = [n for n in all_shmem_names if not n.endswith("_t") and not n.isupper()]

macros = set(re.findall(r"#\s*define\s+(shmem_[a-zA-Z0-9_]+)", real_shmem_content))
static_inlines = set(re.findall(r"static\s+inline\s+[^(]+\s+(shmem_[a-zA-Z0-9_]+)\(", real_shmem_content))

with open("./include/pshmem.h", "w") as f:
    f.write("#ifndef _PSHMEM_H\n")
    f.write("#define _PSHMEM_H\n\n")

    f.write("""
    /*
     * this file is generated by gen_pshmem.py
     * do not modify by hand
     * do not check into version control
     * instead, edit gen_pshmem.py 
     */
    """)

    f.write("#include <stddef.h>\n")
    f.write("#include <stdint.h>\n")
    f.write("#include <stdio.h>\n\n")
    f.write('#ifdef __cplusplus\nextern "C" {\n#endif\n\n')
    
    f.write("// rename underlying shmem symbols to avoid conflict with our wrappers\n")
    f.write("#pragma clang diagnostic push\n")
    f.write("#pragma clang diagnostic ignored \"-Wmacro-redefined\"\n")
    for n in rename_list:
        f.write(f"#define {n} real_{n}\n")
    f.write("\n")
    f.write(f'#include "{real_shmem_dir}/shmem.h"\n\n')
    for n in rename_list:
        f.write(f"#undef {n}\n")
    f.write("#pragma clang diagnostic pop\n\n")

    f.write("// use asm aliasing to point real_shmem symbols back to library symbols\n")
    f.write("#define SYM_QUAL(n) SYM_QUAL_INNER(__USER_LABEL_PREFIX__, n)\n")
    f.write("#define SYM_QUAL_INNER(p, n) SYM_QUAL_FINAL(p, n)\n")
    f.write("#define SYM_QUAL_FINAL(p, n) #p #n\n\n")
    for n in rename_list:
        if n in macros or n in static_inlines:
            continue
        # for actual functions, we need the asm() trick to link correctly.
        f.write(f"extern __typeof__(real_{n}) real_{n} __asm__(SYM_QUAL({n}));\n")
    f.write("\n")
    
    for ret, name, decl, call in functions:
        real_name = get_real_name(name)
        if real_name:
            actual_call_name = f"real_{real_name}" if real_name in rename_list else real_name
            real_ret = get_real_ret(real_name)
            
            if ret != "void" and real_ret == "void":
                f.write(f"static inline {ret} p{name}{decl} {{ {actual_call_name}{call}; return 0; }}\n")
            else:
                f.write(f"static inline {ret} p{name}{decl} {{ {'return ' if ret != 'void' else ''}{actual_call_name}{call}; }}\n")
        else:
            if "_nbi" in name:
                blocking_name = name.replace("_nbi", "")
                real_blocking = get_real_name(blocking_name)
                if real_blocking:
                    actual_blocking = f"real_{real_blocking}" if real_blocking in rename_list else real_blocking
                    if "fetch" in name or "swap" in name:
                        m = re.match(r"\(([^,]+) \*([^,]+),", decl)
                        if m:
                            fetch_ptr_name = m.group(2)
                            call_no_fetch = re.sub(r"\([^,]+,\s*", "(", call)
                            f.write(f"static inline {ret} p{name}{decl} {{ *{fetch_ptr_name} = {actual_blocking}{call_no_fetch}; }}\n")
                            continue
                    else:
                        f.write(f"static inline {ret} p{name}{decl} {{ {actual_blocking}{call}; }}\n")
                        continue
            
            # default stub
            if ret == "void": f.write(f"static inline void p{name}{decl} {{ (void)0; }}\n")
            elif ret == "int": f.write(f"static inline int p{name}{decl} {{ return 0; }}\n")
            elif ret == "void *": f.write(f"static inline void *p{name}{decl} {{ return NULL; }}\n")
            else: f.write(f"static inline {ret} p{name}{decl} {{ {ret} zero = {{0}}; return zero; }}\n")
            
    f.write('\n#ifdef __cplusplus\n}\n#endif\n\n#endif\n')




