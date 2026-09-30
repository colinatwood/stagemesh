#include "stagemesh/uwb_hardware_bridge.hpp"

#include <algorithm>
#include <cerrno>
#include <cmath>
#include <cstring>

#if defined(__unix__) || defined(__APPLE__)
#include <fcntl.h>
#include <termios.h>
#include <unistd.h>
#endif

namespace stagemesh {
namespace {

constexpr std::array<std::uint8_t,4> magic{'S','F','U','W'};
constexpr std::uint8_t wire_version=1;
constexpr std::uint8_t observation_type=1;

void put_u16(std::uint8_t* p,std::uint16_t value) noexcept {p[0]=static_cast<std::uint8_t>(value);p[1]=static_cast<std::uint8_t>(value>>8U);}
void put_u32(std::uint8_t* p,std::uint32_t value) noexcept {for(unsigned int i=0;i<4;++i)p[i]=static_cast<std::uint8_t>(value>>(i*8U));}
void put_u64(std::uint8_t* p,std::uint64_t value) noexcept {for(unsigned int i=0;i<8;++i)p[i]=static_cast<std::uint8_t>(value>>(i*8U));}
std::uint16_t get_u16(const std::uint8_t* p) noexcept {return static_cast<std::uint16_t>(p[0])|static_cast<std::uint16_t>(p[1])<<8U;}
std::uint32_t get_u32(const std::uint8_t* p) noexcept {std::uint32_t v=0;for(unsigned int i=0;i<4;++i)v|=static_cast<std::uint32_t>(p[i])<<(i*8U);return v;}
std::uint64_t get_u64(const std::uint8_t* p) noexcept {std::uint64_t v=0;for(unsigned int i=0;i<8;++i)v|=static_cast<std::uint64_t>(p[i])<<(i*8U);return v;}
void put_double(std::uint8_t* p,double value) noexcept {std::uint64_t bits=0;std::memcpy(&bits,&value,sizeof(bits));put_u64(p,bits);}
double get_double(const std::uint8_t* p) noexcept {const auto bits=get_u64(p);double value=0.0;std::memcpy(&value,&bits,sizeof(value));return value;}

#if defined(__unix__) || defined(__APPLE__)
bool baud_constant(std::uint32_t baud,speed_t& out) noexcept {
    switch(baud){
        case 115200:out=B115200;return true;
#ifdef B230400
        case 230400:out=B230400;return true;
#endif
#ifdef B460800
        case 460800:out=B460800;return true;
#endif
#ifdef B921600
        case 921600:out=B921600;return true;
#endif
#ifdef B1000000
        case 1000000:out=B1000000;return true;
#endif
#ifdef B2000000
        case 2000000:out=B2000000;return true;
#endif
        default:return false;
    }
}
#endif

} // namespace

std::uint32_t hardware_crc32(const std::uint8_t* data,std::size_t size) noexcept {
    if(!data&&size>0)return 0;
    std::uint32_t crc=0xffffffffU;
    for(std::size_t i=0;i<size;++i){crc^=data[i];for(unsigned int bit=0;bit<8;++bit)crc=(crc>>1U)^(0xedb88320U&static_cast<std::uint32_t>(-static_cast<std::int32_t>(crc&1U)));}
    return ~crc;
}

bool encode_uwb_hardware_frame(const UwbHardwareObservation& o,std::array<std::uint8_t,uwb_hardware_frame_size>& frame) noexcept {
    if(o.node_id==0||o.sequence==0||o.authority_epoch==0||o.hub_time_ns==0||o.node_time_ns==0||
       !std::isfinite(o.distance_mm)||o.distance_mm<0.0||!std::isfinite(o.range_uncertainty_mm)||o.range_uncertainty_mm<0.0)return false;
    frame.fill(0);std::copy(magic.begin(),magic.end(),frame.begin());frame[4]=wire_version;frame[5]=observation_type;put_u16(frame.data()+6,uwb_hardware_frame_size);
    put_u64(frame.data()+8,o.node_id);put_u64(frame.data()+16,o.sequence);put_u64(frame.data()+24,o.authority_epoch);
    put_u64(frame.data()+32,o.hub_time_ns);put_u64(frame.data()+40,o.node_time_ns);put_double(frame.data()+48,o.distance_mm);
    put_double(frame.data()+56,o.range_uncertainty_mm);put_u64(frame.data()+64,o.clock_uncertainty_ns);frame[72]=o.authenticated?1U:0U;
    put_u32(frame.data()+76,hardware_crc32(frame.data(),76));return true;
}

bool decode_uwb_hardware_frame(const std::uint8_t* frame,std::size_t size,UwbHardwareObservation& o) noexcept {
    if(!frame||size!=uwb_hardware_frame_size||!std::equal(magic.begin(),magic.end(),frame)||frame[4]!=wire_version||
       frame[5]!=observation_type||get_u16(frame+6)!=uwb_hardware_frame_size||get_u32(frame+76)!=hardware_crc32(frame,76))return false;
    UwbHardwareObservation parsed{};parsed.node_id=get_u64(frame+8);parsed.sequence=get_u64(frame+16);parsed.authority_epoch=get_u64(frame+24);
    parsed.hub_time_ns=get_u64(frame+32);parsed.node_time_ns=get_u64(frame+40);parsed.distance_mm=get_double(frame+48);
    parsed.range_uncertainty_mm=get_double(frame+56);parsed.clock_uncertainty_ns=get_u64(frame+64);parsed.authenticated=(frame[72]&1U)!=0;
    if(parsed.node_id==0||parsed.sequence==0||parsed.authority_epoch==0||parsed.hub_time_ns==0||parsed.node_time_ns==0||
       !std::isfinite(parsed.distance_mm)||parsed.distance_mm<0.0||!std::isfinite(parsed.range_uncertainty_mm)||parsed.range_uncertainty_mm<0.0)return false;
    o=parsed;return true;
}

UwbHardwareBridge::~UwbHardwareBridge(){close();}

bool UwbHardwareBridge::open_device(const char* path,std::uint32_t baud) noexcept {
    close();
#if defined(__unix__) || defined(__APPLE__)
    speed_t speed{};if(!path||!*path||!baud_constant(baud,speed)){status_.last_errno=EINVAL;return false;}
    const int fd=::open(path,O_RDWR|O_NOCTTY|O_NONBLOCK|O_CLOEXEC);if(fd<0){status_.last_errno=errno;return false;}
    termios settings{};if(tcgetattr(fd,&settings)!=0){const int e=errno;::close(fd);status_.last_errno=e;return false;}
    cfmakeraw(&settings);if(cfsetispeed(&settings,speed)!=0||cfsetospeed(&settings,speed)!=0||tcsetattr(fd,TCSANOW,&settings)!=0){const int e=errno;::close(fd);status_.last_errno=e;return false;}
    fd_=fd;status_.open=true;status_.faulted=false;status_.last_errno=0;return true;
#else
    (void)path;(void)baud;status_.last_errno=ENOTSUP;return false;
#endif
}

bool UwbHardwareBridge::adopt_fd_for_test(int fd) noexcept {close();if(fd<0){status_.last_errno=EINVAL;return false;}fd_=fd;status_.open=true;status_.faulted=false;status_.last_errno=0;return true;}

void UwbHardwareBridge::close() noexcept {
#if defined(__unix__) || defined(__APPLE__)
    if(fd_>=0)::close(fd_);
#endif
    fd_=-1;used_=0;status_.open=false;
}

void UwbHardwareBridge::discard_prefix(std::size_t count) noexcept {
    count=std::min(count,used_);if(count<used_)std::memmove(buffer_.data(),buffer_.data()+count,used_-count);used_-=count;
}

void UwbHardwareBridge::fault(int error_number) noexcept {status_.faulted=true;status_.last_errno=error_number;++status_.io_errors;close();status_.faulted=true;}

bool UwbHardwareBridge::parse_buffer(UwbHardwareObservation& observation) noexcept {
    while(used_>=4){
        if(!std::equal(magic.begin(),magic.end(),buffer_.begin())){discard_prefix(1);++status_.resync_bytes;continue;}
        if(used_<uwb_hardware_frame_size)return false;
        if(decode_uwb_hardware_frame(buffer_.data(),uwb_hardware_frame_size,observation)){discard_prefix(uwb_hardware_frame_size);++status_.valid_frames;return true;}
        discard_prefix(1);++status_.invalid_frames;++status_.resync_bytes;
    }
    return false;
}

bool UwbHardwareBridge::try_read(UwbHardwareObservation& observation) noexcept {
    if(parse_buffer(observation))return true;
    if(fd_<0)return false;
#if defined(__unix__) || defined(__APPLE__)
    while(used_<buffer_.size()){
        const auto count=::read(fd_,buffer_.data()+used_,buffer_.size()-used_);
        if(count>0){used_+=static_cast<std::size_t>(count);status_.bytes_read+=static_cast<std::uint64_t>(count);continue;}
        if(count==0){fault(ENODATA);break;}
        if(errno==EINTR)continue;
        if(errno==EAGAIN||errno==EWOULDBLOCK)break;
        fault(errno);break;
    }
#endif
    return parse_buffer(observation);
}

} // namespace stagemesh
