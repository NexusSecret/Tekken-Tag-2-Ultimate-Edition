#include "install.h"
#include <cstdio>
#include <cstring>
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
namespace cafe::install {
int run(const std::vector<std::string>&) {
    std::fprintf(stderr,"The Windows installer is not implemented yet. Start ttt2-ultimate.exe with the Wii U .wua path.\n");
    return 2;
}
std::optional<std::filesystem::path> installed_game() {
    wchar_t executable[32768];
    const auto size=GetModuleFileNameW(nullptr,executable,32768);
    if(!size || size==32768) return std::nullopt;
    auto game=std::filesystem::path(executable).parent_path()/"game";
    if(std::filesystem::is_regular_file(game/"code/Tekken.rpx")) return game;
    return std::nullopt;
}
bool decode_tga(const std::vector<uint8_t>& tga, std::vector<uint8_t>& rgba, uint32_t& width, uint32_t& height) {
    if (tga.size() < 18) return false;
    const uint32_t w = tga[12] | uint32_t{tga[13]} << 8, h = tga[14] | uint32_t{tga[15]} << 8;
    const uint32_t type = tga[2], bits = tga[16], descriptor = tga[17];
    // Uncompressed or run-length true colour, 24 or 32 bits.
    if (tga[1] != 0 || (type != 2 && type != 10) || (bits != 24 && bits != 32) || w == 0 || h == 0) return false;
    const size_t bytes = bits / 8, count = size_t{w} * h;
    size_t at = 18 + tga[0];
    // (A run-length packet holds at most 128 pixels in 1 + bytes bytes.)
    if (at > tga.size() || count > (tga.size() - at) / bytes * (type == 10 ? 128 : 1)) return false;
    std::vector<uint8_t> pixels;
    pixels.reserve(count * 4);
    const auto put = [&](size_t from) { // BGR(A)
        pixels.insert(pixels.end(), {tga[from + 2], tga[from + 1], tga[from], bytes == 4 ? tga[from + 3] : uint8_t{255}});
    };
    while (pixels.size() < count * 4) {
        size_t run = 1;
        bool repeat = false;
        if (type == 10) {
            if (at >= tga.size()) return false;
            run = (tga[at] & 0x7F) + 1;
            repeat = tga[at++] & 0x80;
        }
        if (pixels.size() / 4 + run > count || at + (repeat ? 1 : run) * bytes > tga.size()) return false;
        for (size_t i = 0; i < run; ++i) {
            put(at);
            if (!repeat) at += bytes;
        }
        if (repeat) at += bytes;
    }
    // Rows bottom up unless the descriptor says top down; columns left to
    // right unless it says otherwise.
    rgba.resize(pixels.size());
    for (uint32_t y = 0; y < h; ++y) {
        const uint32_t row = (descriptor & 0x20) ? y : h - 1 - y;
        for (uint32_t x = 0; x < w; ++x) {
            const uint32_t column = (descriptor & 0x10) ? w - 1 - x : x;
            std::memcpy(&rgba[(size_t{y} * w + x) * 4], &pixels[(size_t{row} * w + column) * 4], 4);
        }
    }
    width = w;
    height = h;
    return true;
}

} // namespace cafe::install
