#pragma once

// Practice: frame data and combat information, a panel for each side at the
// bottom of the screen (title/framedata.cpp).

#include <cstdint>

namespace cafe::title::framedata {

// The fighters' frame of a Practice round has run (not while the pause menu
// is open): `fighters` are the two sides' fighters in play.
void fighters_frame(uint8_t* base, const uint32_t fighters[2]);
// The position reset: the session's totals start over.
void reset();
// The ULTIMATE SETTINGS submenu's settings, as on (1) or off (0): the
// frame data panels at all, 1P's, 2P's, the fighters coloured by frame
// advantage, the hitboxes, the camera from above.
enum Setting { kPanels, kPanel1P, kPanel2P, kAdvantageColours, kHitboxes, kTopCamera, kSettings };
uint32_t setting(Setting s);
void set_setting(Setting s, uint32_t on);

} // namespace cafe::title::framedata
