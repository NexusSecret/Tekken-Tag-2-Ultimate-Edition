#include "gpu/overlay.h"

#include <chrono>
#include <deque>
#include <mutex>

namespace cafe::gpu::overlay {
namespace {

using Clock = std::chrono::steady_clock;

std::mutex g_mutex;
State g_state;
Clock::time_point g_until;
std::deque<std::shared_ptr<const Window>> g_recent; // newest first
constexpr size_t kRecent = 6;

} // namespace

void set_atlas(std::shared_ptr<const Atlas> atlas) {
    std::lock_guard lock(g_mutex);
    g_state.atlas = std::move(atlas);
}

void show(std::vector<Quad> quads, double seconds, std::shared_ptr<const Scene> scene,
          std::shared_ptr<const Window> window) {
    auto shared = quads.empty() ? nullptr : std::make_shared<const std::vector<Quad>>(std::move(quads));
    if (scene && scene->solids.empty()) scene = nullptr;
    std::lock_guard lock(g_mutex);
    g_state.quads = std::move(shared);
    g_state.scene = std::move(scene);
    if (window) {
        g_recent.push_front(window);
        if (g_recent.size() > kRecent) g_recent.pop_back();
    } else {
        g_recent.clear();
    }
    g_state.window = std::move(window);
    g_until = Clock::now() + std::chrono::duration_cast<Clock::duration>(std::chrono::duration<double>(seconds));
}

State current() {
    std::lock_guard lock(g_mutex);
    State s = g_state;
    if (Clock::now() >= g_until) s.quads = nullptr, s.scene = nullptr, s.window = nullptr;
    return s;
}

std::vector<std::shared_ptr<const Window>> recent_windows() {
    std::lock_guard lock(g_mutex);
    if (Clock::now() >= g_until) return {};
    return {g_recent.begin(), g_recent.end()};
}

} // namespace cafe::gpu::overlay
