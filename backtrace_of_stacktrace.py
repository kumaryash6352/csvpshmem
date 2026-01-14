#!/usr/bin/env python3
import csv
import glob
import os
import sys
import subprocess
import tempfile
import shutil

import platform

def symbolize_addresses(addresses, binary):
    if not binary or not os.path.exists(binary):
        return {addr: addr for addr in addresses}
    
    valid_addrs = [a for a in addresses if a.startswith('0x')]
    if not valid_addrs:
        return {addr: addr for addr in addresses}
    
    sym_map = {addr: addr for addr in addresses}
    system = platform.system()
    
    try:
        if system == "Darwin":
            # no addr2line on mac :(
            cmd = ["atos", "-o", binary] + valid_addrs
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            symbols = result.stdout.splitlines()
            for i, addr in enumerate(valid_addrs):
                if i < len(symbols):
                    sym_map[addr] = symbols[i]
        else:
            cmd = ["addr2line", "-e", binary, "-f", "-C"] + valid_addrs
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            lines = result.stdout.splitlines()
            # two lines per address: function name \n file:line
            for i, addr in enumerate(valid_addrs):
                if 2 * i + 1 < len(lines):
                    func = lines[2 * i]
                    loc = lines[2 * i + 1]
                    # morph output to match mac
                    sym_map[addr] = f"{func} ({loc})"
        return sym_map
    except Exception as e:
        print(f"symbolization failed for {binary} on {system}: {e}")
        return sym_map

def append_symboltrace_column(pattern="pperf.*.csv", binary="a.out"):
    files = glob.glob(pattern)
    if not files:
        print(f"no files matching {pattern} found")
        return

    unique_addresses = set()
    for f in files:
        with open(f, 'r') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                stacktrace = row.get('Stacktrace', '')
                if stacktrace:
                    for addr in stacktrace.split('|'):
                        addr = addr.strip()
                        if addr:
                            unique_addresses.add(addr)
    
    print(f"found {len(unique_addresses)} unique addresses. symbolizing with {binary}...")
    symbol_map = symbolize_addresses(unique_addresses, binary)

    for f in files:
        print(f"updating {f}...")
        temp_fd, temp_path = tempfile.mkstemp()
        try:
            with os.fdopen(temp_fd, 'w', newline='') as temp_file:
                with open(f, 'r') as csvfile:
                    reader = csv.DictReader(csvfile)
                    fieldnames = reader.fieldnames
                    if fieldnames is None:
                        continue
                    
                    if 'Symboltrace' not in fieldnames:
                        fieldnames = list(fieldnames) + ['Symboltrace']
                    
                    writer = csv.DictWriter(temp_file, fieldnames=fieldnames)
                    writer.writeheader()
                    
                    for row in reader:
                        stacktrace = row.get('Stacktrace', '')
                        if stacktrace:
                            symbols = []
                            for addr in stacktrace.split('|'):
                                addr = addr.strip()
                                if addr:
                                    symbols.append(symbol_map.get(addr, addr))
                            row['Symboltrace'] = '|'.join(symbols)
                        else:
                            row['Symboltrace'] = ''
                        writer.writerow(row)
            
            shutil.move(temp_path, f)
        except Exception as e:
            print(f"failed to update {f}: {e}")
            os.remove(temp_path)

if __name__ == "__main__":
    binary_to_use = sys.argv[1] if len(sys.argv) > 1 else "a.out"
    append_symboltrace_column(binary=binary_to_use)
    print("done")
