"""The Vulkan back end's play profile (profile-guided optimisation of hookshot_vk.so / hookshot_vk.dll), read by nx2/build.py.
After Hookshot's f12054fe5 (#569), whose method came from ProjectReLink (https://github.com/pixl27/ProjectReLink), both
GPL-3.0-or-later. The replay thread inside the back end is what limits the frame rate in heavy places, and this is its code.

  RX_VK_PGO=gen     the back end's own files (gpu/vk/*.cpp and suyu's texture decoders; not Eden's recompiler, sirit, Dear ImGui
                    or zstd) count their branches. Linux only: the module links compiler-rt's profile runtime in continuous mode,
                    so the counters live in the file LLVM_PROFILE_FILE names (a pattern with %c, e.g.
                    <dir>/hookshot_vk-%p.%cprofraw) and are kept whatever way the game ends (SIGTERM, a crash, _exit).
                    On Windows (llvm-mingw has no profile runtime) the back end is built as usual.
  RX_VK_PGO=<file>  built with that merged profile, when it matches (below).
  RX_VK_PGO=0       never a profile.
  unset             <work>/hookshot_vk.profdata when there is one and it matches, else the back end as it always was.

A profile matches when its stamp (<profile>.stamp, written by scripts/vk_profile.py merge) names the same sources and the same
compiler as this build: the back end's own files, the headers beside them and the compiler's --version line. Anything else, a
missing file or stamp included, builds the back end exactly as without this switch (the same flags, the same object keys) and
says why in one line. A profile made on Linux never matches a Windows build (another compiler), so there it changes nothing.

The profile holds the names of the back end's functions, a hash of each one's shape and how often its branches ran: no game
code or data."""
import hashlib
import os
import subprocess

PROFILE = "hookshot_vk.profdata"   # (in the work folder: OOT_WORK, by default the checkout's work/)
STAMP_FORMAT = "hookshot_vk profile stamp 1"
GEN_FLAGS = ["-fprofile-instr-generate", "-fprofile-continuous", "-mllvm", "-disable-vp=true"]
GEN_LINK = ["-fprofile-instr-generate"]
SUYU_TEXTURES = ("decoders.cpp", "astc.cpp")   # (nx2/build.py vk_sources(): suyu's texture decoders, in the back end)


def source_files(gpu):
    """What the stamp covers: the back end's own sources and headers in gpu/vk (not its eden/, sirit/ or compat/ folders),
    and suyu's texture decoders that are compiled into it"""
    vk = os.path.join(gpu, "vk")
    own = [os.path.join(vk, f) for f in os.listdir(vk) if f.endswith((".cpp", ".h", ".inc")) and os.path.isfile(os.path.join(vk, f))]
    textures = os.path.join(gpu, "third_party", "suyu", "video_core", "textures")
    return sorted(own) + [os.path.join(textures, f) for f in SUYU_TEXTURES if os.path.isfile(os.path.join(textures, f))]


def compiler_version(cxx):
    """The compiler's --version first line ("clang version 23.1.5"), or "?" when it does not answer"""
    quiet = {"creationflags": 0x08000000} if os.name == "nt" else {}   # (CREATE_NO_WINDOW: no console from the builder)
    try:
        r = subprocess.run([cxx, "--version"], capture_output=True, text=True, encoding="utf-8", errors="replace", **quiet)
    except OSError:
        return "?"
    return (r.stdout.strip().splitlines() or ["?"])[0].strip()


def stamp_text(gpu, compiler):
    """The stamp a profile recorded from these sources with this compiler carries (line endings normalised, as the shader stamp)"""
    h = hashlib.sha1(usedforsecurity=False)
    for f in source_files(gpu):
        with open(f, "rb") as src:
            h.update(os.path.relpath(f, gpu).replace("\\", "/").encode() + b"\0" + src.read().replace(b"\r\n", b"\n") + b"\0")
    return "%s\nsources %s\ncompiler %s\n" % (STAMP_FORMAT, h.hexdigest(), compiler)


def choose(environ, work, gpu, compiler, windows):
    """(compile flags for the back end's own files, link flags for the module, the line the build prints). compiler: a
    callable giving the compiler's --version line, called only when there is a profile to check"""
    mode = environ.get("RX_VK_PGO", "")
    if mode == "gen":
        if windows:
            return [], [], ("the Vulkan back end: RX_VK_PGO=gen is Linux only (llvm-mingw has no profile runtime): built as usual")
        return list(GEN_FLAGS), list(GEN_LINK), ("the Vulkan back end: counting its branches for a profile (RX_VK_PGO=gen; in a run, "
                                                 "LLVM_PROFILE_FILE=<dir>/hookshot_vk-%p.%cprofraw, then scripts/vk_profile.py merge)")
    if mode in ("0", "off"):
        return [], [], "the Vulkan back end: no play profile (RX_VK_PGO=%s)" % mode
    prof = mode or os.path.join(work, PROFILE)
    if not os.path.isfile(prof):
        return [], [], "the Vulkan back end: no play profile (%s not found): built as usual" % prof
    try:
        with open(prof + ".stamp", encoding="utf-8") as f:
            recorded = f.read()
    except OSError:
        return [], [], ("the Vulkan back end: the play profile %s has no stamp (scripts/vk_profile.py merge writes it): "
                        "built without it" % prof)
    now = stamp_text(gpu, compiler())
    if recorded != now:
        old, new = recorded.splitlines(), now.splitlines()
        why = [k for k, a, b in (("format", old[0:1], new[0:1]), ("the back end's sources", old[1:2], new[1:2]),
                                 ("the compiler", old[2:3], new[2:3])) if a != b] or ["the stamp"]
        return [], [], ("the Vulkan back end: the play profile %s is stale (%s changed since it was recorded): built without it"
                        % (prof, " and ".join(why)))
    with open(prof, "rb") as f:
        # (the profile's contents in the flags the object keys hash, as RX_PGO's: another profile at the same path builds the
        # back end's own objects again, and nothing else)
        sha = hashlib.sha1(f.read(), usedforsecurity=False).hexdigest()[:16]
    return (["-fprofile-instr-use=" + prof, "-DHOOKSHOT_VK_PROFILE_SHA1=" + sha], [],
            "the Vulkan back end: built with the play profile %s" % prof)
