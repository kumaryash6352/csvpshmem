#!/usr/bin/env python3
import csv
import json
import glob
import os
import sys
import subprocess

def symbolize_addresses(addresses, binary):
    if not binary or not os.path.exists(binary):
        return {addr: addr for addr in addresses}
    
    valid_addrs = [a for a in addresses if a.startswith('0x')]
    if not valid_addrs:
        return {addr: addr for addr in addresses}
    
    try:
        cmd = ["atos", "-o", binary] + valid_addrs
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        symbols = result.stdout.splitlines()
        
        sym_map = {addr: addr for addr in addresses}
        for i, addr in enumerate(valid_addrs):
            if i < len(symbols):
                sym_map[addr] = symbols[i]
        return sym_map
    except Exception as e:
        print(f"symbols failed: {e}")
        return {addr: addr for addr in addresses}

def convert_csv_to_perfetto(pattern="pperf.*.csv", output_file="trace.json", binary=None):
    all_trace_events = []
    stack_frames = {}
    next_frame_id = 1
    
    frame_cache = {}
    
    files = glob.glob(pattern)
    if not files:
        print(f"no files matching {pattern} found.")
        return
    
    print(f"converting {len(files)} files...")
    
    unique_addrs = set()
    rows_data = []
    
    for filename in sorted(files):
        try:
            pe_id = int(filename.split('.')[-2])
        except:
            pe_id = 0
            
        with open(filename, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows_data.append((pe_id, row))
                bt = row.get('Stacktrace', '')
                if bt:
                    for addr in bt.split('|'):
                        addr = addr.strip()
                        if addr:
                            unique_addrs.add(addr)

    addr_map = symbolize_addresses(unique_addrs, binary)
    
    for pe_id, row in rows_data:
        try:
            start_sec = float(row['Time'])
            dur_sec = float(row['Duration_Sec'])
            func = row['Function']
            target_pe = int(row.get('Target_PE', -1))
            size = int(row.get('Size_Bytes', 0))
            symbol_trace = row.get('Symboltrace', '')
            if symbol_trace:
                bt = [s.strip() for s in symbol_trace.split('|') if s.strip()]
                resolved_names = bt
            else:
                bt_raw = row.get('Stacktrace', '').split('|')
                bt = [addr.strip() for addr in bt_raw if addr.strip()]
                resolved_names = [str(addr_map.get(addr, addr)) for addr in bt]
            
            current_parent = None
            # reverse because perfetto 
            for name in reversed(resolved_names):
                if any(x in name for x in ["_osh_log_call", "_osh_wrap_"]):
                    continue
                
                key = (name, current_parent)
                
                if key not in frame_cache:
                    frame_id = next_frame_id
                    next_frame_id += 1
                    frame_cache[key] = frame_id
                    stack_frames[str(frame_id)] = {"name": name}
                    if current_parent:
                        stack_frames[str(frame_id)]["parent"] = current_parent
                
                current_parent = frame_cache[key]
                
            ts_us = int(start_sec * 1_000_000)
            dur_us = int(dur_sec * 1_000_000)
            
            event = {
                "name": func,
                "cat": "PERF",
                "ph": "X",
                "ts": ts_us,
                "dur": dur_us,
                "pid": pe_id,
                "tid": 1,
                "args": {
                    "target_pe": target_pe,
                    "size_bytes": size,
                    **({"msg": f"To PE {target_pe}"} if target_pe != -1 else {})
                }
            }
            
            if current_parent:
                event["sf"] = current_parent
                
            all_trace_events.append(event)
        except Exception as e:
            print(e)
            continue
        
    for filename in sorted(files):
        try:
            pe_id = int(filename.split('.')[-2])
            all_trace_events.append({
                "name": "process_name", "ph": "M", "pid": pe_id,
                "args": {"name": f"PE {pe_id}"}
            })
        except:
            pass
        
    output_data = {
        "traceEvents": all_trace_events,
        "stackFrames": stack_frames
    }
    
    with open(output_file, 'w') as f:
        json.dump(output_data, f, indent=2)
    
    print(f"wrote {len(all_trace_events)} events to {output_file}")
    if binary:
        print(f"symbols from binary: {binary}")
    else:
        print("no binary provided, enjoy offsets!")

if __name__ == "__main__":
    bin_name = sys.argv[1] if len(sys.argv) > 1 else None
    convert_csv_to_perfetto(binary=bin_name)
