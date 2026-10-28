#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "lvgl_port.h"
#include "lvgl.h"
#include "esp_log.h"
#include "esp_err.h"
#include "esp_timer.h"
#include "user_config.h"
#include "esp_lcd_panel_rgb.h"
#include "esp_lcd_panel_ops.h"
#include "src/st7701_bsp/esp_lcd_st7701.h"
#include "src/io_additions/esp_lcd_panel_io_additions.h"
#include "demos/lv_demos.h"

static SemaphoreHandle_t lvgl_mux = NULL;
#define EXAMPLE_LCD_BIT_PER_PIXEL 16


/*静态函数定义*/
static void example_lvgl_flush_cb(lv_disp_drv_t *drv, const lv_area_t *area, lv_color_t *color_map);
static void hud_round_redraw(lv_disp_drv_t *drv, lv_area_t *area)
{
  (void)drv;
  // The Waveshare LVGL8 rotation routine rounds chunk heights down to even.
  // An odd residual row otherwise produces a zero-height flush forever.
  // Round both axes: its initial square rotation must also have even width.
  area->x1 &= ~1;
  area->y1 &= ~1;
  area->x2 |= 1;
  area->y2 |= 1;
}
static esp_lcd_panel_handle_t rgb_port_init(void);
static void example_increase_lvgl_tick(void *arg);
bool example_lvgl_lock(int timeout_ms);
void example_lvgl_unlock(void);
static void example_lvgl_port_task(void *arg);


static const st7701_lcd_init_cmd_t lcd_init_cmds[] = 
{
//   cmd   data        data_size  delay_ms 1
  {0xFF,(uint8_t []){0x77,0x01,0x00,0x00,0x13},5,0},
  {0xEF,(uint8_t []){0x08},1,0},
  {0xFF,(uint8_t []){0x77,0x01,0x00,0x00,0x10},5,0},
  {0xC0,(uint8_t []){0xE5,0x02},2,0},
  {0xC1,(uint8_t []){0x15,0x0A},2,0},
  {0xC2,(uint8_t []){0x07,0x02},2,0},
  {0xCC,(uint8_t []){0x10},1,0},
  {0xB0,(uint8_t []){0x00,0x08,0x51,0x0D,0xCE,0x06,0x00,0x08,0x08,0x24,0x05,0xD0,0x0F,0x6F,0x36,0x1F},16,0},
  {0xB1,(uint8_t []){0x00,0x10,0x4F,0x0C,0x11,0x05,0x00,0x07,0x07,0x18,0x02,0xD3,0x11,0x6E,0x34,0x1F},16,0},
  {0xFF,(uint8_t []){0x77,0x01,0x00,0x00,0x11},5,0},
  {0xB0,(uint8_t []){0x4D},1,0},
  {0xB1,(uint8_t []){0x37},1,0},
  {0xB2,(uint8_t []){0x87},1,0},
  {0xB3,(uint8_t []){0x80},1,0},
  {0xB5,(uint8_t []){0x4A},1,0},
  {0xB7,(uint8_t []){0x85},1,0},
  {0xB8,(uint8_t []){0x21},1,0},
  {0xB9,(uint8_t []){0x00,0x13},2,0},
  {0xC0,(uint8_t []){0x09},1,0},
  {0xC1,(uint8_t []){0x78},1,0},
  {0xC2,(uint8_t []){0x78},1,0},
  {0xD0,(uint8_t []){0x88},1,0},
  {0xE0,(uint8_t []){0x80,0x00,0x02},3,100},
  {0xE1,(uint8_t []){0x0F,0xA0,0x00,0x00,0x10,0xA0,0x00,0x00,0x00,0x60,0x60},11,0},
  {0xE2,(uint8_t []){0x30,0x30,0x60,0x60,0x45,0xA0,0x00,0x00,0x46,0xA0,0x00,0x00,0x00},13,0},
  {0xE3,(uint8_t []){0x00,0x00,0x33,0x33},4,0},
  {0xE4,(uint8_t []){0x44,0x44},2,0},
  {0xE5,(uint8_t []){0x0F,0x4A,0xA0,0xA0,0x11,0x4A,0xA0,0xA0,0x13,0x4A,0xA0,0xA0,0x15,0x4A,0xA0,0xA0},16,0},
  {0xE6,(uint8_t []){0x00,0x00,0x33,0x33},4,0},
  {0xE7,(uint8_t []){0x44,0x44},2,0},
  {0xE8,(uint8_t []){0x10,0x4A,0xA0,0xA0,0x12,0x4A,0xA0,0xA0,0x14,0x4A,0xA0,0xA0,0x16,0x4A,0xA0,0xA0},16,0},
  {0xEB,(uint8_t []){0x02,0x00,0x4E,0x4E,0xEE,0x44,0x00},7,0},
  {0xED,(uint8_t []){0xFF,0xFF,0x04,0x56,0x72,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0x27,0x65,0x40,0xFF,0xFF},16,0},
  {0xEF,(uint8_t []){0x08,0x08,0x08,0x40,0x3F,0x64},6,0},
  {0xFF,(uint8_t []){0x77,0x01,0x00,0x00,0x13},5,0},
  {0xE8,(uint8_t []){0x00,0x0E},2,0},
  {0xFF,(uint8_t []){0x77,0x01,0x00,0x00,0x00},5,0},
  {0x11,(uint8_t []){0x00},0,120},
  {0xFF,(uint8_t []){0x77,0x01,0x00,0x00,0x13},5,0},
  {0xE8,(uint8_t []){0x00,0x0C},2,10},
  {0xE8,(uint8_t []){0x00,0x00},2,0},
  {0xFF,(uint8_t []){0x77,0x01,0x00,0x00,0x00},5,0},
  {0x3A,(uint8_t []){0x55},1,0},
  {0x36,(uint8_t []){0x00},1,0},
  {0x35,(uint8_t []){0x00},1,0},
  {0x29,(uint8_t []){0x00},0,20},

  {0xC3,(uint8_t []){0x80},1,0}, //user 测试不同的模式
};

