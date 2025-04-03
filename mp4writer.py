import struct
import io
from collections import defaultdict

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
        self.sample_times = []
        self.current_offset = 0
        self.nalu_buffer = []
        
        # 写入ftyp box
        self._write_ftyp()
        
        # 预留moov box位置(最后写入)
        self.moov_position = self.current_offset
        self.current_offset += 8  # 先预留moov头部空间
        
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
            if nalu_type == 5 or len(self.nalu_buffer) >= 10:
                self._write_frame()
    
    def _write_frame(self):
        """将缓冲区的NALU写入为一个帧"""
        if not self.nalu_buffer:
            return
            
        # 记录样本信息
        self.sample_times.append(self.frame_count * self.frame_duration)
        self.sample_offsets.append(self.current_offset)
        
        # 计算帧大小(包括起始码和NALU)
        frame_size = 0
        for nalu in self.nalu_buffer:
            # 使用4字节起始码
            frame_size += 4 + len(nalu)
        
        # 写入帧数据到mdat
        for nalu in self.nalu_buffer:
            self.output.write(struct.pack('>I', 1))  # 起始码
            self.output.write(nalu)
            self.current_offset += 4 + len(nalu)
        
        self.sample_sizes.append(frame_size)
        self.frame_count += 1
        self.nalu_buffer = []
    
    def _write_moov(self):
        """写入moov box"""
        moov_data = self._write_mvhd()
        moov_data += self._write_trak()
        moov_data += self._write_mvex()
        
        # 更新moov box大小并写入
        self.output.seek(self.moov_position)
        self._write_box('moov', moov_data)
    
    def _write_mvhd(self):
        """写入mvhd box(影片头)"""
        mvhd_data = struct.pack('>I', 0)  # version + flags
        mvhd_data += struct.pack('>I', 0)  # creation time
        mvhd_data += struct.pack('>I', 0)  # modification time
        mvhd_data += struct.pack('>I', self.timescale)  # timescale
        mvhd_data += struct.pack('>I', self.frame_count * self.frame_duration)  # duration
        mvhd_data += struct.pack('>I', 0x00010000)  # rate (1.0)
        mvhd_data += struct.pack('>H', 0x0100)  # volume (1.0)
        mvhd_data += struct.pack('>H', 0)  # reserved
        mvhd_data += struct.pack('>II', 0, 0)  # reserved
        mvhd_data += struct.pack('>iiiiiiiii',  # matrix
            0x00010000, 0, 0, 0, 0x00010000, 0, 0, 0, 0x40000000)
        mvhd_data += struct.pack('>I', 0)  # preview time
        mvhd_data += struct.pack('>I', 0)  # preview duration
        mvhd_data += struct.pack('>I', 0)  # poster time
        mvhd_data += struct.pack('>I', 0)  # selection time
        mvhd_data += struct.pack('>I', 0)  # selection duration
        mvhd_data += struct.pack('>I', 0)  # current time
        mvhd_data += struct.pack('>I', 1)  # next track ID
        
        return self._create_box('mvhd', mvhd_data)
    
    def _write_trak(self):
        """写入trak box(轨道)"""
        trak_data = self._write_tkhd()
        trak_data += self._write_mdia()
        return self._create_box('trak', trak_data)
    
    def _write_tkhd(self):
        """写入tkhd box(轨道头)"""
        tkhd_data = struct.pack('>I', 0x0000000f)  # version + flags (enabled, in movie, in preview)
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
        tkhd_data += struct.pack('>II', self.width << 16, self.height << 16)  # width/height (fixed-point)
        
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
        dref_data = struct.pack('>I', 0)  # version + flags
        dref_data += struct.pack('>I', 1)  # entry count
        
        # data reference entry
        dref_data += struct.pack('>I', 12)  # entry size
        dref_data += struct.pack('>I', 0)  # entry flags
        dref_data += b'url '  # entry type
        dref_data += struct.pack('>I', 0x00000001)  # entry flags (self-contained)
        
        dinf_data = self._create_box('dref', dref_data)
        return self._create_box('dinf', dinf_data)
    
    def _write_stbl(self):
        """写入stbl box(采样表)"""
        stbl_data = self._write_stsd()
        stbl_data += self._write_stts()
        stbl_data += self._write_stsc()
        stbl_data += self._write_stsz()
        stbl_data += self._write_stco()
        return self._create_box('stbl', stbl_data)
    
    def _write_stsd(self):
        """写入stsd box(采样描述)"""
        # AVC1描述
        avc1_data = struct.pack('>H', 1)  # entry count
        
        # AVC1 entry
        avc1_entry = struct.pack('>I', 0)  # reserved
        avc1_entry += struct.pack('>H', 0)  # reserved
        avc1_entry += struct.pack('>H', 1)  # data reference index
        avc1_entry += struct.pack('>H', 0)  # pre-defined
        avc1_entry += struct.pack('>H', 0)  # reserved
        avc1_entry += struct.pack('>IIII', 0, 0, 0, 0)  # pre-defined
        avc1_entry += struct.pack('>HH', self.width, self.height)  # width/height
        avc1_entry += struct.pack('>I', 0x00480000)  # horiz resolution (72 dpi)
        avc1_entry += struct.pack('>I', 0x00480000)  # vert resolution (72 dpi)
        avc1_entry += struct.pack('>I', 0)  # reserved
        avc1_entry += struct.pack('>H', 1)  # frame count
        avc1_entry += b'AVC Coding' + b'\x00' * 22  # compressor name (32 bytes)
        avc1_entry += struct.pack('>H', 0x0018)  # depth
        avc1_entry += struct.pack('>H', 0xffff)  # pre-defined
        
        # AVC配置
        avcc_data = self._create_avcc()
        avc1_entry += self._create_box('avcC', avcc_data)
        
        avc1_data += self._create_box('avc1', avc1_entry)
        
        return self._create_box('stsd', avc1_data)
    
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
    
    def _write_stsc(self):
        """写入stsc box(采样到chunk的映射)"""
        stsc_data = struct.pack('>I', 0)  # version + flags
        stsc_data += struct.pack('>I', 1)  # entry count
        stsc_data += struct.pack('>III', 1, 1, 1)  # first chunk/samples per chunk/sample description index
        
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
        stco_data += struct.pack('>I', len(self.sample_offsets))  # entry count
        
        for offset in self.sample_offsets:
            stco_data += struct.pack('>I', offset)
        
        return self._create_box('stco', stco_data)
    
    def _write_mvex(self):
        """写入mvex box(电影扩展)"""
        mvex_data = self._write_mehd()
        mvex_data += self._write_trex()
        return self._create_box('mvex', mvex_data)
    
    def _write_mehd(self):
        """写入mehd box(电影扩展头)"""
        mehd_data = struct.pack('>I', 0)  # version + flags
        mehd_data += struct.pack('>I', self.frame_count * self.frame_duration)  # fragment duration
        
        return self._create_box('mehd', mehd_data)
    
    def _write_trex(self):
        """写入trex box(轨道扩展)"""
        trex_data = struct.pack('>I', 0)  # version + flags
        trex_data += struct.pack('>I', 1)  # track ID
        trex_data += struct.pack('>I', 1)  # default sample description index
        trex_data += struct.pack('>I', 0)  # default sample duration
        trex_data += struct.pack('>I', 0)  # default sample size
        trex_data += struct.pack('>I', 0)  # default sample flags
        
        return self._create_box('trex', trex_data)
    
    def _create_box(self, box_type, box_data):
        """创建一个box"""
        print('创建盒子', box_type.encode('ascii'), len(box_data) + 8)
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
        
        # 写入moov box
        self._write_moov()
        
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

# 示例用法
if __name__ == "__main__":
    # 示例: 从文件中读取NALU并写入MP4
    # 实际使用时需要替换为真实的NALU数据
    example_nalus = [
        # SPS
        b'\x67\x42\x00\x1e\xa6\x02\x80\xbc\x08\x88\x00\x00\x03\x00\x02\x00\x00\x03\x00\x79\x08',
        # PPS
        b'\x68\xee\x3c\x80',
        # IDR帧
        b'\x65\x88\x84\x21\xa0\x0f\x08\x84\x42\x10\x80\x42\x10\x84\x20\x10',
        # 其他帧...
    ]
    
    # 转换为MP4 (假设视频分辨率为640x480，帧率30fps)
    nalu_to_mp4(example_nalus, 'output.mp4', 640, 480, 30)