#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <mmdeviceapi.h>
#include <audioclient.h>
#include <avrt.h>
#include <new>
#include <stdint.h>
#include <stdlib.h>
#include <process.h>

extern "C" int op_audio_callback(void *, int, int, float **, int, float **);
#define API extern "C" __declspec(dllexport)

struct wasapi_output {
    void *render;
    unsigned int rate, periods, diagnostics;
    wchar_t *device_id;
    HANDLE thread, stop, ready;
    HRESULT startup;
    LARGE_INTEGER frequency;
    volatile LONG running, error;
    volatile LONG64 capacity, period_frames, empty_refills, timeouts, submitted,
        refills, max_interval, mmcss, clock_position, clock_frequency,
        max_render, missed_padding, mix_rate;
};

static void maximum(volatile LONG64 *target, LONGLONG value) {
    LONGLONG old = InterlockedCompareExchange64(target, 0, 0);
    while (value > old) {
        LONGLONG found = InterlockedCompareExchange64(target, value, old);
        if (found == old) break;
        old = found;
    }
}

static HRESULT fill(wasapi_output *state, IAudioRenderClient *renderer,
                    UINT32 count, float *left, float *right) {
    BYTE *buffer = NULL;
    float *channels[2] = {left, right};
    HRESULT result = renderer->GetBuffer(count, &buffer);
    if (FAILED(result)) return result;
    int rendered = op_audio_callback(state->render, (int)count, 0, NULL, 2, channels);
    if (rendered == 0) {
        float *target = reinterpret_cast<float *>(buffer);
        for (UINT32 i = 0; i < count; ++i) {
            target[2 * i] = left[i];
            target[2 * i + 1] = right[i];
        }
    }
    result = renderer->ReleaseBuffer(count, rendered ? AUDCLNT_BUFFERFLAGS_SILENT : 0);
    if (SUCCEEDED(result)) InterlockedAdd64(&state->submitted, count);
    return result;
}

