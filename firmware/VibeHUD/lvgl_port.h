#ifndef LVGL_PORT_H
#define LVGL_PORT_H

#ifdef __cplusplus
extern "C" {
#endif

void lvgl_port_init(void);
#include <stdbool.h>
bool example_lvgl_lock(int timeout_ms);
void example_lvgl_unlock(void);
bool hud_panel_framebuffers(void **fb0, void **fb1);


#ifdef __cplusplus
}
#endif



#endif











