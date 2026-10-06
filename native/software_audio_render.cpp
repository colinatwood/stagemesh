#include "audio_stream_lifecycle.h"
#include <stdexcept>
#include <vector>
#ifdef __APPLE__
#include <AudioToolbox/AudioToolbox.h>
#include <AudioUnit/AudioUnit.h>
#endif

namespace stagemesh {
#ifdef __APPLE__
namespace {
void checked(OSStatus status, const char* operation) {
    if (status != noErr) throw std::runtime_error(std::string(operation) + ": " + std::to_string(status));
}
struct RenderContext {
    GuardedAudioStreamLifecycle* lifecycle;
    std::uint64_t calls = 0;
    std::uint64_t frames = 0;
};
OSStatus render(void* raw, AudioUnitRenderActionFlags*, const AudioTimeStamp*, UInt32,
                UInt32 frames, AudioBufferList* data) {
    auto& context = *static_cast<RenderContext*>(raw);
    if (!data || data->mNumberBuffers != 1 || data->mBuffers[0].mNumberChannels != 2 ||
        !data->mBuffers[0].mData || data->mBuffers[0].mDataByteSize < frames * 2 * sizeof(float))
        return kAudio_ParamError;
    const float value = context.lifecycle->observation().callback_execution_allowed ? 0.125f : 0.0f;
    auto* samples = static_cast<float*>(data->mBuffers[0].mData);
    for (UInt32 i = 0; i < frames * 2; ++i) samples[i] = value;
    ++context.calls; context.frames += frames;
    return noErr;
}
// Context outlives the unit. Cleanup order is stop, uninitialize, dispose.
struct Unit {
    AudioComponentInstance value = nullptr;
    bool initialized = false;
    bool started = false;
    void stop() { if (started) { checked(AudioOutputUnitStop(value), "stop Generic Output"); started = false; } }
    void close() {
        stop();
        if (initialized) { checked(AudioUnitUninitialize(value), "uninitialize Generic Output"); initialized = false; }
        if (value) { checked(AudioComponentInstanceDispose(value), "dispose Generic Output"); value = nullptr; }
    }
    ~Unit() { try { close(); } catch (...) { std::terminate(); } }
};
}
#endif
SoftwareAudioRenderResult run_software_audio_render(std::uint32_t rate, std::uint32_t frames, std::uint32_t slices) {
    if (rate < 8000 || rate > 192000 || !frames || frames > 4096 || !slices || slices > 1000)
        throw std::invalid_argument("software rendering request outside bounded fixture limits");
    SoftwareAudioRenderResult result{};
#ifdef __APPLE__
    GuardedAudioStreamLifecycle lifecycle;
    RenderContext context{&lifecycle};
    Unit unit;
    AudioComponentDescription description{};
    description.componentType = kAudioUnitType_Output;
    description.componentSubType = kAudioUnitSubType_GenericOutput;
    description.componentManufacturer = kAudioUnitManufacturer_Apple;
    auto component = AudioComponentFindNext(nullptr, &description);
    if (!component) throw std::runtime_error("Generic Output unavailable");
    checked(AudioComponentInstanceNew(component, &unit.value), "create Generic Output");
    result.available = true;
    AudioStreamBasicDescription format{};
    format.mSampleRate = rate; format.mFormatID = kAudioFormatLinearPCM;
    format.mFormatFlags = kAudioFormatFlagsNativeFloatPacked;
    format.mBytesPerPacket = format.mBytesPerFrame = 2 * sizeof(float);
    format.mFramesPerPacket = 1; format.mChannelsPerFrame = 2; format.mBitsPerChannel = 32;
    checked(AudioUnitSetProperty(unit.value, kAudioUnitProperty_StreamFormat, kAudioUnitScope_Input, 0, &format, sizeof(format)), "set input format");
    checked(AudioUnitSetProperty(unit.value, kAudioUnitProperty_StreamFormat, kAudioUnitScope_Output, 0, &format, sizeof(format)), "set output format");
    checked(AudioUnitSetProperty(unit.value, kAudioUnitProperty_MaximumFramesPerSlice, kAudioUnitScope_Global, 0, &frames, sizeof(frames)), "set maximum slice");
    AURenderCallbackStruct callback{render, &context};
    checked(AudioUnitSetProperty(unit.value, kAudioUnitProperty_SetRenderCallback, kAudioUnitScope_Input, 0, &callback, sizeof(callback)), "set render callback");
    checked(AudioUnitInitialize(unit.value), "initialize Generic Output"); unit.initialized = true;
    AudioPreflightDecision plan{};
    plan.status = AudioPreflightStatus::Exact; plan.configured_sample_rate_hz = rate;
    plan.configured_period_frames = frames; plan.configured_channels = 2; plan.configured_format = AudioSampleFormat::Float32;
    FenceObservation fence{ExecutionFenceState::Armed, ResolutionStatus::Attached, true, false, 1};
    if (!lifecycle.prepare(plan, fence) || !lifecycle.start(fence)) throw std::runtime_error("prepare software lifecycle failed");
    checked(AudioOutputUnitStart(unit.value), "start Generic Output"); unit.started = true; result.started = true;
    std::vector<float> samples(frames * 2);
    AudioTimeStamp timestamp{}; timestamp.mFlags = kAudioTimeStampSampleTimeValid;
    auto pull = [&](float expected) {
        AudioBufferList buffers{}; buffers.mNumberBuffers = 1;
        buffers.mBuffers[0] = {2, static_cast<UInt32>(samples.size() * sizeof(float)), samples.data()};
        AudioUnitRenderActionFlags flags = 0;
        checked(AudioUnitRender(unit.value, &flags, &timestamp, 0, frames, &buffers), "manual AudioUnitRender");
        for (auto sample : samples) if (sample != expected) throw std::runtime_error("rendered samples differ from expected value");
        timestamp.mSampleTime += frames;
    };
    for (std::uint32_t i = 0; i < slices; ++i) pull(0.125f);
    result.samples_verified = true;
    fence = {ExecutionFenceState::FencedDetached, ResolutionStatus::Detached, false, true, 2};
    if (!lifecycle.reconcile(fence).stop_required) throw std::runtime_error("detach did not request stop");
    // Deliberately issue one manual pull while revoked to prove the callback
    // emits silence. This is synchronous software rendering, not device I/O.
    pull(0.0f); result.fenced_render_silent = true;
    unit.stop(); lifecycle.mark_stopped(); result.stopped = true;
    fence = {ExecutionFenceState::Armed, ResolutionStatus::Attached, true, false, 3};
    if (!lifecycle.prepare(plan, fence) || !lifecycle.start(fence)) throw std::runtime_error("explicit software restart failed");
    checked(AudioOutputUnitStart(unit.value), "restart Generic Output"); unit.started = true;
    pull(0.125f); result.restart_verified = true;
    unit.stop(); lifecycle.mark_stopped(); lifecycle.close(); unit.close();
    result.callback_count = context.calls; result.rendered_frames = context.frames;
    if (context.calls != slices + 2 || context.frames != static_cast<std::uint64_t>(slices + 2) * frames)
        throw std::runtime_error("unexpected callback count/frame accounting");
#endif
    return result;
}
}
