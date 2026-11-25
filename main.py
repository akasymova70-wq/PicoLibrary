"""
# main.py
# Application entry point and dependency-injection composition root for Lab 4 (Sequence B).
# Author: Aidana
"""

import time
from Log import *
import secrets

# ---------------------------------------------------------------------------
# Hardware Configuration (fill in your actual Raspberry Pi Pico 2 W GPIO pins)
# Leave unused LCD mode pins as None.
# ---------------------------------------------------------------------------
LCD_MODE = ""              # Set to "i2c" or "parallel"

# I2C LCD pins (required when LCD_MODE == "i2c")
LCD_SDA_PIN = None
LCD_SCL_PIN = None
LCD_I2C_ADDR = None        # Optional; leave None to auto-detect I2C backpack address

# Parallel LCD pins (required when LCD_MODE == "parallel")
LCD_RS_PIN = None
LCD_E_PIN = None
LCD_D4_PIN = None
LCD_D5_PIN = None
LCD_D6_PIN = None
LCD_D7_PIN = None

# Four mandatory physical buttons
BTN_NEXT_PIN = None
BTN_PREVIOUS_PIN = None
BTN_DETAILS_PIN = None
BTN_VIEW_PIN = None

# Mandatory LightStrip configuration
LIGHTSTRIP_PIN = None
LIGHTSTRIP_NUM_LEDS = None
LIGHTSTRIP_BRIGHTNESS = 0.3

# Mandatory PassiveBuzzer configuration
BUZZER_PIN = None

# Nonblocking LCD page rotation interval in milliseconds
LCD_PAGE_INTERVAL_MS = 2500


def validate_configuration():
    """
    Validate secrets and hardware pin settings before initializing peripherals.
    Returns a list of missing or invalid configuration items without logging secrets.
    """
    missing = []

    if not getattr(secrets, "WIFI_SSID", "").strip():
        missing.append("secrets.WIFI_SSID")

    for endpoint_name in ("VERSION_URL", "CUSTOMERS_URL", "CONTACTS_URL", "ACTIVITIES_URL"):
        if not getattr(secrets, endpoint_name, "").strip():
            missing.append(f"secrets.{endpoint_name}")

    mode = (LCD_MODE or "").strip().lower()
    if mode == "i2c":
        if LCD_SDA_PIN is None:
            missing.append("LCD_SDA_PIN")
        if LCD_SCL_PIN is None:
            missing.append("LCD_SCL_PIN")
    elif mode == "parallel":
        for name, val in (
            ("LCD_RS_PIN", LCD_RS_PIN),
            ("LCD_E_PIN", LCD_E_PIN),
            ("LCD_D4_PIN", LCD_D4_PIN),
            ("LCD_D5_PIN", LCD_D5_PIN),
            ("LCD_D6_PIN", LCD_D6_PIN),
            ("LCD_D7_PIN", LCD_D7_PIN),
        ):
            if val is None:
                missing.append(name)
    else:
        missing.append("LCD_MODE ('i2c' or 'parallel')")

    for name, val in (
        ("BTN_NEXT_PIN", BTN_NEXT_PIN),
        ("BTN_PREVIOUS_PIN", BTN_PREVIOUS_PIN),
        ("BTN_DETAILS_PIN", BTN_DETAILS_PIN),
        ("BTN_VIEW_PIN", BTN_VIEW_PIN),
        ("LIGHTSTRIP_PIN", LIGHTSTRIP_PIN),
        ("LIGHTSTRIP_NUM_LEDS", LIGHTSTRIP_NUM_LEDS),
        ("BUZZER_PIN", BUZZER_PIN),
    ):
        if val is None:
            missing.append(name)

    return missing


def _create_display():
    """Instantiate CRMDisplay using the validated LCD configuration."""
    from CRMDisplay import CRMDisplay

    mode = LCD_MODE.strip().lower()
    if mode == "i2c":
        return CRMDisplay(
            sda=LCD_SDA_PIN,
            scl=LCD_SCL_PIN,
            i2c_addr=LCD_I2C_ADDR,
            page_interval_ms=LCD_PAGE_INTERVAL_MS,
        )
    return CRMDisplay(
        rs=LCD_RS_PIN,
        e=LCD_E_PIN,
        d4=LCD_D4_PIN,
        d5=LCD_D5_PIN,
        d6=LCD_D6_PIN,
        d7=LCD_D7_PIN,
        page_interval_ms=LCD_PAGE_INTERVAL_MS,
    )


def main():
    """Wire all collaborators via dependency injection and run the Sequence B loop."""
    Log.level = INFO
    Log.name = "Lab4CRM"

    missing = validate_configuration()
    if missing:
        Log.e("Configuration incomplete. Please complete the following settings before running:")
        for item in missing:
            Log.e(f"  - {item}")
        return

    from Net import Net
    from Button import Button
    from LightStrip import LightStrip
    from Buzzer import PassiveBuzzer
    from Customer_API import Customer_API
    from CRM_Controller import CRM_Controller

    controller = None
    try:
        net = Net()
        api = Customer_API(
            net=net,
            base_url=secrets.API_BASE_URL,
            version_url=secrets.VERSION_URL,
            customers_url=secrets.CUSTOMERS_URL,
            contacts_url=secrets.CONTACTS_URL,
            activities_url=secrets.ACTIVITIES_URL,
        )
        display = _create_display()
        light_strip = LightStrip(
            pin=LIGHTSTRIP_PIN,
            name="CRMStatusStrip",
            numleds=LIGHTSTRIP_NUM_LEDS,
            brightness=LIGHTSTRIP_BRIGHTNESS,
        )
        buzzer = PassiveBuzzer(BUZZER_PIN, name="CRMFeedbackBuzzer")

        btn_next = Button(BTN_NEXT_PIN, "Next")
        btn_previous = Button(BTN_PREVIOUS_PIN, "Previous")
        btn_details = Button(BTN_DETAILS_PIN, "Details")
        btn_view = Button(BTN_VIEW_PIN, "View")
        buttons = [btn_next, btn_previous, btn_details, btn_view]

        controller = CRM_Controller(
            net=net,
            api=api,
            display=display,
            light_strip=light_strip,
            buzzer=buzzer,
            wifi_ssid=secrets.WIFI_SSID,
            wifi_password=secrets.WIFI_PASSWORD,
            buttons=buttons,
        )

        # Register controller as handler on all four PicoLibrary Button instances
        for btn in buttons:
            btn.setHandler(controller)

        controller.start()

        while True:
            controller.process_events()
            if hasattr(time, "sleep_ms"):
                time.sleep_ms(20)
            else:
                time.sleep(0.02)
    except KeyboardInterrupt:
        Log.i("Application stopped by user.")
    except Exception as err:
        Log.e(f"Fatal startup or hardware initialization error: {err}")
    finally:
        if controller is not None:
            controller.cleanup()


if __name__ == "__main__":
    main()