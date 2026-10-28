#include "telemetry.h"
#include "input.h"
#include "ui.h"
#include "host_link.h"
#include "lvgl_port.h"
#include "lcd_bl_pwm_bsp.h"
#include "lvgl.h"
#include "esp_heap_caps.h"
Telemetry telemetry;
HudButton button;
HostLink hostLink;
bool demo=false;   // serial command "o" toggles built-in mock data
uint32_t lastUi=0,lastLog=0;
void capture() {
    uint32_t size=lv_snapshot_buf_size_needed(lv_scr_act(),LV_IMG_CF_TRUE_COLOR);
    void *buffer=heap_caps_malloc(size,MALLOC_CAP_SPIRAM);
    lv_img_dsc_t image={};
    if(buffer && lv_snapshot_take_to_buf(lv_scr_act(),LV_IMG_CF_TRUE_COLOR,&image,buffer,size)==LV_RES_OK) {
        Serial.printf("FRAME %u %u %lu\n",image.header.w,image.header.h,(unsigned long)image.data_size);
        Serial.write(image.data,image.data_size);Serial.println("\nEND FRAME");
    } else Serial.println("FRAME FAILED");
    free(buffer);
}
void capturePanel() {
    void *fb[2]={nullptr,nullptr};
    if(!hud_panel_framebuffers(&fb[0],&fb[1])) { Serial.println("PANEL FAILED"); return; }
    for(int i=0;i<2;++i) {
        Serial.printf("PANEL %d 320 820 %u\n",i,320*820*2);
        Serial.write((const uint8_t*)fb[i],320*820*2);Serial.println("\nEND PANEL");
    }
}
void setMode(LayoutMode m,uint32_t now) {
    uiSetMode(m,telemetry,now);
    Serial.printf("MODE %d PAGE %u/%u\n",int(m),uiPage(),uiPageCount(telemetry));
}
void setup() {
    Serial.setRxBufferSize(49152);   // a snapshot is ~10 KB (up to ~32 KB with 24 runs) and arrives in one USB burst while the loop may be rendering
    Serial.begin(115200);
    lvgl_port_init();
    lcd_bl_pwm_bsp_init(LCD_PWM_MODE_150);
    button.begin();
    if(example_lvgl_lock(-1)) { uiInit(telemetry,millis());example_lvgl_unlock(); }
    Serial.printf("VibeHUD READY 820x320 protocol=VH1 GPIO0 BOOT PSRAM=%u\n",ESP.getPsramSize());
}
void loop() {
    uint32_t now=millis();
    char command=0;
    while(Serial.available()) { char c=hostLink.feed(Serial.read(),telemetry,now); if(c) command=c; }
    if(demo) mockTick(telemetry,now); else hostLink.expire(telemetry,now);
    auto event=button.take();
    if(example_lvgl_lock(-1)) {
        if(event==ButtonEvent::NextPage || command=='p') {
            uiNextPage(telemetry,now);Serial.printf("PAGE %u/%u source=%s\n",uiPage(),uiPageCount(telemetry),command=='p'?"serial":"BOOT");
        }
        if(event==ButtonEvent::NextMode || command=='m') {
            // Long press cycles: automatic layout -> run overview -> GPUs -> automatic layout.
            if(!uiForced()) setMode(LayoutMode::Overview,now);
            else if(uiMode()==LayoutMode::Overview) setMode(LayoutMode::Gpu,now);
            else uiAuto(telemetry,now);
        }
        if(command=='a') uiAuto(telemetry,now);
        if(command=='t') setMode(LayoutMode::Training,now);
        if(command=='s') setMode(LayoutMode::SleepingFooter,now);
        if(command=='f') setMode(LayoutMode::FullSessions,now);
        if(command=='v') setMode(LayoutMode::Overview,now);
        if(command=='g') setMode(LayoutMode::Gpu,now);
        if(telemetry.runCount) {
            auto &run=telemetry.runs[uiRun(telemetry)];
            if(command=='r') run.state=RunState::Running;
            if(command=='h') run.state=RunState::Stalled;
            if(command=='d') run.state=RunState::Completed;
            if(command=='e') run.state=RunState::Error;
            if(command=='q') run.state=RunState::Queued;
        }
        if(command=='o') { demo=!demo; if(demo) mockInit(telemetry,now); else memset(&telemetry,0,sizeof(telemetry)); }
        if(command=='c') capture();
        if(command=='x') capturePanel();
        if(uint32_t(now-lastUi)>=100) { uiTick(telemetry,now);lastUi=now; }
        example_lvgl_unlock();
    }
    if(uint32_t(now-lastLog)>=5000) {
        Serial.printf("HUD alive ms=%lu page=%u/%u mode=%d run=%d free=%u snapshots=%lu\n",(unsigned long)now,uiPage(),uiPageCount(telemetry),int(uiMode()),int(telemetry.runCount?telemetry.runs[uiRun(telemetry)].state:RunState::Stalled),ESP.getFreeHeap(),(unsigned long)hostLink.snapshotCount());lastLog=now;
    }
    delay(5);
}
