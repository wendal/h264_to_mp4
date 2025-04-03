#!/usr/bin/python3
# -*- coding: UTF-8 -*-

import sys

def nalu_type_name(tp):
    if tp == 7 :
        return "SPS"
    if tp == 8 :
        return "PPS"
    if tp == 5:
        return "IDR"
    if tp == 6 :
        return "SEI"
    if tp == 1 :
        return "Non-IDR"
    return "?" + str(tp)

def find_nalu_start(buffer, start_pos=0):
    """
    在缓冲区中查找NALU起始码(0x000001或0x00000001)
    返回起始码的起始位置和长度(3或4字节)
    """
    pos = start_pos
    while pos < len(buffer) - 3:
        # 检查3字节起始码(0x000001)
        if buffer[pos] == 0 and buffer[pos+1] == 0 and buffer[pos+2] == 1:
            return pos, 3
        
        # 检查4字节起始码(0x00000001)
        if pos < len(buffer) - 4:
            if buffer[pos] == 0 and buffer[pos+1] == 0 and buffer[pos+2] == 0 and buffer[pos+3] == 1:
                return pos, 4
        
        pos += 1
    
    return -1, 0

def parse_nalu(buffer, start_pos, start_code_len):
    """
    解析NALU单元
    返回NALU头信息和负载数据
    """
    if start_pos + start_code_len >= len(buffer):
        return None, None, buffer
    
    # 读取NALU头(第一个字节)
    nalu_header = buffer[start_pos + start_code_len]
    
    # 提取NALU类型(低5位)
    nalu_type = nalu_header & 0x1F
    
    # NALU负载从起始码后开始
    payload_start = start_pos + start_code_len + 1
    
    # 查找下一个起始码以确定当前NALU的结束位置
    next_start_pos, _ = find_nalu_start(buffer, payload_start)
    
    if next_start_pos == -1:
        # 没有找到下一个起始码，使用剩余所有数据
        nalu_payload = buffer[payload_start:]
        remaining_buffer = bytearray()
    else:
        # 提取当前NALU的负载
        nalu_payload = buffer[payload_start:next_start_pos]
        remaining_buffer = buffer[next_start_pos:]
    
    return nalu_type, nalu_payload, remaining_buffer

def read_nalu_from_file(file_path):
    """
    从H.264文件中读取NALU单元
    """
    with open(file_path, 'rb') as f:
        buffer = bytearray(f.read())
    
    nalu_list = []
    current_pos = 0
    
    while True:
        # 查找下一个NALU起始码
        start_pos, start_code_len = find_nalu_start(buffer, current_pos)
        if start_pos == -1:
            break
        
        # 解析NALU
        nalu_type, nalu_payload, remaining_buffer = parse_nalu(buffer, start_pos, start_code_len)
        
        if nalu_type is not None:
            nalu_list.append({
                'type': nalu_type,
                'payload': nalu_payload,
                'start_code_len': start_code_len
            })
        
        # 更新缓冲区为剩余部分
        buffer = remaining_buffer
        current_pos = 0
    
    return nalu_list

def nalu_list_print(nalu_list):
    # 打印NALU信息
    print(f"Found {len(nalu_list)} NALUs:")
    for i, nalu in enumerate(nalu_list):
        if nalu['type'] == 6 :
            # size_sei += len(nalu['payload'])
            continue
        print(f"NALU {i+1}: Type={nalu_type_name(nalu['type'])}, Payload size={len(nalu['payload'])} bytes")
    # 统计每种帧的大小
    nalu_sizes = {}
    nalu_counter = {}
    for i, nalu in enumerate(nalu_list):
        if not str(nalu['type']) in nalu_sizes :
            nalu_sizes[str(nalu['type'])] = 0
            nalu_counter[str(nalu['type'])] = 0
        nalu_sizes[str(nalu['type'])] += len(nalu['payload'])
        nalu_counter[str(nalu['type'])] += 1
    for k in nalu_sizes:
        nalu_size = nalu_sizes[k]
        print("NALU %16s count %4d size %16d" % (nalu_type_name(int(k)), nalu_counter[k], nalu_size))

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python h264_nalu_reader.py <h264_file>")
        sys.exit(1)
    
    file_path = sys.argv[1]
    nalu_list = read_nalu_from_file(file_path)

    nalu_list_print(nalu_list)

