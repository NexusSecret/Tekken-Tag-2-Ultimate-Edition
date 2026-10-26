#pragma once
#include <cstdint>
#include <ctime>
#include <stdexcept>
namespace cafe::host {
// Offset at the supplied instant, including daylight saving time.
inline int64_t utc_offset_seconds(std::time_t instant) {
    std::tm local{};
#ifdef _WIN32
    if (localtime_s(&local, &instant) != 0)
        throw std::runtime_error("cannot convert local time");
    return static_cast<int64_t>(_mkgmtime64(&local)) - static_cast<int64_t>(instant);
#else
    if (!localtime_r(&instant, &local))
        throw std::runtime_error("cannot convert local time");
    return local.tm_gmtoff;
#endif
}
} // namespace cafe::host
