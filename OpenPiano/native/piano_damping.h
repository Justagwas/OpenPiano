typedef int (__cdecl *p_start_fn)(void *, unsigned int, void *, int, int, int, int);
typedef void (__cdecl *p_list_fn)(void *, void **, int, int);
typedef int (__cdecl *p_int_fn)(const void *);
typedef unsigned int (__cdecl *p_id_fn)(const void *);
typedef float (__cdecl *p_gen_fn)(void *, int);
typedef void (__cdecl *p_set_fn)(void *, int, float);
typedef void (__cdecl *p_update_fn)(void *, int);
typedef int (__cdecl *p_stop_fn)(void *, unsigned int);
typedef void *(__cdecl *p_data_fn)(void *);
typedef int (__cdecl *p_data_set_fn)(void *, void *);
typedef void (__cdecl *p_delete_fn)(void *);
typedef const char *(__cdecl *p_name_fn)(void *);
typedef void *(__cdecl *p_preset_fn)(void *, int, int);
typedef void (__cdecl *p_iter_fn)(void *);
typedef void *(__cdecl *p_next_fn)(void *);
typedef int (__cdecl *p_free_fn)(void *);
typedef int (__cdecl *p_note_fn)(void *, void *, int, int, int);
typedef void *(__cdecl *p_new_font_fn)(p_name_fn, p_preset_fn, p_iter_fn, p_next_fn, p_free_fn);
typedef void *(__cdecl *p_new_preset_fn)(void *, p_name_fn, p_int_fn, p_int_fn, p_note_fn, p_free_fn);

typedef struct {
    void *voice[2];
    float base[2];
    unsigned int id;
    int active, released;
    double attenuation, increment;
} piano_group;

typedef struct {
    void *synth, *font, *preset;
    int rate, enabled, pedal;
    int half_pedal;
    double damping_fraction;
    p_start_fn start;
    p_list_fn list;
    p_int_fn key, channel, playing, on;
    p_id_fn id;
    p_gen_fn gen;
    p_set_fn set;
    p_update_fn update;
    p_stop_fn stop;
    p_delete_fn delete_font, delete_preset;
    piano_group groups[128];
} piano_state;

static p_data_fn piano_get_data;
static const char *piano_name(void *object) { (void)object; return "OpenPiano control"; }
static void *piano_no_preset(void *object, int bank, int program) {
    (void)object; (void)bank; (void)program; return NULL;
}
static void piano_iteration(void *object) { (void)object; }
static void *piano_next(void *object) { (void)object; return NULL; }
static int piano_no_free(void *object) { (void)object; return 0; }
static int piano_number(const void *object) { (void)object; return 0; }

static int piano_valid(piano_state *state, piano_group *group) {
    int i;
    for (i = 0; i < 2; ++i) {
        void *voice = group->voice[i];
        if (!voice || !state->playing(voice) || state->id(voice) != group->id || !state->on(voice))
            return 0;
    }
    return 1;
}

static int piano_note(void *preset, void *synth, int channel, int key, int op) {
    piano_state *state = (piano_state *)piano_get_data(preset);
    piano_group *group;
    int i;
    (void)channel;
    if (!state || synth != state->synth) return -1;
    if (op == 4 || op == 6 || op == 7) {
        memset(state->groups, 0, sizeof(state->groups));
        state->pedal = 0;
        state->damping_fraction = 1.0;
        if (op != 4) state->enabled = op == 6;
        return 0;
    }
    if (!state->enabled) return op == 2 || op == 5 ? 0 : -1;
    if (op == 9) {
        if (key > 1) return -1;
        for (i = 21; i < 89; ++i) if (state->groups[i].active) return -1;
        state->half_pedal = key;
        key = state->pedal;
        op = 3;
    }
    if (op == 3) {
        double position = fmin(64.0, key) / 64.0;
        state->pedal = key;
        state->damping_fraction = state->half_pedal
            ? (1.0 - position) * (1.0 - position) * (1.0 + 2.0 * position)
            : (key < 64 ? 1.0 : 0.0);
        return 0;
    }
    if (op == 5) {
        for (i = 21; i < 89; ++i) {
            group = &state->groups[i];
            if (!group->active) continue;
            if (!piano_valid(state, group)) { group->active = 0; continue; }
            if (!group->released || state->pedal >= 64) continue;
            group->attenuation = fmin(960.0,
                group->attenuation + group->increment * state->damping_fraction);
            state->set(group->voice[0], 48, group->base[0] + (float)nearbyint(group->attenuation));
            state->set(group->voice[1], 48, group->base[1] + (float)nearbyint(group->attenuation));
            state->update(group->voice[0], 48);
            state->update(group->voice[1], 48);
            if (group->attenuation >= 960.0) {
                state->stop(synth, group->id);
                group->active = 0;
            }
        }
        return 0;
    }
    if (key < 21 || key >= 89) return 0;
    group = &state->groups[key];
    if (op == 8) {
        if (!group->active || !group->released || !piano_valid(state, group)) return 0;
        return 1 + (int)nearbyint(group->attenuation);
    }
    if (op == 2) {
        if (!group->active || !piano_valid(state, group)) { group->active = 0; return 0; }
        group->released = 1;
        return 1;
    }
    if (op == 1) {
        void *voices[1024] = {0}, *pair[2] = {0};
        unsigned int latest = 0;
        int found = 0, count = 0;
        double release;
        state->list(synth, voices, 1024, -1);
        for (i = 0; i < 1024 && voices[i]; ++i) {
            void *voice = voices[i];
            unsigned int id;
            if (state->channel(voice) != 0 || state->key(voice) != key || !state->on(voice)) continue;
            id = state->id(voice);
            if (!found || (int32_t)(id - latest) > 0) { latest = id; count = 0; found = 1; }
            if (id == latest) { if (count < 2) pair[count] = voice; ++count; }
        }
        memset(group, 0, sizeof(*group));
        if (count != 2) return 0;
        group->voice[0] = pair[0]; group->voice[1] = pair[1]; group->id = latest;
        group->base[0] = state->gen(pair[0], 48); group->base[1] = state->gen(pair[1], 48);
        release = fmax(.016, pow(2.0, state->gen(pair[0], 38) / 1200.0));
        group->increment = 960.0 / (1.0 + floor(release * state->rate / 64.0));
        group->active = 1;
        return 0;
    }
    return -1;
}