static unsigned __stdcall run(void *argument) {
    wasapi_output *state = static_cast<wasapi_output *>(argument);
    IMMDeviceEnumerator *enumerator = NULL;
    IMMDevice *device = NULL;
    IAudioClient *client = NULL;
    IAudioRenderClient *renderer = NULL;
    IAudioClock *clock = NULL;
    WAVEFORMATEX *mix = NULL;
    float *left = NULL, *right = NULL;
    HANDLE event = NULL, scheduling = NULL;
    DWORD task = 0;
    UINT32 capacity = 0;
    REFERENCE_TIME period = 0;
    LARGE_INTEGER previous = {};
    bool started = false;
    HRESULT result = CoInitializeEx(NULL, COINIT_MULTITHREADED);
    const bool com = SUCCEEDED(result);
    WAVEFORMATEX format = {};
    if (FAILED(result)) goto done;
    result = CoCreateInstance(__uuidof(MMDeviceEnumerator), NULL, CLSCTX_ALL,
                              __uuidof(IMMDeviceEnumerator), (void **)&enumerator);
    if (FAILED(result)) goto done;
    if (state->device_id)
        result = enumerator->GetDevice(state->device_id, &device);
    else
        result = enumerator->GetDefaultAudioEndpoint(eRender, eMultimedia, &device);
    if (FAILED(result)) goto done;
    result = device->Activate(__uuidof(IAudioClient), CLSCTX_ALL, NULL, (void **)&client);
    if (FAILED(result)) goto done;
    result = client->GetDevicePeriod(&period, NULL);
    if (FAILED(result)) goto done;
    if (period <= 0 || period > 10000000) { result = E_INVALIDARG; goto done; }
    state->period_frames = period * state->rate / 10000000;
    result = client->GetMixFormat(&mix);
    if (FAILED(result)) goto done;
    state->mix_rate = mix->nSamplesPerSec;
    format.wFormatTag = WAVE_FORMAT_IEEE_FLOAT;
    format.nChannels = 2;
    format.nSamplesPerSec = state->rate;
    format.wBitsPerSample = 32;
    format.nBlockAlign = 8;
    format.nAvgBytesPerSec = state->rate * 8;
    result = client->Initialize(AUDCLNT_SHAREMODE_SHARED,
        AUDCLNT_STREAMFLAGS_EVENTCALLBACK | AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM |
        AUDCLNT_STREAMFLAGS_SRC_DEFAULT_QUALITY,
        period * state->periods, 0, &format, NULL);
    if (FAILED(result)) goto done;
    event = CreateEventW(NULL, FALSE, FALSE, NULL);
    if (!event) { result = HRESULT_FROM_WIN32(GetLastError()); goto done; }
    result = client->SetEventHandle(event);
    if (FAILED(result)) goto done;
    result = client->GetBufferSize(&capacity);
    if (FAILED(result)) goto done;
    if (!capacity || capacity > state->rate * 2) { result = E_INVALIDARG; goto done; }
    state->capacity = capacity;
    left = static_cast<float *>(malloc((size_t)capacity * sizeof(float)));
    right = static_cast<float *>(malloc((size_t)capacity * sizeof(float)));
    if (!left || !right) { result = E_OUTOFMEMORY; goto done; }
    result = client->GetService(__uuidof(IAudioRenderClient), (void **)&renderer);
    if (FAILED(result)) goto done;
    if (state->diagnostics) {
        result = client->GetService(__uuidof(IAudioClock), (void **)&clock);
        if (FAILED(result)) goto done;
        UINT64 clock_frequency = 0;
        result = clock->GetFrequency(&clock_frequency);
        if (FAILED(result)) goto done;
        state->clock_frequency = (LONGLONG)clock_frequency;
    }
    scheduling = AvSetMmThreadCharacteristicsW(L"Audio", &task);
    state->mmcss = scheduling ? 1 : 0;
    result = fill(state, renderer, capacity, left, right);
    if (FAILED(result)) goto done;
    if (WaitForSingleObject(state->stop, 0) == WAIT_OBJECT_0) { result = E_ABORT; goto done; }
    result = client->Start();
    if (FAILED(result)) goto done;
    started = true;
    state->startup = S_OK;
    InterlockedExchange(&state->running, 1);
    SetEvent(state->ready);
    for (;;) {
        HANDLE events[2] = {state->stop, event};
        DWORD wait = WaitForMultipleObjects(2, events, FALSE, 1000);
        if (wait == WAIT_OBJECT_0) break;
        if (wait == WAIT_FAILED) { result = HRESULT_FROM_WIN32(GetLastError()); break; }
        if (wait == WAIT_TIMEOUT) InterlockedIncrement64(&state->timeouts);
        if (wait != WAIT_OBJECT_0 + 1 && wait != WAIT_TIMEOUT) { result = E_UNEXPECTED; break; }
        UINT32 padding = 0;
        result = client->GetCurrentPadding(&padding);
        if (FAILED(result)) break;
        if (padding > capacity) { result = E_UNEXPECTED; break; }
        UINT32 available = capacity - padding;
        if (!available) continue;
        LARGE_INTEGER begin = {}, finish = {};
        if (state->diagnostics) {
            QueryPerformanceCounter(&begin);
            if (previous.QuadPart) maximum(&state->max_interval, begin.QuadPart - previous.QuadPart);
            previous = begin;
        }
        if (!padding) InterlockedIncrement64(&state->empty_refills);
        result = fill(state, renderer, available, left, right);
        if (state->diagnostics) {
            QueryPerformanceCounter(&finish);
            maximum(&state->max_render, finish.QuadPart - begin.QuadPart);
            if (padding && (double)(finish.QuadPart - begin.QuadPart) * state->rate >
                    (double)padding * state->frequency.QuadPart)
                InterlockedIncrement64(&state->missed_padding);
        }
        if (FAILED(result)) break;
        InterlockedIncrement64(&state->refills);
        if (clock) {
            UINT64 position = 0;
            result = clock->GetPosition(&position, NULL);
            if (FAILED(result)) break;
            InterlockedExchange64(&state->clock_position, (LONGLONG)position);
        }
    }
done:
    if (FAILED(result)) InterlockedExchange(&state->error, result);
    if (!started) state->startup = result;
    if (started) {
        HRESULT stopped = client->Stop();
        if (FAILED(stopped) && SUCCEEDED(result)) InterlockedExchange(&state->error, stopped);
    }
    if (clock) clock->Release();
    if (renderer) renderer->Release();
    if (client) client->Release();
    if (device) device->Release();
    if (enumerator) enumerator->Release();
    if (mix) CoTaskMemFree(mix);
    if (scheduling) AvRevertMmThreadCharacteristics(scheduling);
    if (event) CloseHandle(event);
    free(left); free(right);
    if (com) CoUninitialize();
    InterlockedExchange(&state->running, 0);
    SetEvent(state->ready);
    return 0;
}