static esp_lcd_panel_handle_t rgb_port_init(void)
{
  spi_line_config_t line_config = 
  {
    .cs_io_type = IO_TYPE_GPIO,             // Set to `IO_TYPE_GPIO` if using GPIO, same to below
    .cs_gpio_num = EXAMPLE_LCD_IO_SPI_CS,
    .scl_io_type = IO_TYPE_GPIO,
    .scl_gpio_num = EXAMPLE_LCD_IO_SPI_SCK,
    .sda_io_type = IO_TYPE_GPIO,
    .sda_gpio_num = EXAMPLE_LCD_IO_SPI_SDO,
    .io_expander = NULL,                        // Set to NULL if not using IO expander
  };
  esp_lcd_panel_io_3wire_spi_config_t io_config = ST7701_PANEL_IO_3WIRE_SPI_CONFIG(line_config, 0);
  esp_lcd_panel_io_handle_t io_handle = NULL;

  ESP_ERROR_CHECK(esp_lcd_new_panel_io_3wire_spi(&io_config, &io_handle));

  esp_lcd_rgb_panel_config_t rgb_config = {};
  rgb_config.clk_src = LCD_CLK_SRC_DEFAULT;
  rgb_config.psram_trans_align = 64;
  rgb_config.bounce_buffer_size_px = 10 * EXAMPLE_LCD_H_RES;
  rgb_config.num_fbs = 2;
  rgb_config.data_width = 16;
  rgb_config.bits_per_pixel = 16;
  rgb_config.de_gpio_num = EXAMPLE_LCD_IO_RGB_DE;
  rgb_config.pclk_gpio_num = EXAMPLE_LCD_IO_RGB_PCLK;
  rgb_config.vsync_gpio_num = EXAMPLE_LCD_IO_RGB_VSYNC;
  rgb_config.hsync_gpio_num = EXAMPLE_LCD_IO_RGB_HSYNC;
  rgb_config.flags.fb_in_psram = true;
  rgb_config.disp_gpio_num = -1;
  //BGR
  rgb_config.data_gpio_nums[0]  = EXAMPLE_LCD_IO_RGB_B0;
  rgb_config.data_gpio_nums[1]  = EXAMPLE_LCD_IO_RGB_B1;
  rgb_config.data_gpio_nums[2]  = EXAMPLE_LCD_IO_RGB_B2;
  rgb_config.data_gpio_nums[3]  = EXAMPLE_LCD_IO_RGB_B3;
  rgb_config.data_gpio_nums[4]  = EXAMPLE_LCD_IO_RGB_B4;

  rgb_config.data_gpio_nums[5]  = EXAMPLE_LCD_IO_RGB_G0;
  rgb_config.data_gpio_nums[6]  = EXAMPLE_LCD_IO_RGB_G1;
  rgb_config.data_gpio_nums[7]  = EXAMPLE_LCD_IO_RGB_G2;
  rgb_config.data_gpio_nums[8]  = EXAMPLE_LCD_IO_RGB_G3;
  rgb_config.data_gpio_nums[9]  = EXAMPLE_LCD_IO_RGB_G4;
  rgb_config.data_gpio_nums[10] = EXAMPLE_LCD_IO_RGB_G5;

  rgb_config.data_gpio_nums[11] = EXAMPLE_LCD_IO_RGB_R0;
  rgb_config.data_gpio_nums[12] = EXAMPLE_LCD_IO_RGB_R1;
  rgb_config.data_gpio_nums[13] = EXAMPLE_LCD_IO_RGB_R2;
  rgb_config.data_gpio_nums[14] = EXAMPLE_LCD_IO_RGB_R3;
  rgb_config.data_gpio_nums[15] = EXAMPLE_LCD_IO_RGB_R4;
  
  rgb_config.timings.pclk_hz = 18 * 1000 * 1000;
  rgb_config.timings.h_res = EXAMPLE_LCD_H_RES;
  rgb_config.timings.v_res = EXAMPLE_LCD_V_RES;
  // Waveshare's 30/30 left white specks on bright text at the start of each panel line (the top
  // edge in landscape); 60/60 gives the panel's source drivers more time per line. ~45 fps at 18 MHz.
  rgb_config.timings.hsync_back_porch = 60;
  rgb_config.timings.hsync_front_porch = 60;
  rgb_config.timings.hsync_pulse_width = 6;
  rgb_config.timings.vsync_back_porch = 20;
  rgb_config.timings.vsync_front_porch = 20;
  rgb_config.timings.vsync_pulse_width = 40;

  st7701_vendor_config_t vendor_config = {};
  vendor_config.rgb_config = &rgb_config;
  vendor_config.init_cmds = lcd_init_cmds;// Uncomment these line if use custom initialization commands
  vendor_config.init_cmds_size = sizeof(lcd_init_cmds) / sizeof(st7701_lcd_init_cmd_t);
  vendor_config.flags.mirror_by_cmd = 1;        // Only work when `enable_io_multiplex` is set to 
  vendor_config.flags.enable_io_multiplex = 0;  /**
                                                 * Set to 1 if panel IO is no longer needed after 
                                                 * If the panel IO pins are sharing other pins of 
                                                 * Please set it to 1 to release the pins.
                                                */
  const esp_lcd_panel_dev_config_t panel_config = 
  {
    .reset_gpio_num = EXAMPLE_LCD_IO_RGB_RESET,                           // Set to -1 if not use
    .rgb_ele_order = LCD_RGB_ELEMENT_ORDER_RGB,     // Implemented by LCD command `36h`
    .bits_per_pixel = EXAMPLE_LCD_BIT_PER_PIXEL,    // Implemented by LCD command `3Ah` (16/18/24)
    .vendor_config = &vendor_config,
  };

  esp_lcd_panel_handle_t panel_handle = NULL;
  ESP_ERROR_CHECK(esp_lcd_new_panel_st7701(io_handle, &panel_config, &panel_handle));   /**
                                                                                         * Only create RGB when `enable_io_multiplex` is set to 0,
                                                                                         * or initialize st7701 meanwhile
                                                                                       */
  ESP_ERROR_CHECK(esp_lcd_panel_reset(panel_handle));             // Only reset RGB when `enable_io_multiplex` is set to 1, or reset st7701 meanwhile
  ESP_ERROR_CHECK(esp_lcd_panel_init(panel_handle));              // Only initialize RGB when `enable_io_multiplex` is set to 1, or initialize st7701 meanwhile

  return panel_handle;
}

