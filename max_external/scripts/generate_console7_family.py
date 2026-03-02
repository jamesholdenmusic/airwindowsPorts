#!/usr/bin/env python3
"""Generate Max externals for selected Airwindows VST sources."""



from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PluginSpec:
    vst_class: str
    external_name: str

    @property
    def folder_name(self) -> str:
        return self.external_name.replace(".", "_").replace("~", "_tilde")


@dataclass(frozen=True)
class ParamSpec:
    index: int
    letter: str
    label: str
    symbol: str
    default: float

    @property
    def field_name(self) -> str:
        return f"param_{self.index}"


PLUGIN_SPECS = (
    PluginSpec("FatEQ", "airfx.fateq~"),
    PluginSpec("Console7Channel", "airfx.console7channel~"),
    PluginSpec("Console7Buss", "airfx.console7buss~"),
    PluginSpec("Console7Cascade", "airfx.console7cascade~"),
    PluginSpec("Console7Crunch", "airfx.console7crunch~"),
    PluginSpec("ToTape6", "airfx.totape6~"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--only",
        nargs="*",
        help="Optional list of VST class names to generate (e.g. Console7Channel ToTape6).",
    )
    return parser.parse_args()


def find_repo_root() -> Path:
    here = Path(__file__).resolve()
    return here.parents[2]


def extract_brace_block(text: str, anchor: str) -> str:
    start_anchor = text.find(anchor)
    if start_anchor < 0:
        raise RuntimeError(f"Could not find anchor: {anchor}")

    brace_start = text.find("{", start_anchor)
    if brace_start < 0:
        raise RuntimeError(f"Could not find opening brace after: {anchor}")

    depth = 0
    for idx in range(brace_start, len(text)):
        char = text[idx]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[brace_start + 1 : idx]

    raise RuntimeError(f"Could not find closing brace for: {anchor}")


def cxx_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def sanitize_symbol(label: str) -> str:
    symbol = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    return symbol or "param"


def indent_block(text: str, spaces: int) -> str:
    prefix = " " * spaces
    lines = text.splitlines()
    if not lines:
        return ""
    return "\n".join(prefix + line if line else "" for line in lines)


def extract_private_members(header_text: str) -> str:
    match = re.search(r"private:\s*(.*?)\n};", header_text, re.DOTALL)
    if not match:
        raise RuntimeError("Could not locate private member section")

    lines = []
    for raw_line in match.group(1).splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("//"):
            continue
        if "_programName" in stripped:
            continue
        if "_canDo" in stripped:
            continue
        lines.append(line)

    if not lines:
        raise RuntimeError("No private members were extracted")

    return "\n".join(lines)


def extract_parameter_order(header_text: str) -> list[tuple[int, str]]:
    matches = re.findall(r"kParam([A-Z])\s*=\s*(\d+)", header_text)
    if not matches:
        raise RuntimeError("No kParam* enum entries found")

    seen = set()
    ordered: list[tuple[int, str]] = []
    for letter, index_text in matches:
        index = int(index_text)
        key = (index, letter)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(key)

    ordered.sort(key=lambda item: item[0])
    return ordered


def extract_constructor_init(
    cpp_text: str,
    class_name: str,
    parameter_letters: set[str],
) -> tuple[str, dict[str, float]]:
    body = extract_brace_block(cpp_text, f"{class_name}::{class_name}")
    defaults: dict[str, float] = {}

    skip_tokens = (
        "_canDo.insert",
        "setNumInputs(",
        "setNumOutputs(",
        "setUniqueID(",
        "canProcessReplacing",
        "canDoubleReplacing",
        "programsAreChunks",
        "vst_strncpy",
    )

    kept = []
    for raw_line in body.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        if any(token in line for token in skip_tokens):
            continue

        for letter, value_text in re.findall(
            r"\b([A-Z])\s*=\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*;",
            line,
        ):
            if letter in parameter_letters:
                defaults[letter] = float(value_text)

        kept.append(line)

    if not kept:
        raise RuntimeError("No constructor init lines were extracted")

    return "\n".join(kept), defaults


def extract_parameter_labels(cpp_text: str, class_name: str) -> dict[str, str]:
    body = extract_brace_block(cpp_text, f"void {class_name}::getParameterName")
    labels: dict[str, str] = {}
    for letter, label in re.findall(
        r"case\s+kParam([A-Z])\s*:\s*vst_strncpy\s*\(\s*text\s*,\s*\"([^\"]*)\"",
        body,
    ):
        labels[letter] = label
    return labels


def build_param_specs(
    header_text: str,
    cpp_text: str,
    class_name: str,
    defaults: dict[str, float],
) -> list[ParamSpec]:
    order = extract_parameter_order(header_text)
    labels = extract_parameter_labels(cpp_text, class_name)

    used_symbols: set[str] = set()
    params: list[ParamSpec] = []
    for index, letter in order:
        label = labels.get(letter, letter)
        base_symbol = sanitize_symbol(label)
        symbol = base_symbol
        suffix = 2
        while symbol in used_symbols:
            symbol = f"{base_symbol}_{suffix}"
            suffix += 1
        used_symbols.add(symbol)

        default_value = defaults.get(letter, 0.5)
        params.append(ParamSpec(index=index, letter=letter, label=label, symbol=symbol, default=default_value))

    return params


def extract_process_body(proc_text: str, class_name: str) -> str:
    body = extract_brace_block(proc_text, f"void {class_name}::processDoubleReplacing")
    # Convert VST-style pointer increments that trigger warnings in strict builds.
    body = re.sub(r"\*(in[12]|out[12])\+\+;", r"\1++;", body)
    return body


def build_engine_header(
    class_name: str,
    members: str,
    init_body: str,
    process_body: str,
    params: list[ParamSpec],
) -> str:
    set_cases = "\n".join(
        f"case {param.index}: {param.letter} = pinParameter(static_cast<float>(value)); break;"
        for param in params
    )
    get_cases = "\n".join(
        f"case {param.index}: return {param.letter};"
        for param in params
    )

    return f"""#pragma once

#include <cmath>
#include <cstdint>
#include <cstdlib>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

class {class_name}Engine {{
public:
    static constexpr int kParameterCount = {len(params)};

    {class_name}Engine() {{ reset(44100.0); }}

    void reset(double sampleRate) {{
        sampleRate_ = (sampleRate > 1.0) ? sampleRate : 44100.0;
{indent_block(init_body, 8)}
    }}

    void setParameterByIndex(int index, double value) {{
        switch (index) {{
{indent_block(set_cases, 12)}
            default: break;
        }}
    }}

    double getParameterByIndex(int index) const {{
        switch (index) {{
{indent_block(get_cases, 12)}
            default: return 0.0;
        }}
    }}

    void process(double** inputs, double** outputs, int sampleFrames) {{
        processDoubleReplacing(inputs, outputs, sampleFrames);
    }}

private:
    static float pinParameter(float data) {{
        if (data < 0.0f) return 0.0f;
        if (data > 1.0f) return 1.0f;
        return data;
    }}

    double getSampleRate() const {{ return sampleRate_; }}

    void processDoubleReplacing(double **inputs, double **outputs, int sampleFrames)
    {{
{indent_block(process_body, 8)}
    }}

    double sampleRate_ = 44100.0;
{indent_block(members, 4)}
}};
"""


def build_wrapper_source(
    class_name: str,
    external_name: str,
    folder_name: str,
    params: list[ParamSpec],
) -> str:
    struct_name = f"t_{folder_name}"
    prefix = folder_name
    engine_header = f"{class_name}Engine.hpp"

    member_fields = "\n".join(f"    double {param.field_name};" for param in params)

    set_struct_cases = "\n".join(
        f"case {param.index}: x->{param.field_name} = clamped; break;"
        for param in params
    )

    init_fields = "\n".join(
        f"x->{param.field_name} = x->engine.getParameterByIndex({param.index});"
        for param in params
    )

    set_engine_after_reset = "\n".join(
        f"x->engine.setParameterByIndex({param.index}, x->{param.field_name});"
        for param in params
    )

    named_symbol_map = "\n".join(
        f"else if (std::strcmp(name->s_name, \"{param.symbol}\") == 0) {{ index = {param.index}; }}"
        for param in params
    )

    named_param_funcs = "\n\n".join(
        f"""static void {prefix}_named_param_{param.index}({struct_name}* x, double value)
{{
    {prefix}_set_parameter_by_index(x, {param.index}, value);
}}"""
        for param in params
    )

    attr_set_funcs = "\n\n".join(
        f"""static t_max_err {prefix}_attr_set_{param.index}({struct_name}* x, void* /*attr*/, long argc, t_atom* argv)
{{
    if (!x || argc < 1 || !argv) {{
        return MAX_ERR_GENERIC;
    }}
    {prefix}_set_parameter_by_index(x, {param.index}, atom_getfloat(argv));
    return MAX_ERR_NONE;
}}"""
        for param in params
    )

    class_add_named_methods = "\n".join(
        f"class_addmethod(c, (method){prefix}_named_param_{param.index}, \"{param.symbol}\", A_FLOAT, 0);"
        for param in params
    )

    class_attrs = "\n".join(
        (
            f"CLASS_ATTR_DOUBLE(c, \"{param.symbol}\", 0, {struct_name}, {param.field_name});\n"
            f"CLASS_ATTR_ACCESSORS(c, \"{param.symbol}\", nullptr, (method){prefix}_attr_set_{param.index});\n"
            f"CLASS_ATTR_LABEL(c, \"{param.symbol}\", 0, \"{cxx_escape(param.label)}\");\n"
            f"CLASS_ATTR_FILTER_CLIP(c, \"{param.symbol}\", 0.0, 1.0);\n"
            f"CLASS_ATTR_SAVE(c, \"{param.symbol}\", 1);"
        )
        for param in params
    )

    params_post_lines = "\n".join(
        f"object_post((t_object*)x, \"  {param.index + 1}: {param.symbol} ({cxx_escape(param.label)}) default={param.default:.6f}\");"
        for param in params
    )

    first_label = cxx_escape(params[0].label if params else "Param")

    return f"""#include \"ext.h\"
#include \"ext_obex.h\"
#include \"ext_assist.h\"
#include \"z_dsp.h\"

#include <algorithm>
#include <cstring>

#include \"{engine_header}\"

typedef struct _{struct_name} {{
    t_pxobject obj;
    {class_name}Engine engine;
{member_fields}
    double sample_rate;
}} {struct_name};

static t_class* s_{prefix}_class = nullptr;
static constexpr std::size_t k_assist_max_len = ASSIST_MAX_STRING_LEN;
static constexpr long k_{prefix}_param_count = {len(params)};

static double {prefix}_clamp01(double value)
{{
    return std::max(0.0, std::min(1.0, value));
}}

static bool {prefix}_has_attr_args(long argc, t_atom* argv)
{{
    for (long i = 0; i < argc; ++i) {{
        if (atom_gettype(argv + i) == A_SYM) {{
            t_symbol* sym = atom_getsym(argv + i);
            if (sym && sym->s_name && sym->s_name[0] == '@') {{
                return true;
            }}
        }}
    }}
    return false;
}}

static void {prefix}_set_parameter_by_index({struct_name}* x, long index, double value)
{{
    if (!x || index < 0 || index >= k_{prefix}_param_count) {{
        return;
    }}

    const double clamped = {prefix}_clamp01(value);
    switch (index) {{
{indent_block(set_struct_cases, 8)}
        default: return;
    }}
    x->engine.setParameterByIndex(static_cast<int>(index), clamped);
}}

{named_param_funcs}

{attr_set_funcs}

static void* {prefix}_new(t_symbol* /*s*/, long argc, t_atom* argv)
{{
    auto* x = ({struct_name}*)object_alloc(s_{prefix}_class);
    if (!x) {{
        return nullptr;
    }}

    dsp_setup((t_pxobject*)x, 2);
    outlet_new((t_object*)x, \"signal\");
    outlet_new((t_object*)x, \"signal\");

    x->sample_rate = sys_getsr();
    if (x->sample_rate <= 0.0) {{
        x->sample_rate = 44100.0;
    }}

    x->engine.reset(x->sample_rate);
{indent_block(init_fields, 4)}

    const bool has_attrs = {prefix}_has_attr_args(argc, argv);
    if (!has_attrs && argc > 0) {{
        const long assign_count = std::min<long>(argc, k_{prefix}_param_count);
        for (long i = 0; i < assign_count; ++i) {{
            const auto atom_type = atom_gettype(argv + i);
            if (atom_type != A_LONG && atom_type != A_FLOAT) {{
                break;
            }}
            {prefix}_set_parameter_by_index(x, i, atom_getfloat(argv + i));
        }}
    }}

    if (has_attrs) {{
        attr_args_process(x, argc, argv);
    }}

    return x;
}}

static void {prefix}_free({struct_name}* x)
{{
    dsp_free((t_pxobject*)x);
}}

static void {prefix}_float({struct_name}* x, double value)
{{
    {prefix}_set_parameter_by_index(x, 0, value);
}}

static void {prefix}_int({struct_name}* x, long value)
{{
    {prefix}_set_parameter_by_index(x, 0, static_cast<double>(value));
}}

static void {prefix}_param({struct_name}* x, t_symbol* /*s*/, long argc, t_atom* argv)
{{
    if (argc < 1) {{
        return;
    }}

    long index = 0;
    double value = atom_getfloat(argv);

    if (argc >= 2) {{
        if (atom_gettype(argv) == A_SYM) {{
            t_symbol* name = atom_getsym(argv);
            if (!name || !name->s_name) {{
                return;
            }}
            if (false) {{}}
            {indent_block(named_symbol_map, 12)}
            else {{
                return;
            }}
        }} else {{
            const long raw = static_cast<long>(atom_getfloat(argv));
            if (raw >= 1 && raw <= k_{prefix}_param_count) {{
                index = raw - 1;
            }} else {{
                index = raw;
            }}
        }}
        value = atom_getfloat(argv + 1);
    }}

    {prefix}_set_parameter_by_index(x, index, value);
}}

static void {prefix}_params({struct_name}* x)
{{
    object_post((t_object*)x, \"{external_name} parameter map:\");
{indent_block(params_post_lines, 4)}
}}

static void {prefix}_assist({struct_name}* /*x*/, void* /*b*/, long m, long a, char* s)
{{
    if (m == ASSIST_INLET) {{
        if (a == 0) {{
            std::strncpy(s, \"(signal/float) Left input, param 1 ({first_label})\", k_assist_max_len);
        }} else {{
            std::strncpy(s, \"(signal) Right input\", k_assist_max_len);
        }}
    }} else {{
        if (a == 0) {{
            std::strncpy(s, \"(signal) Left output\", k_assist_max_len);
        }} else {{
            std::strncpy(s, \"(signal) Right output\", k_assist_max_len);
        }}
    }}
    s[k_assist_max_len - 1] = '\\0';
}}

static void {prefix}_perform64(
    {struct_name}* x,
    t_object* /*dsp64*/,
    double** ins,
    long numins,
    double** outs,
    long numouts,
    long sampleframes,
    long /*flags*/,
    void* /*userparam*/)
{{
    if (numins < 2 || numouts < 2) {{
        return;
    }}

    if (x->obj.z_disabled) {{
        if (ins[0] && outs[0] && ins[0] != outs[0]) {{
            std::memcpy(outs[0], ins[0], static_cast<size_t>(sampleframes) * sizeof(double));
        }}
        if (ins[1] && outs[1] && ins[1] != outs[1]) {{
            std::memcpy(outs[1], ins[1], static_cast<size_t>(sampleframes) * sizeof(double));
        }}
        return;
    }}

    x->engine.process(ins, outs, static_cast<int>(sampleframes));
}}

static void {prefix}_dsp64(
    {struct_name}* x,
    t_object* dsp64,
    short* /*count*/,
    double samplerate,
    long /*maxvectorsize*/,
    long /*flags*/)
{{
    if (samplerate > 0.0 && samplerate != x->sample_rate) {{
        x->sample_rate = samplerate;
        x->engine.reset(x->sample_rate);
{indent_block(set_engine_after_reset, 8)}
    }}

    object_method(dsp64, gensym(\"dsp_add64\"), x, {prefix}_perform64, 0, nullptr);
}}

extern \"C\" void ext_main(void* r)
{{
    t_class* c = class_new(
        \"{external_name}\",
        (method){prefix}_new,
        (method){prefix}_free,
        sizeof({struct_name}),
        0L,
        A_GIMME,
        0);

    class_addmethod(c, (method){prefix}_dsp64, \"dsp64\", A_CANT, 0);
    class_addmethod(c, (method){prefix}_assist, \"assist\", A_CANT, 0);
    class_addmethod(c, (method){prefix}_float, \"float\", A_FLOAT, 0);
    class_addmethod(c, (method){prefix}_int, \"int\", A_LONG, 0);
    class_addmethod(c, (method){prefix}_param, \"param\", A_GIMME, 0);
    class_addmethod(c, (method){prefix}_params, \"params\", 0);
{indent_block(class_add_named_methods, 4)}

{indent_block(class_attrs, 4)}

    class_dspinit(c);
    class_register(CLASS_BOX, c);
    s_{prefix}_class = c;

    object_post(nullptr, \"{external_name}: loaded ({len(params)} params)\");
}}
"""


def build_target_cmake(folder_name: str, external_name: str, source_name: str, engine_header_name: str) -> str:
    return f"""include(${{MAX_SDK_BASE_DIR}}/script/max-pretarget.cmake)

include_directories(
    \"${{MAX_SDK_INCLUDES}}\"
    \"${{MAX_SDK_MSP_INCLUDES}}\"
    \"${{MAX_SDK_JIT_INCLUDES}}\"
)

add_library(
    ${{PROJECT_NAME}}
    MODULE
    \"{source_name}\"
    \"{engine_header_name}\"
)

if(WIN32)
    target_compile_definitions(${{PROJECT_NAME}} PRIVATE NOMINMAX)
endif()

set(${{PROJECT_NAME}}_EXTERN_OUTPUT_NAME \"{external_name}\" CACHE STRING \"\" FORCE)
mark_as_advanced(${{PROJECT_NAME}}_EXTERN_OUTPUT_NAME)

include(${{MAX_SDK_BASE_DIR}}/script/max-posttarget.cmake)
"""


def generate_plugin(repo_root: Path, generated_root: Path, spec: PluginSpec) -> str:
    vst_root = repo_root / "plugins" / "LinuxVST" / "src" / spec.vst_class
    header_path = vst_root / f"{spec.vst_class}.h"
    cpp_path = vst_root / f"{spec.vst_class}.cpp"
    proc_path = vst_root / f"{spec.vst_class}Proc.cpp"

    if not header_path.exists() or not cpp_path.exists() or not proc_path.exists():
        raise RuntimeError(f"Missing VST source files for {spec.vst_class}")

    header_text = header_path.read_text()
    cpp_text = cpp_path.read_text()
    proc_text = proc_path.read_text()

    param_order = extract_parameter_order(header_text)
    param_letters = {letter for _, letter in param_order}

    members = extract_private_members(header_text)
    init_body, defaults = extract_constructor_init(cpp_text, spec.vst_class, param_letters)
    params = build_param_specs(header_text, cpp_text, spec.vst_class, defaults)
    process_body = extract_process_body(proc_text, spec.vst_class)

    plugin_dir = generated_root / spec.folder_name
    plugin_dir.mkdir(parents=True, exist_ok=True)

    engine_header_name = f"{spec.vst_class}Engine.hpp"
    source_name = f"{spec.folder_name}.cpp"

    (plugin_dir / engine_header_name).write_text(
        build_engine_header(spec.vst_class, members, init_body, process_body, params)
    )
    (plugin_dir / source_name).write_text(
        build_wrapper_source(spec.vst_class, spec.external_name, spec.folder_name, params)
    )
    (plugin_dir / "CMakeLists.txt").write_text(
        build_target_cmake(spec.folder_name, spec.external_name, source_name, engine_header_name)
    )

    return spec.folder_name


def build_targets_file(generated_root: Path, folder_names: list[str]) -> None:
    lines = ["# Auto-generated by scripts/generate_console7_family.py", ""]
    for folder_name in folder_names:
        lines.append(
            f"add_subdirectory(${{CMAKE_CURRENT_SOURCE_DIR}}/src/generated/{folder_name} "
            f"${{CMAKE_CURRENT_BINARY_DIR}}/{folder_name})"
        )
    lines.append("")
    (generated_root / "targets.cmake").write_text("\n".join(lines))


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root().resolve()
    max_external_root = repo_root / "max_external"
    generated_root = max_external_root / "src" / "generated"
    generated_root.mkdir(parents=True, exist_ok=True)

    selected = {name for name in (args.only or [])}
    specs = [spec for spec in PLUGIN_SPECS if not selected or spec.vst_class in selected]

    if selected and len(specs) != len(selected):
        missing = sorted(selected - {spec.vst_class for spec in specs})
        raise RuntimeError(f"Unknown class name(s): {', '.join(missing)}")

    folder_names = []
    for spec in specs:
        folder_names.append(generate_plugin(repo_root, generated_root, spec))

    build_targets_file(generated_root, folder_names)

    print(f"Generated {len(folder_names)} target(s):")
    for folder_name in folder_names:
        print(f"  - {folder_name}")


if __name__ == "__main__":
    main()
