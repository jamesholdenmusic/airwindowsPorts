#include "ext.h"
#include "ext_obex.h"
#include "ext_assist.h"
#include "z_dsp.h"

#include <algorithm>
#include <cstring>

#include "Console7ChannelEngine.hpp"

typedef struct _t_airfx_console7channel_tilde {
    t_pxobject obj;
    Console7ChannelEngine engine;
    double param_0;
    double sample_rate;
} t_airfx_console7channel_tilde;

static t_class* s_airfx_console7channel_tilde_class = nullptr;
static constexpr std::size_t k_assist_max_len = ASSIST_MAX_STRING_LEN;
static constexpr long k_airfx_console7channel_tilde_param_count = 1;

static double airfx_console7channel_tilde_clamp01(double value)
{
    return std::max(0.0, std::min(1.0, value));
}

static bool airfx_console7channel_tilde_has_attr_args(long argc, t_atom* argv)
{
    for (long i = 0; i < argc; ++i) {
        if (atom_gettype(argv + i) == A_SYM) {
            t_symbol* sym = atom_getsym(argv + i);
            if (sym && sym->s_name && sym->s_name[0] == '@') {
                return true;
            }
        }
    }
    return false;
}

static void airfx_console7channel_tilde_set_parameter_by_index(t_airfx_console7channel_tilde* x, long index, double value)
{
    if (!x || index < 0 || index >= k_airfx_console7channel_tilde_param_count) {
        return;
    }

    const double clamped = airfx_console7channel_tilde_clamp01(value);
    switch (index) {
        case 0: x->param_0 = clamped; break;
        default: return;
    }
    x->engine.setParameterByIndex(static_cast<int>(index), clamped);
}

static void airfx_console7channel_tilde_named_param_0(t_airfx_console7channel_tilde* x, double value)
{
    airfx_console7channel_tilde_set_parameter_by_index(x, 0, value);
}

static t_max_err airfx_console7channel_tilde_attr_set_0(t_airfx_console7channel_tilde* x, void* /*attr*/, long argc, t_atom* argv)
{
    if (!x || argc < 1 || !argv) {
        return MAX_ERR_GENERIC;
    }
    airfx_console7channel_tilde_set_parameter_by_index(x, 0, atom_getfloat(argv));
    return MAX_ERR_NONE;
}

static void* airfx_console7channel_tilde_new(t_symbol* /*s*/, long argc, t_atom* argv)
{
    auto* x = (t_airfx_console7channel_tilde*)object_alloc(s_airfx_console7channel_tilde_class);
    if (!x) {
        return nullptr;
    }

    dsp_setup((t_pxobject*)x, 2);
    outlet_new((t_object*)x, "signal");
    outlet_new((t_object*)x, "signal");

    x->sample_rate = sys_getsr();
    if (x->sample_rate <= 0.0) {
        x->sample_rate = 44100.0;
    }

    x->engine.reset(x->sample_rate);
    x->param_0 = x->engine.getParameterByIndex(0);

    const bool has_attrs = airfx_console7channel_tilde_has_attr_args(argc, argv);
    if (!has_attrs && argc > 0) {
        const long assign_count = std::min<long>(argc, k_airfx_console7channel_tilde_param_count);
        for (long i = 0; i < assign_count; ++i) {
            const auto atom_type = atom_gettype(argv + i);
            if (atom_type != A_LONG && atom_type != A_FLOAT) {
                break;
            }
            airfx_console7channel_tilde_set_parameter_by_index(x, i, atom_getfloat(argv + i));
        }
    }

    if (has_attrs) {
        attr_args_process(x, argc, argv);
    }

    return x;
}

static void airfx_console7channel_tilde_free(t_airfx_console7channel_tilde* x)
{
    dsp_free((t_pxobject*)x);
}

static void airfx_console7channel_tilde_float(t_airfx_console7channel_tilde* x, double value)
{
    airfx_console7channel_tilde_set_parameter_by_index(x, 0, value);
}

static void airfx_console7channel_tilde_int(t_airfx_console7channel_tilde* x, long value)
{
    airfx_console7channel_tilde_set_parameter_by_index(x, 0, static_cast<double>(value));
}

