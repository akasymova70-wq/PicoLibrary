"""
# CRM_Controller.py
# Main handler and coordinator implementing Sequence B (on-demand customer detail loading)
# with deferred button event processing, nonblocking display paging, and LED/buzzer feedback.
# Author: Aidana
"""

import time
from Log import *
from Client import Client
from Contact import Contact
from Activity import Activity

# RGB tuples matching PicoLibrary Lights.py color constants
COLOR_OFF = (0, 0, 0)
COLOR_LOADING = (0, 0, 255)   # Blue
COLOR_SUCCESS = (0, 255, 0)   # Green
COLOR_ERROR = (255, 0, 0)     # Red

# Bounded buzzer feedback parameters:
# Loading uses a short 60 ms bounded beep before blocking network I/O so the buzzer
# never stays on during HTTP/Wi-Fi waits. Success and error run nonblockingly via
# update_feedback() in the main loop: list of (frequency_hz, duration_ms); 0 = silent gap.
LOADING_TONE_HZ = 600
LOADING_TONE_MS = 60
TONE_SUCCESS = [(880, 65), (0, 25), (1175, 80)]
TONE_ERROR = [(262, 110), (0, 40), (220, 140)]


def _ticks_ms():
    """Return a millisecond timestamp compatible with both MicroPython and CPython."""
    if hasattr(time, "ticks_ms"):
        return time.ticks_ms()
    return int(time.monotonic() * 1000)


def _ticks_diff(now_ms, past_ms):
    """Compute elapsed milliseconds safely across MicroPython tick wrap-around."""
    if hasattr(time, "ticks_diff"):
        return time.ticks_diff(now_ms, past_ms)
    return now_ms - past_ms


