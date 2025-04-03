#!/usr/bin/python3
# -*- coding: UTF-8 -*-

import sys, os
import mp4writer
import h264_nalu_reader

def main():
    if len(sys.argv) < 3:
        print("Usage: %s <input_file> <output_file>" % sys.argv[0])
        return
    
    h264_path = sys.argv[1]
    dst_path = sys.argv[2]
    print("h264_path: %s" % h264_path)
    print("dst_path: %s" % dst_path)
    if os.path.exists(dst_path):
        os.remove(dst_path)
    
    nalu_list = h264_nalu_reader.read_nalu_from_file(h264_path)
    h264_nalu_reader.nalu_list_print(nalu_list)
    
    writer = mp4writer.MP4Writer(dst_path, 1280, 720, 16, 1000)
    for nalu in nalu_list:
        tmpbuff = bytes([nalu["header"]])
        tmpbuff += nalu["payload"]
        writer.add_nalu(tmpbuff)
    writer.finalize()
    
if __name__ == "__main__":
    main()