API void op_wasapi_stop(wasapi_output *state) {
    if (!state) return;
    if (state->stop) SetEvent(state->stop);
    if (state->thread) WaitForSingleObject(state->thread, INFINITE);
}

API void op_wasapi_destroy(wasapi_output *state) {
    if (!state) return;
    op_wasapi_stop(state);
    if (state->thread) CloseHandle(state->thread);
    if (state->stop) CloseHandle(state->stop);
    if (state->ready) CloseHandle(state->ready);
    free(state->device_id);
    delete state;
}

API wasapi_output *op_wasapi_open(void *render, unsigned int rate, unsigned int periods,
                                const wchar_t *device_id, unsigned int diagnostics, int32_t *error) {
    if (error) *error = E_INVALIDARG;
    if (!render || rate < 8000 || rate > 192000 || periods < 2 || periods > 16) return NULL;
    wasapi_output *state = new (std::nothrow) wasapi_output();
    if (!state) { if (error) *error = E_OUTOFMEMORY; return NULL; }
    state->render = render; state->rate = rate; state->periods = periods;
    state->diagnostics = diagnostics;
    state->startup = E_PENDING;
    QueryPerformanceFrequency(&state->frequency);
    if (device_id && *device_id) {
        state->device_id = _wcsdup(device_id);
        if (!state->device_id) { if (error) *error = E_OUTOFMEMORY; op_wasapi_destroy(state); return NULL; }
    }
    state->stop = CreateEventW(NULL, TRUE, FALSE, NULL);
    if (!state->stop) {
        if (error) *error = HRESULT_FROM_WIN32(GetLastError());
        op_wasapi_destroy(state); return NULL;
    }
    state->ready = CreateEventW(NULL, TRUE, FALSE, NULL);
    if (state->ready)
        state->thread = reinterpret_cast<HANDLE>(_beginthreadex(NULL, 0, run, state, 0, NULL));
    if (!state->thread) {
        DWORD code = GetLastError();
        if (error) *error = HRESULT_FROM_WIN32(code ? code : ERROR_NOT_ENOUGH_MEMORY);
        op_wasapi_destroy(state); return NULL;
    }
    DWORD wait = WaitForSingleObject(state->ready, 5000);
    HRESULT result = wait == WAIT_OBJECT_0 ? state->startup :
        (wait == WAIT_TIMEOUT ? HRESULT_FROM_WIN32(ERROR_TIMEOUT) : HRESULT_FROM_WIN32(GetLastError()));
    if (error) *error = result;
    if (FAILED(result)) { op_wasapi_destroy(state); return NULL; }
    return state;
}

API void op_wasapi_stats(wasapi_output *state, int64_t *values) {
    if (!state || !values) return;
    volatile LONG64 *fields[] = {&state->capacity, &state->period_frames,
        &state->empty_refills, &state->timeouts, &state->submitted, &state->refills,
        &state->max_interval, &state->mmcss, &state->clock_position,
        &state->clock_frequency, &state->max_render, &state->missed_padding, &state->mix_rate};
    for (int i = 0; i < 13; ++i) values[i] = InterlockedCompareExchange64(fields[i], 0, 0);
    values[13] = InterlockedCompareExchange(&state->error, 0, 0);
    values[14] = InterlockedCompareExchange(&state->running, 0, 0);
    values[15] = state->frequency.QuadPart;
}