class CRM_Controller:
    """
    Coordinates Sequence B CRM operations on Raspberry Pi Pico 2 W.

    Acts as the PicoLibrary Button handler (<<handler>> stereotype), deferring all
    network, LCD, LightStrip, and PassiveBuzzer actions out of interrupt callbacks into
    process_events() executed by the main loop.

    Parameters:
    ----------
    net : Net
        Injected PicoLibrary Net instance for Wi-Fi operations.
    api : Customer_API
        Injected local REST wrapper for CRM requests.
    display : CRMDisplay
        Injected 16x2 LCD display subclass.
    light_strip : LightStrip
        Injected PicoLibrary LightStrip for loading/success/error visual feedback.
    buzzer : PassiveBuzzer
        Injected PicoLibrary PassiveBuzzer for loading/success/error audio feedback.
    wifi_ssid : str
        Wi-Fi SSID from secrets.py.
    wifi_password : str
        Wi-Fi password from secrets.py (never logged).
    buttons : list, optional
        List of the four injected PicoLibrary Button objects (default: None).

    Examples:
    ---------
    1. controller = CRM_Controller(net, api, display, strip, buzzer, ssid, password, buttons)
    2. controller.start()
    3. controller.process_events()
    """

    VIEW_CONTACTS = "Contacts"
    VIEW_ACTIVITIES = "Activities"

    def __init__(
        self,
        net,
        api,
        display,
        light_strip,
        buzzer,
        wifi_ssid,
        wifi_password,
        buttons=None,
    ):
        missing = []
        if net is None:
            missing.append("net")
        if api is None:
            missing.append("api")
        if display is None:
            missing.append("display")
        if light_strip is None:
            missing.append("light_strip")
        if buzzer is None:
            missing.append("buzzer")
        if missing:
            raise ValueError(
                "CRM_Controller missing required collaborators: " + ", ".join(missing)
            )

        self._net = net
        self._api = api
        self._display = display
        self._light_strip = light_strip
        self._buzzer = buzzer
        self._buttons = list(buttons) if buttons is not None else []
        self._wifi_ssid = (wifi_ssid or "").strip()
        self._wifi_password = "" if wifi_password is None else str(wifi_password)

        self._clients = []
        self._current_index = 0
        self._selected_client = None
        self._current_view = self.VIEW_CONTACTS

        # Deferred event flags set inside buttonPressed() IRQ and cleared in process_events()
        self._pending_next = False
        self._pending_previous = False
        self._pending_details = False
        self._pending_view = False

        # Nonblocking buzzer step queue
        self._tone_queue = []
        self._tone_deadline_ms = 0
        self._tone_active = False

    @property
    def clients(self):
        """Return a shallow copy of the loaded Client list."""
        return list(self._clients)

    @property
    def current_index(self):
        """Return the active customer index."""
        return self._current_index

    @property
    def selected_client(self):
        """Return the currently selected Client object, or None."""
        return self._selected_client

    @property
    def current_view(self):
        """Return the current detail view ('Contacts' or 'Activities')."""
        return self._current_view

    def _safe_display_status(self, line1, line2=""):
        """Update LCD status safely so display errors do not crash the main loop."""
        try:
            self._display.show_status(line1, line2)
        except Exception as err:
            Log.e(f"CRM_Controller: display status error: {err}")

    def _safe_display_error(self, message):
        """Update LCD error screen safely."""
        try:
            self._display.show_error(message)
        except Exception as err:
            Log.e(f"CRM_Controller: display error failed: {err}")

    def _safe_set_light(self, color, label):
        """Set LightStrip color safely and log the feedback state."""
        try:
            self._light_strip.setColor(color)
            Log.i(f"CRM_Controller: LightStrip -> {label}")
        except Exception as err:
            Log.e(f"CRM_Controller: LightStrip error ({label}): {err}")

    def _start_tone_pattern(self, pattern, label):
        """Start a short bounded nonblocking tone sequence on PassiveBuzzer."""
        self._tone_queue = list(pattern)
        self._tone_active = False
        self._tone_deadline_ms = 0
        Log.i(f"CRM_Controller: PassiveBuzzer -> {label} signal")
        self._advance_tone_step()

    def _advance_tone_step(self):
        """Play the next queued buzzer step or stop cleanly when complete."""
        if not self._tone_queue:
            try:
                self._buzzer.stop()
            except Exception as err:
                Log.e(f"CRM_Controller: PassiveBuzzer stop error: {err}")
            self._tone_active = False
            return

        freq, duration_ms = self._tone_queue.pop(0)
        try:
            if freq > 0:
                self._buzzer.play(freq)
            else:
                self._buzzer.stop()
            self._tone_active = True
            self._tone_deadline_ms = _ticks_ms() + int(duration_ms)
        except Exception as err:
            Log.e(f"CRM_Controller: PassiveBuzzer play error: {err}")
            self._tone_queue = []
            self._tone_active = False

    def update_feedback(self):
        """
        Advance or stop active nonblocking buzzer feedback steps.

        Parameters:
        ----------
        None

        Examples:
        ---------
        1. controller.update_feedback()
        """
        if not self._tone_active:
            return
        if _ticks_diff(_ticks_ms(), self._tone_deadline_ms) >= 0:
            self._advance_tone_step()

    def _show_loading_feedback(self, line1, line2=""):
        """Indicate loading state via LCD, LightStrip, and short bounded PassiveBuzzer signal."""
        self._tone_queue = []
        self._tone_active = False
        try:
            self._buzzer.stop()
        except Exception:
            pass
        self._safe_display_status(line1, line2)
        self._safe_set_light(COLOR_LOADING, "LOADING (Blue)")
        try:
            Log.i("CRM_Controller: PassiveBuzzer -> loading signal")
            self._buzzer.beep(LOADING_TONE_HZ, LOADING_TONE_MS)
        except Exception as err:
            Log.e(f"CRM_Controller: PassiveBuzzer loading signal error: {err}")

    def _show_success_feedback(self):
        """Indicate success state via LightStrip and short PassiveBuzzer signal."""
        self._safe_set_light(COLOR_SUCCESS, "SUCCESS (Green)")
        self._start_tone_pattern(TONE_SUCCESS, "success")

    def _show_error_feedback(self, message):
        """Indicate error state via LCD, LightStrip, and distinct PassiveBuzzer signal."""
        self._safe_display_error(message)
        self._safe_set_light(COLOR_ERROR, "ERROR (Red)")
        self._start_tone_pattern(TONE_ERROR, "error")

    def start(self):
        """
        Execute Sequence B startup: connect Wi-Fi, verify API version, load only the
        customer list, select and display the first customer, and await button input.

        Parameters:
        ----------
        None

        Examples:
        ---------
        1. controller.start()
        """
        Log.i("CRM_Controller: starting Lab 4 CRM application (Sequence B - on-demand details).")
        Log.i("CRM_Controller: startup loads customer list only; contacts and activities are deferred.")

        if not self.connect_wifi():
            Log.e("CRM_Controller: startup halted at Wi-Fi step; press Details to retry.")
            return

        version = self.check_version()
        if version is None:
            Log.w("CRM_Controller: version check did not succeed; attempting customer list load.")

        clients = self.get_clients()
        if not clients:
            Log.w("CRM_Controller: no customers available to display; press Details to retry.")
            return

        self._current_index = 0
        self._selected_client = self._clients[0]
        try:
            self._display.show_customer(self._selected_client)
        except Exception as err:
            Log.e(f"CRM_Controller: failed to show initial customer: {err}")

        Log.i(
            f"CRM_Controller: selected customer [1/{len(self._clients)}] -> "
            f"Name='{self._selected_client.name}', ID='{self._selected_client.customer_id}'"
        )
        Log.i(
            "CRM_Controller: startup complete (contacts and activities NOT requested). "
            "Waiting for Next, Previous, Details, or View button input."
        )
        self._show_success_feedback()

    def connect_wifi(self):
        """
        Connect to Wi-Fi through PicoLibrary Net and report local IP without logging secrets.

        Parameters:
        ----------
        None

        Examples:
        ---------
        1. connected = controller.connect_wifi()
        """
        if not self._wifi_ssid:
            Log.e("CRM_Controller: WIFI_SSID is blank in secrets.py.")
            self._show_error_feedback("Missing WiFi SSID")
            return False

        self._show_loading_feedback("Connecting WiFi", self._wifi_ssid[:16])
        Log.i(f"CRM_Controller: connecting to Wi-Fi SSID '{self._wifi_ssid}'...")

        try:
            password_arg = self._wifi_password if self._wifi_password != "" else None
            self._net.connect(self._wifi_ssid, password_arg)
            if not self._net.isConnected():
                raise RuntimeError("Wi-Fi interface is not connected after connect().")

            local_ip = self._net.getLocalIp()
            Log.i(f"CRM_Controller: Wi-Fi connected. Local IP: {local_ip}")
            self._safe_display_status("WiFi Connected", local_ip)
            self._show_success_feedback()
            return True
        except Exception as err:
            Log.e(f"CRM_Controller: Wi-Fi connection failed: {err}")
            self._show_error_feedback("WiFi Failed")
            return False

    def check_version(self):
        """
        Query the CRM API version through Customer_API -> Net.

        Parameters:
        ----------
        None

        Examples:
        ---------
        1. ver = controller.check_version()
        """
        self._show_loading_feedback("Checking API", "Version...")
        try:
            data = self._api.get_version()
            if isinstance(data, dict):
                version_val = (
                    data.get("version")
                    or data.get("api_version")
                    or data.get("status")
                    or str(data)
                )
            else:
                version_val = str(data)
            version_str = str(version_val).strip()
            Log.i(f"CRM_Controller: API version verified -> {version_str}")
            self._safe_display_status("API Version", version_str[:16])
            return version_str
        except Exception as err:
            Log.e(f"CRM_Controller: API version check failed: {err}")
            self._show_error_feedback("Version Error")
            return None

    def get_clients(self):
        """
        Retrieve only the customer list through Customer_API -> Net and convert records
        to Client objects. Does not request contacts or activities.

        Parameters:
        ----------
        None

        Examples:
        ---------
        1. clients = controller.get_clients()
        """
        self._show_loading_feedback("Loading", "Customers...")
        try:
            records = self._api.get_customers()
            loaded = []
            for record in records:
                try:
                    loaded.append(Client.from_dict(record))
                except Exception as parse_err:
                    Log.w(f"CRM_Controller: skipping malformed customer record: {parse_err}")

            self._clients = loaded
            if not self._clients:
                self._current_index = 0
                self._selected_client = None
                Log.w("CRM_Controller: customer list is empty (0 customers loaded).")
                self._show_error_feedback("No Customers")
                return []

            self._current_index = 0
            self._selected_client = self._clients[0]
            Log.i(
                f"CRM_Controller: loaded {len(self._clients)} customer(s) into memory "
                "(0 contact requests, 0 activity requests)."
            )
            return self.clients
        except Exception as err:
            Log.e(f"CRM_Controller: failed to load customers: {err}")
            self._show_error_feedback("Load Clients Err")
            return []

    def buttonPressed(self, name):
        """
        PicoLibrary Button interrupt callback. Only records the pending event flag.
        Performs no network, LCD, LightStrip, or buzzer work inside interrupt context.

        Parameters:
        ----------
        name : str
            Name of the pressed button ("Next", "Previous", "Details", or "View").

        Examples:
        ---------
        1. controller.buttonPressed("Details")
        """
        if name == "Next":
            self._pending_next = True
        elif name == "Previous":
            self._pending_previous = True
        elif name == "Details":
            self._pending_details = True
        elif name == "View":
            self._pending_view = True

    def buttonReleased(self, name):
        """
        PicoLibrary Button release callback (no-op in interrupt context).

        Parameters:
        ----------
        name : str
            Name of the released button.

        Examples:
        ---------
        1. controller.buttonReleased("Next")
        """
        return

    def process_events(self):
        """
        Safely clear pending button flags and dispatch actions outside interrupt context,
        then service nonblocking buzzer feedback and LCD paging.

        Parameters:
        ----------
        None

        Examples:
        ---------
        1. controller.process_events()
        """
        if self._pending_next:
            self._pending_next = False
            self.next_customer()

        if self._pending_previous:
            self._pending_previous = False
            self.previous_customer()

        if self._pending_details:
            self._pending_details = False
            if self._selected_client is None:
                Log.i("CRM_Controller: Details pressed with no loaded customers -> retrying startup.")
                self.start()
            else:
                self.get_client_details(self._selected_client.customer_id)

        if self._pending_view:
            self._pending_view = False
            self.toggle_view()

        self.update_feedback()
        try:
            self._display.update()
        except Exception as err:
            Log.e(f"CRM_Controller: display update error: {err}")

    def next_customer(self):
        """
        Select the next customer with wrap-around and update the LCD from memory only.
        Never issues contact or activity REST requests.

        Parameters:
        ----------
        None

        Examples:
        ---------
        1. controller.next_customer()
        """
        if not self._clients:
            Log.w("CRM_Controller: Next ignored - no customers loaded.")
            self._safe_display_status("No Customers", "Press Details")
            return

        self._current_index = (self._current_index + 1) % len(self._clients)
        self._selected_client = self._clients[self._current_index]
        Log.i(
            f"CRM_Controller: Next -> [{self._current_index + 1}/{len(self._clients)}] "
            f"Name='{self._selected_client.name}', ID='{self._selected_client.customer_id}' "
            "(no REST request)."
        )
        try:
            self._display.show_customer(self._selected_client)
        except Exception as err:
            Log.e(f"CRM_Controller: display error on Next: {err}")

    def previous_customer(self):
        """
        Select the previous customer with wrap-around and update the LCD from memory only.
        Never issues contact or activity REST requests.

        Parameters:
        ----------
        None

        Examples:
        ---------
        1. controller.previous_customer()
        """
        if not self._clients:
            Log.w("CRM_Controller: Previous ignored - no customers loaded.")
            self._safe_display_status("No Customers", "Press Details")
            return

        self._current_index = (self._current_index - 1) % len(self._clients)
        self._selected_client = self._clients[self._current_index]
        Log.i(
            f"CRM_Controller: Previous -> [{self._current_index + 1}/{len(self._clients)}] "
            f"Name='{self._selected_client.name}', ID='{self._selected_client.customer_id}' "
            "(no REST request)."
        )
        try:
            self._display.show_customer(self._selected_client)
        except Exception as err:
            Log.e(f"CRM_Controller: display error on Previous: {err}")

    def get_client_details(self, customer_id):
        """
        Load or reload contacts and activities on demand for the selected customer only.

        Parameters:
        ----------
        customer_id : str
            Identifier of the selected customer whose contacts and activities are requested.

        Examples:
        ---------
        1. controller.get_client_details(selected_client.customer_id)
        """
        if self._selected_client is None:
            Log.w("CRM_Controller: Details requested with no selected customer.")
            self._show_error_feedback("No Customer")
            return False

        clean_id = "" if customer_id is None else str(customer_id).strip()
        if not clean_id:
            Log.e("CRM_Controller: cannot load details because customer_id is empty.")
            self._show_error_feedback("Invalid Cust ID")
            return False

        Log.i(
            f"CRM_Controller: Details pressed for Name='{self._selected_client.name}', "
            f"ID='{clean_id}'."
        )

        if not self._net.isConnected():
            Log.w("CRM_Controller: Wi-Fi disconnected; attempting reconnect before loading details.")
            if not self.connect_wifi():
                return False

        self._show_loading_feedback("Loading Details", clean_id[:16])

        try:
            raw_contacts = self._api.get_contacts(clean_id)
            raw_activities = self._api.get_activities(clean_id)

            contacts = []
            for rec in raw_contacts:
                try:
                    contacts.append(Contact.from_dict(rec))
                except Exception as parse_err:
                    Log.w(f"CRM_Controller: skipping malformed contact record: {parse_err}")

            activities = []
            for rec in raw_activities:
                try:
                    activities.append(Activity.from_dict(rec))
                except Exception as parse_err:
                    Log.w(f"CRM_Controller: skipping malformed activity record: {parse_err}")

            self._selected_client.set_contacts(contacts)
            self._selected_client.set_activities(activities)

            Log.i(
                f"CRM_Controller: stored {len(contacts)} contact(s) and "
                f"{len(activities)} activity(ies) on Client ID='{clean_id}'."
            )
            if contacts:
                for idx, contact in enumerate(contacts, 1):
                    Log.i(f"  Contact {idx}: {contact.format_summary()}")
            else:
                Log.i("  Contacts: none returned for this customer.")

            if activities:
                for idx, activity in enumerate(activities, 1):
                    Log.i(f"  Activity {idx}: {activity.format_summary()}")
            else:
                Log.i("  Activities: none returned for this customer.")

            self._display.show_details(
                self._selected_client,
                self._selected_client.contacts,
                self._selected_client.activities,
                self._current_view,
            )
            self._show_success_feedback()
            return True
        except Exception as err:
            Log.e(f"CRM_Controller: failed to load details for ID='{clean_id}': {err}")
            self._show_error_feedback("Details Error")
            return False

    def toggle_view(self):
        """
        Switch between Contacts and Activities using data already stored in memory.
        Never makes a REST request. Prompts the user to press Details if unloaded.

        Parameters:
        ----------
        None

        Examples:
        ---------
        1. controller.toggle_view()
        """
        if self._selected_client is None:
            Log.w("CRM_Controller: View ignored - no customers loaded.")
            self._safe_display_status("No Customers", "Press Details")
            return

        if not self._selected_client.details_loaded:
            Log.i(
                f"CRM_Controller: View pressed before details loaded for "
                f"ID='{self._selected_client.customer_id}'; prompting user to press Details "
                "(no REST request)."
            )
            self._safe_display_status("No Details Yet", "Press Details")
            return

        self._current_view = (
            self.VIEW_ACTIVITIES
            if self._current_view == self.VIEW_CONTACTS
            else self.VIEW_CONTACTS
        )
        Log.i(
            f"CRM_Controller: View switched to '{self._current_view}' for "
            f"ID='{self._selected_client.customer_id}' (memory only, no REST request)."
        )

        try:
            self._display.show_details(
                self._selected_client,
                self._selected_client.contacts,
                self._selected_client.activities,
                self._current_view,
            )
        except Exception as err:
            Log.e(f"CRM_Controller: display error on View toggle: {err}")

    def cleanup(self):
        """
        Safely detach button handlers and silence LightStrip and PassiveBuzzer on exit.

        Parameters:
        ----------
        None

        Examples:
        ---------
        1. controller.cleanup()
        """
        for btn in self._buttons:
            try:
                btn.setHandler(None)
            except Exception:
                pass
        try:
            self._buzzer.stop()
        except Exception:
            pass
        try:
            self._light_strip.setColor(COLOR_OFF)
        except Exception:
            pass
        Log.i("CRM_Controller: hardware cleanup complete.")


