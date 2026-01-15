#!/usr/bin/env python3
import csv
import glob
import os
import sys
import subprocess
import tempfile
import shutil
import platform

def symbolize_addresses(addresses, binary, slide=None):
    if not binary or not os.path.exists(binary):
        return {addr: addr for addr in addresses}
    
    valid_addrs = [a for a in addresses if a.startswith('0x')]
    if not valid_addrs:
        return {addr: addr for addr in addresses}
    
    sym_map = {addr: addr for addr in addresses}
    system = platform.system()
    
    try:
        if system == "Darwin":
            cmd = ["atos", "-o", binary]
            if slide:
                cmd.extend(["-s", slide])
            else:
                print(f"warning: no slide found in csv, assuming slide = 0. symbols may be wildly incorrect")

            cmd += valid_addrs
            # print(f"running: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            symbols = result.stdout.splitlines()
            for i, addr in enumerate(valid_addrs):
                if i < len(symbols):
                    sym_map[addr] = symbols[i]
        else:
            effective_addrs = valid_addrs
            if slide:
                try:
                    is_pie = False
                    try:
                        res = subprocess.run(["readelf", "-h", binary], capture_output=True, text=True)
                        if "Type:" in res.stdout and "DYN" in res.stdout:
                            is_pie = True
                    except Exception:
                        pass

                    slide_val = int(slide, 16)
                    if is_pie and slide_val != 0:
                        effective_addrs = [hex(int(a, 16) - slide_val) for a in valid_addrs]
                except ValueError:
                    print(f"Warning: invalid slide value {slide}")
            
            cmd = ["addr2line", "-e", binary, "-f", "-C"] + effective_addrs
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            lines = result.stdout.splitlines()
            # two lines per address: function name \n file:line
            for i, addr in enumerate(valid_addrs):
                if 2 * i + 1 < len(lines):
                    func = lines[2 * i]
                    loc = lines[2 * i + 1]
                    # morph output to match mac
                    sym_map[addr] = f"{func} ({loc})"
        print(f"registered {len(sym_map)} symbols")    
        return sym_map
    except Exception as e:
        print(f"symbolization failed for {binary} on {system}: {e}")
        return sym_map

def append_symboltrace_column(pattern="pperf.*.csv", binary="a.out"):
    files = glob.glob(pattern)
    if not files:
        print(f"no files matching {pattern} found")
        return

    slide_groups = {}
    
    # identify slides and collect addresses per file
    for f in files:
        slide = None
        current_addrs = set()
        file_rows = []
        
        try:
            with open(f, 'r') as csvfile:
                reader = csv.DictReader(csvfile)
                file_rows = list(reader)
                
                for row in file_rows:
                    if row.get('Function') == 'shmem_init':
                        extra = row.get('Extra', '')
                        if 'slide=' in extra:
                            parts = extra.split(';')
                            for p in parts:
                                if p.strip().startswith('slide='):
                                    slide = p.strip().split('=')[1]
                                    break
                    if slide:
                        break
                
                for row in file_rows:
                    stacktrace = row.get('Stacktrace', '')
                    if stacktrace:
                        for addr in stacktrace.split('|'):
                            addr = addr.strip()
                            if addr:
                                current_addrs.add(addr)
                                
            if slide not in slide_groups:
                slide_groups[slide] = {'addresses': set(), 'files': []}
            slide_groups[slide]['addresses'].update(current_addrs)
            slide_groups[slide]['files'].append(f)
            
        except Exception as e:
            print(f"Error reading {f}: {e}")
            continue

    for slide, group in slide_groups.items():
        print(f"Processing group with slide={slide} ({len(group['files'])} files)")
        
        symbol_map = symbolize_addresses(group['addresses'], binary, slide=slide)
        
        for f in group['files']:
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
                            symbols = []
                            if stacktrace:
                                for addr in stacktrace.split('|'):
                                    addr = addr.strip()
                                    if addr:
                                        symbols.append(symbol_map.get(addr, addr))
                            
                            row['Symboltrace'] = '|'.join(symbols)
                            writer.writerow(row)
                
                shutil.move(temp_path, f)
            except Exception as e:
                print(f"failed to update {f}: {e}")
                if os.path.exists(temp_path):
                    os.remove(temp_path)

if __name__ == "__main__":
    binary_to_use = sys.argv[1] if len(sys.argv) > 1 else "a.out"
    append_symboltrace_column(binary=binary_to_use)
    print("done")