static esp_lcd_panel_handle_t hud_panel;
// Debug: the RGB panel's real (physical, unrotated) frame buffers.
bool hud_panel_framebuffers(void **fb0, void **fb1)
{
  return hud_panel && esp_lcd_rgb_panel_get_frame_buffer(hud_panel, 2, fb0, fb1) == ESP_OK;
}
void lvgl_port_init(void)
{
  esp_lcd_panel_handle_t panel_handle = rgb_port_init();
  hud_panel = panel_handle;
  static lv_disp_draw_buf_t disp_buf;
  static lv_disp_drv_t disp_drv;
  lv_init();
  lv_color_t *buf_1 = NULL;
  lv_color_t *buf_2 = NULL;
  buf_1 = (lv_color_t *)heap_caps_malloc(EXAMPLE_LCD_V_RES * EXAMPLE_LCD_H_RES * sizeof(lv_color_t), MALLOC_CAP_SPIRAM);
  buf_2 = (lv_color_t *)heap_caps_malloc(EXAMPLE_LCD_V_RES * EXAMPLE_LCD_H_RES * sizeof(lv_color_t), MALLOC_CAP_SPIRAM);
  lv_disp_draw_buf_init(&disp_buf, buf_1, buf_2 , EXAMPLE_LCD_V_RES * EXAMPLE_LCD_H_RES);
  lv_disp_drv_init(&disp_drv);
  disp_drv.draw_buf = &disp_buf;
  disp_drv.hor_res = EXAMPLE_LCD_H_RES;
  disp_drv.ver_res = EXAMPLE_LCD_V_RES;
  disp_drv.flush_cb = example_lvgl_flush_cb;
  disp_drv.rounder_cb = hud_round_redraw;
  disp_drv.user_data = panel_handle;
  #ifdef EXAMPLE_Rotate_90
  disp_drv.sw_rotate = 1;
  disp_drv.rotated = LV_DISP_ROT_90;
  #endif
  lv_disp_drv_register(&disp_drv);
  const esp_timer_create_args_t lvgl_tick_timer_args = 
  {
    .callback = &example_increase_lvgl_tick,
    .name = "lvgl_tick"
  };
  esp_timer_handle_t lvgl_tick_timer = NULL;
  ESP_ERROR_CHECK(esp_timer_create(&lvgl_tick_timer_args, &lvgl_tick_timer));
  ESP_ERROR_CHECK(esp_timer_start_periodic(lvgl_tick_timer, EXAMPLE_LVGL_TICK_PERIOD_MS * 1000));
  lvgl_mux = xSemaphoreCreateMutex();
  assert(lvgl_mux);
  xTaskCreatePinnedToCore(example_lvgl_port_task, "LVGL", EXAMPLE_LVGL_TASK_STACK_SIZE, NULL, EXAMPLE_LVGL_TASK_PRIORITY, NULL,1); 
  if (example_lvgl_lock(-1))
  {
    //lv_demo_music();
    /* HUD is created by the application. */      /* A widgets example */
    //lv_demo_music();        /* A modern, smartphone-like music player demo. */
    // lv_demo_stress();      /* A stress test for LVGL. */
    //lv_demo_benchmark();    /* A demo to measure the performance of LVGL or to compare different settings. */
    // Release the mutex
    example_lvgl_unlock();
  }
}