static void airfx_console7channel_tilde_param(t_airfx_console7channel_tilde* x, t_symbol* /*s*/, long argc, t_atom* argv)
{
    if (argc < 1) {
        return;
    }

    long index = 0;
    double value = atom_getfloat(argv);

    if (argc >= 2) {
        if (atom_gettype(argv) == A_SYM) {
            t_symbol* name = atom_getsym(argv);
            if (!name || !name->s_name) {
                return;
            }
            if (false) {}
                        else if (std::strcmp(name->s_name, "fader") == 0) { index = 0; }
            else {
                return;
            }
        } else {
            const long raw = static_cast<long>(atom_getfloat(argv));
            if (raw >= 1 && raw <= k_airfx_console7channel_tilde_param_count) {
                index = raw - 1;
            } else {
                index = raw;
            }
        }
        value = atom_getfloat(argv + 1);
    }

    airfx_console7channel_tilde_set_parameter_by_index(x, index, value);
}

static void airfx_console7channel_tilde_params(t_airfx_console7channel_tilde* x)
{
    object_post((t_object*)x, "airfx.console7channel~ parameter map:");
    object_post((t_object*)x, "  1: fader (Fader) default=0.772000");
}

static void airfx_console7channel_tilde_assist(t_airfx_console7channel_tilde* /*x*/, void* /*b*/, long m, long a, char* s)
{
    if (m == ASSIST_INLET) {
        if (a == 0) {
            std::strncpy(s, "(signal/float) Left input, param 1 (Fader)", k_assist_max_len);
        } else {
            std::strncpy(s, "(signal) Right input", k_assist_max_len);
        }
    } else {
        if (a == 0) {
            std::strncpy(s, "(signal) Left output", k_assist_max_len);
        } else {
            std::strncpy(s, "(signal) Right output", k_assist_max_len);
        }
    }
    s[k_assist_max_len - 1] = '\0';
}

static void airfx_console7channel_tilde_perform64(
    t_airfx_console7channel_tilde* x,
    t_object* /*dsp64*/,
    double** ins,
    long numins,
    double** outs,
    long numouts,
    long sampleframes,
    long /*flags*/,
    void* /*userparam*/)
{
    if (numins < 2 || numouts < 2) {
        return;
    }

    if (x->obj.z_disabled) {
        if (ins[0] && outs[0] && ins[0] != outs[0]) {
            std::memcpy(outs[0], ins[0], static_cast<size_t>(sampleframes) * sizeof(double));
        }
        if (ins[1] && outs[1] && ins[1] != outs[1]) {
            std::memcpy(outs[1], ins[1], static_cast<size_t>(sampleframes) * sizeof(double));
        }
        return;
    }

    x->engine.process(ins, outs, static_cast<int>(sampleframes));
}

static void airfx_console7channel_tilde_dsp64(
    t_airfx_console7channel_tilde* x,
    t_object* dsp64,
    short* /*count*/,
    double samplerate,
    long /*maxvectorsize*/,
    long /*flags*/)
{
    if (samplerate > 0.0 && samplerate != x->sample_rate) {
        x->sample_rate = samplerate;
        x->engine.reset(x->sample_rate);
        x->engine.setParameterByIndex(0, x->param_0);
    }

    object_method(dsp64, gensym("dsp_add64"), x, airfx_console7channel_tilde_perform64, 0, nullptr);
}

extern "C" void ext_main(void* r)
{
    t_class* c = class_new(
        "airfx.console7channel~",
        (method)airfx_console7channel_tilde_new,
        (method)airfx_console7channel_tilde_free,
        sizeof(t_airfx_console7channel_tilde),
        0L,
        A_GIMME,
        0);

    class_addmethod(c, (method)airfx_console7channel_tilde_dsp64, "dsp64", A_CANT, 0);
    class_addmethod(c, (method)airfx_console7channel_tilde_assist, "assist", A_CANT, 0);
    class_addmethod(c, (method)airfx_console7channel_tilde_float, "float", A_FLOAT, 0);
    class_addmethod(c, (method)airfx_console7channel_tilde_int, "int", A_LONG, 0);
    class_addmethod(c, (method)airfx_console7channel_tilde_param, "param", A_GIMME, 0);
    class_addmethod(c, (method)airfx_console7channel_tilde_params, "params", 0);
    class_addmethod(c, (method)airfx_console7channel_tilde_named_param_0, "fader", A_FLOAT, 0);

    CLASS_ATTR_DOUBLE(c, "fader", 0, t_airfx_console7channel_tilde, param_0);
    CLASS_ATTR_ACCESSORS(c, "fader", nullptr, (method)airfx_console7channel_tilde_attr_set_0);
    CLASS_ATTR_LABEL(c, "fader", 0, "Fader");
    CLASS_ATTR_FILTER_CLIP(c, "fader", 0.0, 1.0);
    CLASS_ATTR_SAVE(c, "fader", 1);

    class_dspinit(c);
    class_register(CLASS_BOX, c);
    s_airfx_console7channel_tilde_class = c;

    object_post(nullptr, "airfx.console7channel~: loaded (1 params)");
}