if __name__ == "__main__":
    from Customer_API import Customer_API

    class _MockNet:
        def __init__(self):
            self.connected = False
            self.status_code = 200
            self.requests = []

        def connect(self, ssid, password=None):
            self.connected = True

        def isConnected(self):
            return self.connected

        def getLocalIp(self):
            return "local-test-ip"

        def getJson(self, url):
            self.requests.append(url)
            if url == "ep_version":
                return {"version": "2.1"}
            if url == "ep_customers":
                return [
                    {"customer_id": "C-10", "name": "Alpha Inc"},
                    {"customer_id": "C-20", "name": "Beta LLC"},
                ]
            if url == "ep_contacts/C-20":
                return [{"contact_id": "CT-2", "name": "Dana", "title": "CTO"}]
            if url == "ep_activities/C-20":
                return [{"activity_id": "AC-2", "type": "Demo", "activity_name": "Setup"}]
            return None

    class _MockDisplay:
        def __init__(self):
            self.events = []

        def show_customer(self, client):
            self.events.append(("customer", client.customer_id))

        def show_details(self, client, contacts, activities, view):
            self.events.append(("details", client.customer_id, view, len(contacts), len(activities)))

        def show_status(self, line1, line2=""):
            self.events.append(("status", line1, line2))

        def show_error(self, message):
            self.events.append(("error", message))

        def update(self):
            return False

    class _MockLightStrip:
        def __init__(self):
            self.colors = []

        def setColor(self, color):
            self.colors.append(color)

    class _MockBuzzer:
        def __init__(self):
            self.tones = []

        def beep(self, tone=500, duration=150):
            self.tones.append(("beep", tone, duration))

        def play(self, tone=500):
            self.tones.append(("play", tone))

        def stop(self):
            self.tones.append(("stop", 0))

    mock_net = _MockNet()
    mock_api = Customer_API(
        mock_net,
        version_url="ep_version",
        customers_url="ep_customers",
        contacts_url="ep_contacts",
        activities_url="ep_activities",
    )
    mock_display = _MockDisplay()
    mock_strip = _MockLightStrip()
    mock_buzzer = _MockBuzzer()

    ctrl = CRM_Controller(
        net=mock_net,
        api=mock_api,
        display=mock_display,
        light_strip=mock_strip,
        buzzer=mock_buzzer,
        wifi_ssid="mock_net",
        wifi_password="",
    )
    ctrl.start()
    assert mock_net.requests == ["ep_version", "ep_customers"]

    ctrl.buttonPressed("Next")
    ctrl.process_events()
    assert ctrl.selected_client.customer_id == "C-20"
    assert len(mock_net.requests) == 2

    ctrl.buttonPressed("View")
    ctrl.process_events()
    assert mock_display.events[-1] == ("status", "No Details Yet", "Press Details")
    assert len(mock_net.requests) == 2

    ctrl.buttonPressed("Details")
    ctrl.process_events()
    assert mock_net.requests == ["ep_version", "ep_customers", "ep_contacts/C-20", "ep_activities/C-20"]
    assert ctrl.selected_client.details_loaded is True

    ctrl.buttonPressed("View")
    ctrl.process_events()
    assert len(mock_net.requests) == 4

    ctrl.cleanup()
    Log.i("Testing complete - CRM_Controller checks passed")