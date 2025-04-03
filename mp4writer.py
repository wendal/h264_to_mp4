import struct
import io

class MP4Writer:
    def __init__(self, output_file, width, height, fps=30, timescale=1000):
        """
        初始化MP4写入器
        :param output_file: 输出文件名或文件对象
        :param width: 视频宽度
        :param height: 视频高度
        :param fps: 帧率(默认30)
        :param timescale: 时间尺度(默认1000)
        """
        self.output = open(output_file, 'wb') if isinstance(output_file, str) else output_file
        self.width = width
        self.height = height
        self.fps = fps
        self.timescale = timescale
        self.frame_duration = self.timescale // self.fps
        self.sps = None
        self.pps = None
        self.frame_count = 0
        self.sample_sizes = []
        self.sample_offsets = []
        self.current_offset = 0
        self.nalu_buffer = []
        self.i_frame_ids = []
        
        # 写入ftyp box
        self._write_ftyp()
        
        # 预留moov box位置(最后写入)
        self.moov_position = self.current_offset
        self.current_offset += 16*1024 + 8  # 先预留moov空间+mdat头部
        self.output.write(b'\x00' * (16*1024 + 8))
        # print("当前位置估算", self.current_offset, "实际位置", self.output.tell())
    
    def _write_ftyp(self):
        """写入ftyp box"""
        ftyp_data = b'ftyp'
        ftyp_data += b'mp42'  # major brand
        ftyp_data += struct.pack('>I', 0)  # minor version
        ftyp_data += b'mp42isom'  # compatible brands
        
        self._write_box('ftyp', ftyp_data)
    
    def _write_box(self, box_type, box_data):
        """写入一个box"""
        box_size = 8 + len(box_data)
        self.output.write(struct.pack('>I', box_size))
        self.output.write(box_type.encode('ascii'))
        self.output.write(box_data)
        self.current_offset += box_size
    
    def add_nalu(self, nalu):
        """
        添加NALU单元
        :param nalu: NALU数据(包含起始码或NAL头)
        """
        # 检查NALU类型
        nalu_type = nalu[0] & 0x1F if len(nalu) > 0 else None
        
        # 处理SPS/PPS
        if nalu_type == 7:  # SPS
            self.sps = nalu
        elif nalu_type == 8:  # PPS
            self.pps = nalu
        elif nalu_type in [1, 5]:  # 帧数据
            self.nalu_buffer.append(nalu)
            
            # 如果是IDR帧，确保前面有SPS/PPS
            if nalu_type == 5 and (self.sps is None or self.pps is None):
                raise ValueError("IDR frame found but SPS/PPS not available")
            
            # 如果是IDR帧或缓冲区达到一定大小，写入帧
            # if nalu_type == 5 or len(self.nalu_buffer) >= 10:
            self._write_frame()
            if nalu_type == 5 :
                self.i_frame_ids.append(self.frame_count)
    
    def _write_frame(self):
        """将缓冲区的NALU写入为一个帧"""
        if not self.nalu_buffer:
            return
            
        # 记录样本信息
        self.sample_offsets.append(self.current_offset)
        print("写入帧偏移量", "%08X" % self.current_offset, "帧大小", len(self.nalu_buffer[0]))
        
        # 计算帧大小(包括起始码和NALU)
        frame_size = 0
        for nalu in self.nalu_buffer:
            # 使用4字节起始码
            frame_size += 4 + len(nalu)
        
        # 写入帧数据到mdat
        for nalu in self.nalu_buffer:
            self.output.write(struct.pack('>I', len(nalu)))  # 起始码
            self.output.write(nalu)
            self.current_offset += self.output.tell()
        
        self.sample_sizes.append(frame_size)
        self.frame_count += 1
        self.nalu_buffer = []
    
    def _write_moov(self):
        """写入moov box"""
        moov_data = self._write_mvhd()
        moov_data += self._write_trak()
        
        # 更新moov box大小并写入
        self.output.seek(self.moov_position)
        self._write_box('moov', moov_data)
    
    def _write_mvhd(self):
        """写入mvhd box(影片头)"""
        mvhd_data = struct.pack('>I', 0)  # version + flags
        mvhd_data += struct.pack('>I', 1743651892)  # creation time
        mvhd_data += struct.pack('>I', 1743651892)  # modification time
        mvhd_data += struct.pack('>I', self.timescale)  # timescale
        mvhd_data += struct.pack('>I', self.frame_count * self.frame_duration)  # duration
        mvhd_data += struct.pack('>I', 0x00010000)  # rate (1.0)
        mvhd_data += struct.pack('>H', 0x0100)  # volume (1.0)
        mvhd_data += struct.pack('>H', 0)  # reserved
        mvhd_data += struct.pack('>II', 0, 0)  # reserved
        mvhd_data += struct.pack('>iiiiiiiii',  # matrix
            0x10000, 0, 0, 0, 0x10000, 0, 0, 0, 0x10000)
        mvhd_data += struct.pack(">I", 0) #preview time
        mvhd_data += struct.pack(">I", 0) #preview duration
        mvhd_data += struct.pack(">I", 0) #Poster time
        mvhd_data += struct.pack(">I", 0) #Selection time
        mvhd_data += struct.pack(">I", 0) #Selection duration
        mvhd_data += struct.pack(">I", 0) #Current time

        mvhd_data += struct.pack('>I', 2)  # next track ID
        
        return self._create_box('mvhd', mvhd_data)
    
    def _write_trak(self):
        """写入trak box(轨道)"""
        trak_data = self._write_tkhd()
        trak_data += self._write_mdia()
        return self._create_box('trak', trak_data)
    
    def _write_tkhd(self):
        """写入tkhd box(轨道头)"""
        tkhd_data = struct.pack('>I', 0x00000007)  # version + flags (enabled, in movie)
        tkhd_data += struct.pack('>I', 0)  # creation time
        tkhd_data += struct.pack('>I', 0)  # modification time
        tkhd_data += struct.pack('>I', 1)  # track ID
        tkhd_data += struct.pack('>I', 0)  # reserved
        tkhd_data += struct.pack('>I', self.frame_count * self.frame_duration)  # duration
        tkhd_data += struct.pack('>II', 0, 0)  # reserved
        tkhd_data += struct.pack('>H', 0)  # layer
        tkhd_data += struct.pack('>H', 0)  # alternate group
        tkhd_data += struct.pack('>H', 0)  # volume
        tkhd_data += struct.pack('>H', 0)  # reserved
        tkhd_data += struct.pack('>iiiiiiiii',  # matrix
            0x00010000, 0, 0, 0, 0x00010000, 0, 0, 0, 0x40000000)
        tkhd_data += struct.pack('>II', self.width << 16, self.height << 16)  # width/height
        
        return self._create_box('tkhd', tkhd_data)
    
    def _write_mdia(self):
        """写入mdia box(媒体信息)"""
        mdia_data = self._write_mdhd()
        mdia_data += self._write_hdlr()
        mdia_data += self._write_minf()
        return self._create_box('mdia', mdia_data)
    
    def _write_mdhd(self):
        """写入mdhd box(媒体头)"""
        mdhd_data = struct.pack('>I', 0)  # version + flags
        mdhd_data += struct.pack('>I', 0)  # creation time
        mdhd_data += struct.pack('>I', 0)  # modification time
        mdhd_data += struct.pack('>I', self.timescale)  # timescale
        mdhd_data += struct.pack('>I', self.frame_count * self.frame_duration)  # duration
        mdhd_data += struct.pack('>H', 0x55c4)  # language (und)
        mdhd_data += struct.pack('>H', 0)  # quality
        
        return self._create_box('mdhd', mdhd_data)
    
    def _write_hdlr(self):
        """写入hdlr box(处理器参考)"""
        hdlr_data = struct.pack('>I', 0)  # version + flags
        hdlr_data += struct.pack('>I', 0)  # component type
        hdlr_data += b'vide'  # component subtype
        hdlr_data += struct.pack('>III', 0, 0, 0)  # component manufacturer/flags/mask
        hdlr_data += b'VideoHandler\x00'  # component name
        
        return self._create_box('hdlr', hdlr_data)
    
    def _write_minf(self):
        """写入minf box(媒体信息)"""
        minf_data = self._write_vmhd()
        minf_data += self._write_dinf()
        minf_data += self._write_stbl()
        return self._create_box('minf', minf_data)
    
    def _write_vmhd(self):
        """写入vmhd box(视频媒体头)"""
        vmhd_data = struct.pack('>I', 0x00000001)  # version + flags
        vmhd_data += struct.pack('>HHHH', 0, 0, 0, 0)  # graphics mode and opcolor
        
        return self._create_box('vmhd', vmhd_data)
    
    def _write_dinf(self):
        """写入dinf box(数据信息)"""
        # data reference entry
        dref_data = struct.pack('>I', 0)  # version + flags
        dref_data += struct.pack('>I', 1)  # entry count

        # dref_data += b'url '  # entry type
        # dref_data += struct.pack('>I', 0x00000001)  # entry flags (self-contained)
        url = struct.pack('>I', 1)  # version + flags
        url_data = self._create_box('url ', url)
        dref_data += url_data
        
        dinf_data = self._create_box('dref', dref_data)
        data = self._create_box('dinf', dinf_data)
        return data
    
    def _write_stbl(self):
        """写入stbl box(采样表)"""
        stbl_data = self._write_stsd()
        stbl_data += self._write_stts()
        stbl_data += self._write_stss()
        stbl_data += self._write_stsc()
        stbl_data += self._write_stsz()
        stbl_data += self._write_stco()
        return self._create_box('stbl', stbl_data)
    
    def _write_stsd(self):
        """写入stsd box(采样描述)"""
        # AVC1描述
        stsd_data = struct.pack('>I', 0)  # version + flags
        stsd_data += struct.pack('>I', 1)  # entry count
        
        # AVC1 entry
        avc1_entry = struct.pack('>I', 0)  # reserved
        avc1_entry += struct.pack('>H', 0)  # reserved
        avc1_entry += struct.pack('>H', 1)  # data reference index
        avc1_entry += struct.pack('>H', 0)  # pre-defined
        avc1_entry += struct.pack('>H', 0)  # reserved
        avc1_entry += struct.pack('>III', 0, 0, 0)  # pre-defined
        avc1_entry += struct.pack('>HH', self.width, self.height)  # width/height
        avc1_entry += struct.pack('>I', 0x00480000)  # horiz resolution (72 dpi)
        avc1_entry += struct.pack('>I', 0x00480000)  # vert resolution (72 dpi)
        avc1_entry += struct.pack('>I', 0)  # reserved
        avc1_entry += struct.pack('>H', 1)  # frame count
        avc1_entry += b'AVC Coding' + b'\x00' * 22  # compressor name (32 bytes)
        avc1_entry += struct.pack('>H', 0x0018)  # depth
        avc1_entry += struct.pack('>H', 0xffff)  # pre-defined

        # print("AVC1固定头部的长度", len(avc1_entry))
        # print("AVC1数据", avc1_entry.hex().upper())
        
        # AVC配置
        avcc_data = self._create_avcc()
        # print("avcc数据", avcc_data.hex().upper())
        avc1_entry += self._create_box('avcC', avcc_data)
        
        avc1_data = self._create_box('avc1', avc1_entry)
        stsd_data += avc1_data
        
        tmpdata = self._create_box('stsd', stsd_data)
        # print("stsd数据", tmpdata.hex().upper())
        return tmpdata
    
    def _create_avcc(self):
        """创建AVC配置记录"""
        if self.sps is None or self.pps is None:
            raise ValueError("SPS/PPS not available for AVCC configuration")
            
        avcc_data = struct.pack('B', 0x01)  # configuration version
        avcc_data += self.sps[1:4]  # profile, compatibility, level
        avcc_data += struct.pack('B', 0xff)  # NALU length size - 1
        
        # SPS
        avcc_data += struct.pack('B', 0x01)  # number of SPS
        avcc_data += struct.pack('>H', len(self.sps))  # SPS length
        avcc_data += self.sps
        
        # PPS
        avcc_data += struct.pack('B', 0x01)  # number of PPS
        avcc_data += struct.pack('>H', len(self.pps))  # PPS length
        avcc_data += self.pps
        
        return avcc_data
    
    def _write_stts(self):
        """写入stts box(解码时间到采样时间)"""
        stts_data = struct.pack('>I', 0)  # version + flags
        stts_data += struct.pack('>I', 1)  # entry count
        stts_data += struct.pack('>II', self.frame_count, self.frame_duration)  # sample count/duration
        
        return self._create_box('stts', stts_data)
    
    def _write_stss(self):
        stss_data = struct.pack('>I', 0)  # version + flags
        stss_data += struct.pack('>I', len(self.i_frame_ids))  # entry count
        for i in self.i_frame_ids:
            stss_data += struct.pack('>I', i)  # sample count/duration
        
        return self._create_box('stss', stss_data)
    
    def _write_stsc(self):
        """写入stsc box(采样到chunk的映射)"""
        stsc_data = struct.pack('>I', 0)  # version + flags
        stsc_data += struct.pack('>I', 1)  # entry count
        stsc_data += struct.pack('>III', 1, self.frame_count, 1)  # first chunk/samples per chunk/sample description index
        
        return self._create_box('stsc', stsc_data)
    
    def _write_stsz(self):
        """写入stsz box(采样大小)"""
        stsz_data = struct.pack('>I', 0)  # version + flags
        stsz_data += struct.pack('>I', 0)  # sample size (0 means variable)
        stsz_data += struct.pack('>I', len(self.sample_sizes))  # sample count
        
        for size in self.sample_sizes:
            stsz_data += struct.pack('>I', size)
        
        return self._create_box('stsz', stsz_data)
    
    def _write_stco(self):
        """写入stco box(chunk偏移)"""
        stco_data = struct.pack('>I', 0)  # version + flags
        # stco_data += struct.pack('>I', len(self.sample_offsets))  # entry count
        
        # for offset in self.sample_offsets:
            # stco_data += struct.pack('>I', offset)

        stco_data += struct.pack('>I', 1)
        stco_data += struct.pack('>I', self.sample_offsets[0])
        
        return self._create_box('stco', stco_data)
    
    def _create_box(self, box_type, box_data):
        """创建一个box"""
        return struct.pack('>I', 8 + len(box_data)) + box_type.encode('ascii') + box_data
    
    def finalize(self):
        """完成MP4文件写入"""
        # 写入剩余的帧
        if self.nalu_buffer:
            self._write_frame()
            
        # 确保有SPS/PPS
        if self.sps is None or self.pps is None:
            raise ValueError("SPS/PPS not available for MP4 creation")
            
        # 确保有帧数据
        if self.frame_count == 0:
            raise ValueError("No frame data available for MP4 creation")
        
        mdat_len = self.current_offset - self.moov_position - 16 * 1024 - 8
        file_len = self.current_offset

        # 写入moov box
        self.current_offset = self.moov_position
        self._write_moov()
        moov_len = self.current_offset - self.moov_position
        # moov_len = ((moov_len + 3) & ~3)  # 4字节对齐
        # print("moov的大小", moov_len)

        # 填充一个free
        self.output.seek(self.moov_position + moov_len)
        free_len = 16 * 1024 - moov_len
        # print("输出一个free box", "大小", free_len)
        self._write_box('free', b'\x00' * (free_len - 8))

        # 计算mdat box大小
        # print("mdat的大小是", mdat_len, "mdat头部写入的位置",  "%08X" % (self.moov_position + 16 * 1024,))
        self.output.seek(self.moov_position + 16 * 1024)
        self.output.write(struct.pack(">I", mdat_len + 8))
        self.output.write(b'mdat')
        
        # 关闭文件
        if isinstance(self.output, io.IOBase):
            self.output.close()

def nalu_to_mp4(input_nalus, output_file, width, height, fps=30):
    """
    将NALU列表转换为MP4文件
    :param input_nalus: NALU列表(每个NALU包含起始码或NAL头)
    :param output_file: 输出MP4文件名
    :param width: 视频宽度
    :param height: 视频高度
    :param fps: 帧率(默认30)
    """
    writer = MP4Writer(output_file, width, height, fps)
    
    for nalu in input_nalus:
        writer.add_nalu(nalu)
    
    writer.finalize()