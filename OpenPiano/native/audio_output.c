#include <windows.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

#define API __declspec(dllexport)
typedef int (__cdecl *write_float_fn)(void *, int, void *, int, int, void *, int, int);

#include "piano_damping.h"

typedef struct {
    void *synth;
    write_float_fn write_float;
    piano_state *volatile piano;
    volatile LONG render_cursor;
    double envelope, release, ceiling;
    LONG diagnostics, muted;
    LARGE_INTEGER frequency;
    LONGLONG last_start;
    volatile LONG64 blocks, frames, max_frames, max_render_ticks, max_interval_ticks, failures;
} audio_state;

static void maximum(volatile LONG64 *target, LONG64 value) {
    LONG64 previous = InterlockedCompareExchange64(target, 0, 0);
    while (value > previous) {
        LONG64 actual = InterlockedCompareExchange64(target, value, previous);
        if (actual == previous) break;
        previous = actual;
    }
}

API int op_audio_abi_version(void) { return 1; }

static int pcm16_sample(float sample) {
    double value = (double)sample * 32767.0;
    double fraction;
    int base;
    if (value >= 32767.0) return 32767;
    if (value <= -32768.0) return -32768;
    base = (int)floor(value);
    fraction = value - base;
    if (fraction > 0.5 || (fraction == 0.5 && (base & 1))) ++base;
    return base;
}

API int op_audio_pcm16(const float *left, const float *right, int frames, uint8_t *destination) {
    int i;
    if (frames < 0 || (frames && (!left || !right || !destination))) return -1;
    for (i = 0; i < frames; ++i) {
        if (!isfinite(left[i]) || !isfinite(right[i])) return -1;
    }
    for (i = 0; i < frames; ++i) {
        uint16_t l = (uint16_t)pcm16_sample(left[i]);
        uint16_t r = (uint16_t)pcm16_sample(right[i]);
        size_t offset = (size_t)i * 4;
        destination[offset] = (uint8_t)l;
        destination[offset + 1] = (uint8_t)(l >> 8);
        destination[offset + 2] = (uint8_t)r;
        destination[offset + 3] = (uint8_t)(r >> 8);
    }
    return 0;
}

API audio_state *op_audio_create(void *synth, write_float_fn write_float, int rate) {
    audio_state *state;
    if (!synth || !write_float || rate < 8000) return NULL;
    state = (audio_state *)calloc(1, sizeof(*state));
    if (!state) return NULL;
    state->synth = synth;
    state->write_float = write_float;
    state->ceiling = 0.95;
    state->release = exp(-1.0 / (0.080 * rate));
    QueryPerformanceFrequency(&state->frequency);
    return state;
}

API void op_audio_destroy(audio_state *state) { free(state); }

API double op_audio_envelope(audio_state *state) { return state->envelope; }

API void op_audio_piano(audio_state *state, piano_state *piano) {
    InterlockedExchangePointer((void *volatile *)&state->piano, piano);
}

API void op_audio_copy_phase(audio_state *state, const audio_state *previous) {
    if (state && previous && state->synth == previous->synth) {
        state->render_cursor = previous->render_cursor;
        state->envelope = previous->envelope;
    }
}

API int op_audio_phase(audio_state *state) {
    return (int)InterlockedCompareExchange(&state->render_cursor, 0, 0);
}

API int op_audio_render(audio_state *state, float *left, float *right, int frames) {
    int remaining = frames, offset = 0, result;
    piano_state *piano;
    if (!state || !left || !right || frames < 0) return -1;
    piano = (piano_state *)InterlockedCompareExchangePointer(
        (void *volatile *)&state->piano, NULL, NULL);
    if (!piano) {
        result = state->write_float(state->synth, frames, left, 0, 1, right, 0, 1);
        InterlockedExchange(&state->render_cursor, (state->render_cursor + (unsigned int)frames) % 64);
        return result;
    }
    while (remaining) {
        int count = 64 - (int)state->render_cursor;
        if (state->render_cursor == 0 && op_piano_command(piano, 0, 5) != 0) return -1;
        if (count > remaining) count = remaining;
        result = state->write_float(state->synth, count, left + offset, 0, 1, right + offset, 0, 1);
        if (result != 0) return result;
        InterlockedExchange(&state->render_cursor, (state->render_cursor + (unsigned int)count) % 64);
        offset += count; remaining -= count;
    }
    return 0;
}

API int op_audio_protect(audio_state *state, float *left, float *right, int frames) {
    int i;
    double peak = 0.0, envelope = state->envelope;
    for (i = 0; i < frames; ++i) {
        double l = fabs(left[i]), r = fabs(right[i]);
        if (!isfinite(l) || !isfinite(r)) return -1;
        if (l > peak) peak = l;
        if (r > peak) peak = r;
    }
    if (peak <= state->ceiling && envelope <= state->ceiling) {
        state->envelope = 0.0;
        return 0;
    }
    for (i = 0; i < frames; ++i) {
        double l = fabs(left[i]), r = fabs(right[i]);
        envelope *= state->release;
        if (l > envelope) envelope = l;
        if (r > envelope) envelope = r;
        if (envelope > state->ceiling) {
            double gain = state->ceiling / envelope;
            left[i] = (float)(left[i] * gain);
            right[i] = (float)(right[i] * gain);
        }
    }
    state->envelope = envelope;
    return 0;
}

API int op_audio_callback(void *data, int frames, int nfx, float **fx, int nout, float **out) {
    audio_state *state = (audio_state *)data;
    LARGE_INTEGER start = {0}, finish = {0};
    int result, channel, diagnostics;
    (void)nfx; (void)fx;
    if (!state || !out || frames < 0 || nout < 2) return -1;
    diagnostics = state->diagnostics;
    if (diagnostics) QueryPerformanceCounter(&start);
    result = op_audio_render(state, out[0], out[1], frames);
    if (result == 0) result = op_audio_protect(state, out[0], out[1], frames);
    if (result != 0 || state->muted) {
        for (channel = 0; channel < nout; ++channel)
            memset(out[channel], 0, (size_t)frames * sizeof(float));
    }
    if (result != 0) InterlockedIncrement64(&state->failures);
    if (diagnostics) {
        QueryPerformanceCounter(&finish);
        InterlockedIncrement64(&state->blocks);
        InterlockedAdd64(&state->frames, frames);
        maximum(&state->max_frames, frames);
        maximum(&state->max_render_ticks, finish.QuadPart - start.QuadPart);
        if (state->last_start)
            maximum(&state->max_interval_ticks, start.QuadPart - state->last_start);
        state->last_start = start.QuadPart;
    }
    return result;
}

API void op_audio_diagnostics(audio_state *state, int enabled, int muted) {
    state->diagnostics = enabled;
    state->muted = muted;
}

API void op_audio_stats(audio_state *state, int64_t *values) {
    values[0] = InterlockedCompareExchange64(&state->blocks, 0, 0);
    values[1] = InterlockedCompareExchange64(&state->frames, 0, 0);
    values[2] = InterlockedCompareExchange64(&state->max_frames, 0, 0);
    values[3] = InterlockedCompareExchange64(&state->max_render_ticks, 0, 0);
    values[4] = InterlockedCompareExchange64(&state->max_interval_ticks, 0, 0);
    values[5] = InterlockedCompareExchange64(&state->failures, 0, 0);
    values[6] = state->frequency.QuadPart;
}
