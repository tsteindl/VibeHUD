#include "user_config.h"
#include "lvgl_port.h"
#include "lcd_bl_pwm_bsp.h"
void setup()
{
  Serial.begin(115200);
  lvgl_port_init();
  lcd_bl_pwm_bsp_init(LCD_PWM_MODE_255);
}
void loop()
{
#ifdef  Backlight_Testing
  setUpduty(LCD_PWM_MODE_255);
  delay(2000);
  setUpduty(LCD_PWM_MODE_150);
  delay(2000);
  setUpduty(LCD_PWM_MODE_75);
  delay(2000);
  setUpduty(LCD_PWM_MODE_0);
  delay(2000);
#endif
}