static void example_increase_lvgl_tick(void *arg)
{
  /* Tell LVGL how many milliseconds has elapsed */
  lv_tick_inc(EXAMPLE_LVGL_TICK_PERIOD_MS);
}
bool example_lvgl_lock(int timeout_ms)
{
  assert(lvgl_mux && "bsp_display_start must be called first");

  const TickType_t timeout_ticks = (timeout_ms == -1) ? portMAX_DELAY : pdMS_TO_TICKS(timeout_ms);
  return xSemaphoreTake(lvgl_mux, timeout_ticks) == pdTRUE;
}
void example_lvgl_unlock(void)
{
  assert(lvgl_mux && "bsp_display_start must be called first");
  xSemaphoreGive(lvgl_mux);
}
static void example_lvgl_port_task(void *arg)
{
  uint32_t task_delay_ms = EXAMPLE_LVGL_TASK_MAX_DELAY_MS;
  for(;;)
  {
    // Lock the mutex due to the LVGL APIs are not thread-safe
    if (example_lvgl_lock(-1))
    {
      task_delay_ms = lv_timer_handler();
      // Release the mutex
      example_lvgl_unlock();
    }
    if (task_delay_ms > EXAMPLE_LVGL_TASK_MAX_DELAY_MS)
    {
      task_delay_ms = EXAMPLE_LVGL_TASK_MAX_DELAY_MS;
    }
    else if (task_delay_ms < EXAMPLE_LVGL_TASK_MIN_DELAY_MS)
    {
      task_delay_ms = EXAMPLE_LVGL_TASK_MIN_DELAY_MS;
    }
    vTaskDelay(pdMS_TO_TICKS(task_delay_ms));
  }
}
static void example_lvgl_flush_cb(lv_disp_drv_t *drv, const lv_area_t *area, lv_color_t *color_map)
{
  esp_lcd_panel_handle_t panel_handle = (esp_lcd_panel_handle_t) drv->user_data;
  const int offsetx1 = area->x1;
  const int offsetx2 = area->x2;
  const int offsety1 = area->y1;
  const int offsety2 = area->y2;

  //copy a buffer's content to a specific area of the display
  esp_lcd_panel_draw_bitmap(panel_handle, offsetx1, offsety1, offsetx2+1, offsety2+1, color_map);
  lv_disp_flush_ready(drv);
}