API int op_piano_abi_version(void) { return 3; }

API piano_state *op_piano_create(void *synth, HMODULE library, int rate) {
    piano_state *state;
    p_new_font_fn new_font;
    p_new_preset_fn new_preset;
    p_data_set_fn set_data;
    p_data_fn get_data, previous_data;
    if (!synth || !library || rate < 8000) return NULL;
    state = (piano_state *)calloc(1, sizeof(*state));
    if (!state) return NULL;
    state->synth = synth; state->rate = rate;
#pragma warning(push)
#pragma warning(disable:4191)
#define P_BIND(target, type, name) target = (type)GetProcAddress(library, name); if (!target) goto failed
    P_BIND(state->start, p_start_fn, "fluid_synth_start");
    P_BIND(state->list, p_list_fn, "fluid_synth_get_voicelist");
    P_BIND(state->key, p_int_fn, "fluid_voice_get_key");
    P_BIND(state->channel, p_int_fn, "fluid_voice_get_channel");
    P_BIND(state->playing, p_int_fn, "fluid_voice_is_playing");
    P_BIND(state->on, p_int_fn, "fluid_voice_is_on");
    P_BIND(state->id, p_id_fn, "fluid_voice_get_id");
    P_BIND(state->gen, p_gen_fn, "fluid_voice_gen_get");
    P_BIND(state->set, p_set_fn, "fluid_voice_gen_set");
    P_BIND(state->update, p_update_fn, "fluid_voice_update_param");
    P_BIND(state->stop, p_stop_fn, "fluid_synth_stop");
    P_BIND(state->delete_font, p_delete_fn, "delete_fluid_sfont");
    P_BIND(state->delete_preset, p_delete_fn, "delete_fluid_preset");
    P_BIND(new_font, p_new_font_fn, "new_fluid_sfont");
    P_BIND(new_preset, p_new_preset_fn, "new_fluid_preset");
    P_BIND(set_data, p_data_set_fn, "fluid_preset_set_data");
    P_BIND(get_data, p_data_fn, "fluid_preset_get_data");
#undef P_BIND
#pragma warning(pop)
    previous_data = (p_data_fn)InterlockedCompareExchangePointer(
        (void *volatile *)&piano_get_data, (void *)get_data, NULL);
    if (previous_data && previous_data != get_data) goto failed;
    state->font = new_font(piano_name, piano_no_preset, piano_iteration, piano_next, piano_no_free);
    if (!state->font) goto failed;
    state->preset = new_preset(state->font, piano_name, piano_number, piano_number, piano_note, piano_no_free);
    if (!state->preset || set_data(state->preset, state) < 0) goto failed;
    return state;
failed:
    if (state->preset) state->delete_preset(state->preset);
    if (state->font) state->delete_font(state->font);
    free(state);
    return NULL;
}

API int op_piano_command(piano_state *state, int key, int op) {
    if (!state || key < 0 || key > 127 || op < 1 || op > 9) return -1;
    return state->start(state->synth, 0, state->preset, 0, 0, key, op);
}

API void op_piano_destroy(piano_state *state) {
    if (!state) return;
    state->delete_preset(state->preset);
    state->delete_font(state->font);
    free(state);
}
