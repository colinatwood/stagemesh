#include "stagemesh/le_iso_hardware.hpp"

#include "stagemesh/uwb_hardware_bridge.hpp"

#include <algorithm>
#include <cerrno>
#include <cstring>

#if defined(__linux__)
#include <ctime>
#include <sys/socket.h>
#include <unistd.h>
#endif

namespace stagemesh {
namespace {

constexpr std::array<std::uint8_t,4> timing_magic{'S','F','L','E'};
constexpr std::uint8_t timing_version=1;
constexpr std::uint8_t timing_type=1;

void put_u16(std::uint8_t* p,std::uint16_t value) noexcept {p[0]=static_cast<std::uint8_t>(value);p[1]=static_cast<std::uint8_t>(value>>8U);}
void put_u32(std::uint8_t* p,std::uint32_t value) noexcept {for(unsigned int i=0;i<4;++i)p[i]=static_cast<std::uint8_t>(value>>(i*8U));}
void put_u64(std::uint8_t* p,std::uint64_t value) noexcept {for(unsigned int i=0;i<8;++i)p[i]=static_cast<std::uint8_t>(value>>(i*8U));}
std::uint16_t get_u16(const std::uint8_t* p) noexcept {return static_cast<std::uint16_t>(p[0])|static_cast<std::uint16_t>(p[1])<<8U;}
std::uint32_t get_u32(const std::uint8_t* p) noexcept {std::uint32_t v=0;for(unsigned int i=0;i<4;++i)v|=static_cast<std::uint32_t>(p[i])<<(i*8U);return v;}
std::uint64_t get_u64(const std::uint8_t* p) noexcept {std::uint64_t v=0;for(unsigned int i=0;i<8;++i)v|=static_cast<std::uint64_t>(p[i])<<(i*8U);return v;}

#if defined(__linux__)
constexpr int bluetooth_protocol_iso=8;
constexpr std::uint8_t le_public_address=0x01;
constexpr std::uint8_t le_random_address=0x02;
struct BluetoothAddress {std::uint8_t bytes[6];};
struct BluetoothIsoAddress {
    sa_family_t family;
    BluetoothAddress address;
    std::uint8_t address_type;
    struct {BluetoothAddress address;std::uint8_t address_type;std::uint8_t sid;} broadcast;
};

int hex_value(char ch) noexcept {
    if(ch>='0'&&ch<='9')return ch-'0';
    if(ch>='a'&&ch<='f')return ch-'a'+10;
    if(ch>='A'&&ch<='F')return ch-'A'+10;
    return -1;
}
bool parse_address(const char* text,BluetoothAddress& address) noexcept {
    if(!text||std::strlen(text)!=17)return false;
    for(std::size_t i=0;i<6;++i){const std::size_t at=i*3;const int high=hex_value(text[at]),low=hex_value(text[at+1]);
        if(high<0||low<0||(i<5&&text[at+2]!=':'))return false;
        address.bytes[5-i]=static_cast<std::uint8_t>((high<<4)|low);
    }
    return true;
}
std::uint64_t monotonic_now_ns() noexcept {
    timespec now{};if(clock_gettime(CLOCK_MONOTONIC,&now)!=0)return 0;
    return static_cast<std::uint64_t>(now.tv_sec)*1'000'000'000ULL+static_cast<std::uint64_t>(now.tv_nsec);
}
#endif

} // namespace

bool encode_le_iso_timing_frame(const LeIsoTimingObservation& o,std::array<std::uint8_t,le_iso_timing_frame_size>& frame) noexcept {
    if(o.node_id==0||o.sequence==0||o.authority_epoch==0||o.event_counter==0||o.node_transmit_ns==0)return false;
    frame.fill(0);std::copy(timing_magic.begin(),timing_magic.end(),frame.begin());frame[4]=timing_version;frame[5]=timing_type;put_u16(frame.data()+6,le_iso_timing_frame_size);
    put_u64(frame.data()+8,o.node_id);put_u64(frame.data()+16,o.sequence);put_u64(frame.data()+24,o.authority_epoch);
    put_u64(frame.data()+32,o.event_counter);put_u64(frame.data()+40,o.node_transmit_ns);frame[48]=o.authenticated?1U:0U;
    put_u32(frame.data()+52,hardware_crc32(frame.data(),52));return true;
}

bool decode_le_iso_timing_frame(const std::uint8_t* frame,std::size_t size,LeIsoTimingObservation& o) noexcept {
    if(!frame||size!=le_iso_timing_frame_size||!std::equal(timing_magic.begin(),timing_magic.end(),frame)||frame[4]!=timing_version||
       frame[5]!=timing_type||get_u16(frame+6)!=le_iso_timing_frame_size||get_u32(frame+52)!=hardware_crc32(frame,52))return false;
    LeIsoTimingObservation parsed{};parsed.node_id=get_u64(frame+8);parsed.sequence=get_u64(frame+16);parsed.authority_epoch=get_u64(frame+24);
    parsed.event_counter=get_u64(frame+32);parsed.node_transmit_ns=get_u64(frame+40);parsed.authenticated=(frame[48]&1U)!=0;
    if(parsed.node_id==0||parsed.sequence==0||parsed.authority_epoch==0||parsed.event_counter==0||parsed.node_transmit_ns==0)return false;
    o=parsed;return true;
}

LeIsoHardwareSocket::LeIsoHardwareSocket() noexcept = default;

bool LeIsoHardwareSocket::probe_kernel_support() noexcept {
#if defined(__linux__)
    const int probe=::socket(AF_BLUETOOTH,SOCK_SEQPACKET|SOCK_NONBLOCK|SOCK_CLOEXEC,bluetooth_protocol_iso);
    if(probe>=0){::close(probe);return true;}
    return errno!=EAFNOSUPPORT&&errno!=EPROTONOSUPPORT;
#else
    return false;
#endif
}
LeIsoHardwareSocket::~LeIsoHardwareSocket(){close();}

bool LeIsoHardwareSocket::open_unicast(const char* local_address,const char* remote_address,bool random_address) noexcept {
    close();
#if defined(__linux__)
    BluetoothAddress local{},remote{};if(!parse_address(local_address,local)||!parse_address(remote_address,remote)){status_.last_errno=EINVAL;return false;}
    const int fd=::socket(AF_BLUETOOTH,SOCK_SEQPACKET|SOCK_NONBLOCK|SOCK_CLOEXEC,bluetooth_protocol_iso);
    if(fd<0){status_.last_errno=errno;status_.kernel_iso_supported=errno!=EAFNOSUPPORT&&errno!=EPROTONOSUPPORT;return false;}
    status_.kernel_iso_supported=true;BluetoothIsoAddress local_socket{};local_socket.family=AF_BLUETOOTH;local_socket.address=local;
    local_socket.address_type=random_address?le_random_address:le_public_address;
    if(::bind(fd,reinterpret_cast<const sockaddr*>(&local_socket),sizeof(local_socket))!=0){const int e=errno;::close(fd);status_.last_errno=e;return false;}
    BluetoothIsoAddress remote_socket{};remote_socket.family=AF_BLUETOOTH;remote_socket.address=remote;
    remote_socket.address_type=random_address?le_random_address:le_public_address;
    const int connected=::connect(fd,reinterpret_cast<const sockaddr*>(&remote_socket),sizeof(remote_socket));
    if(connected!=0&&errno!=EINPROGRESS&&errno!=EAGAIN){const int e=errno;::close(fd);status_.last_errno=e;return false;}
    fd_=fd;status_.open=true;status_.connected=connected==0;status_.connecting=connected!=0;status_.last_errno=0;return true;
#else
    (void)local_address;(void)remote_address;(void)random_address;status_.last_errno=ENOTSUP;return false;
#endif
}

bool LeIsoHardwareSocket::adopt_fd_for_test(int fd) noexcept {close();if(fd<0){status_.last_errno=EINVAL;return false;}fd_=fd;status_.kernel_iso_supported=true;status_.open=true;status_.connected=true;status_.last_errno=0;return true;}

bool LeIsoHardwareSocket::refresh_connection() noexcept {
    if(fd_<0)return false;
    if(status_.connected)return true;
#if defined(__linux__)
    int socket_error=0;socklen_t size=sizeof(socket_error);if(getsockopt(fd_,SOL_SOCKET,SO_ERROR,&socket_error,&size)!=0){fail(errno);return false;}
    if(socket_error==0){status_.connecting=false;status_.connected=true;return true;}
    if(socket_error==EINPROGRESS||socket_error==EAGAIN)return false;
    fail(socket_error);
#endif
    return false;
}

bool LeIsoHardwareSocket::receive(std::uint8_t* destination,std::size_t capacity,std::size_t& received,std::uint64_t& received_monotonic_ns) noexcept {
    received=0;received_monotonic_ns=0;if(fd_<0||!destination||capacity==0)return false;
#if defined(__linux__)
    ssize_t count=0;do{count=::recv(fd_,destination,capacity,MSG_DONTWAIT);}while(count<0&&errno==EINTR);
    if(count>0){received=static_cast<std::size_t>(count);received_monotonic_ns=monotonic_now_ns();++status_.received_sdus;status_.received_bytes+=received;return true;}
    if(count==0){fail(ENODATA);return false;}
    if(errno==EAGAIN||errno==EWOULDBLOCK){++status_.would_block;return false;}fail(errno);
#endif
    return false;
}

bool LeIsoHardwareSocket::send(const std::uint8_t* data,std::size_t size) noexcept {
    if(fd_<0||!data||size==0)return false;
#if defined(__linux__)
    ssize_t count=0;do{count=::send(fd_,data,size,MSG_DONTWAIT|MSG_NOSIGNAL);}while(count<0&&errno==EINTR);
    if(count==static_cast<ssize_t>(size)){++status_.transmitted_sdus;status_.transmitted_bytes+=size;return true;}
    if(count>=0){status_.transmitted_bytes+=static_cast<std::uint64_t>(count);fail(EMSGSIZE);return false;}
    if(errno==EAGAIN||errno==EWOULDBLOCK){++status_.would_block;return false;}fail(errno);
#endif
    return false;
}

void LeIsoHardwareSocket::fail(int error_number) noexcept {status_.last_errno=error_number;++status_.io_errors;close();status_.last_errno=error_number;}
void LeIsoHardwareSocket::close() noexcept {
#if defined(__linux__)
    if(fd_>=0)::close(fd_);
#endif
    fd_=-1;status_.open=false;status_.connecting=false;status_.connected=false;
}

} // namespace stagemesh
